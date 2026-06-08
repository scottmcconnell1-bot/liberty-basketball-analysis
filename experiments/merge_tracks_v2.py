#!/usr/bin/env python3
"""
merge_tracks_v2.py - Merge tracks that represent the same player based on
spatial overlap and time gap.

Two tracks are candidates if:
1. They never overlap in time
2. Their average positions are within max_spatial_dist
3. The gap between them is < max_gap frames

Then greedily merges until stable.
"""

import sqlite3
import math
import sys
from collections import defaultdict


def resolve(tid, merge_map):
    visited = set()
    while tid in merge_map and tid not in visited:
        visited.add(tid)
        tid = merge_map[tid]
    return tid


def merge_tracks_v2(db_path, game_id, max_spatial_dist=150, max_gap=120):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get all significant tracks (>= 10 detections)
    rows = conn.execute("""
        SELECT tracker_id, COUNT(*) as n_frames,
               MIN(frame_number) as first_frame, MAX(frame_number) as last_frame,
               AVG(x_center) as avg_x, AVG(y_center) as avg_y
        FROM detections
        WHERE game_id=? AND object_class='person'
        GROUP BY tracker_id
        HAVING n_frames >= 10
        ORDER BY first_frame
    """, (game_id,)).fetchall()

    tracks = [dict(r) for r in rows]
    print(f"[{game_id}] {len(tracks)} tracks with 10+ detections")

    # Load detection positions per track
    track_frames = {}
    track_positions = {}
    for t in tracks:
        rows = conn.execute(
            "SELECT frame_number, x_center, y_center FROM detections WHERE game_id=? AND object_class='person' AND tracker_id=?",
            (game_id, t['tracker_id'])
        ).fetchall()
        track_frames[t['tracker_id']] = {r[0] for r in rows}
        track_positions[t['tracker_id']] = rows

    merge_map = {}

    # Iteratively merge
    for iteration in range(20):
        changed = False
        # Compute current root for each track
        roots = {}
        for t in tracks:
            roots[t['tracker_id']] = resolve(t['tracker_id'], merge_map)

        # Build merged track data
        merged = defaultdict(lambda: {'frames': set(), 'avg_x': [], 'avg_y': []})
        for t in tracks:
            r = roots[t['tracker_id']]
            merged[r]['frames'] |= track_frames[t['tracker_id']]
            for _, x, y in track_positions[t['tracker_id']]:
                merged[r]['avg_x'].append(x)
                merged[r]['avg_y'].append(y)

        # Compute centroids
        for r, d in merged.items():
            if d['avg_x']:
                d['cx'] = sum(d['avg_x']) / len(d['avg_x'])
                d['cy'] = sum(d['avg_y']) / len(d['avg_y'])
                d['first'] = min(d['frames'])
                d['last'] = max(d['frames'])
                d['n'] = len(d['frames'])

        root_list = list(merged.keys())
        for i, r1 in enumerate(root_list):
            for j, r2 in enumerate(root_list):
                if i >= j:
                    continue
                d1, d2 = merged[r1], merged[r2]
                # No time overlap
                if d1['frames'] & d2['frames']:
                    continue
                # Spatial proximity
                dist = math.sqrt((d1['cx'] - d2['cx'])**2 + (d1['cy'] - d2['cy'])**2)
                if dist > max_spatial_dist:
                    continue
                # Time gap
                gap = d2['first'] - d1['last'] if d1['last'] < d2['first'] else d1['first'] - d2['last']
                if gap > max_gap or gap < 0:
                    continue
                # Merge smaller into larger
                if d1['n'] >= d2['n']:
                    merge_map[r2] = r1
                else:
                    merge_map[r1] = r2
                changed = True

        print(f"  Iter {iteration+1}: {len(merge_map)} merges total, changed={changed}")
        if not changed:
            break

    # Apply merges
    updates = {}
    for tid in set(merge_map.keys()):
        root = resolve(tid, merge_map)
        if tid != root:
            updates[tid] = root

    print(f"Applying {len(updates)} track merges to DB...")
    total_rows = 0
    for old_tid, new_tid in updates.items():
        conn.execute("UPDATE detections SET tracker_id=? WHERE game_id=? AND object_class='person' AND tracker_id=?",
                     (new_tid, game_id, old_tid))
        total_rows += conn.total_changes
    conn.commit()

    final = conn.execute("SELECT COUNT(DISTINCT tracker_id) FROM detections WHERE game_id=? AND object_class='person'",
                         (game_id,)).fetchone()[0]
    print(f"Result: {final} unique tracker IDs (from {len(tracks)} tracks)")

    # Show top 25 tracks
    rows = conn.execute("""
        SELECT tracker_id, COUNT(*) as cnt,
               MIN(frame_number) as first_f, MAX(frame_number) as last_f,
               AVG(x_center) as avg_x, AVG(y_center) as avg_y
        FROM detections
        WHERE game_id=? AND object_class='person'
        GROUP BY tracker_id
        ORDER BY cnt DESC
        LIMIT 25
    """, (game_id,)).fetchall()
    print(f"\nTop 25 tracks:")
    for r in rows:
        print(f"  ID {r[0]}: {r[1]:5d} det, frames {r[2]:5d}-{r[3]:5d}, pos ({r[4]:.0f},{r[5]:.0f})")

    conn.close()


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: merge_tracks_v2.py <db_path> <game_id>")
        sys.exit(1)
    merge_tracks_v2(sys.argv[1], sys.argv[2])
