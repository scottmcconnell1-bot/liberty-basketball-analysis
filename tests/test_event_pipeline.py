"""
test_event_pipeline.py – Pure-Python tests for possession detection
and event generation logic (no pandas/scipy required).
"""
import os
import sys
import sqlite3
import tempfile
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


def test_cluster_players_spatially_without_sklearn(monkeypatch):
    import pandas as pd
    from event_generator import _cluster_players_spatially

    monkeypatch.setitem(__import__("sys").modules, "sklearn", None)

    def _fail_import(name, *args, **kwargs):
        if name == "sklearn.cluster":
            raise ImportError("No module named 'sklearn'")
        return __import__(name, *args, **kwargs)

    import builtins
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sklearn" or (fromlist and "sklearn" in str(fromlist)):
            raise ImportError("No module named 'sklearn'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    detections = pd.DataFrame([
        {"class_name": "person", "x_center": 100.0, "y_center": 200.0},
        {"class_name": "person", "x_center": 105.0, "y_center": 205.0},
        {"class_name": "person", "x_center": 500.0, "y_center": 300.0},
        {"class_name": "person", "x_center": 505.0, "y_center": 310.0},
        {"class_name": "ball", "x_center": 320.0, "y_center": 240.0},
    ])
    result = _cluster_players_spatially(detections, n_clusters=2)
    person_clusters = result.loc[result["class_name"] == "person", "cluster_id"].tolist()
    assert len(set(person_clusters)) == 2
    assert result.loc[result["class_name"] == "ball", "cluster_id"].iloc[0] == -1


def test_event_generator_connection_uses_row_factory():
    from event_generator import get_db_connection

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?)", ("ai.detector_model", "yolov8n.pt"))
        conn.commit()
        conn.close()

        conn2 = get_db_connection(db_path)
        row = conn2.execute("SELECT key, value FROM app_settings").fetchone()
        assert row["key"] == "ai.detector_model"
        conn2.close()
    finally:
        os.unlink(db_path)


def test_ball_detector_settings_default_and_custom(monkeypatch):
    import importlib
    import types

    monkeypatch.setitem(sys.modules, "cv2", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "ultralytics", types.SimpleNamespace(YOLO=object))
    monkeypatch.setitem(sys.modules, "event_generator", types.SimpleNamespace(main=lambda *args, **kwargs: None))
    sys.modules.pop("ai_analyzer", None)
    ai_analyzer = importlib.import_module("ai_analyzer")

    assert ai_analyzer.ball_detector_settings({}) == ("models/ball_detector.pt", 0, 0.25)
    assert ai_analyzer.ball_detector_settings({
        "ball_detector_model": "custom",
        "custom_ball_detector_model": "models/candidate.pt",
        "ball_class_id": "3",
        "ball_confidence": "0.42",
    }) == ("models/candidate.pt", 3, 0.42)


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
            "mean_ball_distance": 50.0,
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

    # Shot is a make (ball reaches y=145, near basket), so expect shot+make but no miss/rebound
    assert {"shot", "make", "assist", "possession_change"} <= event_types
    # Verify no miss/rebound events for this make
    assert "miss" not in event_types
    assert "rebound" not in event_types

