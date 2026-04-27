
import sqlite3
import pandas as pd
from scipy.spatial import distance

def get_db_connection(db_path):
    """Establishes a connection to the SQLite database."""
    return sqlite3.connect(db_path)

def get_detections(conn, game_id):
    """Retrieves all detections for a given game_id from the database."""
    print(f"INFO: Reading detections for game_id: {game_id}")
    query = "SELECT * FROM detections WHERE game_id = ?"
    df = pd.read_sql_query(query, conn, params=(game_id,))
    print(f"INFO: Found {len(df)} detections in the database.")
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

def find_dribbles(detections_with_possession_df):
    """Identifies dribble events from possession data."""
    print("INFO: Identifying dribble events.")
    dribble_events = []
    
    # Filter for player detections that have the ball
    player_possessions = detections_with_possession_df[
        (detections_with_possession_df['class_name'] == 'person') &
        (detections_with_possession_df['has_ball'] == True)
    ].sort_values(by=['tracker_id', 'frame_number'])

    print(f"DEBUG: Found {len(player_possessions)} total possession frames to analyze for dribbles.")
    
    # This is the section currently under development.
    # The next step is to group by tracker_id and find continuous frame sequences.

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
        print(f"INFO: Identified {len(dribbles)} dribble events (logic in development).")

        print("INFO: Successfully completed event generation pipeline.")
        
        return True
        
    except (sqlite3.Error, ImportError) as e:
        print(f"ERROR: An error occurred in event_generator: {e}")
        return False
    finally:
        if conn:
            conn.close()
            print("INFO: Database connection closed.")
