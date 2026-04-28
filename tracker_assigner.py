"""
tracker_assigner.py

Lightweight centroid-based tracker to assign tracker_id to person detections
in film_analysis.db for a single game. This is a scaffolded tracker to be
replaced later by a production tracker (ByteTrack/DeepSort). It assigns stable
tracker IDs across frames using nearest-neighbor matching with a distance and
frame-gap threshold.

Usage:
    source .venv/bin/activate
    python tracker_assigner.py --db film_analysis.db --game_id game_001

Outputs:
    Updates detections table: sets tracker_id for person detections for the
    provided game_id.

Notes:
- Works on detections already written to the DB by ai_analyzer.py.
- Only assigns tracker_id for object_class == 'person'.
- Parameters (max_distance, max_frame_gap) are configurable via CLI.

"""

import argparse
import sqlite3
import pandas as pd
import math
from collections import defaultdict


def load_detections(conn, game_id):
    query = """
    SELECT id, frame_number, timestamp_ms, object_class, x_center, y_center, width, height
    FROM detections
    WHERE game_id = ? AND object_class = 'person'
    ORDER BY frame_number, id
    """
    return pd.read_sql_query(query, conn, params=(game_id,))


def assign_trackers(detections_df, max_distance=80, max_frame_gap=5):
    # detections_df: columns -> id, frame_number, x_center, y_center
    tracks = {}  # track_id -> {'last_centroid':(x,y), 'last_frame':n}
    next_track_id = 1
    det_to_track = {}

    grouped = detections_df.groupby('frame_number')
    for frame, group in grouped:
        detections = group[['id','x_center','y_center']].to_dict('records')
        assigned = set()

        # Try to match detections to existing tracks
        for det in detections:
            x, y = det['x_center'], det['y_center']
            best_track = None
            best_dist = None
            for t_id, t in tracks.items():
                frame_gap = frame - t['last_frame']
                if frame_gap > max_frame_gap:
                    continue
                lx, ly = t['last_centroid']
                dist = math.hypot(x - lx, y - ly)
                if dist <= max_distance and (best_dist is None or dist < best_dist):
                    best_dist = dist
                    best_track = t_id
            if best_track is not None:
                # assign
                det_to_track[det['id']] = best_track
                tracks[best_track]['last_centroid'] = (x, y)
                tracks[best_track]['last_frame'] = frame
                assigned.add(det['id'])

        # unmatched detections -> new tracks
        for det in detections:
            if det['id'] in assigned:
                continue
            t_id = next_track_id
            next_track_id += 1
            tracks[t_id] = {'last_centroid': (det['x_center'], det['y_center']), 'last_frame': frame}
            det_to_track[det['id']] = t_id

    return det_to_track


def write_tracker_ids(conn, det_to_track):
    cur = conn.cursor()
    updates = 0
    for det_id, t_id in det_to_track.items():
        cur.execute('UPDATE detections SET tracker_id = ? WHERE id = ?', (int(t_id), int(det_id)))
        updates += 1
    conn.commit()
    return updates


def main(db_path, game_id, max_distance, max_frame_gap):
    conn = sqlite3.connect(db_path)
    try:
        detections_df = load_detections(conn, game_id)
        if detections_df.empty:
            print(f'No person detections found for game_id={game_id}')
            return
        det_to_track = assign_trackers(detections_df, max_distance=max_distance, max_frame_gap=max_frame_gap)
        updated = write_tracker_ids(conn, det_to_track)
        print(f'Assigned tracker_id to {updated} detections for game_id={game_id}')
    finally:
        conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Assign tracker_id to person detections in film_analysis.db')
    parser.add_argument('--db', required=True, help='Path to SQLite DB (e.g. film_analysis.db)')
    parser.add_argument('--game_id', required=True, help='Game ID to process (e.g. game_001)')
    parser.add_argument('--max_distance', type=int, default=80, help='Max pixel distance to match across frames')
    parser.add_argument('--max_frame_gap', type=int, default=5, help='Max frames to allow a track to be unmatched')
    args = parser.parse_args()
    main(args.db, args.game_id, args.max_distance, args.max_frame_gap)
