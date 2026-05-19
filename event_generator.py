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

    # Calculate distances vectorized
    import numpy as np
    dx = merged['x_center'].values - merged['ball_x'].values
    dy = merged['y_center'].values - merged['ball_y'].values
    dists = np.sqrt(dx**2 + dy**2)

    # Set ball_distance for all player detections using original indices
    detections_df.loc[merged.index, 'ball_distance'] = dists

    # Find closest player per frame
    merged['_dist'] = dists
    closest_per_frame = merged.loc[merged.groupby('frame_number')['_dist'].idxmin()]
    closest_per_frame = closest_per_frame[closest_per_frame['_dist'] <= possession_threshold]

    # Set has_ball for closest players within threshold
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


def build_possession_segments(detections_with_possession_df, max_ball_distance=None, max_gap_frames=30, min_segment_frames=3):
    """
    Build possession segments from detections with ball possession data.

    Args:
        max_ball_distance: max distance for ball possession (auto-calculated if None)
        max_gap_frames: max gap between frames in a single possession segment
        min_segment_frames: minimum frames for a valid segment (default 3, ~0.12s at stride=10)
    """
    players = detections_with_possession_df[detections_with_possession_df["class_name"] == "person"].copy()
    if players.empty:
        return []

    if "tracker_id" in players.columns and players["tracker_id"].notna().any():
        players["owner_key"] = players["tracker_id"].fillna(-1).astype(int).astype(str)
    else:
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


def detect_shot_from_segment(segment, ball_track, min_ball_rise=70):
    if ball_track.empty:
        return None

    anchor_window = ball_track[
        (ball_track["frame_number"] >= max(segment["start_frame"], segment["end_frame"] - 2))
        & (ball_track["frame_number"] <= segment["end_frame"] + 6)
    ].copy()
    if len(anchor_window) < 3:
        return None

    release_window = ball_track[
        (ball_track["frame_number"] >= max(segment["start_frame"], segment["end_frame"] - 4))
        & (ball_track["frame_number"] <= segment["end_frame"] + 20)
    ].copy()
    if len(release_window) < 4:
        return None

    min_ball_row = release_window.loc[release_window["y_center"].idxmin()]
    ball_rise = float(segment["player_y_median"] - float(min_ball_row["y_center"]))
    lateral_travel = abs(float(min_ball_row["x_center"]) - float(segment["player_x_end"]))
    if ball_rise < min_ball_rise or lateral_travel < 10:
        return None

    return {
        "timestamp_ms": segment["end_timestamp_ms"],
        "peak_frame": int(min_ball_row["frame_number"]),
        "ball_rise": ball_rise,
        "lateral_travel": lateral_travel,
    }


def generate_expanded_events_from_segments(game_id, segments, ball_track):
    events = []
    seen_keys = set()
    shot_segments = {}

    for index, segment in enumerate(segments):
        shot_info = detect_shot_from_segment(segment, ball_track)
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
                # - Previous segment was very short (< 1 second) OR gap is tiny (< 3 frames)
                # - AND previous segment was NOT a shot
                # This avoids marking every pass or play development as a turnover
                is_abrupt = (prev_duration < 12 or gap_frames < 3)
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
        shot_result = "make"
        if next_segment is not None and next_gap is not None and next_gap <= 60:
            shot_result = "miss"
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

        # Step 2: Determine who has the ball in each frame
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
    Interpolate ball positions between anchor frames.

    Ball detection only runs on anchor frames (every N frames), so we only
    see the ball a few times per possession. This function estimates ball
    positions on frames between anchor detections using linear interpolation,
    giving us ball positions on every frame that has person detections.
    """
    ball_df = detections_df[detections_df['class_name'] == 'ball'].sort_values('frame_number')
    person_df = detections_df[detections_df['class_name'] == 'person'].sort_values('frame_number')

    if len(ball_df) < 2 or person_df.empty:
        return detections_df

    person_frames = set(person_df['frame_number'].values)
    ball_frames = set(ball_df['frame_number'].values)

    # Build anchor positions
    anchor_frames = sorted(ball_df['frame_number'].values)
    anchor_positions = {}
    for _, row in ball_df.iterrows():
        anchor_positions[row['frame_number']] = (row['x_center'], row['y_center'])

    # Interpolate for person-only frames
    new_rows = []
    for frame in person_frames:
        if frame in ball_frames:
            continue

        # Find nearest anchor frames
        before = None
        after = None
        for af in anchor_frames:
            if af <= frame:
                before = af
            if af >= frame and after is None:
                after = af

        if before is not None and after is not None and before != after:
            t = (frame - before) / (after - before)
            bx, by = anchor_positions[before]
            ax, ay = anchor_positions[after]
            ix = bx + t * (ax - bx)
            iy = by + t * (ay - by)

            # Get timestamp from person detection
            person_row = person_df[person_df['frame_number'] == frame]
            ts = person_row['timestamp_ms'].values[0] if len(person_row) > 0 and 'timestamp_ms' in person_row.columns else 0

            new_rows.append({
                'frame_number': frame,
                'x_center': ix,
                'y_center': iy,
                'class_name': 'ball',
                'confidence': 0.3,
                'object_class': 'ball',
                'timestamp_ms': ts,
                'width': ball_df['width'].mean() if 'width' in ball_df.columns else 20,
                'height': ball_df['height'].mean() if 'height' in ball_df.columns else 20,
                'tracker_id': None,
            })

    if new_rows:
        interp_df = pd.DataFrame(new_rows)
        detections_df = pd.concat([detections_df, interp_df], ignore_index=True)
        detections_df = detections_df.sort_values(['frame_number', 'class_name']).reset_index(drop=True)

    return detections_df
