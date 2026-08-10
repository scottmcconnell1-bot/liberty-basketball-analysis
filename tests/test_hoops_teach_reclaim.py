"""Per-game zombie reclaim: live launcher for game A must not block reclaim of B."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import hoops_teach_loop as teach  # noqa: E402


@pytest.fixture()
def mem_db(tmp_path, monkeypatch):
    db_path = tmp_path / "film.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE analysis_runs (
            id INTEGER PRIMARY KEY,
            analysis_key TEXT,
            status TEXT,
            progress_pct REAL,
            progress_step TEXT,
            started_at TEXT,
            completed_at TEXT,
            error_message TEXT
        );
        CREATE TABLE detections (
            game_id TEXT,
            timestamp_ms INTEGER
        );
        """
    )
    monkeypatch.setattr(teach, "DB", db_path)
    yield conn
    conn.close()


def test_extract_analysis_key_from_cmdline():
    cmd = (
        r"C:\Python\python.exe analysis_launcher.py film_analysis.db "
        r"C:\repo\uploads\hudl_x.mp4 hudl_north_star_key"
    )
    assert teach._extract_analysis_key_from_cmdline(cmd) == "hudl_north_star_key"
    assert teach._extract_analysis_key_from_cmdline("python hoops_teach_loop.py") is None


def test_reclaim_mid_detect_partial_marks_failed(mem_db, monkeypatch):
    """Incomplete detection zombie must fail (re-queue), not complete forever."""
    conn = mem_db
    conn.execute(
        """INSERT INTO analysis_runs
           (id, analysis_key, status, progress_pct, progress_step, started_at)
           VALUES (1, 'hudl_partial', 'running', 8,
                   'Detecting objects: frame 10500/122252', '2026-08-06')"""
    )
    # 60s of detections — above 50s keep gate, below full-film 20min gate
    conn.execute(
        "INSERT INTO detections (game_id, timestamp_ms) VALUES ('hudl_partial', 60000)"
    )
    conn.commit()
    monkeypatch.setattr(
        teach,
        "list_live_analysis_workers",
        lambda: {"ok": True, "any_worker": False, "keys": set(), "unkeyed_workers": 0},
    )
    n = teach._reclaim_zombie_runs_once(conn, stale_minutes=0)
    assert n == 1
    row = conn.execute(
        "SELECT status, error_message FROM analysis_runs WHERE id=1"
    ).fetchone()
    assert row[0] == "failed"
    assert "zombie" in (row[1] or "")


def test_reclaim_other_games_while_live_worker(mem_db, monkeypatch):
    conn = mem_db
    conn.execute(
        """INSERT INTO analysis_runs
           (id, analysis_key, status, progress_pct, progress_step, started_at)
           VALUES
           (1, 'hudl_marsing', 'running', 50, 'Regenerating events…', '2026-08-01 00:00:00'),
           (2, 'hudl_north_star', 'running', 2, 'Detecting objects', '2026-08-06 08:00:00')"""
    )
    # Marsing has enough detections to keep
    conn.execute(
        "INSERT INTO detections (game_id, timestamp_ms) VALUES ('hudl_marsing', 60000)"
    )
    conn.commit()

    monkeypatch.setattr(
        teach,
        "list_live_analysis_workers",
        lambda: {
            "ok": True,
            "any_worker": True,
            "keys": {"hudl_north_star"},
            "unkeyed_workers": 0,
        },
    )

    n = teach._reclaim_zombie_runs_once(conn, stale_minutes=15)
    assert n == 1
    marsing = conn.execute(
        "SELECT status, progress_step FROM analysis_runs WHERE id=1"
    ).fetchone()
    north = conn.execute(
        "SELECT status FROM analysis_runs WHERE id=2"
    ).fetchone()
    assert marsing[0] == "completed"
    assert "Reclaimed zombie" in (marsing[1] or "")
    assert north[0] == "running"


def test_reclaim_skips_when_worker_key_unknown(mem_db, monkeypatch):
    conn = mem_db
    conn.execute(
        """INSERT INTO analysis_runs
           (id, analysis_key, status, progress_pct, progress_step, started_at)
           VALUES (1, 'hudl_marsing', 'running', 50, 'Regenerating', '2026-08-01')"""
    )
    conn.commit()
    monkeypatch.setattr(
        teach,
        "list_live_analysis_workers",
        lambda: {
            "ok": True,
            "any_worker": True,
            "keys": set(),
            "unkeyed_workers": 1,
        },
    )
    n = teach._reclaim_zombie_runs_once(conn, stale_minutes=0)
    assert n == 0
    assert conn.execute("SELECT status FROM analysis_runs WHERE id=1").fetchone()[0] == "running"


