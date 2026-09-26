"""Wipe film-analysis tables without touching videos."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from wipe_film_analysis import ANALYSIS_TABLES, wipe


def test_wipe_film_analysis_deletes_events_keeps_videos(tmp_path, monkeypatch):
    import sqlite3

    # the pre-wipe backup must land in tmp, never in ~/LibertyData
    monkeypatch.setenv("LIBERTY_BACKUP_DIR", str(tmp_path / "backups"))

    db_path = tmp_path / "t.db"
    db = sqlite3.connect(str(db_path))
    db.executescript(
        """
        CREATE TABLE videos (id INTEGER PRIMARY KEY, filename TEXT);
        CREATE TABLE events (id INTEGER PRIMARY KEY, game_id TEXT);
        CREATE TABLE detections (id INTEGER PRIMARY KEY, game_id TEXT);
        CREATE TABLE analysis_runs (id INTEGER PRIMARY KEY, analysis_key TEXT);
        INSERT INTO videos (filename) VALUES ('keep.mp4');
        INSERT INTO events (game_id) VALUES ('g1');
        INSERT INTO detections (game_id) VALUES ('g1');
        INSERT INTO analysis_runs (analysis_key) VALUES ('g1');
        """
    )
    db.commit()
    db.close()

    counts = wipe(db_path, apply=True)
    assert counts["events"] == 1
    db = sqlite3.connect(str(db_path))
    assert db.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    # Table still exists (rows deleted, schema untouched).
    assert db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'").fetchone()
    db.close()
    assert list((tmp_path / "backups").glob("prewipe_film_analysis_*.db"))
    assert "videos" not in ANALYSIS_TABLES
