import json
import math
import sqlite3
import pandas as pd
from scipy.spatial import distance

from config import AnalysisConfig
from settings_store import AI_DEFAULTS, load_all_settings


def get_db_connection(db_path):
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def get_detections(
    conn,
    game_id,
    relational_game_id=None,
    *,
    video_game_id=None,
    base_analysis_key=None,
    video_relational_game_id=None,
):
    """Load detections using the same key resolution as the video library counts.

    A run's own detections (game_id == analysis key) win: reruns share the
    relational_game_id and base key with the primary run, so the wider lookup would
    mix several runs' detections. The wider lookup is only a fallback for legacy
    rows stored under another key.
    """
    game_ids = [gid for gid in {game_id, video_game_id, base_analysis_key} if gid]
    rel_ids = [rid for rid in {relational_game_id, video_relational_game_id} if rid is not None]
    if game_id and conn.execute(
        "SELECT 1 FROM detections WHERE game_id = ? LIMIT 1", (game_id,)
    ).fetchone():
        game_ids, rel_ids = [game_id], []

    conditions = []
    params = []
    for rel_id in rel_ids:
        conditions.append("relational_game_id = ?")
        params.append(rel_id)
    for gid in game_ids:
        conditions.append("game_id = ?")
        params.append(gid)

    if not conditions:
        print(f"INFO: No detection lookup keys provided for game_id: {game_id}")
        return _empty_detections_frame(conn)

    query = f"SELECT * FROM detections WHERE {' OR '.join(conditions)}"
    print(
        "INFO: Reading detections for keys "
        f"game_ids={game_ids}, relational_ids={rel_ids}"
    )
    df = pd.read_sql_query(query, conn, params=params)
    print(f"INFO: Found {len(df)} detections in the database.")

    # Normalize column names and values for downstream processing
    if 'object_class' in df.columns:
        # Map detector labels to canonical names used by the pipeline
        df['class_name'] = df['object_class'].replace({
            'sports ball': 'ball',
            'sports_ball': 'ball'
        }).fillna(df['object_class'])
    else:
        # Backwards-compatibility: if older column exists
        df['class_name'] = df.get('class_name', '')

    # Ensure tracker_id column exists in DataFrame even if DB doesn't have it yet
    if 'tracker_id' not in df.columns:
        df['tracker_id'] = pd.NA

    return df


def _empty_detections_frame(conn):
    """Return an empty detections frame with expected columns."""
    try:
        rows = conn.execute("SELECT * FROM detections LIMIT 0").fetchall()
        if rows:
            return pd.DataFrame(columns=rows[0].keys())
    except Exception:
        pass
    return pd.DataFrame()


def find_ball_possession(detections_df, possession_threshold=None):
    """
    Analyzes detections to determine ball possession for each frame.
    Adds 'has_ball' and 'ball_distance' columns to the player detections.

    possession_threshold: max distance (pixels) for ball possession.
        If None, auto-calculated from video resolution (10% of frame diagonal).
    """
    print("INFO: Analyzing ball possession.")
    detections_df = detections_df.sort_values('frame_number').reset_index(drop=True)

    detections_df['has_ball'] = False
    detections_df['ball_distance'] = float('inf')

    # Auto-calculate threshold from video resolution if not provided
    if possession_threshold is None:
        # Cap coordinates to reasonable frame bounds (YOLO boxes can overflow)
        x_max = min(detections_df['x_center'].quantile(0.99), 3840)  # cap at 4K width
        y_max = min(detections_df['y_center'].quantile(0.99), 2160)  # cap at 4K height
        diagonal = math.sqrt(x_max**2 + y_max**2)
        possession_threshold = diagonal * 0.10  # 10% of frame diagonal
        print(f"INFO: Auto possession threshold: {possession_threshold:.0f}px (diagonal={diagonal:.0f}px, x_max={x_max:.0f}, y_max={y_max:.0f})")

    # Vectorized possession detection — much faster than groupby loop
    # Build per-frame ball positions (use first ball detection per frame)
    ball_df = detections_df[detections_df['class_name'] == 'ball'][['frame_number', 'x_center', 'y_center']].copy()
    ball_df = ball_df.rename(columns={'x_center': 'ball_x', 'y_center': 'ball_y'})
    ball_df = ball_df.groupby('frame_number').first()  # one ball pos per frame

    player_mask = detections_df['class_name'] == 'person'
    if ball_df.empty or player_mask.sum() == 0:
        print("INFO: No ball or player detections — skipping possession analysis.")
        return detections_df

    # Get player rows with original index preserved
    player_df = detections_df.loc[player_mask, ['frame_number', 'x_center', 'y_center']]

    # Merge ball positions onto player detections by frame
    merged = player_df.merge(ball_df, left_on='frame_number', right_index=True, how='left')

    # Calculate distances vectorized (NaN ball pos = inf distance)
    import numpy as np
    dx = merged['x_center'].values - merged['ball_x'].values
    dy = merged['y_center'].values - merged['ball_y'].values
    dists = np.sqrt(dx**2 + dy**2)
    dists = np.where(np.isnan(dists), np.inf, dists)

    # Set ball_distance for all player detections using original indices
    detections_df.loc[merged.index, 'ball_distance'] = dists

    # Find closest player per frame (only frames with valid ball data)
    merged['_dist'] = dists
    valid = merged[merged['_dist'] < np.inf].copy()
    if not valid.empty:
        closest_per_frame = valid.loc[valid.groupby('frame_number')['_dist'].idxmin()]
        closest_per_frame = closest_per_frame[closest_per_frame['_dist'] <= possession_threshold]
        detections_df.loc[closest_per_frame.index, 'has_ball'] = True

    possession_events = detections_df[detections_df['has_ball'] == True]
    print(f"INFO: Identified {len(possession_events)} instances of player possession.")

    return detections_df


def make_event(game_id, event_type, timestamp_ms, player=None, shot_result=None, confidence=0.45, details=None):
    return {
        "game_id": game_id,
        "player": None if player is None else str(player),
        "event_type": event_type,
        "shot_result": shot_result,
        "timestamp_ms": int(timestamp_ms),
        "confidence": float(confidence),
        "details_json": json.dumps(details or {}),
    }


def append_unique_event(events, seen_keys, event):
    key = (event["event_type"], event["timestamp_ms"], event.get("player"), event.get("shot_result"))
    if key in seen_keys:
        return
    seen_keys.add(key)
    events.append(event)


# A second ball box on the same frame is often a false ball with slightly higher
# confidence. The box at the locked hoop is the one a shot can be corrected from.
_RIM_MAX_DIST = 280.0
_RIM_CONF_FLOOR = 0.35


def _hoop_on_court(hoop) -> bool:
    if not hoop:
        return False
    x = float(hoop.get("x") or 0)
    y = float(hoop.get("y") or 0)
    return 80.0 <= x <= 1840.0 and 40.0 <= y <= 450.0


def _ball_at_hoop(x, y, confidence, hoop) -> bool:
    """True when this box is above the locked rim and within the attempt gate."""
    if not _hoop_on_court(hoop):
        return False
    if confidence is not None and float(confidence) < _RIM_CONF_FLOOR:
        return False
    hx = float(hoop["x"])
    hy = float(hoop["y"])
    if float(y) >= hy:
        return False
    dx = float(x) - hx
    dy = float(y) - hy
    return (dx * dx + dy * dy) ** 0.5 <= _RIM_MAX_DIST


def _load_hoop_samples(game_id):
    try:
        from net_detector import load_hoop_track

        return load_hoop_track(game_id) or []
    except Exception:
        return []


