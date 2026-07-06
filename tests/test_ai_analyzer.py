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
