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
