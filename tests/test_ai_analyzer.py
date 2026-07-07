import os
import sqlite3

import pytest


def test_resolve_relational_game_id_from_analysis_run(app, tmp_path):
    from helpers import resolve_relational_game_id_for_analysis

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE games (id INTEGER PRIMARY KEY, source_type TEXT, source_key TEXT, nfhs_game_id TEXT, nfhs_url TEXT)"
    )
    conn.execute(
        "CREATE TABLE videos (id INTEGER PRIMARY KEY, game_id TEXT, relational_game_id INTEGER, file_path TEXT)"
    )
    conn.execute(
        """CREATE TABLE analysis_runs (
            id INTEGER PRIMARY KEY,
            game_id INTEGER,
            analysis_key TEXT,
            source_video_id INTEGER,
            video_path TEXT,
            status TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO games (id, source_type, source_key) VALUES (7, 'nfhs_vod', 'uploads/nfhs_gam1.mp4')"
    )
    conn.execute(
        "INSERT INTO videos (id, game_id, relational_game_id, file_path) VALUES (1, 'nfhs_gam1_20260101', 7, 'uploads/nfhs_gam1.mp4')"
    )
    conn.execute(
        "INSERT INTO analysis_runs (game_id, analysis_key, source_video_id, video_path, status) VALUES (7, 'nfhs_gam1_20260101', 1, 'uploads/nfhs_gam1.mp4', 'pending')"
    )
    conn.commit()
    conn.close()

    assert resolve_relational_game_id_for_analysis(str(db_path), "nfhs_gam1_20260101") == 7


def test_run_ai_analysis_raises_when_video_missing(tmp_path):
    pytest.importorskip("cv2")
    from ai_analyzer import run_ai_analysis

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE games (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    with pytest.raises(RuntimeError, match="Could not open video file"):
        run_ai_analysis(str(db_path), str(tmp_path / "missing.mp4"), "nfhs_gam1_20260101")


def test_validate_video_for_analysis_rejects_missing_file():
    from helpers import validate_video_for_analysis

    ok, message = validate_video_for_analysis("/tmp/does-not-exist-liberty-test.mp4")
    assert ok is False
    assert "not found" in (message or "").lower()


def test_validate_model_weights_rejects_git_lfs_pointer(tmp_path):
    from helpers import validate_model_weights

    pointer = tmp_path / "models" / "ball_detector.pt"
    pointer.parent.mkdir(parents=True)
    pointer.write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 123\n",
        encoding="utf-8",
    )
    ok, message = validate_model_weights(str(pointer))
    assert ok is False
    assert "git lfs" in (message or "").lower()


def test_reconcile_stuck_analysis_run_marks_failed_on_traceback(app, tmp_path):
    from helpers import ai_analysis_log_path, reconcile_stuck_analysis_run

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE analysis_runs (
            id INTEGER PRIMARY KEY,
            analysis_key TEXT,
            status TEXT,
            error_message TEXT,
            progress_step TEXT,
            progress_pct REAL,
            completed_at TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO analysis_runs (analysis_key, status) VALUES (?, 'pending')",
        ("nfhs_gam1_trim_20260101",),
    )
    conn.commit()
    conn.close()

    log_path = ai_analysis_log_path("nfhs_gam1_trim_20260101")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write("[launcher] Started\nTraceback\nModuleNotFoundError: No module named 'cv2'\n")

    conn = sqlite3.connect(db_path)
    reconcile_stuck_analysis_run(conn, "nfhs_gam1_trim_20260101")
    row = conn.execute("SELECT status, error_message FROM analysis_runs").fetchone()
    assert row[0] == "failed"
    assert "cv2" in row[1]


def test_reconcile_stuck_running_run_marks_failed_on_sklearn_error(app, tmp_path):
    from helpers import ai_analysis_log_path, reconcile_stuck_analysis_run

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE analysis_runs (
            id INTEGER PRIMARY KEY,
            analysis_key TEXT,
            status TEXT,
            error_message TEXT,
            progress_step TEXT,
            progress_pct REAL,
            completed_at TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO analysis_runs (analysis_key, status, progress_step) VALUES (?, 'running', 'Regenerating events…')",
        ("nfhs_gam30_running",),
    )
    conn.commit()
    conn.close()

    log_path = ai_analysis_log_path("nfhs_gam30_running")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write("INFO: Clustering players spatially...\n")
        handle.write("ERROR: An error occurred in event_generator: No module named 'sklearn'\n")

    conn = sqlite3.connect(db_path)
    reconcile_stuck_analysis_run(conn, "nfhs_gam30_running")
    row = conn.execute("SELECT status, error_message FROM analysis_runs").fetchone()
    assert row[0] == "failed"
    assert "Rebuild" in row[1]


def test_reconcile_stuck_running_run_marks_completed_from_log(app, tmp_path):
    from helpers import ai_analysis_log_path, reconcile_stuck_analysis_run

    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE analysis_runs (
            id INTEGER PRIMARY KEY,
            analysis_key TEXT,
            status TEXT,
            error_message TEXT,
            progress_step TEXT,
            progress_pct REAL,
            completed_at TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO analysis_runs (analysis_key, status, progress_step) VALUES (?, 'running', 'Regenerating events…')",
        ("nfhs_gam30_done",),
    )
    conn.commit()
    conn.close()

    log_path = ai_analysis_log_path("nfhs_gam30_done")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write("[AI] analysis_runs updated to 'completed' for nfhs_gam30_done\n")

    conn = sqlite3.connect(db_path)
    reconcile_stuck_analysis_run(conn, "nfhs_gam30_done")
    row = conn.execute("SELECT status, progress_step FROM analysis_runs").fetchone()
    assert row[0] == "completed"
    assert row[1] == "Done"


def test_analysis_runs_has_progress_columns(db):
    cols = {row[1] for row in db.execute("PRAGMA table_info(analysis_runs)").fetchall()}
    assert "progress_pct" in cols
    assert "progress_step" in cols


def test_resolve_analysis_run_for_progress_follows_replacement(db):
    from helpers import resolve_analysis_run_for_progress

    db.execute(
        """INSERT INTO analysis_runs
           (analysis_key, video_path, status, error_message)
           VALUES (?, ?, ?, ?)""",
        ("old_rerun", "uploads/game.mp4", "failed", "Previous pending run never started; replaced by new request"),
    )
    db.execute(
        """INSERT INTO analysis_runs
           (analysis_key, video_path, status, base_analysis_key)
           VALUES (?, ?, ?, ?)""",
        ("new_rerun", "uploads/game.mp4", "pending", "game_primary"),
    )
    db.commit()

    row = resolve_analysis_run_for_progress(db, "old_rerun")
    assert row["analysis_key"] == "new_rerun"
    assert row["status"] == "pending"
