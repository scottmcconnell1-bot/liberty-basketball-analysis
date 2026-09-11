import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mark_stale_analysis_runs as msr  # noqa: E402


def _db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE analysis_runs (id INTEGER PRIMARY KEY, analysis_key TEXT, status TEXT, progress_step TEXT, started_at TEXT, completed_at TEXT, error_message TEXT)")
    return conn


def _ts(epoch):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(epoch))


def test_stale_detection_uses_age_and_log_activity(tmp_path):
    now = 1_800_000_000.0
    conn = _db(tmp_path / "t.db")
    logs = tmp_path / "logs"; logs.mkdir(exist_ok=True)  # conftest may pre-create it
    conn.executemany("INSERT INTO analysis_runs (analysis_key, status, started_at) VALUES (?,?,?)", [
        ("old_no_log", "running", _ts(now - 3 * 3600)),        # stale: old, no log
        ("old_live_log", "running", _ts(now - 3 * 3600)),      # NOT stale: log recently written
        ("old_dead_log", "pending", _ts(now - 3 * 3600)),      # stale: log idle
        ("fresh", "running", _ts(now - 60)),                   # NOT stale: just started
        ("done", "completed", _ts(now - 3 * 3600)),            # ignored
    ])
    conn.commit()
    (logs / "ai-old_live_log.log").write_text("x"); os.utime(logs / "ai-old_live_log.log", (now - 60, now - 60))
    (logs / "ai-old_dead_log.log").write_text("x"); os.utime(logs / "ai-old_dead_log.log", (now - 7200, now - 7200))
    stale = msr.find_stale(conn, logs, minutes=45, now=now)
    assert sorted(s["analysis_key"] for s in stale) == ["old_dead_log", "old_no_log"]
    assert msr.mark_failed(conn, stale, 45) == 2
    rows = dict(conn.execute("SELECT analysis_key, status FROM analysis_runs").fetchall())
    assert rows["old_no_log"] == "failed" and rows["old_dead_log"] == "failed"
    assert rows["old_live_log"] == "running" and rows["fresh"] == "running" and rows["done"] == "completed"
    assert "Marked stale" in conn.execute("SELECT error_message FROM analysis_runs WHERE analysis_key='old_no_log'").fetchone()[0]


def test_cli_dry_run_does_not_write(tmp_path, capsys):
    conn = _db(tmp_path / "t.db")
    conn.execute("INSERT INTO analysis_runs (analysis_key, status, started_at) VALUES ('k','running','2020-01-01 00:00:00')"); conn.commit(); conn.close()
    assert msr.main(["--db", str(tmp_path / "t.db"), "--logs-dir", str(tmp_path)]) == 0
    assert '"mode": "DRY RUN"' in capsys.readouterr().out
    assert sqlite3.connect(tmp_path / "t.db").execute("SELECT status FROM analysis_runs").fetchone()[0] == "running"
