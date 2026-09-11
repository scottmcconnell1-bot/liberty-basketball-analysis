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
    """Load detections using the same key resolution as the video library counts."""
    game_ids = [gid for gid in {game_id, video_game_id, base_analysis_key} if gid]
    rel_ids = [rid for rid in {relational_game_id, video_relational_game_id} if rid is not None]

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


# -- Precision mode -----------------------------------------------------------
# Opt-in generator (ai.event_generator_mode = "precision"). Same possession segments and
# ball track as "expanded", but tuned for the Review queue: it emits far fewer, better-
# supported events. Measured against Scott's manual Wilder Q1 tags with
# scripts/score_manual_q1_regression.py — see docs/ANALYSIS_QUALITY_BASELINE_2026-09-10.md.
# "expanded" is untouched; nothing changes for production until the mode is switched.
PRECISION_DEFAULTS = {
    # a segment must last this many frames before it counts as a real possession
    # (12 / 80 below: measured on Scott's manual Wilder Q1 tags -> precision 0.087,
    #  recall 0.623, AI-only 346; the expanded generator scores 0.014 / 0.660 / 2415)
    "min_hold_frames": 12,
    # primary-pass shot detection only (no low-threshold secondary pass); px of ball rise
    "shot_min_ball_rise": 80.0,
    # at most one shot per possessor within this window
    "shot_refractory_ms": 6000,
    # blocks are rare; the expanded heuristic fired on almost every miss
    "emit_blocks": False,
    # assist only if the passer held the ball and the hand-off was quick
    "assist_max_gap_frames": 15,
    # turnover/steal: the lost possession must have been brief and the new possessor must
    # actually keep the ball
    "turnover_min_next_hold_frames": 6,
    "turnover_max_prev_hold_frames": 60,
    # foul-after-dead-ball heuristic is weak; keep it opt-in
    "emit_fouls": False,
    # "make" needs a longer dead-ball gap than expanded mode's 15 frames (inbound after a
    # score) unless the ball is seen reaching the basket area
    "make_min_gap_frames": 15,
}


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _merge_short_segments(segments, min_hold_frames):
    """Drop segments shorter than min_hold_frames and merge neighbours with the same player.

    Tracker fragmentation produces many 1–5 frame "possessions" that flip between cluster
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


def generate_precision_events_from_segments(game_id, segments, ball_track, params=None):
    p = {**PRECISION_DEFAULTS, **(params or {})}
    events = []
    seen_keys = set()

    segments = _merge_short_segments(segments, p["min_hold_frames"])

    # Shots: primary detector only, higher rise threshold, one per possessor per window.
    shot_segments = {}
    last_shot_ms_by_player = {}
    for index, segment in enumerate(segments):
        next_start = segments[index + 1]["start_frame"] if index + 1 < len(segments) else None
        shot_info = detect_shot_from_segment(
            segment, ball_track, min_ball_rise=p["shot_min_ball_rise"], next_segment_start=next_start
        )
        if not shot_info:
            continue
        last_ms = last_shot_ms_by_player.get(segment["player"])
        if last_ms is not None and shot_info["timestamp_ms"] - last_ms < p["shot_refractory_ms"]:
            continue
        last_shot_ms_by_player[segment["player"]] = shot_info["timestamp_ms"]
        shot_segments[index] = shot_info

    for index, segment in enumerate(segments):
        hold = segment.get("duration_frames", 1)
        if index > 0:
            previous = segments[index - 1]
            if previous["player"] != segment["player"]:
                prev_hold = previous.get("duration_frames", 1)
                gap_frames = segment["start_frame"] - previous["end_frame"]
                append_unique_event(events, seen_keys, make_event(
                    game_id, "possession_change", segment["start_timestamp_ms"],
                    player=segment["player"],
                    # grows with how long BOTH players held the ball; saturates at 45 frames
                    confidence=_clamp(0.4 + 0.01 * min(hold, prev_hold), 0.4, 0.85),
                    details={"from_player": previous["player"], "to_player": segment["player"],
                             "gap_frames": gap_frames, "hold_frames": hold},
                ))
                is_abrupt = (
                    prev_hold <= p["turnover_max_prev_hold_frames"]
                    and gap_frames < 20
                    and previous.get("mean_ball_distance", 0) > 25
                    and hold >= p["turnover_min_next_hold_frames"]
                    and (index - 1) not in shot_segments
                )
                if is_abrupt:
                    conf = _clamp(0.35 + 0.01 * hold, 0.35, 0.7)
                    append_unique_event(events, seen_keys, make_event(
                        game_id, "turnover", segment["start_timestamp_ms"], player=previous["player"],
                        confidence=conf, details={"next_possessor": segment["player"]}))
                    append_unique_event(events, seen_keys, make_event(
                        game_id, "steal", segment["start_timestamp_ms"], player=segment["player"],
                        confidence=conf, details={"from_player": previous["player"]}))

        if index not in shot_segments:
            continue

        shot_info = shot_segments[index]
        next_segment = segments[index + 1] if index + 1 < len(segments) else None
        next_gap = None if next_segment is None else next_segment["start_frame"] - segment["end_frame"]

        # make/miss: same gap/trajectory heuristic as expanded mode
        shot_result = "miss"
        peak_frame = shot_info.get("peak_frame")
        ball_moving_to_basket = False
        if peak_frame:
            post_peak = ball_track[(ball_track["frame_number"] > peak_frame) & (ball_track["frame_number"] <= peak_frame + 30)]
            ball_moving_to_basket = (not post_peak.empty) and post_peak["y_center"].min() < 240
        if next_segment is None or (next_gap is not None and next_gap > p["make_min_gap_frames"]) or ball_moving_to_basket:
            shot_result = "make"

        shot_conf = _clamp(0.35 + shot_info["ball_rise"] / 200.0, 0.35, 0.9)
        append_unique_event(events, seen_keys, make_event(
            game_id, "shot", shot_info["timestamp_ms"], player=segment["player"], shot_result=shot_result,
            confidence=shot_conf,
            details={"ball_rise": round(shot_info["ball_rise"], 1), "lateral_travel": round(shot_info["lateral_travel"], 1),
                     "peak_frame": peak_frame, "generator": "precision"},
        ))
        # keep the derived make/miss row: stats.py and the Review queue expect it
        append_unique_event(events, seen_keys, make_event(
            game_id, shot_result, shot_info["timestamp_ms"], player=segment["player"],
            confidence=round(shot_conf * 0.9, 3), details={"derived_from": "shot"}))

        if shot_result == "miss" and next_segment is not None:
            append_unique_event(events, seen_keys, make_event(
                game_id, "rebound", next_segment["start_timestamp_ms"], player=next_segment["player"],
                confidence=_clamp(0.6 - 0.01 * max(next_gap or 0, 0), 0.3, 0.6),
                details={"shot_player": segment["player"], "gap_frames": next_gap}))
            if p["emit_blocks"] and next_segment["player"] != segment["player"] and (next_gap or 0) <= 3:
                append_unique_event(events, seen_keys, make_event(
                    game_id, "block", next_segment["start_timestamp_ms"], player=next_segment["player"],
                    confidence=0.3, details={"shot_player": segment["player"], "gap_frames": next_gap}))

        if shot_result == "make" and index > 0:
            previous = segments[index - 1]
            assist_gap = segment["start_frame"] - previous["end_frame"]
            if (previous["player"] != segment["player"] and assist_gap <= p["assist_max_gap_frames"]
                    and previous.get("duration_frames", 1) >= p["min_hold_frames"]):
                append_unique_event(events, seen_keys, make_event(
                    game_id, "assist", shot_info["timestamp_ms"], player=previous["player"],
                    confidence=_clamp(0.5 - 0.01 * assist_gap, 0.3, 0.5),
                    details={"scorer": segment["player"], "gap_frames": assist_gap}))

        if p["emit_fouls"] and (next_segment is None or (next_gap is not None and next_gap >= 90)):
            append_unique_event(events, seen_keys, make_event(
                game_id, "foul", shot_info["timestamp_ms"], player=segment["player"], confidence=0.18,
                details={"reason": "long_dead_ball_after_shot", "gap_frames": next_gap}))

    return events


def _lookup_event_type_id(conn, event_type):
    if not event_type:
        return None
    row = conn.execute(
        "SELECT id FROM event_types WHERE lower(code) = lower(?)",
        (event_type,),
    ).fetchone()
    return row["id"] if row else None


def persist_events(conn, game_id, events, relational_game_id=None):
    if relational_game_id is not None:
        # Delete unverified events that are either linked to the relational game_id
        # or, for legacy rows where relational_game_id is NULL, match by game_id.
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
        # Legacy behavior: delete only unverified events matching game_id
        conn.execute(
            "DELETE FROM events WHERE game_id = ? AND human_verified = 0",
            (game_id,),
        )
    if not events:
        conn.commit()
        return

    cur = conn.cursor()
    for ev in events:
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

    auto_accept_high_confidence_events(
        conn,
        game_id,
        relational_game_id=relational_game_id,
    )


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
        print(f"INFO: Ball detections: {ball_count_before} → {ball_count_after} (after interpolation)")

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
            ball_track = build_ball_track(detections_df)
            print(f"INFO: Built {len(segments)} possession segments for precision generation.")
            events_to_persist = generate_precision_events_from_segments(
                game_id, segments, ball_track, params=precision_params
            )
            print(f"INFO: Precision generator produced {len(events_to_persist)} events.")
            persist_events(conn, game_id, events_to_persist, relational_game_id=relational_game_id)
        elif generator_mode == "expanded":
            segments = build_possession_segments(detections_with_possession_df)
            ball_track = build_ball_track(detections_df)
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
