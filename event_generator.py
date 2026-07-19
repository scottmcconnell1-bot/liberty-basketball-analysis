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


def get_detections(conn, game_id, relational_game_id=None):
    """Retrieves all detections for a given game_id from the database and normalizes columns."""
    print(f"INFO: Reading detections for game_id: {game_id}")
    if relational_game_id is not None:
        query = """
            SELECT * FROM detections
            WHERE relational_game_id = ?
               OR (relational_game_id IS NULL AND game_id = ?)
        """
        params = (relational_game_id, game_id)
    else:
        query = "SELECT * FROM detections WHERE game_id = ?"
        params = (game_id,)
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


# Post-filter floors / NMS windows tuned against manual Q1 Wilder ground truth
# (tag-exports/manual_vs_ai_q1_side_by_side.md). Goal: cut AI-only flood while
# preserving real shot / rebound / steal / turnover / assist matches.
EVENT_MIN_CONFIDENCE = {
    "shot": 0.50,
    "make": 0.42,
    "miss": 0.42,
    "rebound": 0.50,
    "block": 0.95,  # effectively disable speculative blocks (all were AI-only on Q1)
    "assist": 0.42,
    "steal": 0.45,
    "turnover": 0.45,
    "foul": 0.50,
    "possession_change": 0.55,
}

# Keep highest-confidence event of each type within this window (ms).
# Shot window collapses near-duplicates; rate cap handles sustained flood.
EVENT_NMS_WINDOW_MS = {
    "shot": 3000,
    "make": 3000,
    "miss": 3000,
    "rebound": 3500,
    "block": 8000,
    "assist": 6000,
    "steal": 6000,
    "turnover": 6000,
    "foul": 10000,
    "possession_change": 2000,
}

# Hard rate cap: ~1 FGA / 10s; putbacks within the window compete by confidence.
MAX_SHOTS_PER_WINDOW = 1
SHOT_RATE_WINDOW_MS = 10000


