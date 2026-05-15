
import sqlite3
import pandas as pd
from scipy.spatial import distance


def get_db_connection(db_path):
    """Establishes a connection to the SQLite database with WAL mode."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def get_detections(conn, game_id):
    """Retrieves all detections for a given game_id from the database and normalizes columns."""
    print(f"INFO: Reading detections for game_id: {game_id}")
    query = "SELECT * FROM detections WHERE game_id = ?"
    df = pd.read_sql_query(query, conn, params=(game_id,))
    print(f"INFO: Found {len(df)} detections in the database.")

    # Normalize column names and values for downstream processing
    if 'object_class' in df.columns:
        df['class_name'] = df['object_class'].replace({
            'sports ball': 'ball',
            'sports_ball': 'ball'
        }).fillna(df['object_class'])
    else:
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
    detections_df = detections_df.sort_values('frame_number').reset_index(drop=True)

    detections_df['has_ball'] = False
    detections_df['ball_distance'] = float('inf')

    for frame, frame_df in detections_df.groupby('frame_number'):
        ball_detection = frame_df[frame_df['class_name'] == 'ball']
        player_detections = frame_df[frame_df['class_name'] == 'person']

        if ball_detection.empty or player_detections.empty:
            continue

        ball_coords = (ball_detection.iloc[0]['x_center'], ball_detection.iloc[0]['y_center'])
        
        player_indices = player_detections.index
        player_coords = list(zip(player_detections['x_center'], player_detections['y_center']))
        
        if not player_coords:
            continue
        
        distances = distance.cdist([ball_coords], player_coords, 'euclidean')[0]
        
        min_dist_index = distances.argmin()
        min_dist = distances[min_dist_index]
        
        if min_dist <= possession_threshold:
            closest_player_original_index = player_indices[min_dist_index]
            detections_df.loc[closest_player_original_index, 'has_ball'] = True

        for i, player_index in enumerate(player_indices):
            detections_df.loc[player_index, 'ball_distance'] = distances[i]

    possession_events = detections_df[detections_df['has_ball'] == True]
    print(f"INFO: Identified {len(possession_events)} instances of player possession.")
    
    return detections_df


def find_dribbles(detections_with_possession_df, min_sequence_frames=6, y_movement_thresh=3):
    """Identifies dribble events from possession data."""
    print("INFO: Identifying dribble events.")
    dribble_events = []

    player_possessions = detections_with_possession_df[
        (detections_with_possession_df['class_name'] == 'person') &
        (detections_with_possession_df['has_ball'] == True)
    ].sort_values(by=['frame_number'])

    print(f"DEBUG: Found {len(player_possessions)} total possession frames to analyze for dribbles.")

    if player_possessions.empty:
        return dribble_events

    if 'tracker_id' in player_possessions.columns and player_possessions['tracker_id'].notna().any():
        groups = player_possessions.groupby('tracker_id')
    else:
        bp = player_possessions.copy()
        bp['person_key'] = ((bp['x_center'] // 50).astype(int).astype(str) + '_' + (bp['y_center'] // 50).astype(int).astype(str))
        groups = bp.groupby('person_key')

    for key, group in groups:
        group = group.sort_values('frame_number')
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

        for s in sequences:
            if len(s) < min_sequence_frames:
                continue
            y_vals = s['y_center'].astype(float)
            y_std = y_vals.diff().abs().median()
            if pd.isna(y_std):
                continue
            if y_std >= y_movement_thresh:
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


def main(game_id, db_path):
    """
    Analyzes raw detection data to identify and store basketball events.
    """
    print(f"INFO: Starting event generation for game_id: {game_id}")
    
    conn = None
    try:
        conn = get_db_connection(db_path)
        detections_df = get_detections(conn, game_id)
        
        if detections_df.empty:
            print("INFO: No detections found for this game. Exiting.")
            return True

        detections_with_possession_df = find_ball_possession(detections_df)

        dribbles = find_dribbles(detections_with_possession_df)
        print(f"INFO: Identified {len(dribbles)} dribble events (heuristic).")

        if dribbles:
            cur = conn.cursor()
            for ev in dribbles:
                cur.execute(
                    "INSERT INTO events (game_id, player, event_type, shot_result, timestamp_ms, details_json) VALUES (?, ?, ?, ?, ?, ?)",
                    (ev['game_id'], ev['player'], ev['event_type'], ev['shot_result'], ev['timestamp_ms'], ev['details_json'])
                )
            conn.commit()
            print(f"INFO: Persisted {len(dribbles)} dribble events to the database.")

        print("INFO: Successfully completed event generation pipeline.")
        
        return True
        
    except (sqlite3.Error, ImportError) as e:
        print(f"ERROR: An error occurred in event_generator: {e}")
        return False
    finally:
        if conn:
            conn.close()
            print("INFO: Database connection closed.")
