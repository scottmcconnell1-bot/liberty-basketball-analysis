#!/usr/bin/env python3
"""
demo_run.py - Creates film_analysis.db from schema.sql, inserts synthetic detections for a demo game,
runs tracker_assigner and event_generator, and prints resulting events. Intended for quick verification.
"""

import sqlite3
import os
import time
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DB_PATH = str(ROOT / "film_analysis.db")
SCHEMA_PATH = str(ROOT / "schema.sql")


def init_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()
    print("[demo] Initialized DB at", DB_PATH)


def insert_demo_detections():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    game_id = "demo_game"
    rows = []
    for frame in range(12):
        timestamp_ms = frame * 40
        y1 = 200 + ((-1) ** frame) * 10
        rows.append((game_id, frame, timestamp_ms, "person", 0.99, 100, int(y1), 50, 90, None))
        rows.append((game_id, frame, timestamp_ms, "person", 0.98, 300, 200, 50, 90, None))
        rows.append((game_id, frame, timestamp_ms, "ball", 0.9, 105, int(y1), 30, 30, None))
    cur.executemany('''INSERT INTO detections (game_id, frame_number, timestamp_ms, object_class, confidence, x_center, y_center, width, height, tracker_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', rows)
    conn.commit()
    count = cur.execute("SELECT COUNT(*) FROM detections WHERE game_id = ?", (game_id,)).fetchone()[0]
    print(f"[demo] Inserted {count} detections for game_id={game_id}")
    conn.close()


def run_tracker_assigner():
    # Try to use the bundled tracker_assigner if available, otherwise fall back
    try:
        import tracker_assigner
        print("[demo] Running tracker_assigner.main...")
        tracker_assigner.main(DB_PATH, "demo_game", 80, 5)
        return
    except Exception as e:
        print("[demo] tracker_assigner import failed, falling back to lightweight SQL tracker:", e)

    # Fallback: simple centroid-based tracker implemented without pandas
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id, frame_number, x_center, y_center FROM detections WHERE game_id = ? AND object_class = 'person' ORDER BY frame_number, id", ("demo_game",))
        rows = cur.fetchall()
        # Group detections by frame
        frames = {}
        for rid, frame, x, y in rows:
            frames.setdefault(frame, []).append({"id": rid, "x": x, "y": y})

        tracks = {}  # track_id -> {'last_centroid': (x,y), 'last_frame': n}
        next_track_id = 1
        det_to_track = {}

        for frame in sorted(frames.keys()):
            detections = frames[frame]
            assigned = set()

            # Match to existing tracks
            for det in detections:
                x = det['x']
                y = det['y']
                best_track = None
                best_dist = None
                for t_id, t in list(tracks.items()):
                    frame_gap = frame - t['last_frame']
                    if frame_gap > 5:
                        continue
                    lx, ly = t['last_centroid']
                    dist = ((x - lx) ** 2 + (y - ly) ** 2) ** 0.5
                    if dist <= 80 and (best_dist is None or dist < best_dist):
                        best_dist = dist
                        best_track = t_id
                if best_track is not None:
                    det_to_track[det['id']] = best_track
                    tracks[best_track]['last_centroid'] = (x, y)
                    tracks[best_track]['last_frame'] = frame
                    assigned.add(det['id'])

            # Unmatched detections -> new tracks
            for det in detections:
                if det['id'] in assigned:
                    continue
                t_id = next_track_id
                next_track_id += 1
                tracks[t_id] = {'last_centroid': (det['x'], det['y']), 'last_frame': frame}
                det_to_track[det['id']] = t_id

        updates = 0
        for det_id, t_id in det_to_track.items():
            cur.execute('UPDATE detections SET tracker_id = ? WHERE id = ?', (int(t_id), int(det_id)))
            updates += 1
        conn.commit()
        conn.close()
        print(f"[demo] Fallback tracker assigned tracker_id to {updates} detections.")
    except Exception as e:
        print("[demo] Fallback tracker failed:", e)


def run_event_generator():
    try:
        import event_generator
        print("[demo] Running event_generator.main...")
        event_generator.main("demo_game", DB_PATH)
        return
    except Exception as e:
        print("[demo] event_generator import failed, falling back to lightweight SQL event generator:", e)

    # Fallback pure-Python event generation (possession + dribble detection) without pandas/scipy
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id, frame_number, timestamp_ms, object_class, x_center, y_center, tracker_id FROM detections WHERE game_id = ? ORDER BY frame_number, id", ("demo_game",))
        rows = cur.fetchall()
        frames = {}
        for rid, frame_num, ts, objc, x, y, tracker in rows:
            frames.setdefault(frame_num, []).append({"id": rid, "timestamp_ms": ts, "object_class": objc, "x": x, "y": y, "tracker_id": tracker})

        # possession detection
        possession_threshold = 50
        possessions = []  # list of {frame, tracker_id, timestamp_ms, y}
        for frame_num in sorted(frames.keys()):
            frame = frames[frame_num]
            balls = [d for d in frame if d['object_class'] == 'ball']
            players = [d for d in frame if d['object_class'] == 'person']
            if not balls or not players:
                continue
            ball = balls[0]
            bx, by = ball['x'], ball['y']
            best = None
            best_dist = None
            for p in players:
                dx = p['x'] - bx
                dy = p['y'] - by
                dist = (dx*dx + dy*dy) ** 0.5
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best = p
            if best_dist is not None and best_dist <= possession_threshold:
                possessions.append({"frame": frame_num, "tracker_id": best['tracker_id'], "timestamp_ms": int(best['timestamp_ms']), "y": best['y']})

        # group by tracker and detect dribbles
        from collections import defaultdict
        grouped = defaultdict(list)
        for p in possessions:
            grouped[p['tracker_id']].append(p)

        dribble_events = []
        for tracker_id, seq in grouped.items():
            seq = sorted(seq, key=lambda s: s['frame'])
            # split into contiguous sequences allowing small gaps <=2
            current = []
            last_frame = None
            sequences = []
            for s in seq:
                if last_frame is None or s['frame'] - last_frame <= 2:
                    current.append(s)
                else:
                    sequences.append(current)
                    current = [s]
                last_frame = s['frame']
            if current:
                sequences.append(current)

            for s in sequences:
                if len(s) < 6:
                    continue
                y_vals = [itm['y'] for itm in s]
                diffs = [abs(y_vals[i] - y_vals[i-1]) for i in range(1, len(y_vals))]
                if not diffs:
                    continue
                median_diff = sorted(diffs)[len(diffs)//2]
                if median_diff >= 3:
                    ev = (
                        'demo_game',
                        str(tracker_id),
                        'dribble',
                        None,
                        int(s[0]['timestamp_ms']),
                        str({'frames': [itm['frame'] for itm in s]})
                    )
                    cur.execute("INSERT INTO events (game_id, player, event_type, shot_result, timestamp_ms, details_json) VALUES (?, ?, ?, ?, ?, ?)", ev)
                    dribble_events.append(ev)

        conn.commit()
        print(f"[demo] Fallback event generator inserted {len(dribble_events)} dribble events.")
        conn.close()
    except Exception as e:
        print("[demo] Fallback event generator failed:", e)


def print_events():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    rows = cur.execute("SELECT id, game_id, player, event_type, timestamp_ms, details_json FROM events WHERE game_id = ? ORDER BY timestamp_ms", ("demo_game",)).fetchall()
    print("[demo] events:", rows)
    conn.close()


if __name__ == "__main__":
    init_db()
    insert_demo_detections()
    run_tracker_assigner()
    run_event_generator()
    time.sleep(0.5)
    print_events()
