
import sqlite3
import pandas as pd
from scipy.spatial import distance


def get_db_connection(db_path):
    """Establishes a connection to the SQLite database."""
    return sqlite3.connect(db_path)


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

        # Step 2: Determine who has the ball in each frame
        detections_with_possession_df = find_ball_possession(detections_df)

        # Step 3: Identify Dribble Events
        dribbles = find_dribbles(detections_with_possession_df)
        print(f"INFO: Identified {len(dribbles)} dribble events (heuristic).")

        # (Optional) Persist dribble events to the events table
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