def build_ball_track(detections_df, hoop_samples=None):
    ball_df = detections_df[detections_df["class_name"] == "ball"].copy()
    if ball_df.empty:
        return ball_df
    ball_df = ball_df.sort_values(["frame_number", "confidence"], ascending=[True, False])
    if not hoop_samples:
        return ball_df.groupby("frame_number", as_index=False).first()

    from net_detector import hoop_at

    chosen = []
    has_conf = "confidence" in ball_df.columns
    for _frame, grp in ball_df.groupby("frame_number", sort=False):
        hoop = hoop_at(hoop_samples, int(grp.iloc[0]["timestamp_ms"]))
        at_rim = []
        for idx, row in grp.iterrows():
            conf = row["confidence"] if has_conf else 1.0
            if _ball_at_hoop(row["x_center"], row["y_center"], conf, hoop):
                dx = float(row["x_center"]) - float(hoop["x"])
                dy = float(row["y_center"]) - float(hoop["y"])
                at_rim.append(((dx * dx + dy * dy), idx))
        if at_rim:
            at_rim.sort()
            chosen.append(grp.loc[at_rim[0][1]])
        else:
            chosen.append(grp.iloc[0])
    return pd.DataFrame(chosen).reset_index(drop=True)


def _numpy_kmeans_fit(coords, n_clusters, max_iter=20, seed=42):
    """Lightweight KMeans for spatial clustering when scikit-learn is unavailable."""
    import numpy as np

    coords = np.asarray(coords, dtype=float)
    n_samples = coords.shape[0]
    n_clusters = min(int(n_clusters), n_samples)
    if n_clusters <= 0:
        return np.empty((0, coords.shape[1]), dtype=float)

    rng = np.random.default_rng(seed)
    center_idx = rng.choice(n_samples, size=n_clusters, replace=False)
    centers = coords[center_idx].copy()
    labels = np.zeros(n_samples, dtype=int)

    for _ in range(max_iter):
        dists = ((coords[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new_labels = dists.argmin(axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for cluster_id in range(n_clusters):
            mask = labels == cluster_id
            if mask.any():
                centers[cluster_id] = coords[mask].mean(axis=0)
            else:
                centers[cluster_id] = coords[rng.integers(0, n_samples)]
    return centers


def _numpy_kmeans_predict(coords, centers):
    import numpy as np

    coords = np.asarray(coords, dtype=float)
    if centers.size == 0 or len(coords) == 0:
        return np.full(len(coords), -1, dtype=int)
    dists = ((coords[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    return dists.argmin(axis=1)


def _fit_spatial_clusters(sample_coords, n_clusters):
    """Fit KMeans on sample coordinates, preferring scikit-learn with numpy fallback."""
    import numpy as np

    coords = np.asarray(sample_coords, dtype=float)
    n_clusters = min(int(n_clusters), len(coords))
    if n_clusters <= 0:
        return np.empty((0, coords.shape[1]), dtype=float), "none"

    try:
        from sklearn.cluster import KMeans

        model = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        model.fit(coords)
        return model.cluster_centers_, "sklearn"
    except ImportError:
        print("INFO: scikit-learn not installed; using built-in numpy clustering fallback.")
        return _numpy_kmeans_fit(coords, n_clusters), "numpy"


def _predict_spatial_clusters(coords, centers, backend="sklearn"):
    return _numpy_kmeans_predict(coords, centers)


def _cluster_players_spatially(detections_df, n_clusters=10, conn=None, game_id=None):
    """
    Cluster person detections into stable player slots by spatial position.

    YOLO tracker_ids are unstable (median 2-frame lifespan), so we can't use
    them to identify players across frames. Instead, we cluster all person
    detections by (x_center, y_center) into n_clusters groups, then assign
    each detection to its nearest cluster center.

    If conn and game_id are provided, writes cluster assignments back to the
    detections table so enhanced analysis can use them.

    Returns: DataFrame with added 'cluster_id' column.
    """
    import numpy as np

    persons = detections_df[detections_df['class_name'] == 'person'].copy()
    if persons.empty:
        detections_df['cluster_id'] = -1
        return detections_df

    # Sample detections for clustering
    sample = persons[['x_center', 'y_center']].dropna()
    if len(sample) > 50000:
        sample = sample.sample(50000, random_state=42)

    centers, backend = _fit_spatial_clusters(sample.values, n_clusters)
    if backend != "none":
        print(f"INFO: Player clustering backend: {backend}")

    # Assign ALL person detections to nearest cluster
    person_mask = detections_df['class_name'] == 'person'
    person_coords = detections_df.loc[person_mask, ['x_center', 'y_center']].values
    valid_coords = ~np.isnan(person_coords).any(axis=1)
    clusters = np.full(len(person_coords), -1)
    if valid_coords.any():
        clusters[valid_coords] = _predict_spatial_clusters(
            person_coords[valid_coords], centers, backend=backend
        )
    detections_df.loc[person_mask, 'cluster_id'] = clusters

    # Write cluster assignments to DB for enhanced analysis
    if conn is not None and game_id is not None:
        person_df = detections_df[person_mask & (detections_df['cluster_id'] >= 0)]
        if 'id' in person_df.columns and not person_df.empty:
            # Batch update using executemany
            update_data = [
                (int(row['cluster_id']), int(row['id']))
                for _, row in person_df.iterrows()
            ]
            conn.executemany(
                "UPDATE detections SET player_cluster = ? WHERE id = ?",
                update_data
            )
            conn.commit()
            print(f"INFO: Wrote cluster assignments for {len(update_data)} detections to DB")

    detections_df['cluster_id'] = detections_df['cluster_id'].fillna(-1).astype(int)
    return detections_df


def build_possession_segments(detections_with_possession_df, max_ball_distance=None, max_gap_frames=30, min_segment_frames=3):
    """
    Build possession segments from detections with ball possession data.

    Uses spatial clustering (cluster_id) instead of tracker_id for player identity,
    since YOLO tracker_ids are unstable at imgsz=320.

    Args:
        max_ball_distance: max distance for ball possession (auto-calculated if None)
        max_gap_frames: max gap between frames in a single possession segment
        min_segment_frames: minimum frames for a valid segment (default 3, ~0.8s at stride=10)
    """
    players = detections_with_possession_df[detections_with_possession_df["class_name"] == "person"].copy()
    if players.empty:
        return []

    # Use cluster_id as owner_key (stable spatial identity)
    # Fall back to spatial grid if cluster_id not available
    if "cluster_id" in players.columns and (players["cluster_id"] >= 0).any():
        players["owner_key"] = players["cluster_id"].astype(str)
    else:
        # Fallback: spatial grid bucketing (60x60 pixel cells)
        players["owner_key"] = (
            (players["x_center"] // 60).astype(int).astype(str) + "_" +
            (players["y_center"] // 60).astype(int).astype(str)
        )

    # Filter to players who have the ball
    has_ball = players[players["has_ball"] == True].copy()
    if has_ball.empty:
        # Fallback: use closest player to ball on each frame
        players = players[players["ball_distance"].notna() & (players["ball_distance"] < float("inf"))].copy()
        if players.empty:
            return []
        frame_best = (
            players.sort_values(["frame_number", "ball_distance"])
            .groupby("frame_number", as_index=False)
            .first()
        )
    else:
        frame_best = has_ball

    frame_best = frame_best.sort_values("frame_number")
    if frame_best.empty:
        return []

    segments = []
    current_rows = []
    for _, row in frame_best.iterrows():
        if not current_rows:
            current_rows = [row]
            continue
        last_row = current_rows[-1]
        same_owner = str(row["owner_key"]) == str(last_row["owner_key"])
        frame_gap = int(row["frame_number"]) - int(last_row["frame_number"])
        if same_owner and frame_gap <= max_gap_frames:
            current_rows.append(row)
        else:
            if len(current_rows) >= min_segment_frames:
                segment_df = pd.DataFrame(current_rows)
                segments.append(
                    {
                        "player": str(segment_df.iloc[0]["owner_key"]),
                        "start_frame": int(segment_df["frame_number"].min()),
                        "end_frame": int(segment_df["frame_number"].max()),
                        "start_timestamp_ms": int(segment_df.iloc[0]["timestamp_ms"]),
                        "end_timestamp_ms": int(segment_df.iloc[-1]["timestamp_ms"]),
                        "duration_frames": int(len(segment_df)),
                        "frames": [int(v) for v in segment_df["frame_number"].tolist()],
                        "player_x_start": int(segment_df.iloc[0]["x_center"]),
                        "player_x_end": int(segment_df.iloc[-1]["x_center"]),
                        "player_y_median": float(segment_df["y_center"].median()),
                        "mean_ball_distance": float(segment_df["ball_distance"].mean()) if "ball_distance" in segment_df.columns else 0.0,
                    }
                )
            current_rows = [row]
    if len(current_rows) >= min_segment_frames:
        segment_df = pd.DataFrame(current_rows)
        segments.append(
            {
                "player": str(segment_df.iloc[0]["owner_key"]),
                "start_frame": int(segment_df["frame_number"].min()),
                "end_frame": int(segment_df["frame_number"].max()),
                "start_timestamp_ms": int(segment_df.iloc[0]["timestamp_ms"]),
                "end_timestamp_ms": int(segment_df.iloc[-1]["timestamp_ms"]),
                "duration_frames": int(len(segment_df)),
                "frames": [int(v) for v in segment_df["frame_number"].tolist()],
                "player_x_start": int(segment_df.iloc[0]["x_center"]),
                "player_x_end": int(segment_df.iloc[-1]["x_center"]),
                "player_y_median": float(segment_df["y_center"].median()),
                "mean_ball_distance": float(segment_df["ball_distance"].mean()) if "ball_distance" in segment_df.columns else 0.0,
            }
        )
    return segments


def _shot_peak_index(search_window, hoop_samples):
    """Highest ball that is at the hoop. A higher box away from the hoop is not the shot."""
    if (
        hoop_samples
        and not search_window.empty
        and "timestamp_ms" in search_window.columns
    ):
        from net_detector import hoop_at

        has_conf = "confidence" in search_window.columns
        rim_idx = []
        for idx, row in search_window.iterrows():
            conf = row["confidence"] if has_conf else None
            hoop = hoop_at(hoop_samples, int(row["timestamp_ms"]))
            if _ball_at_hoop(row["x_center"], row["y_center"], conf, hoop):
                rim_idx.append(idx)
        if rim_idx:
            return search_window.loc[rim_idx, "y_center"].idxmin()
    return search_window["y_center"].idxmin()


def detect_shot_from_segment(segment, ball_track, min_ball_rise=10, next_segment_start=None,
                              secondary_pass=False, ball_y_threshold=400, hoop_samples=None):
    """
    Detect if a shot was taken at the end of a possession segment.

    A real shot has a characteristic arc:
    1. Ball starts near the player (at segment end)
    2. Ball rises to a peak (minimum y_center in image coords = highest point)
    3. Ball falls back down

    We look for this pattern in a window around the segment end.
    The window is constrained to not overlap with the next segment.

    min_ball_rise: minimum pixel rise from player height to ball peak.
        Default 15px (~1-2 feet in a 1080p court view).

    secondary_pass: if True, use relaxed criteria for sparse ball detections.
        Uses a wider window and checks if ball y_center drops below ball_y_threshold
        (ball near top of frame = near basket) instead of requiring a clear arc.
    ball_y_threshold: y_center threshold for secondary pass (default 400px).
        A ball above this y-coordinate (lower y value = higher in frame) is
        considered to be near the basket area.
    """
    if ball_track.empty:
        return None

    if secondary_pass:
        # Secondary pass: wide window looking for ball near basket (low y_center)
        window_start = segment["start_frame"]
        window_end = segment["end_frame"] + 30
        if next_segment_start is not None:
            window_end = min(window_end, next_segment_start - 1)

        search_window = ball_track[
            (ball_track["frame_number"] >= window_start)
            & (ball_track["frame_number"] <= window_end)
        ].copy()
        if len(search_window) < 1:
            return None

        # Find the ball's highest point (minimum y_center) in the wide window
        peak_idx = _shot_peak_index(search_window, hoop_samples)
        peak_row = search_window.loc[peak_idx]
        peak_y = float(peak_row["y_center"])
        peak_x = float(peak_row["x_center"])

        # Ball must be near the top of the frame (near basket area)
        if peak_y > ball_y_threshold:
            return None

        # Ball must rise above the player's head (relaxed threshold)
        ball_rise = float(segment["player_y_median"]) - peak_y
        if ball_rise < min_ball_rise:
            return None

        # Relaxed lateral travel check
        lateral_travel = abs(peak_x - float(segment["player_x_end"]))
        if lateral_travel < 3:
            return None

        return {
            "timestamp_ms": int(peak_row["timestamp_ms"]),
            "peak_frame": int(peak_row["frame_number"]),
            "ball_rise": ball_rise,
            "lateral_travel": lateral_travel,
            "peak_x": peak_x,
            "peak_y": peak_y,
            "secondary_pass": True,
        }

    # Primary pass: standard arc detection
    # Search window: look for ball arc starting from segment start through
    # segment end + buffer. Wider window to handle sparse ball detections.
    window_start = segment["start_frame"]
    window_end = segment["end_frame"] + 40
    if next_segment_start is not None:
        window_end = min(window_end, next_segment_start - 1)

    search_window = ball_track[
        (ball_track["frame_number"] >= window_start) &
        (ball_track["frame_number"] <= window_end)
    ].copy()
    if len(search_window) < 2:
        return None

    # Find the ball's highest point (minimum y_center) in the window
    peak_idx = _shot_peak_index(search_window, hoop_samples)
    peak_row = search_window.loc[peak_idx]
    peak_y = float(peak_row["y_center"])
    peak_x = float(peak_row["x_center"])

    # Ball must rise above the player's head (player_y_median is torso height)
    # Use a lower threshold since ball detections are sparse
    ball_rise = float(segment["player_y_median"]) - peak_y
    if ball_rise < min_ball_rise:
        return None

    # Ball must travel laterally (relaxed for sparse detections)
    lateral_travel = abs(peak_x - float(segment["player_x_end"]))
    if lateral_travel < 3:
        return None

    # Relaxed arc shape check: ball should not continue rising significantly after peak
    after_peak = search_window[search_window["frame_number"] > peak_row["frame_number"]]
    if len(after_peak) >= 2:
        min_y_after = after_peak["y_center"].min()
        # If ball continues rising after "peak", it's not a real arc
        if min_y_after < peak_y - 10:
            return None
        # Real shots come down. Interpolated passes often peak and stay high.
        if float(after_peak["y_center"].max()) < peak_y + 8:
            return None

    return {
        "timestamp_ms": int(peak_row["timestamp_ms"]),
        "peak_frame": int(peak_row["frame_number"]),
        "ball_rise": ball_rise,
        "lateral_travel": lateral_travel,
        "peak_x": peak_x,
        "peak_y": peak_y,
    }


# -- Precision mode -----------------------------------------------------------
# Opt-in generator (ai.event_generator_mode = "precision"). Same possession segments and
# ball track as "expanded", but tuned for the Review queue: it emits far fewer, better-
# supported events. Measured against Scott's manual Wilder Q1 tags with
# scripts/score_manual_q1_regression.py ΓÇö see docs/ANALYSIS_QUALITY_BASELINE_2026-09-10.md.
# "expanded" is untouched; nothing changes for production until the mode is switched.
PRECISION_DEFAULTS = {
    # a segment must last this many frames before it counts as a real possession
    # (12 / 80 below: measured on Scott's manual Wilder Q1 tags -> precision 0.087,
    #  recall 0.623, AI-only 346; the expanded generator scores 0.014 / 0.660 / 2415)
    "min_hold_frames": 12,
    # primary-pass shot detection only (no low-threshold secondary pass); px of ball rise
    "shot_min_ball_rise": 80.0,
    # Live FG must rise more than a pass/interpolation blip. Lane FTs keep the 80px floor.
    # Set from Liberty vs Adrian Q1: extras were the main miss vs Scott's 44 shots.
    "live_shot_min_ball_rise": 170.0,
    # at most one shot per possessor within this window
    "shot_refractory_ms": 6000,
    # two cluster-ids on the same release
    "shot_global_refractory_ms": 4000,
    # blocks: deflection near the shooter as the ball goes up; makes are FGs
    "emit_blocks": True,
    # assist only if the passer held the ball and the catch-to-shot was 1–2 dribbles
    "assist_max_gap_frames": 15,
    "assist_max_scorer_hold_ms": 1600,
    # turnover/steal: the lost possession must have been brief and the new possessor must
    # actually keep the ball
    "turnover_min_next_hold_frames": 6,
    "turnover_max_prev_hold_frames": 60,
    # foul-after-dead-ball heuristic is weak; keep it opt-in
    "emit_fouls": False,
    # "make" needs a longer dead-ball gap than expanded mode's 15 frames (inbound after a
    # score). Do not treat "ball went high" as a make — that was 80 Q2 makes vs Scott's 9.
    "make_min_gap_frames": 120,
    # a pass is not a turnover; only emit TO when the ball was lost abruptly
    "turnover_require_abrupt": True,
}


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _merge_short_segments(segments, min_hold_frames):
    """Drop segments shorter than min_hold_frames and merge neighbours with the same player.

    Tracker fragmentation produces many 1ΓÇô5 frame "possessions" that flip between cluster
    ids; each flip became a possession_change (and often a shot/rebound/block cascade)."""
    kept = [dict(seg) for seg in segments if seg.get("duration_frames", 1) >= min_hold_frames]
    merged = []
    for seg in kept:
        if merged and merged[-1]["player"] == seg["player"]:
            last = merged[-1]
            last["end_frame"] = max(last["end_frame"], seg["end_frame"])
            last["end_timestamp_ms"] = max(last.get("end_timestamp_ms", 0), seg.get("end_timestamp_ms", 0))
            last["duration_frames"] = last["end_frame"] - last["start_frame"] + 1
            n1, n2 = last.get("_n", 1), seg.get("_n", 1)
            last["mean_ball_distance"] = (
                last.get("mean_ball_distance", 0) * n1 + seg.get("mean_ball_distance", 0) * n2
            ) / (n1 + n2)
            last["_n"] = n1 + n2
            continue
        seg["_n"] = 1
        merged.append(seg)
    return merged


def _rows_at_frame(by_frame, frame_number):
    if not by_frame or frame_number is None:
        return []
    rows = by_frame.get(int(frame_number))
    if rows is None:
        return []
    return rows.to_dict("records")


def _ball_deflected_away(ball_track, peak_frame, window=6):
    if ball_track is None or getattr(ball_track, "empty", True) or not peak_frame:
        return False
    peak = ball_track[ball_track["frame_number"] == peak_frame]
    if peak.empty:
        return False
    peak_y = float(peak.iloc[0]["y_center"])
    peak_x = float(peak.iloc[0]["x_center"])
    post = ball_track[
        (ball_track["frame_number"] > peak_frame)
        & (ball_track["frame_number"] <= peak_frame + window)
    ]
    if post.empty:
        return False
    dy = float(post["y_center"].max()) - peak_y
    dx = abs(float(post["x_center"].median()) - peak_x)
    return dy > 12 or dx > 25


def generate_precision_events_from_segments(
    game_id, segments, ball_track, params=None, detections_df=None, frame_reader=None,
):
    from court_memory import FrameCourtMemory, ball_from_detections, people_from_detections
    from court_memory import ball_through_rim
    from stat_rules import (
        classify_rebound,
        classify_shot_kind,
        classify_turnover_kind,
        credit_assist,
        credit_block,
        credit_steal,
        scoring_event_type,
    )

    p = {**PRECISION_DEFAULTS, **(params or {})}
    events = []
    seen_keys = set()
    try:
        from net_detector import hoop_at, load_hoop_track

        hoop_samples = load_hoop_track(game_id)
    except Exception:
        hoop_samples = []

        def hoop_at(*_a, **_k):
            return None

    segments = _merge_short_segments(segments, p["min_hold_frames"])
    by_frame = {}
    if detections_df is not None and not getattr(detections_df, "empty", True):
        for frame, grp in detections_df.groupby("frame_number"):
            by_frame[int(frame)] = grp

    memory = FrameCourtMemory()
    offense_ids: list[str] = []

    # Shots: primary detector only, higher rise threshold, one per possessor per window.
    shot_segments = {}
    for index, segment in enumerate(segments):
        next_start = segments[index + 1]["start_frame"] if index + 1 < len(segments) else None
        shot_info = detect_shot_from_segment(
            segment, ball_track, min_ball_rise=p["shot_min_ball_rise"], next_segment_start=next_start,
            hoop_samples=hoop_samples,
        )
        if not shot_info:
            continue
        shot_segments[index] = shot_info
    # Per-player refractory is applied in the loop below, after the live-rise,
    # rim and global-gap filters, so a candidate those filters drop (a pump
    # fake) cannot block the same player's real shot a few seconds later.
    last_shot_ms_by_player = {}

    def _observe(frame_number):
        recs = _rows_at_frame(by_frame, frame_number)
        memory.observe(people_from_detections(recs), ball_from_detections(recs))
        return recs

    last_kept_shot_ms = None
    for index, segment in enumerate(segments):
        hold = segment.get("duration_frames", 1)
        _observe(segment["start_frame"])
        if segment["player"] not in offense_ids:
            offense_ids.append(str(segment["player"]))

        if index > 0:
            previous = segments[index - 1]
            if previous["player"] != segment["player"]:
                prev_hold = previous.get("duration_frames", 1)
                gap_frames = segment["start_frame"] - previous["end_frame"]
                append_unique_event(events, seen_keys, make_event(
                    game_id, "possession_change", segment["start_timestamp_ms"],
                    player=segment["player"],
                    confidence=_clamp(0.4 + 0.01 * min(hold, prev_hold), 0.4, 0.85),
                    details={"from_player": previous["player"], "to_player": segment["player"],
                             "gap_frames": gap_frames, "hold_frames": hold},
                ))
                after_shot = (index - 1) in shot_segments
                is_abrupt = (
                    prev_hold <= p["turnover_max_prev_hold_frames"]
                    and gap_frames < 20
                    and previous.get("mean_ball_distance", 0) > 25
                    and hold >= p["turnover_min_next_hold_frames"]
                    and not after_shot
                )
                to_kind = classify_turnover_kind(dead_ball=memory.dead_ball, after_shot=after_shot)
                if to_kind and (is_abrupt or not p.get("turnover_require_abrupt")):
                    conf = _clamp(0.35 + 0.01 * hold, 0.35, 0.7)
                    append_unique_event(events, seen_keys, make_event(
                        game_id, "turnover", segment["start_timestamp_ms"], player=previous["player"],
                        confidence=conf,
                        details={"next_possessor": segment["player"], "turnover_kind": to_kind}))
                    if credit_steal(
                        after_shot=after_shot,
                        dead_ball=memory.dead_ball,
                        next_ball_distance=segment.get("mean_ball_distance"),
                        prev_lost_abruptly=is_abrupt,
                    ):
                        append_unique_event(events, seen_keys, make_event(
                            game_id, "steal", segment["start_timestamp_ms"], player=segment["player"],
                            confidence=conf, details={"from_player": previous["player"], "live": True}))
                    if to_kind == "dead":
                        offense_ids = [str(segment["player"])]
                    else:
                        offense_ids = [str(segment["player"])]

        if index not in shot_segments:
            continue

        shot_info = shot_segments[index]
        next_segment = segments[index + 1] if index + 1 < len(segments) else None
        next_gap = None if next_segment is None else next_segment["start_frame"] - segment["end_frame"]
        peak_frame = shot_info.get("peak_frame")
        from court_memory import detect_ft_formation as _ft
        from court_memory import people_from_detections as _people, _on_court_people
        peak = int(peak_frame or segment["end_frame"])
        start_fr = int(segment["start_frame"])
        pre = max(peak - 24, start_fr)
        earlier = max(pre - 18, start_fr)
        crowd_at_start = len(_on_court_people(_people(_rows_at_frame(by_frame, start_fr)))) >= 4
        ft_formation = None
        for fr in sorted({start_fr, earlier, pre, peak}):
            recs_f = _observe(fr)
            form = memory.last_formation
            if form == "technical" and crowd_at_start:
                form = None
            if form == "lane":
                ft_formation = "lane"
                break
            # Technical is implemented, but zoom-in 1–2 person frames false-trigger it.
            # Do not classify those shots as FT until the crowd/zoom prior is stronger.
        recs = _rows_at_frame(by_frame, peak)
        people = _people(recs)
        ball = ball_from_detections(recs)

        shooter_x = segment.get("player_x_end") or segment.get("player_x_start")
        shooter_y = segment.get("player_y_median")
        in_paint = memory.in_paint(shooter_x, shooter_y)
        dist = None
        if memory.key is not None and shooter_x is not None and shooter_y is not None:
            cx = (memory.key.x0 + memory.key.x1) / 2.0
            cy = (memory.key.y0 + memory.key.y1) / 2.0
            width = max(abs(memory.key.x1 - memory.key.x0), 1.0)
            height = max(abs(memory.key.y1 - memory.key.y0), 1.0)
            dist = ((float(shooter_x) - cx) ** 2 / width ** 2 + (float(shooter_y) - cy) ** 2 / height ** 2) ** 0.5
        shot_kind = classify_shot_kind(ft_formation=ft_formation, in_paint=in_paint, dist_from_basket=dist)
        live_min = float(p.get("live_shot_min_ball_rise") or 0)
        ts = int(shot_info.get("timestamp_ms") or 0)
        peak_x = shot_info.get("peak_x")
        peak_y = shot_info.get("peak_y")
        hoop_hit = hoop_at(hoop_samples, ts) if hoop_samples else None
        if hoop_hit:
            memory.detected_hoop = (float(hoop_hit["x"]), float(hoop_hit["y"]))
            memory.detected_rim_r = float(hoop_hit.get("r") or 0) or None
        hoop = memory.hoop_xy()
        if ft_formation != "lane":
            if live_min and float(shot_info.get("ball_rise") or 0) < live_min:
                continue
        # Lane FTs used to skip this, so a false lane at the far end became extra FTs.
        close = True
        if hoop is not None:
            close = memory.close_to_rim(peak_x, peak_y)
            if not close and peak_frame:
                post_peak = ball_track[
                    (ball_track["frame_number"] > peak_frame)
                    & (ball_track["frame_number"] <= peak_frame + 20)
                ]
                if not post_peak.empty:
                    close = any(
                        memory.close_to_rim(float(r.x_center), float(r.y_center))
                        for r in post_peak.itertuples(index=False)
                    )
            if not close:
                continue
        gap_ms = int(p.get("shot_global_refractory_ms") or 0)
        if last_kept_shot_ms is not None and gap_ms and ts - last_kept_shot_ms < gap_ms:
            continue
        last_player_ms = last_shot_ms_by_player.get(segment["player"])
        if last_player_ms is not None and ts - last_player_ms < p["shot_refractory_ms"]:
            continue
        last_kept_shot_ms = ts
        last_shot_ms_by_player[segment["player"]] = ts

        # Make = through the rim, or the net moves when the ball box vanishes there.
        # A high arc and a dead-ball gap are not a make.
        through = ball_through_rim(ball_track, peak_frame, memory.hoop_xy())
        net_moved = False
        # Only a locked rim. A guessed hoop is not the nylon on this camera.
        if not through and hoop_hit is not None:
            from net_detector import net_moved_after_shot

            net_moved = net_moved_after_shot(
                frame_reader,
                peak_frame,
                (float(hoop_hit["x"]), float(hoop_hit["y"])),
                memory.detected_rim_r,
            )
        shot_result = "make" if (through or net_moved) else "miss"
        made = shot_result == "make"

        shot_conf = _clamp(0.35 + shot_info["ball_rise"] / 200.0, 0.35, 0.9)
        shot_details = {
            "ball_rise": round(shot_info["ball_rise"], 1),
            "lateral_travel": round(shot_info["lateral_travel"], 1),
            "peak_frame": peak_frame,
            "peak_x": None if peak_x is None else round(float(peak_x), 1),
            "peak_y": None if peak_y is None else round(float(peak_y), 1),
            "generator": "precision",
            "shot_kind": shot_kind,
            "in_paint": in_paint,
            "ft_formation": ft_formation,
            "through_rim": through,
            "net_moved": net_moved,
        }
        append_unique_event(events, seen_keys, make_event(
            game_id, "shot", shot_info["timestamp_ms"], player=segment["player"], shot_result=shot_result,
            confidence=shot_conf, details=shot_details,
        ))
        scoring_type = scoring_event_type(shot_kind, made)
        append_unique_event(events, seen_keys, make_event(
            game_id, scoring_type, shot_info["timestamp_ms"], player=segment["player"],
            shot_result=shot_result,
            confidence=round(shot_conf * 0.9, 3),
            details={"derived_from": "shot", "shot_kind": shot_kind, "in_paint": in_paint}))

        if shot_result == "miss" and next_segment is not None:
            reb_kind = classify_rebound(
                shooter_team=None, rebounder_team=None,
                shooter_id=segment["player"], rebounder_id=next_segment["player"],
                offense_ids=offense_ids,
            )
            reb_type = "rebound_offensive" if reb_kind == "oreb" else "rebound_defensive" if reb_kind == "dreb" else "rebound"
            append_unique_event(events, seen_keys, make_event(
                game_id, reb_type, next_segment["start_timestamp_ms"], player=next_segment["player"],
                confidence=_clamp(0.6 - 0.01 * max(next_gap or 0, 0), 0.3, 0.6),
                details={"shot_player": segment["player"], "gap_frames": next_gap, "rebound_kind": reb_kind}))
            deflected = _ball_deflected_away(ball_track, peak_frame)
            near = (next_segment.get("mean_ball_distance") or 99) <= 45
            if p["emit_blocks"] and credit_block(
                shot_went_in=False,
                defender_is_shooter=str(next_segment["player"]) == str(segment["player"]),
                gap_frames=next_gap,
                ball_deflected_away=deflected,
                defender_near_ball=near,
            ):
                append_unique_event(events, seen_keys, make_event(
                    game_id, "block", next_segment["start_timestamp_ms"], player=next_segment["player"],
                    confidence=0.45, details={"shot_player": segment["player"], "gap_frames": next_gap}))
            if reb_kind == "dreb":
                offense_ids = [str(next_segment["player"])]
            elif str(next_segment["player"]) not in offense_ids:
                offense_ids.append(str(next_segment["player"]))

        if made and index > 0:
            previous = segments[index - 1]
            assist_gap = segment["start_frame"] - previous["end_frame"]
            scorer_hold_ms = int(segment.get("end_timestamp_ms", 0) or 0) - int(segment.get("start_timestamp_ms", 0) or 0)
            if credit_assist(
                shot_made=True,
                shot_kind=shot_kind,
                passer_id=previous["player"],
                scorer_id=segment["player"],
                pass_gap_frames=assist_gap,
                scorer_hold_ms=scorer_hold_ms,
                max_scorer_hold_ms=p["assist_max_scorer_hold_ms"],
                max_pass_gap_frames=p["assist_max_gap_frames"],
            ):
                append_unique_event(events, seen_keys, make_event(
                    game_id, "assist", shot_info["timestamp_ms"], player=previous["player"],
                    confidence=_clamp(0.5 - 0.01 * assist_gap, 0.3, 0.5),
                    details={"scorer": segment["player"], "gap_frames": assist_gap, "scorer_hold_ms": scorer_hold_ms}))

        if p["emit_fouls"] and (next_segment is None or (next_gap is not None and next_gap >= 90)):
            append_unique_event(events, seen_keys, make_event(
                game_id, "foul", shot_info["timestamp_ms"], player=segment["player"], confidence=0.18,
                details={"reason": "long_dead_ball_after_shot", "gap_frames": next_gap}))
        if made:
            offense_ids = []

    return events

def generate_expanded_events_from_segments(game_id, segments, ball_track):
    events = []
    seen_keys = set()
    shot_segments = {}

    for index, segment in enumerate(segments):
        next_start = segments[index + 1]["start_frame"] if index + 1 < len(segments) else None
        shot_info = detect_shot_from_segment(segment, ball_track, next_segment_start=next_start)
        if shot_info:
            shot_segments[index] = shot_info

    # Secondary pass: look for shots missed by the primary detector.
    # The primary detector requires a clear arc pattern, but with sparse ball
    # detections the arc is often incomplete. This pass uses a wider window
    # and checks if the ball y_center drops below ball_y_threshold (near the
    # top of the frame = near the basket) with a lower min_ball_rise.
    SECONDARY_BALL_Y_THRESHOLD = 550
    SECONDARY_MIN_BALL_RISE = 10
    for index, segment in enumerate(segments):
        if index in shot_segments:
            continue  # already detected by primary pass
        next_start = segments[index + 1]["start_frame"] if index + 1 < len(segments) else None
        shot_info = detect_shot_from_segment(
            segment, ball_track,
            min_ball_rise=SECONDARY_MIN_BALL_RISE,
            next_segment_start=next_start,
            secondary_pass=True,
            ball_y_threshold=SECONDARY_BALL_Y_THRESHOLD,
        )
        if shot_info:
            shot_segments[index] = shot_info

    rebound_segment_indices = set()
    for index, segment in enumerate(segments):
        if index > 0:
            previous = segments[index - 1]
            if previous["player"] != segment["player"]:
                # Only generate possession change events for segments with meaningful duration
                # Skip noise segments (less than 0.5 seconds = ~12 frames at stride=10)
                prev_duration = previous.get("duration_frames", 1)
                curr_duration = segment.get("duration_frames", 1)
                gap_frames = segment["start_frame"] - previous["end_frame"]

                # Always record possession change
                append_unique_event(
                    events,
                    seen_keys,
                    make_event(
                        game_id,
                        "possession_change",
                        segment["start_timestamp_ms"],
                        player=segment["player"],
                        confidence=0.6,
                        details={
                            "from_player": previous["player"],
                            "to_player": segment["player"],
                            "gap_frames": gap_frames,
                        },
                    ),
                )

                # Only generate turnover+steal for ABRUPT possession changes:
                # - Previous segment was very short (< 5 frames)
                # - AND gap is small (< 20 frames)
                # - AND previous segment was NOT a shot
                # - AND ball was far from the previous player (suggesting deflection)
                is_abrupt = (
                    prev_duration <= 5
                    and gap_frames < 20
                    and previous.get("mean_ball_distance", 0) > 25
                )
                if is_abrupt and (index - 1) not in shot_segments:
                    append_unique_event(
                        events,
                        seen_keys,
                        make_event(
                            game_id,
                            "turnover",
                            segment["start_timestamp_ms"],
                            player=previous["player"],
                            confidence=0.42,
                            details={"next_possessor": segment["player"]},
                        ),
                    )
                    append_unique_event(
                        events,
                        seen_keys,
                        make_event(
                            game_id,
                            "steal",
                            segment["start_timestamp_ms"],
                            player=segment["player"],
                            confidence=0.4,
                            details={"from_player": previous["player"]},
                        ),
                    )

        if index not in shot_segments:
            continue

        shot_info = shot_segments[index]
        next_segment = segments[index + 1] if index + 1 < len(segments) else None
        next_gap = None if next_segment is None else next_segment["start_frame"] - segment["end_frame"]

        # Determine make/miss using gap-based heuristic.
        # At stride=10, possession segments are closely spaced. A gap of > 15 frames
        # (~4 seconds at effective fps) after a shot suggests the other team is
        # inbounding (make). A quick follow-up suggests a rebound (miss).
        # Also check if the ball continues toward the basket after the peak.
        shot_result = "miss"
        if shot_info.get("peak_frame"):
            peak_frame = shot_info["peak_frame"]
            # Check ball trajectory after peak
            post_peak_ball = ball_track[
                (ball_track["frame_number"] > peak_frame) &
                (ball_track["frame_number"] <= peak_frame + 30)
            ]
            ball_moving_to_basket = False
            if not post_peak_ball.empty:
                min_y = post_peak_ball["y_center"].min()
                # Ball reaching top 1/3 of frame (y < 240 on 720p) = near basket
                if min_y < 240:
                    ball_moving_to_basket = True

            # Gap to next possession segment
            if next_segment is None:
                # No follow-up = ball went in
                shot_result = "make"
            elif next_gap is not None and next_gap > 15:
                # Longer gap = other team inbounding after make
                shot_result = "make"
            elif ball_moving_to_basket:
                # Ball reached basket area
                shot_result = "make"
        else:
            if next_segment is None or (next_gap is not None and next_gap > 15):
                shot_result = "make"

        if shot_result == "miss":
            rebound_segment_indices.add(index + 1)

        append_unique_event(
            events,
            seen_keys,
            make_event(
                game_id,
                "shot",
                shot_info["timestamp_ms"],
                player=segment["player"],
                shot_result=shot_result,
                confidence=0.52,
                details={
                    "ball_rise": round(shot_info["ball_rise"], 1),
                    "lateral_travel": round(shot_info["lateral_travel"], 1),
                    "peak_frame": shot_info["peak_frame"],
                },
            ),
        )
        append_unique_event(
            events,
            seen_keys,
            make_event(
                game_id,
                shot_result,
                shot_info["timestamp_ms"],
                player=segment["player"],
                confidence=0.45 if shot_result == "miss" else 0.4,
                details={"derived_from": "shot"},
            ),
        )

        if shot_result == "miss" and next_segment is not None:
            append_unique_event(
                events,
                seen_keys,
                make_event(
                    game_id,
                    "rebound",
                    next_segment["start_timestamp_ms"],
                    player=next_segment["player"],
                    confidence=0.5,
                    details={"shot_player": segment["player"], "gap_frames": next_gap},
                ),
            )
            if next_segment["player"] != segment["player"] and next_gap <= 12:
                append_unique_event(
                    events,
                    seen_keys,
                    make_event(
                        game_id,
                        "block",
                        next_segment["start_timestamp_ms"],
                        player=next_segment["player"],
                        confidence=0.32,
                        details={"shot_player": segment["player"], "gap_frames": next_gap},
                    ),
                )

        if shot_result == "make" and index > 0:
            previous = segments[index - 1]
            assist_gap = segment["start_frame"] - previous["end_frame"]
            if previous["player"] != segment["player"] and assist_gap <= 40:
                append_unique_event(
                    events,
                    seen_keys,
                    make_event(
                        game_id,
                        "assist",
                        shot_info["timestamp_ms"],
                        player=previous["player"],
                        confidence=0.28,
                        details={"scorer": segment["player"], "gap_frames": assist_gap},
                    ),
                )

        if next_segment is None or (next_gap is not None and next_gap >= 90):
            append_unique_event(
                events,
                seen_keys,
                make_event(
                    game_id,
                    "foul",
                    shot_info["timestamp_ms"],
                    player=segment["player"],
                    confidence=0.18,
                    details={"reason": "long_dead_ball_after_shot", "gap_frames": next_gap},
                ),
            )

    return events


def _lookup_event_type_id(conn, event_type):
    if not event_type:
        return None
    row = conn.execute(
        "SELECT id FROM event_types WHERE lower(code) = lower(?)",
        (event_type,),
    ).fetchone()
    return row["id"] if row else None


def _reapply_film_tool_teach(conn, game_id):
    """Re-grade new AI drafts against saved Film Tool tags. No-op on slim test DBs."""
    try:
        from manual_tag_teach import apply_saved_manual_teach

        apply_saved_manual_teach(conn, game_id, commit=True, pending_only=True)
    except sqlite3.OperationalError:
        return
    except Exception as exc:
        print(f"WARN: Film Tool teach reapply skipped: {exc}")


def _apply_event_calibrator(game_id, events):
    """Stamp-over calibrator is off. Shot type comes from FT/court rules."""
    return events


def _clip_referenced_event_ids_sql(conn):
    """SQL fragment listing event ids that saved clips point at (tables may be absent)."""
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('clips', 'player_development_clips')"
        ).fetchall()
    }
    parts = [f"SELECT event_id FROM {t} WHERE event_id IS NOT NULL" for t in sorted(tables)]
    return " UNION ".join(parts)


def _events_columns(conn):
    return {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}


def _delete_machine_events(conn, game_id, relational_game_id=None):
    """Delete this analysis key's machine output so a rebuild can regenerate it.

    Machine output: pending AI drafts, rows auto-accepted by
    review_actions.auto_accept_high_confidence_events, and AI rows graded by the
    Film Tool teach pass (re-derived from the saved manual tags after the rebuild).
    Anything a person decided (manual tags, coach accept/correct/reject) is kept,
    as are rows a saved clip points at. Only rows of this analysis key are touched,
    so a rerun never wipes the primary run's events on a shared relational game.
    Slim/legacy tables without the review columns fall back to human_verified=0.
    """
    from review_actions import AUTO_ACCEPT_NOTE

    teach_note = "Film Tool teach"  # manual_tag_teach.TEACH_NOTE (that module needs Flask helpers)
    cols = _events_columns(conn)
    where = ["game_id = ?"]
    params = [game_id]
    if relational_game_id is not None and "relational_game_id" in cols:
        where.append("(relational_game_id IS NULL OR relational_game_id = ?)")
        params.append(relational_game_id)
    if "source_type" in cols:
        where.append("COALESCE(source_type, 'ai') = 'ai'")
    if "reviewed_by_user_id" in cols:
        where.append("reviewed_by_user_id IS NULL")
    if {"review_status", "review_notes"} <= cols:
        blank_machine = ""
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "human_corrections" in tables:
            # Corrected/rejected with no note and no correction row is machine
            # output (Adrian had 526 of these). A coach decision writes
            # human_corrections even when review_notes is empty.
            blank_machine = """
                OR (review_status IN ('corrected', 'rejected')
                    AND COALESCE(review_notes, '') = ''
                    AND id NOT IN (
                        SELECT event_id FROM human_corrections
                         WHERE event_id IS NOT NULL
                    ))"""
        where.append(
            f"""((review_status = 'pending' AND human_verified = 0)
                OR (review_status = 'accepted' AND review_notes = ?)
                OR (review_status IN ('corrected', 'rejected') AND review_notes LIKE ?)
                {blank_machine})"""
        )
        params += [AUTO_ACCEPT_NOTE, teach_note + "%"]
    else:
        where.append("human_verified = 0")
    clip_ids = _clip_referenced_event_ids_sql(conn)
    if clip_ids and "id" in cols:
        where.append(f"id NOT IN ({clip_ids})")
    conn.execute(f"DELETE FROM events WHERE {' AND '.join(where)}", params)


def _kept_ai_event_signatures(conn, game_id):
    """Per kept AI row, its (event_type, timestamp_ms) as generated and as it is now.

    A regenerated draft with one of these signatures is the same play a person
    already decided on, so it is not inserted again. Corrections keep the generated
    values in human_corrections (first original event_type / timestamp).
    """
    cols = _events_columns(conn)
    if "id" not in cols:
        return []
    source_filter = " AND COALESCE(source_type, 'ai') = 'ai'" if "source_type" in cols else ""
    rows = conn.execute(
        f"SELECT id, event_type, timestamp_ms FROM events WHERE game_id = ?{source_filter}",
        (game_id,),
    ).fetchall()
    kept = []
    for event_id, event_type, timestamp_ms in (tuple(r) for r in rows):
        current = (event_type, int(timestamp_ms))
        origin_type, origin_ts = current
        try:
            corrections = [
                tuple(r) for r in conn.execute(
                    """SELECT field_changed, original_value, timestamp_ms FROM human_corrections
                        WHERE event_id = ? ORDER BY id""",
                    (event_id,),
                ).fetchall()
            ]
        except sqlite3.OperationalError:
            corrections = []
        if corrections and corrections[0][2] is not None:
            origin_ts = int(corrections[0][2])
        for field_changed, original_value, _ts in corrections:
            if field_changed == "event_type" and original_value:
                origin_type = original_value
                break
        kept.append({current, (origin_type, origin_ts)})
    return kept


def persist_events(conn, game_id, events, relational_game_id=None):
    """Replace this analysis key's machine events; keep every person-made decision.

    Rebuilding is idempotent: pending drafts and auto-accepted rows are regenerated,
    while manual tags and coach accept/correct/reject survive and do not get a
    duplicate draft. relational_game_id is stamped on new rows and can only narrow
    the delete, never widen it (reruns share it with the primary run).
    """
    _delete_machine_events(conn, game_id, relational_game_id)
    if not events:
        conn.commit()
        _reapply_film_tool_teach(conn, game_id)
        return

    events = _apply_event_calibrator(game_id, events)
    if not events:
        conn.commit()
        _reapply_film_tool_teach(conn, game_id)
        return

    kept = _kept_ai_event_signatures(conn, game_id)
    cur = conn.cursor()
    for ev in events:
        sig = (ev["event_type"], int(ev["timestamp_ms"]))
        match = next((i for i, sigs in enumerate(kept) if sig in sigs), None)
        if match is not None:
            kept.pop(match)  # one kept row stands in for one regenerated draft
            continue
        event_type_id = _lookup_event_type_id(conn, ev["event_type"])
        cur.execute(
            """
            INSERT INTO events
               (game_id, relational_game_id, player, event_type, event_type_id, shot_result, timestamp_ms, details_json, confidence, source_type)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ai')
            """,
            (
                ev["game_id"],
                relational_game_id,
                ev.get("player"),
                ev["event_type"],
                event_type_id,
                ev.get("shot_result"),
                ev["timestamp_ms"],
                ev.get("details_json"),
                ev.get("confidence"),
            ),
        )
    conn.commit()

    from review_actions import auto_accept_high_confidence_events

    # Grade Film Tool tags while drafts are still pending. Auto-accept after
    # that only promotes shots the tags did not already count.
    _reapply_film_tool_teach(conn, game_id)
    # Scoped to this analysis key: a relational lookup would also promote the
    # primary run's drafts when a rerun is generated.
    auto_accept_high_confidence_events(conn, game_id)


def main(
    game_id,
    db_path,
    relational_game_id=None,
    *,
    video_game_id=None,
    base_analysis_key=None,
    video_relational_game_id=None,
    force_expanded=False,
    mode_override=None,
    precision_params=None,
):
    """
    Analyzes raw detection data to identify and store basketball events.
    """
    print(f"INFO: Starting event generation for game_id: {game_id}")

    conn = None
    try:
        conn = get_db_connection(db_path)
        runtime_settings = load_all_settings(
            feature_defaults={},
            analysis_defaults={},
            ai_defaults=AI_DEFAULTS,
            db=conn,
        )
        ai_settings = runtime_settings["ai"]
        detections_df = get_detections(
            conn,
            game_id,
            relational_game_id=relational_game_id,
            video_game_id=video_game_id,
            base_analysis_key=base_analysis_key,
            video_relational_game_id=video_relational_game_id,
        )

        if detections_df.empty:
            print("INFO: No detections found for this game. Exiting.")
            return False

        # Step 1: Interpolate ball positions between anchor frames
        # This is critical because ball detection only runs on anchor frames
        # and we need ball positions on every frame with person detections
        ball_count_before = len(detections_df[detections_df['class_name'] == 'ball'])
        detections_df = _interpolate_ball(detections_df)
        ball_count_after = len(detections_df[detections_df['class_name'] == 'ball'])
        print(f"INFO: Ball detections: {ball_count_before} -> {ball_count_after} (after interpolation)")

        # Step 2: Cluster players spatially (tracker_ids are unstable at imgsz=320)
        # This must happen BEFORE possession analysis so we have stable player identities
        # Also writes cluster assignments to DB for enhanced analysis
        print("INFO: Clustering players spatially...")
        detections_df = _cluster_players_spatially(detections_df, n_clusters=10, conn=conn, game_id=game_id)
        n_clusters_found = detections_df.loc[detections_df['class_name'] == 'person', 'cluster_id'].nunique()
        print(f"INFO: Found {n_clusters_found} player clusters")

        # Step 3: Determine who has the ball in each frame
        detections_with_possession_df = find_ball_possession(detections_df)

        generator_mode = ai_settings.get("event_generator_mode", "legacy")
        if force_expanded and generator_mode != "precision":
            generator_mode = "expanded"
            print("INFO: Forcing expanded event generator for rebuild.")
        if mode_override:
            generator_mode = mode_override
            print(f"INFO: Event generator mode overridden to {generator_mode!r}.")
        events_to_persist = []

        if generator_mode == "precision":
            segments = build_possession_segments(detections_with_possession_df)
            ball_track = build_ball_track(detections_df, hoop_samples=_load_hoop_samples(game_id))
            print(f"INFO: Built {len(segments)} possession segments for precision generation.")
            frame_reader = _open_frame_reader(conn, game_id)
            try:
                events_to_persist = generate_precision_events_from_segments(
                    game_id, segments, ball_track, params=precision_params,
                    detections_df=detections_df, frame_reader=frame_reader,
                )
            finally:
                if frame_reader is not None:
                    frame_reader.close()
            print(f"INFO: Precision generator produced {len(events_to_persist)} events.")
            persist_events(conn, game_id, events_to_persist, relational_game_id=relational_game_id)
        elif generator_mode == "expanded":
            segments = build_possession_segments(detections_with_possession_df)
            ball_track = build_ball_track(detections_df, hoop_samples=_load_hoop_samples(game_id))
            print(f"INFO: Built {len(segments)} possession segments for expanded generation.")
            events_to_persist = generate_expanded_events_from_segments(game_id, segments, ball_track)
            print(f"INFO: Expanded generator produced {len(events_to_persist)} events.")
            persist_events(conn, game_id, events_to_persist, relational_game_id=relational_game_id)
        else:
            print("WARN: Legacy event generator mode produces no events; skipping persist.")
            persist_events(conn, game_id, [], relational_game_id=relational_game_id)

        print("INFO: Successfully completed event generation pipeline.")

        return True

    except (sqlite3.Error, ValueError) as e:
        print(f"ERROR: An error occurred in event_generator: {e}")
        return False
    finally:
        if conn:
            conn.close()
            print("INFO: Database connection closed.")


class _VideoFrameReader:
    """Seek one analysis frame. Used only to watch the net after a shot."""

    def __init__(self, path: str):
        self.path = path
        self.cap = None

    def __call__(self, frame_number: int):
        import cv2

        if self.cap is None:
            self.cap = cv2.VideoCapture(self.path, cv2.CAP_FFMPEG)
        if self.cap is None or not self.cap.isOpened():
            return None
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_number))
        ok, frame = self.cap.read()
        return frame if ok else None

    def close(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None


def _open_frame_reader(conn, game_id):
    import os

    try:
        row = conn.execute(
            "SELECT video_path FROM analysis_runs WHERE analysis_key = ? ORDER BY id DESC LIMIT 1",
            (game_id,),
        ).fetchone()
    except Exception:
        return None
    path = row["video_path"] if row is not None else None
    if not path or not os.path.isfile(path):
        return None
    return _VideoFrameReader(path)


def _interpolate_ball(detections_df):
    """
    Interpolate ball positions between anchor frames using vectorized numpy.
    """
    ball_df = detections_df[detections_df['class_name'] == 'ball'].sort_values('frame_number')
    person_df = detections_df[detections_df['class_name'] == 'person'].sort_values('frame_number')

    if len(ball_df) < 2 or person_df.empty:
        return detections_df

    # Build sorted anchor arrays
    import numpy as np
    anchor_frames = ball_df['frame_number'].values.astype(float)
    anchor_x = ball_df['x_center'].values.astype(float)
    anchor_y = ball_df['y_center'].values.astype(float)

    # Person frames that need interpolation (not already ball frames)
    ball_frame_set = set(anchor_frames.astype(int))
    person_only = person_df[~person_df['frame_number'].isin(ball_frame_set)].copy()
    if person_only.empty:
        return detections_df

    person_frames = person_only['frame_number'].values.astype(float)

    # Use searchsorted to find surrounding anchors for ALL person frames at once
    idx = np.searchsorted(anchor_frames, person_frames, side='right')
    idx = np.clip(idx, 1, len(anchor_frames) - 1)
    before_idx = idx - 1
    after_idx = idx

    before_frames = anchor_frames[before_idx]
    after_frames = anchor_frames[after_idx]

    # Only interpolate where before != after (valid range)
    valid = before_frames != after_frames
    if not valid.any():
        return detections_df

    t = np.zeros(len(person_frames))
    t[valid] = (person_frames[valid] - before_frames[valid]) / (after_frames[valid] - before_frames[valid])

    ix = anchor_x[before_idx] + t * (anchor_x[after_idx] - anchor_x[before_idx])
    iy = anchor_y[before_idx] + t * (anchor_y[after_idx] - anchor_y[before_idx])

    # Build new rows for interpolated ball positions
    mean_w = ball_df['width'].mean() if 'width' in ball_df.columns else 20
    mean_h = ball_df['height'].mean() if 'height' in ball_df.columns else 20

    new_data = {
        'frame_number': person_only['frame_number'].values,
        'x_center': ix.astype(int),
        'y_center': iy.astype(int),
        'class_name': 'ball',
        'confidence': 0.3,
        'object_class': 'ball',
        'timestamp_ms': person_only['timestamp_ms'].values,
        'width': int(mean_w),
        'height': int(mean_h),
        'tracker_id': -1,
        'ball_distance': 0.0,
        'has_ball': False,
    }
    new_rows = pd.DataFrame(new_data)

    # Only keep valid interpolations
    new_rows = new_rows[valid]

    result = pd.concat([detections_df, new_rows], ignore_index=True)
    return result
