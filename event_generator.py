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


def get_detections(conn, game_id):
    """Retrieves all detections for a given game_id from the database and normalizes columns."""
    print(f"INFO: Reading detections for game_id: {game_id}")
    query = "SELECT * FROM detections WHERE game_id = ?"
    df = pd.read_sql_query(query, conn, params=(game_id,))
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


def build_ball_track(detections_df):
    ball_df = detections_df[detections_df["class_name"] == "ball"].copy()
    if ball_df.empty:
        return ball_df
    ball_df = ball_df.sort_values(["frame_number", "confidence"], ascending=[True, False])
    return ball_df.groupby("frame_number", as_index=False).first()


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
    from sklearn.cluster import KMeans

    persons = detections_df[detections_df['class_name'] == 'person'].copy()
    if persons.empty:
        detections_df['cluster_id'] = -1
        return detections_df

    # Sample detections for clustering
    sample = persons[['x_center', 'y_center']].dropna()
    if len(sample) > 50000:
        sample = sample.sample(50000, random_state=42)

    # KMeans clustering on spatial positions
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    kmeans.fit(sample.values)

    # Assign ALL person detections to nearest cluster
    person_mask = detections_df['class_name'] == 'person'
    person_coords = detections_df.loc[person_mask, ['x_center', 'y_center']].values
    valid_coords = ~np.isnan(person_coords).any(axis=1)
    clusters = np.full(len(person_coords), -1)
    if valid_coords.any():
        clusters[valid_coords] = kmeans.predict(person_coords[valid_coords])
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


def detect_shot_from_segment(segment, ball_track, min_ball_rise=15, next_segment_start=None,
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
    # Search window: ball release happens around end of possession segment
    # Look before segment end (ball may be released during possession)
    # and forward for the ball's peak. Cap to avoid overlapping with next segment.
    window_start = max(segment["end_frame"] - 10, segment["start_frame"])
    window_end = segment["end_frame"] + 25
    if next_segment_start is not None:
        window_end = min(window_end, next_segment_start - 1)

    search_window = ball_track[
        (ball_track["frame_number"] >= window_start)
        & (ball_track["frame_number"] <= window_end)
    ].copy()
    if len(search_window) < 2:
        return None

    # Find the ball's highest point (minimum y_center) in the window
    peak_idx = search_window["y_center"].idxmin()
    peak_row = search_window.loc[peak_idx]
    peak_y = float(peak_row["y_center"])
    peak_x = float(peak_row["x_center"])

    # Ball must rise above the player's head (player_y_median is torso height)
    ball_rise = float(segment["player_y_median"]) - peak_y
    if ball_rise < min_ball_rise:
        return None

    # Ball must travel laterally (not just go straight up and down)
    lateral_travel = abs(peak_x - float(segment["player_x_end"]))
    if lateral_travel < 5:
        return None

    # Verify arc shape: ball should be descending after the peak
    after_peak = search_window[search_window["frame_number"] > peak_row["frame_number"]]
    if len(after_peak) >= 1:
        min_y_after = after_peak["y_center"].min()
        # If ball continues rising after "peak", it's not a real arc
        if min_y_after < peak_y - 5:
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

        # Determine make/miss using ball trajectory relative to basket.
        # After a made shot, the ball should end up near the basket (top of frame).
        # After a missed shot, the ball rebounds away from the basket.
        # Heuristic: look at ball position in the 20 frames after the shot peak.
        # If the ball's minimum y (closest to basket) is below a threshold, it's a make.
        shot_result = "miss"
        if shot_info.get("peak_frame"):
            peak_frame = shot_info["peak_frame"]
            # Look at ball positions after the shot peak (up to 30 frames)
            post_peak_ball = ball_track[
                (ball_track["frame_number"] > peak_frame) &
                (ball_track["frame_number"] <= peak_frame + 30)
            ]
            if not post_peak_ball.empty:
                # Ball near top of frame (y < 200px on 720p) = near basket = make
                min_y = post_peak_ball["y_center"].min()
                if min_y < 200:
                    shot_result = "make"
            elif next_segment is None or (next_gap is not None and next_gap > 60):
                # No ball data after shot AND long gap = likely make
                shot_result = "make"
        elif next_segment is None or (next_gap is not None and next_gap > 60):
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


def persist_events(conn, game_id, events):
    conn.execute("DELETE FROM events WHERE game_id = ? AND human_verified = 0", (game_id,))
    if not events:
        conn.commit()
        return

    cur = conn.cursor()
    for ev in events:
        cur.execute(
            """INSERT INTO events
               (game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                ev["game_id"],
                ev.get("player"),
                ev["event_type"],
                ev.get("shot_result"),
                ev["timestamp_ms"],
                ev.get("details_json"),
                ev.get("confidence"),
            ),
        )
    conn.commit()


def main(game_id, db_path):
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
        detections_df = get_detections(conn, game_id)

        if detections_df.empty:
            print("INFO: No detections found for this game. Exiting.")
            return True

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
        events_to_persist = []

        if generator_mode == "expanded":
            segments = build_possession_segments(detections_with_possession_df)
            ball_track = build_ball_track(detections_df)
            print(f"INFO: Built {len(segments)} possession segments for expanded generation.")
            events_to_persist = generate_expanded_events_from_segments(game_id, segments, ball_track)
            print(f"INFO: Expanded generator produced {len(events_to_persist)} events.")
            persist_events(conn, game_id, events_to_persist)
        else:
            persist_events(conn, game_id, [])

        print("INFO: Successfully completed event generation pipeline.")

        return True

    except (sqlite3.Error, ImportError) as e:
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