def _event_details(event):
    raw = event.get("details_json") or "{}"
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def postprocess_ai_events(events):
    """
    Precision-oriented cleanup of expanded generator output.

    - Drop events below type-specific confidence floors
    - Temporal NMS (keep highest confidence per type in a window)
    - Cap impossible shot rates (dozens of FGA in a few seconds)
    - Prefer primary-pass shots over secondary-pass heuristics
    """
    if not events:
        return []

    kept = []
    for event in events:
        et = str(event.get("event_type") or "").lower()
        conf = float(event.get("confidence") or 0.0)
        min_conf = EVENT_MIN_CONFIDENCE.get(et, 0.35)
        if conf < min_conf:
            continue
        details = _event_details(event)
        # Secondary-pass shots are noisy; require higher confidence to survive.
        if et == "shot" and details.get("secondary_pass") and conf < 0.55:
            continue
        kept.append(event)

    # Prefer primary shots: boost ranking key for non-secondary.
    def _rank(event):
        details = _event_details(event)
        conf = float(event.get("confidence") or 0.0)
        secondary_penalty = 0.15 if details.get("secondary_pass") else 0.0
        return conf - secondary_penalty

    by_type = {}
    for event in kept:
        et = str(event.get("event_type") or "").lower()
        by_type.setdefault(et, []).append(event)

    nms_kept = []
    for et, group in by_type.items():
        window = EVENT_NMS_WINDOW_MS.get(et, 3000)
        group = sorted(group, key=lambda e: (int(e.get("timestamp_ms") or 0), -_rank(e)))
        selected = []
        for event in group:
            ts = int(event.get("timestamp_ms") or 0)
            # Compete with recently selected events of same type.
            conflict = False
            for prev in selected:
                prev_ts = int(prev.get("timestamp_ms") or 0)
                if abs(ts - prev_ts) <= window:
                    # Keep higher-ranked; replace if current is better and close.
                    if _rank(event) > _rank(prev):
                        selected.remove(prev)
                        selected.append(event)
                    conflict = True
                    break
            if not conflict:
                selected.append(event)
        nms_kept.extend(selected)

    # Global shot rate limiter across the timeline.
    shots = [e for e in nms_kept if str(e.get("event_type") or "").lower() == "shot"]
    other = [e for e in nms_kept if str(e.get("event_type") or "").lower() != "shot"]
    shots = sorted(shots, key=lambda e: (int(e.get("timestamp_ms") or 0), -_rank(e)))
    rate_kept_shots = []
    for event in shots:
        ts = int(event.get("timestamp_ms") or 0)
        recent = [
            s for s in rate_kept_shots
            if abs(int(s.get("timestamp_ms") or 0) - ts) <= SHOT_RATE_WINDOW_MS
        ]
        if len(recent) < MAX_SHOTS_PER_WINDOW:
            rate_kept_shots.append(event)
            continue
        # Replace weakest recent shot if this one ranks higher.
        weakest = min(recent, key=_rank)
        if _rank(event) > _rank(weakest):
            rate_kept_shots.remove(weakest)
            rate_kept_shots.append(event)

    # Keep satellite make/miss/rebound/assist only when tightly tied to a surviving shot.
    surviving_shots = sorted(
        (
            int(s.get("timestamp_ms") or 0),
            str(s.get("shot_result") or "").lower(),
            str(s.get("player") or ""),
        )
        for s in rate_kept_shots
    )
    surviving_shot_ts = [ts for ts, _, _ in surviving_shots]

    def _nearest_shot(ts):
        best = None
        best_dt = None
        for shot_ts, shot_result, shot_player in surviving_shots:
            dt = abs(shot_ts - ts)
            if best_dt is None or dt < best_dt:
                best = (shot_ts, shot_result, shot_player)
                best_dt = dt
            if shot_ts > ts + 8000:
                break
        return best, best_dt

    filtered_other = []
    for event in other:
        et = str(event.get("event_type") or "").lower()
        ts = int(event.get("timestamp_ms") or 0)
        if et in {"make", "miss"}:
            nearest, dt = _nearest_shot(ts)
            if nearest is None or dt is None or dt > 250:
                continue
            if nearest[1] and nearest[1] != et:
                continue
        elif et == "rebound":
            # Rebound must follow a miss within a few seconds.
            ok = False
            for shot_ts, shot_result, _shot_player in surviving_shots:
                if shot_result != "miss":
                    continue
                delta = ts - shot_ts
                if 0 <= delta <= 4500:
                    ok = True
                    break
                if shot_ts > ts:
                    break
            if not ok:
                continue
        elif et == "assist":
            nearest, dt = _nearest_shot(ts)
            if nearest is None or dt is None or dt > 250:
                continue
            if nearest[1] != "make":
                continue
        elif et == "block":
            continue  # speculative blocks disabled
        filtered_other.append(event)

    # Steal / turnover rate cap — abrupt flips are noisy on this detector.
    steal_to = [e for e in filtered_other if str(e.get("event_type") or "").lower() in {"steal", "turnover"}]
    rest = [e for e in filtered_other if str(e.get("event_type") or "").lower() not in {"steal", "turnover"}]
    steal_to = sorted(steal_to, key=lambda e: (int(e.get("timestamp_ms") or 0), -_rank(e)))
    kept_st = []
    for event in steal_to:
        ts = int(event.get("timestamp_ms") or 0)
        et = str(event.get("event_type") or "").lower()
        recent_same = [
            s for s in kept_st
            if str(s.get("event_type") or "").lower() == et
            and abs(int(s.get("timestamp_ms") or 0) - ts) <= 8000
        ]
        if recent_same:
            continue
        kept_st.append(event)

    result = rate_kept_shots + rest + kept_st
    result.sort(key=lambda e: (int(e.get("timestamp_ms") or 0), str(e.get("event_type") or "")))
    return result


def build_ball_track(detections_df):
    ball_df = detections_df[detections_df["class_name"] == "ball"].copy()
    if ball_df.empty:
        return ball_df
    ball_df = ball_df.sort_values(["frame_number", "confidence"], ascending=[True, False])
    return ball_df.groupby("frame_number", as_index=False).first()


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


def detect_shot_from_segment(segment, ball_track, min_ball_rise=10, next_segment_start=None,
                              secondary_pass=False, ball_y_threshold=400):
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
        peak_idx = search_window["y_center"].idxmin()
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
    peak_idx = search_window["y_center"].idxmin()
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

    return {
        "timestamp_ms": int(peak_row["timestamp_ms"]),
        "peak_frame": int(peak_row["frame_number"]),
        "ball_rise": ball_rise,
        "lateral_travel": lateral_travel,
    }


