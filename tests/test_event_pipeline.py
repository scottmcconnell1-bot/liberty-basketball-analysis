"""
test_event_pipeline.py – Pure-Python tests for possession detection and dribble
detection logic (no pandas/scipy required). Uses the fallback implementations
from demo_run.py.
"""
import os
import sys
import sqlite3
import tempfile
import pytest
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── Fallback tracker ──────────────────────────────────────────────────

class SimpleTracker:
    def __init__(self, max_dist=80):
        self.tracks = {}
        self.next_id = 1
        self.max_dist = max_dist

    def update(self, detections):
        assigned = []
        for det in detections:
            cx, cy = det["x_center"], det["y_center"]
            best_id, best_dist = None, self.max_dist
            for tid, (tx, ty) in self.tracks.items():
                dist = ((cx - tx) ** 2 + (cy - ty) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_id = tid
            if best_id is None:
                best_id = self.next_id
                self.next_id += 1
            self.tracks[best_id] = (cx, cy)
            assigned.append({**det, "tracker_id": best_id})
        return assigned


# ── Fallback event detector ───────────────────────────────────────────

def detect_dribbles(detections, ball_class="ball", min_bounces=2):
    """Detect dribbles by counting vertical direction reversals of the ball."""
    ball_detections = sorted(
        [d for d in detections if d["object_class"] == ball_class],
        key=lambda d: d["frame_number"],
    )
    events = []
    if len(ball_detections) < 3:
        return events
    ys = [d["y_center"] for d in ball_detections]
    direction = None
    bounces = 0
    for i in range(1, len(ys)):
        dy = ys[i] - ys[i - 1]
        if dy == 0:
            continue
        new_dir = "down" if dy > 0 else "up"
        if direction is not None and new_dir != direction:
            bounces += 1
        direction = new_dir
    if bounces >= min_bounces:
        events.append({
            "event_type": "dribble",
            "timestamp_ms": ball_detections[0]["timestamp_ms"],
            "details": f"bounces={bounces}",
        })
    return events


# ── Test fixtures ─────────────────────────────────────────────────────

def make_detections(frames=12):
    """Generate synthetic detections: 2 players + 1 bouncing ball per frame."""
    dets = []
    for frame in range(frames):
        ts = frame * 33
        # ball bounces: even frames down, odd frames up
        ball_y = 300 + (40 if frame % 2 == 0 else -40)
        dets.append({
            "frame_number": frame,
            "timestamp_ms": ts,
            "object_class": "ball",
            "x_center": 320,
            "y_center": ball_y,
            "confidence": 0.92,
        })
        for pid in range(2):
            dets.append({
                "frame_number": frame,
                "timestamp_ms": ts,
                "object_class": "person",
                "x_center": 200 + pid * 200,
                "y_center": 400,
                "confidence": 0.88,
            })
    return dets


# ── Tests ─────────────────────────────────────────────────────────────

def test_tracker_assigns_ids():
    dets = [d for d in make_detections() if d["object_class"] == "person"]
    tracker = SimpleTracker()
    frame0 = [d for d in dets if d["frame_number"] == 0]
    result = tracker.update(frame0)
    assert all("tracker_id" in d for d in result)
    assert len({d["tracker_id"] for d in result}) == 2  # 2 distinct players


def test_tracker_consistent_ids():
    """Same object in consecutive frames should get the same tracker_id."""
    tracker = SimpleTracker()
    frame0 = [{"frame_number": 0, "timestamp_ms": 0, "object_class": "person",
                "x_center": 100, "y_center": 200, "confidence": 0.9}]
    frame1 = [{"frame_number": 1, "timestamp_ms": 33, "object_class": "person",
                "x_center": 105, "y_center": 202, "confidence": 0.9}]
    r0 = tracker.update(frame0)
    r1 = tracker.update(frame1)
    assert r0[0]["tracker_id"] == r1[0]["tracker_id"]


def test_tracker_assigns_new_id_for_new_object():
    tracker = SimpleTracker(max_dist=50)
    frame0 = [{"frame_number": 0, "timestamp_ms": 0, "object_class": "person",
                "x_center": 100, "y_center": 100, "confidence": 0.9}]
    frame1 = [{"frame_number": 1, "timestamp_ms": 33, "object_class": "person",
                "x_center": 600, "y_center": 600, "confidence": 0.9}]
    r0 = tracker.update(frame0)
    r1 = tracker.update(frame1)
    assert r0[0]["tracker_id"] != r1[0]["tracker_id"]


def test_dribble_detection_bouncing_ball():
    dets = make_detections(frames=12)
    events = detect_dribbles(dets)
    assert len(events) == 1
    assert events[0]["event_type"] == "dribble"


def test_dribble_detection_no_ball():
    dets = [d for d in make_detections() if d["object_class"] == "person"]
    events = detect_dribbles(dets)
    assert events == []


def test_dribble_detection_too_few_frames():
    dets = [
        {"frame_number": 0, "timestamp_ms": 0,  "object_class": "ball", "x_center": 320, "y_center": 300, "confidence": 0.9},
        {"frame_number": 1, "timestamp_ms": 33, "object_class": "ball", "x_center": 320, "y_center": 340, "confidence": 0.9},
    ]
    events = detect_dribbles(dets)
    assert events == []


def test_dribble_detection_steady_ball():
    """Ball that never bounces should produce no dribble events."""
    dets = [
        {"frame_number": i, "timestamp_ms": i*33, "object_class": "ball",
         "x_center": 320, "y_center": 300, "confidence": 0.9}
        for i in range(10)
    ]
    events = detect_dribbles(dets)
    assert events == []


def test_full_pipeline_in_sqlite():
    """End-to-end: insert detections -> track -> detect events -> verify."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT, frame_number INTEGER, timestamp_ms INTEGER,
                object_class TEXT, confidence REAL,
                x_center INTEGER, y_center INTEGER,
                width INTEGER DEFAULT 30, height INTEGER DEFAULT 30,
                tracker_id INTEGER
            );
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT, player TEXT, event_type TEXT,
                shot_result TEXT, timestamp_ms INTEGER,
                details_json TEXT, human_verified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        game_id = "test_game"
        raw = make_detections(frames=12)
        for d in raw:
            conn.execute(
                "INSERT INTO detections (game_id, frame_number, timestamp_ms, object_class, confidence, x_center, y_center) VALUES (?,?,?,?,?,?,?)",
                (game_id, d["frame_number"], d["timestamp_ms"], d["object_class"], d["confidence"], d["x_center"], d["y_center"]),
            )
        conn.commit()

        # Track
        tracker = SimpleTracker()
        rows = conn.execute(
            "SELECT * FROM detections WHERE game_id=? AND object_class='person' ORDER BY frame_number",
            (game_id,),
        ).fetchall()
        for row in rows:
            det = dict(row)
            updated = tracker.update([det])
            if updated:
                conn.execute(
                    "UPDATE detections SET tracker_id=? WHERE id=?",
                    (updated[0]["tracker_id"], det["id"]),
                )
        conn.commit()

        # Verify tracker_ids assigned
        assigned = conn.execute(
            "SELECT COUNT(*) FROM detections WHERE tracker_id IS NOT NULL"
        ).fetchone()[0]
        assert assigned > 0

        # Detect events
        all_dets = [dict(r) for r in conn.execute(
            "SELECT * FROM detections WHERE game_id=? ORDER BY frame_number", (game_id,)
        ).fetchall()]
        events = detect_dribbles(all_dets)
        for ev in events:
            conn.execute(
                "INSERT INTO events (game_id, event_type, timestamp_ms) VALUES (?,?,?)",
                (game_id, ev["event_type"], ev["timestamp_ms"]),
            )
        conn.commit()

        count = conn.execute("SELECT COUNT(*) FROM events WHERE game_id=?", (game_id,)).fetchone()[0]
        assert count == 1

        conn.close()
    finally:
        os.unlink(db_path)


def test_event_generator_connection_uses_row_factory():
    from event_generator import get_db_connection

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?)", ("analysis.USE_DRIBBLE_EVENTS", "0"))
        conn.commit()
        conn.close()

        conn2 = get_db_connection(db_path)
        row = conn2.execute("SELECT key, value FROM app_settings").fetchone()
        assert row["key"] == "analysis.USE_DRIBBLE_EVENTS"
        conn2.close()
    finally:
        os.unlink(db_path)


def test_generate_expanded_events_from_segments_emits_requested_event_types():
    from event_generator import generate_expanded_events_from_segments

    segments = [
        {
            "player": "1",
            "start_frame": 0,
            "end_frame": 4,
            "start_timestamp_ms": 0,
            "end_timestamp_ms": 132,
            "duration_frames": 5,
            "frames": [0, 1, 2, 3, 4],
            "player_x_start": 100,
            "player_x_end": 108,
            "player_y_median": 240.0,
            "mean_ball_distance": 20.0,
        },
        {
            "player": "2",
            "start_frame": 8,
            "end_frame": 12,
            "start_timestamp_ms": 264,
            "end_timestamp_ms": 396,
            "duration_frames": 5,
            "frames": [8, 9, 10, 11, 12],
            "player_x_start": 300,
            "player_x_end": 312,
            "player_y_median": 230.0,
            "mean_ball_distance": 18.0,
        },
        {
            "player": "3",
            "start_frame": 16,
            "end_frame": 20,
            "start_timestamp_ms": 528,
            "end_timestamp_ms": 660,
            "duration_frames": 5,
            "frames": [16, 17, 18, 19, 20],
            "player_x_start": 500,
            "player_x_end": 510,
            "player_y_median": 225.0,
            "mean_ball_distance": 17.0,
        },
        {
            "player": "4",
            "start_frame": 24,
            "end_frame": 28,
            "start_timestamp_ms": 792,
            "end_timestamp_ms": 924,
            "duration_frames": 5,
            "frames": [24, 25, 26, 27, 28],
            "player_x_start": 650,
            "player_x_end": 660,
            "player_y_median": 235.0,
            "mean_ball_distance": 19.0,
        },
        {
            "player": "5",
            "start_frame": 32,
            "end_frame": 36,
            "start_timestamp_ms": 1056,
            "end_timestamp_ms": 1188,
            "duration_frames": 5,
            "frames": [32, 33, 34, 35, 36],
            "player_x_start": 820,
            "player_x_end": 830,
            "player_y_median": 238.0,
            "mean_ball_distance": 16.0,
        },
    ]
    ball_track = pd.DataFrame(
        [
            {"frame_number": 8, "timestamp_ms": 264, "x_center": 305, "y_center": 220},
            {"frame_number": 9, "timestamp_ms": 297, "x_center": 312, "y_center": 205},
            {"frame_number": 10, "timestamp_ms": 330, "x_center": 320, "y_center": 180},
            {"frame_number": 11, "timestamp_ms": 363, "x_center": 330, "y_center": 145},
            {"frame_number": 12, "timestamp_ms": 396, "x_center": 340, "y_center": 160},
            {"frame_number": 13, "timestamp_ms": 429, "x_center": 360, "y_center": 175},
            {"frame_number": 14, "timestamp_ms": 462, "x_center": 390, "y_center": 200},
            {"frame_number": 15, "timestamp_ms": 495, "x_center": 430, "y_center": 220},
            {"frame_number": 32, "timestamp_ms": 1056, "x_center": 824, "y_center": 225},
            {"frame_number": 33, "timestamp_ms": 1089, "x_center": 832, "y_center": 200},
            {"frame_number": 34, "timestamp_ms": 1122, "x_center": 842, "y_center": 170},
            {"frame_number": 35, "timestamp_ms": 1155, "x_center": 852, "y_center": 135},
            {"frame_number": 36, "timestamp_ms": 1188, "x_center": 860, "y_center": 150},
            {"frame_number": 37, "timestamp_ms": 1221, "x_center": 868, "y_center": 165},
            {"frame_number": 38, "timestamp_ms": 1254, "x_center": 874, "y_center": 180},
        ]
    )

    events = generate_expanded_events_from_segments("game", segments, ball_track)
    event_types = {event["event_type"] for event in events}

    assert {"shot", "make", "miss", "rebound", "assist", "steal", "turnover", "block", "foul", "possession_change"} <= event_types