def test_reclaim_all_when_no_worker(mem_db, monkeypatch):
    conn = mem_db
    conn.execute(
        """INSERT INTO analysis_runs
           (id, analysis_key, status, progress_pct, progress_step, started_at)
           VALUES (1, 'thin_key', 'running', 10, 'Detecting', '2026-08-01')"""
    )
    conn.commit()
    monkeypatch.setattr(
        teach,
        "list_live_analysis_workers",
        lambda: {"ok": True, "any_worker": False, "keys": set(), "unkeyed_workers": 0},
    )
    n = teach._reclaim_zombie_runs_once(conn, stale_minutes=0)
    assert n == 1
    row = conn.execute(
        "SELECT status, error_message FROM analysis_runs WHERE id=1"
    ).fetchone()
    assert row[0] == "failed"
    assert "zombie" in (row[1] or "")


def test_hung_wait_due_and_snap_reset():
    now = 1_000_000.0
    snap = teach.update_wait_progress_snap(
        None, key="k1", fingerprint="0|frame 1", now=now
    )
    assert snap["since"] == now
    assert not teach.hung_wait_due(
        snap, key="k1", fingerprint="0|frame 1", now=now + 100, stale_sec=45 * 60
    )
    # Same fingerprint ages → hung
    assert teach.hung_wait_due(
        snap, key="k1", fingerprint="0|frame 1", now=now + 45 * 60, stale_sec=45 * 60
    )
    # Progress advances → reset since
    snap2 = teach.update_wait_progress_snap(
        snap, key="k1", fingerprint="1|frame 2", now=now + 90
    )
    assert snap2["since"] == now + 90
    assert not teach.hung_wait_due(
        snap2, key="k1", fingerprint="1|frame 2", now=now + 200, stale_sec=45 * 60
    )


def test_restart_hung_analysis_kills_and_fails(mem_db, monkeypatch):
    conn = mem_db
    conn.execute(
        """INSERT INTO analysis_runs
           (id, analysis_key, status, progress_pct, progress_step, started_at)
           VALUES (9, 'hudl_stuck', 'running', 2, 'Detecting objects: frame 9', '2026-08-06')"""
    )
    conn.commit()
    killed = []
    monkeypatch.setattr(
        teach,
        "list_live_analysis_workers",
        lambda: {
            "ok": True,
            "any_worker": True,
            "keys": {"hudl_stuck"},
            "pid_by_key": {"hudl_stuck": 4242},
            "unkeyed_workers": 0,
            "unkeyed_pids": [],
        },
    )
    monkeypatch.setattr(teach, "kill_analysis_pids", lambda pids: killed.extend(pids) or pids)
    ok = teach.restart_hung_analysis(
        conn, run_id=9, key="hudl_stuck", fingerprint="2|Detecting", stale_sec=60
    )
    assert ok is True
    assert killed == [4242]
    row = conn.execute(
        "SELECT status, error_message FROM analysis_runs WHERE id=9"
    ).fetchone()
    assert row[0] == "failed"
    assert "hung" in (row[1] or "")


def test_games_panel_first_worst_recall():
    games = [
        (1, "f-a", "hudl_wilder_away_regular_wilder", "HUDL Wilder"),
        (2, "f-b", "hoopsalytics_idaho_city_2026-01-05", "Idaho City"),
        (3, "f-c", "hoopsalytics_harper_or_2025-12-05", "Harper"),
        (4, "f-d", "hudl_rimrock_away_regular_rimrock", "HUDL Rimrock"),
    ]
    scores = {
        "hoopsalytics_idaho_city_2026-01-05": 0.31,
        "hoopsalytics_harper_or_2025-12-05": 0.79,
    }
    ordered = teach.games_panel_first(games, fail_scores=scores)
    names = [g[3] for g in ordered]
    assert names[0] == "Idaho City"
    assert names[1] == "Harper"
    assert set(names[2:]) == {"HUDL Wilder", "HUDL Rimrock"}