def generate_expanded_events_from_segments(game_id, segments, ball_track):
    events = []
    seen_keys = set()
    shot_segments = {}

    # Primary pass: require a clearer arc so possession noise does not flood FGA.
    PRIMARY_MIN_BALL_RISE = 40
    for index, segment in enumerate(segments):
        if int(segment.get("duration_frames") or 0) < 4:
            continue
        next_start = segments[index + 1]["start_frame"] if index + 1 < len(segments) else None
        shot_info = detect_shot_from_segment(
            segment,
            ball_track,
            min_ball_rise=PRIMARY_MIN_BALL_RISE,
            next_segment_start=next_start,
        )
        if shot_info:
            # Require some lateral motion to avoid vertical possession noise.
            if float(shot_info.get("lateral_travel") or 0) < 12:
                continue
            shot_info["secondary_pass"] = False
            shot_segments[index] = shot_info

    # Secondary pass: very strict fallback only. Loose thresholds previously
    # invented ~1 false 2PT Miss per second against manual Q1 ground truth.
    SECONDARY_BALL_Y_THRESHOLD = 280
    SECONDARY_MIN_BALL_RISE = 70
    for index, segment in enumerate(segments):
        if index in shot_segments:
            continue  # already detected by primary pass
        # Skip short noise segments — secondary pass over-fires on them.
        if int(segment.get("duration_frames") or 0) < 6:
            continue
        next_start = segments[index + 1]["start_frame"] if index + 1 < len(segments) else None
        shot_info = detect_shot_from_segment(
            segment, ball_track,
            min_ball_rise=SECONDARY_MIN_BALL_RISE,
            next_segment_start=next_start,
            secondary_pass=True,
            ball_y_threshold=SECONDARY_BALL_Y_THRESHOLD,
        )
        if shot_info:
            # Require meaningful lateral travel for secondary shots.
            if float(shot_info.get("lateral_travel") or 0) < 60:
                continue
            shot_info["secondary_pass"] = True
            shot_segments[index] = shot_info

    rebound_segment_indices = set()
    for index, segment in enumerate(segments):
        if index > 0:
            previous = segments[index - 1]
            if previous["player"] != segment["player"]:
                # Only generate possession change events for segments with meaningful duration
                # Skip noise segments (less than 0.5 seconds = ~12 frames at stride=10)
                prev_duration = previous.get("duration_frames", 1)
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
                # - Previous segment was very short
                # - AND gap is small
                # - AND previous segment was NOT a shot
                # - AND ball was far from the previous player (suggesting deflection)
                is_abrupt = (
                    prev_duration <= 3
                    and gap_frames < 12
                    and previous.get("mean_ball_distance", 0) > 30
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
                            confidence=0.48,
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
                            confidence=0.46,
                            details={"from_player": previous["player"]},
                        ),
                    )

        if index not in shot_segments:
            continue

        shot_info = shot_segments[index]
        next_segment = segments[index + 1] if index + 1 < len(segments) else None
        next_gap = None if next_segment is None else next_segment["start_frame"] - segment["end_frame"]
        is_secondary = bool(shot_info.get("secondary_pass"))

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

        # Keep shot_type=2pt until court geometry / enhanced analysis classifies
        # 3PT reliably. Lateral-travel heuristics mislabeled many 2PT as 3PT.
        shot_type = "2pt"
        shot_confidence = 0.42 if is_secondary else 0.60

        append_unique_event(
            events,
            seen_keys,
            make_event(
                game_id,
                "shot",
                shot_info["timestamp_ms"],
                player=segment["player"],
                shot_result=shot_result,
                confidence=shot_confidence,
                details={
                    "ball_rise": round(shot_info["ball_rise"], 1),
                    "lateral_travel": round(shot_info["lateral_travel"], 1),
                    "peak_frame": shot_info["peak_frame"],
                    "shot_type": shot_type,
                    "secondary_pass": is_secondary,
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
                confidence=0.45 if shot_result == "miss" else 0.42,
                details={"derived_from": "shot", "shot_type": shot_type},
            ),
        )

        if shot_result == "miss" and next_segment is not None:
            rebound_kind = (
                "offensive" if next_segment["player"] == segment["player"] else "defensive"
            )
            append_unique_event(
                events,
                seen_keys,
                make_event(
                    game_id,
                    "rebound",
                    next_segment["start_timestamp_ms"],
                    player=next_segment["player"],
                    confidence=0.55,
                    details={
                        "shot_player": segment["player"],
                        "gap_frames": next_gap,
                        "rebound_type": rebound_kind,
                    },
                ),
            )
            # Blocks are rare and historically all false positives on Q1 —
            # do not invent them from quick rebound gaps.

        if shot_result == "make" and index > 0:
            previous = segments[index - 1]
            assist_gap = segment["start_frame"] - previous["end_frame"]
            prev_duration = int(previous.get("duration_frames") or 0)
            if (
                previous["player"] != segment["player"]
                and assist_gap <= 25
                and prev_duration >= 3
                and not is_secondary
            ):
                append_unique_event(
                    events,
                    seen_keys,
                    make_event(
                        game_id,
                        "assist",
                        shot_info["timestamp_ms"],
                        player=previous["player"],
                        confidence=0.45,
                        details={"scorer": segment["player"], "gap_frames": assist_gap},
                    ),
                )

        # Do not invent fouls from long dead-ball gaps — historically all false positives.

    return postprocess_ai_events(events)


def _lookup_event_type_id(conn, event_type):
    if not event_type:
        return None
    row = conn.execute(
        "SELECT id FROM event_types WHERE lower(code) = lower(?)",
        (event_type,),
    ).fetchone()
    return row["id"] if row else None


def persist_events(conn, game_id, events, relational_game_id=None):
    """Replace regenerable AI events, preserving coach-corrected / non-AI rows.

    Auto-accept marks high-confidence AI events human_verified=1, so regenerate
    must also clear source_type='ai' rows that are not coach-corrected. Otherwise
    old auto-accepted floods survive and stack on every regenerate.
    """
    cols = {row[1] for row in conn.execute("PRAGMA table_info(events)").fetchall()}
    has_ai_lifecycle = "source_type" in cols and "review_status" in cols

    if relational_game_id is not None:
        if has_ai_lifecycle:
            conn.execute(
                """
                DELETE FROM events
                WHERE (
                        human_verified = 0
                        OR (
                            source_type = 'ai'
                            AND COALESCE(review_status, 'pending') != 'corrected'
                        )
                      )
                  AND (
                        relational_game_id = ?
                        OR (relational_game_id IS NULL AND game_id = ?)
                      )
                """,
                (relational_game_id, game_id),
            )
        else:
            conn.execute(
                """
                DELETE FROM events
                WHERE human_verified = 0
                  AND (
                        relational_game_id = ?
                        OR (relational_game_id IS NULL AND game_id = ?)
                      )
                """,
                (relational_game_id, game_id),
            )
    else:
        if has_ai_lifecycle:
            conn.execute(
                """
                DELETE FROM events
                WHERE game_id = ?
                  AND (
                        human_verified = 0
                        OR (
                            source_type = 'ai'
                            AND COALESCE(review_status, 'pending') != 'corrected'
                        )
                      )
                """,
                (game_id,),
            )
        else:
            conn.execute(
                "DELETE FROM events WHERE game_id = ? AND human_verified = 0",
                (game_id,),
            )
    if not events:
        conn.commit()
        return

    cur = conn.cursor()
    for ev in events:
        event_type_id = _lookup_event_type_id(conn, ev["event_type"]) if "event_type_id" in cols else None
        if "event_type_id" in cols and "source_type" in cols:
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
        else:
            cur.execute(
                """
                INSERT INTO events
                   (game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ev["game_id"],
                    relational_game_id,
                    ev.get("player"),
                    ev["event_type"],
                    ev.get("shot_result"),
                    ev["timestamp_ms"],
                    ev.get("details_json"),
                    ev.get("confidence"),
                ),
            )
    conn.commit()

    # Auto-accept is best-effort; never fail event persistence if review/stats
    # helpers need Flask context (AI worker subprocess has none).
    try:
        from review_actions import auto_accept_high_confidence_events

        auto_accept_high_confidence_events(
            conn,
            game_id,
            relational_game_id=relational_game_id,
        )
    except Exception as exc:
        print(f"WARNING: auto_accept_high_confidence_events skipped: {exc}")


def main(game_id, db_path, relational_game_id=None):
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
        detections_df = get_detections(conn, game_id, relational_game_id=relational_game_id)

        if detections_df.empty:
            print("INFO: No detections found for this game. Exiting.")
            return True

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
        events_to_persist = []

        if generator_mode == "expanded":
            segments = build_possession_segments(detections_with_possession_df)
            ball_track = build_ball_track(detections_df)
            print(f"INFO: Built {len(segments)} possession segments for expanded generation.")
            events_to_persist = generate_expanded_events_from_segments(game_id, segments, ball_track)
            print(f"INFO: Expanded generator produced {len(events_to_persist)} events.")
            persist_events(conn, game_id, events_to_persist, relational_game_id=relational_game_id)
        else:
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
