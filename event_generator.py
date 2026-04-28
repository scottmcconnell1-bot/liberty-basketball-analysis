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

    # Build a small lookup of ball detections per frame for speed
    balls = detections_df[detections_df['class_name'] == 'ball'].set_index('frame_number')

    # Group by frame and analyze possession
    for frame, frame_df in detections_df.groupby('frame_number'):
        try:
            ball_detection = balls.loc[frame]
            if isinstance(ball_detection, pd.DataFrame):
                # if multiple balls, pick highest confidence
                ball_detection = ball_detection.sort_values('confidence', ascending=False).iloc[0]
        except KeyError:
            ball_detection = None

        player_detections = frame_df[frame_df['class_name'] == 'person']

        # Skip frames without a ball or players
        if ball_detection is None or player_detections.empty:
            continue

        ball_coords = (float(ball_detection['x_center']), float(ball_detection['y_center']))

        player_indices = player_detections.index
        player_coords = list(zip(player_detections['x_center'].astype(float), player_detections['y_center'].astype(float)))

        if not player_coords:
            continue

        # Calculate distances from ball to all players
        distances = distance.cdist([ball_coords], player_coords, 'euclidean')[0]

        min_dist_index = distances.argmin()
        min_dist = float(distances[min_dist_index])

        # Assign possession if within threshold
        if min_dist <= possession_threshold:
            closest_player_original_index = player_indices[min_dist_index]
            detections_df.loc[closest_player_original_index, 'has_ball'] = True

        # Store all distances for potential future use
        for i, player_index in enumerate(player_indices):
            detections_df.loc[player_index, 'ball_distance'] = float(distances[i])

    possession_events = detections_df[detections_df['has_ball'] == True]
    print(f"INFO: Identified {len(possession_events)} instances of player possession.")

    return detections_df


