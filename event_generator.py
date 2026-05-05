import json
import sqlite3
import pandas as pd
from scipy.spatial import distance

from config import AnalysisConfig
from settings_store import AI_DEFAULTS, load_all_settings


def get_db_connection(db_path):
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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


def find_ball_possession(detections_df, possession_threshold=50):
    """
    Analyzes detections to determine ball possession for each frame.
    Adds 'has_ball' and 'ball_distance' columns to the player detections.
    """
    print("INFO: Analyzing ball possession.")
    # Ensure dataframe is sorted by frame number
    detections_df = detections_df.sort_values('frame_number').reset_index(drop=True)

    # Initialize columns
    detections_df['has_ball'] = False
    detections_df['ball_distance'] = float('inf')

    # Group by frame and analyze possession
    for frame, frame_df in detections_df.groupby('frame_number'):
        ball_detection = frame_df[frame_df['class_name'] == 'ball']
        player_detections = frame_df[frame_df['class_name'] == 'person']

        # Skip frames without a ball or players
        if ball_detection.empty or player_detections.empty:
            continue

        ball_coords = (ball_detection.iloc[0]['x_center'], ball_detection.iloc[0]['y_center'])
        
        player_indices = player_detections.index
        player_coords = list(zip(player_detections['x_center'], player_detections['y_center']))
        
        if not player_coords:
            continue
            
        # Calculate distances from ball to all players
        distances = distance.cdist([ball_coords], player_coords, 'euclidean')[0]
        
        min_dist_index = distances.argmin()
        min_dist = distances[min_dist_index]
        
        # Assign possession if within threshold
        if min_dist <= possession_threshold:
            closest_player_original_index = player_indices[min_dist_index]
            detections_df.loc[closest_player_original_index, 'has_ball'] = True

        # Store all distances for potential future use
        for i, player_index in enumerate(player_indices):
            detections_df.loc[player_index, 'ball_distance'] = distances[i]

    possession_events = detections_df[detections_df['has_ball'] == True]
    print(f"INFO: Identified {len(possession_events)} instances of player possession.")
    
    return detections_df


