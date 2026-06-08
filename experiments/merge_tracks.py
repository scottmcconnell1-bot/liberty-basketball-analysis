#!/usr/bin/env python3
"""
merge_tracks.py - Post-processing to merge tracker IDs representing the same player.

Strategy: Two tracks are the same player if:
1. They don't overlap in time (gap between them, even 1 frame)
2. The last detection of the earlier track is within 150px of the first detection of the later track
3. The gap is < 60 frames (16 seconds at 3.75fps)
"""

import sqlite3
import math
import sys


def merge_tracks(db_path, game_id, max_dist=150, max_gap=60):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Get frame range for each track
    cur.execute("""
        SELECT tracker_id, 
               MIN(frame_number) as first_frame,
               MAX(frame_number) as last_frame,
               COUNT(*) as n_frames
        FROM detections 
        WHERE game_id=? AND object_class='person'
        GROUP BY tracker_id
        HAVING n_frames >= 5
        ORDER BY first_frame
    """, (game_id,))

    tracks = []
    for r in cur.fetchall():
        t = dict(r)

        # Get last position
        cur.execute("""
            SELECT x_center, y_center FROM detections
            WHERE game_id=? AND object_class='person' AND tracker_id=? AND frame_number=?
        """, (game_id, t['tracker_id'], t['last_frame']))
        row = cur.fetchone()
        if row:
            t['last_x'] = row[0]
            t['last_y'] = row[1]

        # Get first position
        cur.execute("""
            SELECT x_center, y_center FROM detections
            WHERE game_id=? AND object_class='person' AND tracker_id=? AND frame_number=?
        """, (game_id, t['tracker_id'], t['first_frame']))
        row = cur.fetchone()
        if row:
            t['first_x'] = row[0]
            t['first_y'] = row[1]

        tracks.append(t)

    # Build merge graph: track -> best_match_for_it (the track that should absorb it)
    # Greedy: process tracks in order of frame, merge forward
    parent = {}  # tid -> root_tid (union-find)

    def find(tid):
        while parent.get(tid, tid) != tid:
            tid = parent[tid]
        return tid

    def union(from_tid, to_tid):
        # Always merge into the track that started earlier
        from_root = find(from_tid)
        to_root = find(to_tid)
        if from_root != to_root:
            # Keep earlier track as root
            if tracks_by_id[from_root]['first_frame'] < tracks_by_id[to_root]['first_frame']:
                parent[to_root] = from_root
            else:
                parent[from_root] = to_root

    tracks_by_id = {t['tracker_id']: t for t in tracks}

    # Sort tracks by first frame
    tracks.sort(key=lambda t: t['first_frame'])

    merges = []
    for i, t1 in enumerate(tracks):
        # Only look at tracks that start AFTER t1 ends
        for j in range(i+1, len(tracks)):
            t2 = tracks[j]
            if t2['first_frame'] > t1['last_frame'] + max_gap:
                break  # too far ahead

            if t2['first_frame'] <= t1['last_frame']:
                continue  # overlapping in time

            # Check if end of t1 is close to start of t2
            if t1.get('last_x') and t2.get('first_x'):
                dist = math.sqrt((t1['last_x'] - t2['first_x'])**2 +
                                (t1['last_y'] - t2['first_y'])**2)
                if dist < max_dist:
                    gap = t2['first_frame'] - t1['last_frame']
                    if 0 < gap < max_gap:
                        merges.append((t1['tracker_id'], t2['tracker_id'], dist, gap))

    print(f"[Merge] {len(tracks)} tracks, {len(merges)} merge pairs found")

    # Apply merges: for each pair, merge the later track into the earlier one
    # Build chain: if A→B and B→C, merge all into A
    merge_map = {}  # from_tid -> to_tid
    for from_tid, to_tid, dist, gap in merges:
        # Merge from_tid into to_tid (earlier absorbs later? No — keep longer track)
        if from_tid not in merge_map:
            merge_map[from_tid] = to_tid

    # Resolve chains
    def resolve(tid):
        visited = set()
        while tid in merge_map and tid not in visited:
            visited.add(tid)
            tid = merge_map[tid]
        return tid

    # Apply to database
    updates = {}
    for from_tid, to_tid in merge_map.items():
        root = resolve(to_tid)
        updates[from_tid] = root

    print(f"[Merge] Applying {len(updates)} track merges...")

    total_merged = 0
    for from_tid, to_tid in updates.items():
        cur.execute("""
            UPDATE detections SET tracker_id=?
            WHERE game_id=? AND object_class='person' AND tracker_id=?
        """, (to_tid, game_id, from_tid))
        total_merged += cur.rowcount

    conn.commit()

    cur.execute("SELECT COUNT(DISTINCT tracker_id) FROM detections WHERE game_id=? AND object_class='person'", (game_id,))
    final = cur.fetchone()[0]
    print(f"[Merge] Merged {len(updates)} track IDs ({total_merged} detections). Final: {final} unique IDs")

    # Show top tracks
    cur.execute("""
        SELECT tracker_id, COUNT(*) as cnt, 
               MIN(frame_number) as first_f, MAX(frame_number) as last_f,
               AVG(x_center) as avg_x, AVG(y_center) as avg_y
        FROM detections 
        WHERE game_id=? AND object_class='person'
        GROUP BY tracker_id 
        HAVING cnt >= 50
        ORDER BY cnt DESC
        LIMIT 20
    """, (game_id,))
    print(f"\nTracks with 50+ detections:")
    for r in cur.fetchall():
        print(f"  ID {r[0]}: {r[1]} det, frames {r[2]}-{r[3]}, pos ({r[4]:.0f},{r[5]:.0f})")

    conn.close()


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python merge_tracks.py <db_path> <game_id>")
        sys.exit(1)
    merge_tracks(sys.argv[1], sys.argv[2])