def test_persist_events_deletes_unverified_relational_events_when_relational_game_id_provided():
    """Test that persist_events deletes unverified events matching relational_game_id or legacy NULL with matching game_id."""
    from event_generator import persist_events

    import sqlite3
    import tempfile
    import os

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE events (game_id TEXT, relational_game_id INTEGER, player TEXT, event_type TEXT, shot_result TEXT, timestamp_ms INTEGER, details_json TEXT, confidence REAL, human_verified INTEGER)")
        conn.execute("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?)", ("ai.detector_model", "yolov8n.pt"))
        # Insert test events
        # unverified, matching relational_game_id -> should be deleted
        conn.execute("INSERT INTO events (game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ("legacy-game-id", 123, "player1", "shot", None, 1000, "{}", 0.5, 0))
        # unverified, relational_game_id NULL, matching game_id -> should be deleted (legacy fallback)
        conn.execute("INSERT INTO events (game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ("legacy-game-id", None, "player2", "shot", None, 2000, "{}", 0.5, 0))
        # unverified, different relational_game_id -> should NOT be deleted
        conn.execute("INSERT INTO events (game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ("legacy-game-id", 999, "player3", "shot", None, 3000, "{}", 0.5, 0))
        # verified, matching relational_game_id -> should NOT be deleted
        conn.execute("INSERT INTO events (game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ("legacy-game-id", 123, "player4", "shot", None, 4000, "{}", 0.5, 1))
        conn.commit()

        # Call persist_events with relational_game_id=123, game_id='legacy-game-id', no new events
        persist_events(conn, "legacy-game-id", [], relational_game_id=123)
        conn.commit()

        # Check remaining events
        cur = conn.cursor()
        cur.execute("SELECT game_id, relational_game_id, human_verified FROM events ORDER BY timestamp_ms")
        rows = cur.fetchall()
        # Expect two rows: the unverified with relational_game_id=999 and the verified with relational_game_id=123
        assert len(rows) == 2
        assert rows[0] == ("legacy-game-id", 999, 0)
        assert rows[1] == ("legacy-game-id", 123, 1)
        conn.close()
    finally:
        os.unlink(db_path)


def test_persist_events_preserves_verified_events_when_relational_game_id_provided():
    """Test that persist_events preserves verified/manual events when relational_game_id is provided."""
    from event_generator import persist_events

    import sqlite3
    import tempfile
    import os

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE events (game_id TEXT, relational_game_id INTEGER, player TEXT, event_type TEXT, shot_result TEXT, timestamp_ms INTEGER, details_json TEXT, confidence REAL, human_verified INTEGER)")
        conn.execute("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?)", ("ai.detector_model", "yolov8n.pt"))
        # Insert test events
        # unverified, matching relational_game_id -> should be deleted
        conn.execute("INSERT INTO events (game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ("legacy-game-id", 123, "player1", "shot", None, 1000, "{}", 0.5, 0))
        # verified, matching relational_game_id -> should NOT be deleted
        conn.execute("INSERT INTO events (game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ("legacy-game-id", 123, "player2", "shot", None, 2000, "{}", 0.5, 1))
        # verified, relational_game_id NULL, matching game_id -> should NOT be deleted (verified overrides)
        conn.execute("INSERT INTO events (game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ("legacy-game-id", None, "player3", "shot", None, 3000, "{}", 0.5, 1))
        conn.commit()

        # Call persist_events with relational_game_id=123, game_id='legacy-game-id', no new events
        persist_events(conn, "legacy-game-id", [], relational_game_id=123)
        conn.commit()

        # Check remaining events: both verified should remain
        cur = conn.cursor()
        cur.execute("SELECT game_id, relational_game_id, human_verified FROM events ORDER BY timestamp_ms")
        rows = cur.fetchall()
        assert len(rows) == 2
        # Both should have human_verified=1
        assert all(row[2] == 1 for row in rows)
        # One with relational_game_id=123, one with NULL
        assert {row[1] for row in rows} == {None, 123}
        conn.close()
    finally:
        os.unlink(db_path)


def test_persist_events_legacy_fallback_works_when_relational_game_id_absent():
    """Test that persist_events maintains legacy behavior when relational_game_id is absent."""
    from event_generator import persist_events

    import sqlite3
    import tempfile
    import os

    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE events (game_id TEXT, relational_game_id INTEGER, player TEXT, event_type TEXT, shot_result TEXT, timestamp_ms INTEGER, details_json TEXT, confidence REAL, human_verified INTEGER)")
        conn.execute("CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        conn.execute("INSERT INTO app_settings (key, value) VALUES (?, ?)", ("ai.detector_model", "yolov8n.pt"))
        # Insert test events
        # unverified, matching game_id -> should be deleted
        conn.execute("INSERT INTO events (game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ("legacy-game-id", 123, "player1", "shot", None, 1000, "{}", 0.5, 0))
        # unverified, matching game_id but different relational_game_id -> should be deleted
        conn.execute("INSERT INTO events (game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ("legacy-game-id", 999, "player2", "shot", None, 2000, "{}", 0.5, 0))
        # unverified, NOT matching game_id -> should NOT be deleted
        conn.execute("INSERT INTO events (game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ("other-game-id", 123, "player3", "shot", None, 3000, "{}", 0.5, 0))
        # verified, matching game_id -> should NOT be deleted (verified preserved)
        conn.execute("INSERT INTO events (game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                     ("legacy-game-id", 123, "player4", "shot", None, 4000, "{}", 0.5, 1))
        conn.commit()

        # Call persist_events with relational_game_id=None (legacy), game_id='legacy-game-id', no new events
        persist_events(conn, "legacy-game-id", [], relational_game_id=None)
        conn.commit()

        # Check remaining events: unverified with other-game-id and verified legacy-game-id
        cur = conn.cursor()
        cur.execute("SELECT game_id, relational_game_id, human_verified FROM events ORDER BY timestamp_ms")
        rows = cur.fetchall()
        assert len(rows) == 2
        # One should be the other-game-id unverified
        assert any(row[0] == "other-game-id" and row[2] == 0 for row in rows)
        # One should be the verified legacy-game-id
        assert any(row[0] == "legacy-game-id" and row[2] == 1 for row in rows)
        conn.close()
    finally:
        os.unlink(db_path)


def test_classify_all_shots_uses_detection_filter(tmp_path):
    import film_analysis

    db_path = tmp_path / "shots.db"
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE events (
            id INTEGER PRIMARY KEY,
            game_id TEXT,
            player TEXT,
            event_type TEXT,
            shot_result TEXT,
            timestamp_ms INTEGER,
            details_json TEXT
        );
        CREATE TABLE detections (
            id INTEGER PRIMARY KEY,
            game_id TEXT,
            relational_game_id INTEGER,
            frame_number INTEGER,
            timestamp_ms INTEGER,
            object_class TEXT,
            x_center REAL,
            y_center REAL,
            player_cluster INTEGER
        );
        CREATE TABLE shot_classifications (
            event_id INTEGER,
            game_id TEXT,
            relational_game_id INTEGER,
            tracker_id TEXT,
            shot_type TEXT,
            shot_result TEXT,
            court_x REAL,
            court_y REAL,
            confidence REAL,
            timestamp_ms INTEGER
        );
    """)
    conn.execute(
        """INSERT INTO events (game_id, player, event_type, shot_result, timestamp_ms, details_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("game1", "3", "make", "made", 1000, '{"peak_frame": 10}'),
    )
    conn.execute(
        """INSERT INTO detections
           (game_id, frame_number, timestamp_ms, object_class, x_center, y_center, player_cluster)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("game1", 10, 1000, "person", 960, 540, 3),
    )
    conn.commit()

    results = film_analysis.classify_all_shots(conn, "game1", video_width=1920, video_height=1080)
    assert len(results) == 1
    assert results[0]["shot_type"] in {"2pt", "3pt", "ft"}
    conn.close()


def test_get_detections_matches_base_analysis_key(tmp_path):
    """Rebuild must find detections stored under base_analysis_key, not only rerun key."""
    from event_generator import get_detections, get_db_connection

    db_path = tmp_path / "detections.db"
    conn = get_db_connection(str(db_path))
    conn.execute(
        """CREATE TABLE detections (
            id INTEGER PRIMARY KEY,
            game_id TEXT,
            relational_game_id INTEGER,
            frame_number INTEGER,
            timestamp_ms INTEGER,
            object_class TEXT,
            confidence REAL,
            x_center REAL,
            y_center REAL,
            width REAL,
            height REAL,
            tracker_id INTEGER
        )"""
    )
    conn.execute(
        """INSERT INTO detections
           (game_id, relational_game_id, frame_number, timestamp_ms, object_class, confidence,
            x_center, y_center, width, height, tracker_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("nfhs_primary", None, 1, 0, "person", 0.9, 100, 200, 10, 10, 1),
    )
    conn.commit()

    narrow = get_detections(conn, "nfhs_primary__rerun_1")
    assert len(narrow) == 0

    broad = get_detections(
        conn,
        "nfhs_primary__rerun_1",
        base_analysis_key="nfhs_primary",
    )
    assert len(broad) == 1
    conn.close()


def test_event_generator_main_returns_false_when_no_detections(tmp_path):
    from event_generator import main

    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE detections (
            id INTEGER PRIMARY KEY,
            game_id TEXT,
            relational_game_id INTEGER,
            frame_number INTEGER,
            timestamp_ms INTEGER,
            object_class TEXT,
            confidence REAL,
            x_center REAL,
            y_center REAL,
            width REAL,
            height REAL,
            tracker_id INTEGER
        )"""
    )
    conn.execute(
        """CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )"""
    )
    conn.commit()
    conn.close()

    assert main("missing_game", str(db_path)) is False