def find_dribbles(detections_with_possession_df, min_sequence_frames=6, y_movement_thresh=3):
    """Identifies dribble events from possession data.

    This function tries to work even when explicit tracker_id values are not present.
    If tracker_id exists, grouping is done by tracker_id. Otherwise a simple spatial-temporal
    heuristic groups player detections into temporary buckets based on proximity.
    """
    print("INFO: Identifying dribble events.")
    dribble_events = []

    # Filter for player detections that have the ball
    player_possessions = detections_with_possession_df[
        (detections_with_possession_df['class_name'] == 'person') &
        (detections_with_possession_df['has_ball'] == True)
    ].sort_values(by=['frame_number'])

    print(f"DEBUG: Found {len(player_possessions)} total possession frames to analyze for dribbles.")

    if player_possessions.empty:
        return dribble_events

    # If tracker_id is available and not all-NA, group by it
    if 'tracker_id' in player_possessions.columns and player_possessions['tracker_id'].notna().any():
        groups = player_possessions.groupby('tracker_id')
    else:
        # Create a coarse spatial bin 'person_key' to approximate identity across nearby frames
        # This is a fallback heuristic when no tracking is available.
        bp = player_possessions.copy()
        bp['person_key'] = ((bp['x_center'] // 50).astype(int).astype(str) + '_' + (bp['y_center'] // 50).astype(int).astype(str))
        groups = bp.groupby('person_key')

    for key, group in groups:
        group = group.sort_values('frame_number')
        # Find contiguous sequences of frames (allow small gaps of up to 2 frames)
        seq = []
        last_frame = None
        sequences = []
        for _, row in group.iterrows():
            fn = int(row['frame_number'])
            if last_frame is None or fn - last_frame <= 2:
                seq.append(row)
            else:
                sequences.append(pd.DataFrame(seq))
                seq = [row]
            last_frame = fn
        if seq:
            sequences.append(pd.DataFrame(seq))

        # Analyze each contiguous sequence for dribble-like vertical movement
        for s in sequences:
            if len(s) < min_sequence_frames:
                continue
            # Examine ball y_center changes (we need ball positions). We approximate by using ball_distance and player y
            # If there is significant vertical movement of the ball relative to the player across the sequence, mark dribble
            y_vals = s['y_center'].astype(float)
            y_std = y_vals.diff().abs().median()
            if pd.isna(y_std):
                continue
            if y_std >= y_movement_thresh:
                # Create a dribble event at the start timestamp
                event = {
                    'game_id': s.iloc[0]['game_id'],
                    'player': str(key),
                    'event_type': 'dribble',
                    'shot_result': None,
                    'timestamp_ms': int(s.iloc[0]['timestamp_ms']),
                    'details_json': str({'frames': list(s['frame_number'])})
                }
                dribble_events.append(event)

    print(f"INFO: Identified {len(dribble_events)} dribble events.")
    return dribble_events


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


def build_possession_segments(detections_with_possession_df, max_ball_distance=120, max_gap_frames=4, min_segment_frames=3):
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

    players = players[players["ball_distance"].notna() & (players["ball_distance"] < float("inf"))].copy()
    if players.empty:
        return []

    frame_best = (
        players.sort_values(["frame_number", "ball_distance"])
        .groupby("frame_number", as_index=False)
        .first()
    )
    frame_best = frame_best[frame_best["ball_distance"] <= max_ball_distance].sort_values("frame_number")
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
                        "mean_ball_distance": float(segment_df["ball_distance"].mean()),
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
                "mean_ball_distance": float(segment_df["ball_distance"].mean()),
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
                            "gap_frames": segment["start_frame"] - previous["end_frame"],
                        },
                    ),
                )

                if (index - 1) not in shot_segments:
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
            analysis_defaults={
                "USE_DRIBBLE_EVENTS": AnalysisConfig.USE_DRIBBLE_EVENTS,
                "USE_DRIBBLE_HEURISTICS": AnalysisConfig.USE_DRIBBLE_HEURISTICS,
            },
            ai_defaults=AI_DEFAULTS,
            db=conn,
        )
        analysis_settings = runtime_settings["analysis"]
        ai_settings = runtime_settings["ai"]
        detections_df = get_detections(conn, game_id)
        
        if detections_df.empty:
            print("INFO: No detections found for this game. Exiting.")
            return True

        # Step 2: Determine who has the ball in each frame
        detections_with_possession_df = find_ball_possession(detections_df)

        dribbles = []
        if analysis_settings["USE_DRIBBLE_HEURISTICS"]:
            dribbles = find_dribbles(detections_with_possession_df)
            print(f"INFO: Identified {len(dribbles)} dribble events (heuristic).")
        else:
            print("INFO: Dribble heuristics disabled by configuration.")

        generator_mode = ai_settings.get("event_generator_mode", "legacy")
        events_to_persist = []

        if generator_mode == "expanded":
            segments = build_possession_segments(detections_with_possession_df)
            ball_track = build_ball_track(detections_df)
            print(f"INFO: Built {len(segments)} possession segments for expanded generation.")
            events_to_persist = generate_expanded_events_from_segments(game_id, segments, ball_track)
            if analysis_settings["USE_DRIBBLE_EVENTS"] and dribbles:
                events_to_persist.extend(
                    make_event(
                        ev["game_id"],
                        ev["event_type"],
                        ev["timestamp_ms"],
                        player=ev.get("player"),
                        shot_result=ev.get("shot_result"),
                        confidence=0.55,
                        details={"legacy_dribble": True},
                    )
                    for ev in dribbles
                )
            print(f"INFO: Expanded generator produced {len(events_to_persist)} events.")
            persist_events(conn, game_id, events_to_persist)
        elif analysis_settings["USE_DRIBBLE_EVENTS"] and dribbles:
            events_to_persist = [
                make_event(
                    ev["game_id"],
                    ev["event_type"],
                    ev["timestamp_ms"],
                    player=ev.get("player"),
                    shot_result=ev.get("shot_result"),
                    confidence=0.55,
                    details={"legacy_dribble": True},
                )
                for ev in dribbles
            ]
            persist_events(conn, game_id, events_to_persist)
            print(f"INFO: Persisted {len(events_to_persist)} dribble events to the database.")
        elif dribbles:
            print("INFO: Dribble events not persisted because USE_DRIBBLE_EVENTS is disabled.")
            persist_events(conn, game_id, [])
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