def assign_possessions(detections_df, gap_tolerance=2):
    """Create contiguous possession segments (possession_id) for players who have the ball.

    Groups by tracker_id when available; falls back to spatial binning 'person_key'.
    Returns a dataframe with an added 'possession_id' column and a list of possession dicts.
    """
    print("INFO: Assigning possessions based on tracker_id or spatial heuristics.")

    # Work on only rows where person has the ball
    person_pos = detections_df[(detections_df['class_name'] == 'person') & (detections_df['has_ball'] == True)].copy()
    if person_pos.empty:
        return detections_df, []

    if 'tracker_id' in person_pos.columns and person_pos['tracker_id'].notna().any():
        person_pos['identity_key'] = person_pos['tracker_id'].astype(str)
    else:
        person_pos['identity_key'] = ((person_pos['x_center'] // 50).astype(int).astype(str) + '_' + (person_pos['y_center'] // 50).astype(int).astype(str))

    possessions = []
    next_pid = 1

    # For each identity, find contiguous sequences of frames
    for key, grp in person_pos.groupby('identity_key'):
        grp = grp.sort_values('frame_number')
        seq = []
        last_frame = None
        for _, row in grp.iterrows():
            fn = int(row['frame_number'])
            if last_frame is None or fn - last_frame <= gap_tolerance:
                seq.append(row)
            else:
                if seq:
                    start = int(seq[0]['frame_number'])
                    end = int(seq[-1]['frame_number'])
                    pid = next_pid
                    next_pid += 1
                    possessions.append({'possession_id': pid, 'identity_key': key, 'start_frame': start, 'end_frame': end, 'tracker_id': seq[0].get('tracker_id', None)})
                    seq = [row]
            last_frame = fn
        if seq:
            start = int(seq[0]['frame_number'])
            end = int(seq[-1]['frame_number'])
            pid = next_pid
            next_pid += 1
            possessions.append({'possession_id': pid, 'identity_key': key, 'start_frame': start, 'end_frame': end, 'tracker_id': seq[0].get('tracker_id', None)})

    # Map possession ids back into detections_df
    detections_df['possession_id'] = pd.NA
    for p in possessions:
        mask = (detections_df['frame_number'].between(p['start_frame'], p['end_frame'])) & (detections_df['class_name'] == 'person')
        # If tracker_id known, narrow mask
        if p.get('tracker_id') is not None and p['tracker_id'] != pd.NA:
            try:
                mask = mask & (detections_df['tracker_id'].astype(str) == str(p['tracker_id']))
            except Exception:
                pass
        detections_df.loc[mask, 'possession_id'] = p['possession_id']

    print(f"INFO: Created {len(possessions)} possessions.")
    return detections_df, possessions


def find_dribbles(detections_with_possession_df, min_sequence_frames=6, y_movement_thresh=3):
    """Identifies dribble events from possession data.

    This improved implementation uses possession segments (created from tracker_id when available) and
    examines the ball vertical movement across the possession to detect dribbling.
    """
    print("INFO: Identifying dribble events (improved).")
    dribble_events = []

    if detections_with_possession_df.empty:
        return dribble_events

    # Ensure possession_id exists
    if 'possession_id' not in detections_with_possession_df.columns:
        detections_with_possession_df['possession_id'] = pd.NA

    # Index ball detections by (frame_number -> y_center)
    balls = detections_with_possession_df[detections_with_possession_df['class_name'] == 'ball'][['frame_number', 'y_center']].set_index('frame_number')

    # Group person possession frames by possession_id
    person_poss = detections_with_possession_df[(detections_with_possession_df['class_name'] == 'person') & (detections_with_possession_df['has_ball'] == True)].copy()
    if person_poss.empty:
        print("INFO: No person possession frames to analyze for dribbles.")
        return dribble_events

    grouped = person_poss.groupby('possession_id')

    for pid, group in grouped:
        if pd.isna(pid):
            continue
        group = group.sort_values('frame_number')
        if len(group) < min_sequence_frames:
            continue

        frames = group['frame_number'].astype(int).tolist()
        # gather ball y positions for these frames
        y_vals = []
        for f in frames:
            try:
                row = balls.loc[f]
                if isinstance(row, pd.DataFrame):
                    y_vals.append(float(row.sort_values('y_center').iloc[0]['y_center']))
                else:
                    y_vals.append(float(row['y_center']))
            except KeyError:
                # missing ball for this frame -> append NaN
                y_vals.append(float('nan'))

        y_series = pd.Series(y_vals).interpolate().fillna(method='bfill').fillna(method='ffill')
        if y_series.isna().all():
            continue

        # measure vertical movement: median absolute diff
        med_abs_diff = y_series.diff().abs().median()
        if pd.isna(med_abs_diff):
            continue
        if med_abs_diff >= y_movement_thresh:
            # Create a dribble event at the start timestamp
            start_row = group.iloc[0]
            event = {
                'game_id': start_row['game_id'],
                'player': str(start_row.get('tracker_id', start_row.get('identity_key', 'unknown'))),
                'event_type': 'dribble',
                'shot_result': None,
                'timestamp_ms': int(start_row['timestamp_ms']),
                'details_json': str({'possession_id': int(pid), 'frames': frames})
            }
            dribble_events.append(event)

    print(f"INFO: Identified {len(dribble_events)} dribble events.")
    return dribble_events


def persist_events(conn, events):
    if not events:
        return
    cur = conn.cursor()
    for ev in events:
        cur.execute(
            "INSERT INTO events (game_id, player, event_type, shot_result, timestamp_ms, details_json) VALUES (?, ?, ?, ?, ?, ?)",
            (ev['game_id'], ev['player'], ev['event_type'], ev['shot_result'], ev['timestamp_ms'], ev['details_json'])
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
        detections_df = get_detections(conn, game_id)

        if detections_df.empty:
            print("INFO: No detections found for this game. Exiting.")
            return True

        # Step 1: Determine who has the ball in each frame
        detections_with_possession_df = find_ball_possession(detections_df)

        # Step 1.5: assign possessions (possession_id)
        detections_with_possession_df, possessions = assign_possessions(detections_with_possession_df)

        # Step 2: Identify Dribble Events
        dribbles = find_dribbles(detections_with_possession_df)
        print(f"INFO: Identified {len(dribbles)} dribble events (heuristic).")

        # Persist possessions as events (summary entries)
        possession_events = []
        for p in possessions:
            possession_events.append({
                'game_id': game_id,
                'player': str(p.get('tracker_id', p.get('identity_key', 'unknown'))),
                'event_type': 'possession',
                'shot_result': None,
                'timestamp_ms': None,
                'details_json': str(p)
            })

        # Persist dribbles and possessions
        persist_events(conn, possession_events)
        persist_events(conn, dribbles)

        print("INFO: Successfully completed event generation pipeline.")
        return True

    except (sqlite3.Error, ImportError) as e:
        print(f"ERROR: An error occurred in event_generator: {e}")
        return False

    finally:
        if conn:
            conn.close()
            print("INFO: Database connection closed.")
