"""Regression tests for unattended ops scripts (teach loop, nightly save, backup, wipe, imports).

Everything runs against temp dirs / temp SQLite files. Tests marked
``xfail(strict=True, reason="BUG: ...")`` document verified defects: they fail today and
will start "XPASS"-failing (strict) once the bug is fixed, so the marker must be removed.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))

import hoops_teach_loop as teach  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _runs_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE analysis_runs (
            id INTEGER PRIMARY KEY, analysis_key TEXT, base_game_id TEXT,
            source_video_id INTEGER, status TEXT, progress_pct REAL,
            progress_step TEXT, started_at TEXT, completed_at TEXT, error_message TEXT
        );
        CREATE TABLE detections (game_id TEXT, timestamp_ms INTEGER);
        """
    )
    return conn


def _daily_save_rules():
    """Parse the unstage pathspecs and the blocklist regexes out of daily_git_save.ps1."""
    text = (SCRIPTS / "daily_git_save.ps1").read_text(encoding="utf-8")
    block = text.split("$unstage = @(", 1)[1].split(")", 1)[0]
    unstage = re.findall(r'"([^"]+)"', block)
    blocked_src = text.split("$blocked = $staged | Where-Object {", 1)[1].split("}", 1)[0]
    blocked = [re.compile(p, re.IGNORECASE) for p in re.findall(r"-match '([^']+)'", blocked_src)]
    return unstage, blocked


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=env
    ).stdout


# ---------------------------------------------------------------------------
# nightly daily_git_save.ps1 staging rules
# ---------------------------------------------------------------------------

def _simulate_daily_save(tmp_path: Path, files: dict[str, bytes]) -> list[str]:
    """Replay daily_git_save.ps1's `git add -A` + per-pattern `git reset` + blocklist."""
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    shutil.copy(ROOT / ".gitignore", repo / ".gitignore")
    for rel, data in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    unstage, blocked = _daily_save_rules()
    _git(repo, "add", "-A")
    for pattern in unstage:
        # unborn HEAD: `git rm --cached` is the equivalent of `git reset HEAD --` here
        subprocess.run(["git", "rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", pattern],
                       cwd=repo, check=False, capture_output=True)
    staged = [s for s in _git(repo, "diff", "--cached", "--name-only").splitlines() if s]
    assert not [s for s in staged if any(r.search(s) for r in blocked)], "blocklist would abort"
    return staged


def test_daily_save_unstages_known_runtime_files(tmp_path):
    staged = _simulate_daily_save(
        tmp_path,
        {
            "app.py": b"print(1)\n",
            "film_analysis.db": b"SQLite",
            "backup/film_analysis_20260101.db": b"SQLite",
            ".env": b"SECRET=1\n",
            "uploads/game.mp4": b"\x00",
            "data/hoopsalytics/teach_loop_state.json": b"{}",
            "data/hoopsalytics/daily_git_save.log": b"log",
        },
    )
    assert staged == [".gitignore", "app.py"]


@pytest.mark.xfail(strict=True, reason="BUG: `git add -A` + denylist stages logs/browser data/scratch files "
                   "outside data/hoopsalytics (seen in history: tag-exports/_chrome_ls_q2/*.ldb, "
                   "data/flask_8080_restart*.log, _tmp_*.png)")
def test_daily_save_does_not_stage_runtime_junk(tmp_path):
    junk = {
        "data/flask_8080_restart.err.log": b"Traceback...",
        "tag-exports/_chrome_ls_q2/001297.ldb": b"\x00leveldb",
        "tag-exports/_chrome_ls_q2/LOG": b"leveldb log",
        "_tmp_game_page32_overlay.png": b"\x89PNG",
        "data/hudl/import_summary.json": b"{}",
    }
    staged = _simulate_daily_save(tmp_path, {"app.py": b"x\n", **junk})
    leaked = sorted(set(staged) & set(junk))
    assert leaked == []


# ---------------------------------------------------------------------------
# teach loop: process-probe failure must not reclaim a live run
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="BUG: list_live_analysis_workers() failure (timeout/non-zero) is "
                   "treated as 'no worker'; reclaim_zombie_runs then fails/completes a LIVE run")
def test_probe_failure_does_not_reclaim_live_run(tmp_path, monkeypatch):
    conn = _runs_db(tmp_path / "film.db")
    conn.execute(
        "INSERT INTO analysis_runs (id, analysis_key, status, progress_pct, progress_step, started_at)"
        " VALUES (1, 'hoopsalytics_melba_2025-12-09', 'running', 40, 'Detecting frame 9000', "
        " datetime('now','-30 minutes'))"
    )
    conn.commit()

    def _boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=20)

    monkeypatch.setattr(teach.subprocess, "run", _boom)
    assert teach.list_live_analysis_workers()["ok"] is False  # probe says "unknown"
    teach.reclaim_zombie_runs(conn, stale_minutes=0)  # what main() does at line 790
    status = conn.execute("SELECT status FROM analysis_runs WHERE id=1").fetchone()[0]
    assert status == "running"


# ---------------------------------------------------------------------------
# teach loop: failed teach/compare must not be recorded as taught with a stale score
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="BUG: teach_and_score ignores subprocess exit codes, reuses a stale "
                   "compare_*.json and adds the key to taught_keys so it is never retried")
def test_failed_teach_is_not_marked_taught(tmp_path, monkeypatch):
    db = tmp_path / "film.db"
    _runs_db(db).close()
    hoops = tmp_path / "data" / "hoopsalytics"
    hoops.mkdir(parents=True)
    film = "hoopsalytics-melba-2025-12-09"
    (hoops / f"compare_{film.replace('-', '_')}.json").write_text(
        json.dumps({"precision": 0.99, "recall": 0.99, "stale": True}), encoding="utf-8"
    )
    monkeypatch.setattr(teach, "ROOT", tmp_path)
    monkeypatch.setattr(teach, "DB", db)
    monkeypatch.setattr(teach, "STATE_PATH", hoops / "teach_loop_state.json")
    monkeypatch.setattr(teach, "PANEL_SCRIPT", tmp_path / "scripts" / "score_full_film_panel.py")
    monkeypatch.setattr(teach, "run", lambda cmd: 1)  # every child script crashes
    state = {"taught_keys": [], "scores": []}
    teach.teach_and_score("hoopsalytics_melba_2025-12-09", film, "Melba", state)
    assert "hoopsalytics_melba_2025-12-09" not in state["taught_keys"]
    assert not state["scores"][-1].get("stale")


def test_panel_rank_puts_worst_panel_game_first():
    games = [(1, "f", "hudl_a", "A"), (2, "f", "hoopsalytics_melba_2025-12-09", "Melba"),
             (3, "f", "hoopsalytics_nyssa_2025-12-04", "Nyssa")]
    out = teach.games_panel_first(games, fail_scores={"hoopsalytics_melba_2025-12-09": 0.2,
                                                      "hoopsalytics_nyssa_2025-12-04": 0.6})
    assert [g[3] for g in out] == ["Melba", "Nyssa", "A"]


@pytest.mark.xfail(strict=True, reason="BUG: needs_full has no retry cap; a game whose analysis always fails "
                   "(missing video) or whose film is short (Idaho City rule) is re-queued forever and, "
                   "being first in panel order, starves every later game")
def test_needs_full_gives_up_after_repeated_failures(tmp_path):
    conn = _runs_db(tmp_path / "film.db")
    gid = "hoopsalytics_melba_2025-12-09"
    for i in range(1, 11):
        conn.execute(
            "INSERT INTO analysis_runs (id, analysis_key, source_video_id, status, error_message)"
            " VALUES (?, ?, 12, 'failed', 'Video file not found')",
            (i, gid),
        )
    # Idaho City film genuinely only ~9 min long, analysis completed
    conn.execute(
        "INSERT INTO analysis_runs (id, analysis_key, source_video_id, status)"
        " VALUES (99, 'hoopsalytics_idaho_city_2026-01-05', 20, 'completed')"
    )
    conn.execute("INSERT INTO detections VALUES ('hoopsalytics_idaho_city_2026-01-05', 540000)")
    conn.commit()
    assert teach.needs_full(conn, 12, gid) is False
    assert teach.needs_full(conn, 20, "hoopsalytics_idaho_city_2026-01-05") is False


@pytest.mark.xfail(strict=True, reason="BUG: load_state() has no recovery for a truncated/corrupt state file "
                   "(non-atomic save_state); main() then crashes on every watchdog restart")
def test_corrupt_state_file_does_not_crash(tmp_path, monkeypatch):
    p = tmp_path / "teach_loop_state.json"
    p.write_text('{"taught_keys": ["hoopsalytics_mel', encoding="utf-8")
    monkeypatch.setattr(teach, "STATE_PATH", p)
    state = teach.load_state()
    assert isinstance(state, dict)


# ---------------------------------------------------------------------------
# box-score model: HUDL caps survive a teach_from_boxscore --write-model
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="BUG: teach_from_boxscore --write-model rebuilds the model from "
                   "data/hoopsalytics only, erasing HUDL caps merged by import_hudl (teach loop runs it after "
                   "every HUDL game)")
def test_hudl_caps_survive_boxscore_teach(tmp_path, monkeypatch):
    import boxscore_constraints as bc
    import import_hudl
    import teach_from_boxscore

    model = tmp_path / "boxscore_event_calibrator.json"
    for mod in (bc, import_hudl, teach_from_boxscore):
        monkeypatch.setattr(mod, "DEFAULT_BOXSCORE_MODEL", model)
    monkeypatch.setattr(bc, "_MODEL_CACHE", None)
    monkeypatch.setattr(teach_from_boxscore, "REPORT_PATH", tmp_path / "report.json")
    import_hudl.merge_boxscore_model({"hudl_marsing_away_regular_marsing": {"team": {"points": 51}}})
    assert "hudl_marsing_away_regular_marsing" in json.loads(model.read_text())["boxscore_by_game"]

    empty_hoops = tmp_path / "hoops"
    empty_hoops.mkdir()
    monkeypatch.setattr(sys, "argv", ["teach_from_boxscore.py", "--write-model",
                                      "--hoops-dir", str(empty_hoops)])
    teach_from_boxscore.main()
    assert "hudl_marsing_away_regular_marsing" in json.loads(model.read_text())["boxscore_by_game"]


# ---------------------------------------------------------------------------
# teach_from_hoops_pbp trains on the key the loop just analysed
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="BUG: build_multi_game_calibrator always prefers the primary key when it "
                   "has any events, ignoring a newer full-film __rerun_ key the teach loop just completed")
def test_pbp_teach_uses_newest_rerun(tmp_path, monkeypatch):
    import teach_from_hoops_pbp as pbp

    base = "hoopsalytics_grace_2026-01-10"
    rerun = base + "__rerun_20260915_193718"
    requested: list[str] = []
    monkeypatch.setattr(pbp, "_discover_ai_keys", lambda conn: {base: [base, rerun]})
    monkeypatch.setattr(pbp, "load_truth_rows", lambda conn, film_id: [{"eventtype": "2PT", "start": "0:10"}])

    def _ai(conn, key):
        requested.append(key)
        return []

    monkeypatch.setattr(pbp, "load_ai_events", _ai)
    with pytest.raises(SystemExit):
        pbp.build_multi_game_calibrator(tmp_path / "x.db",
                                        games=[(19, "hoopsalytics-grace-2026-01-10", base)])
    assert requested == [rerun]


# ---------------------------------------------------------------------------
# backup / archive / wipe DB targeting
# ---------------------------------------------------------------------------

def _py_eval(code: str, env: dict) -> str:
    return subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env={**os.environ, **env},
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.mark.xfail(strict=True, reason="BUG: app reads LIBERTY_DATABASE but backup/archive (LIBERTY_DB_PATH) and "
                   "wipe/teach/import (hard-coded ROOT/film_analysis.db) ignore it")
def test_ops_scripts_follow_app_database_setting(tmp_path):
    live = str((tmp_path / "live.db").resolve())
    code = (
        "import sys; sys.path[:0]=['scripts','.']\n"
        "import liberty_data_paths, wipe_film_analysis, hoops_teach_loop\n"
        "print(liberty_data_paths.LIVE_DB); print(wipe_film_analysis.DEFAULT_DB); print(hoops_teach_loop.DB)"
    )
    out = _py_eval(code, {"LIBERTY_DATABASE": live}).splitlines()
    assert out == [live, live, live]


def test_backup_is_consistent_with_uncheckpointed_wal(tmp_path, monkeypatch):
    import backup_db

    live = tmp_path / "live.db"
    writer = sqlite3.connect(str(live))
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("PRAGMA wal_autocheckpoint=0")
    writer.execute("CREATE TABLE t(x)")
    writer.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(500)])
    writer.commit()  # rows live only in -wal; writer keeps connection open
    out = tmp_path / "backups"
    monkeypatch.setattr(sys, "argv", ["backup_db.py", "--db", str(live), "--out-dir", str(out)])
    monkeypatch.setenv("LIBERTY_DATA_ROOT", str(tmp_path / "ld"))
    assert backup_db.main() == 0
    (snap,) = out.glob("film_analysis_*.db")
    assert sqlite3.connect(str(snap)).execute("SELECT COUNT(*) FROM t").fetchone()[0] == 500
    writer.close()


@pytest.mark.xfail(strict=True, reason="BUG: `file:{path}?mode=ro` URI is not escaped; a '#' in the path "
                   "truncates it, silently opens/creates an EMPTY db and backs that up (then prunes good backups)")
def test_backup_handles_hash_in_path(tmp_path, monkeypatch):
    import backup_db

    folder = tmp_path / "Liberty #2"
    folder.mkdir()
    live = folder / "film_analysis.db"
    c = sqlite3.connect(str(live))
    c.execute("CREATE TABLE t(x)")
    c.execute("INSERT INTO t VALUES (1)")
    c.commit()
    c.close()
    out = tmp_path / "backups"
    monkeypatch.setattr(sys, "argv", ["backup_db.py", "--db", str(live), "--out-dir", str(out)])
    monkeypatch.setenv("LIBERTY_DATA_ROOT", str(tmp_path / "ld"))
    rc = backup_db.main()
    snaps = list(out.glob("film_analysis_*.db"))
    ok = rc == 0 and snaps and sqlite3.connect(str(snaps[0])).execute(
        "SELECT name FROM sqlite_master WHERE name='t'").fetchone()
    assert ok, "backup of a path containing '#' must contain the live tables (or fail loudly)"


@pytest.mark.xfail(strict=True, reason="BUG: wipe_film_analysis drops coach-authored rows (manual/human-verified "
                   "events, human_corrections, practice playlists) with no backup")
def test_wipe_keeps_coach_authored_rows(tmp_path):
    import wipe_film_analysis as wipe

    db = tmp_path / "film.db"
    c = sqlite3.connect(str(db))
    c.executescript((ROOT / "schema.sql").read_text(encoding="utf-8-sig"))
    ev_cols = {r[1] for r in c.execute("PRAGMA table_info(events)")}
    assert "game_id" in ev_cols
    c.execute("INSERT INTO human_corrections (game_id, correction_type, corrected_value, field_changed)"
              " VALUES ('g1', 'add_event', '2PT make #12', 'event')")
    c.commit()
    c.close()
    wipe.wipe(db, apply=True)
    c = sqlite3.connect(str(db))
    assert c.execute("SELECT COUNT(*) FROM human_corrections").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# HUDL import / LFS materialize
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="BUG: stored filename slug collides ('@ Marsing.mp4' vs 'Marsing.mp4', "
                   "'vs Kamiah' vs 'vs. Kamiah'); second import unlinks/overwrites the first upload and "
                   "upsert_video rewrites the first video's row")
def test_hudl_stored_filenames_unique(tmp_path):
    import import_hudl

    for name in ("@ Marsing.mp4", "Marsing.mp4", "vs Kamiah.mp4", "vs. Kamiah.mp4"):
        (tmp_path / name).write_bytes(b"x" * len(name))
    disc = import_hudl.discover(tmp_path)
    stored = [f"hudl_{import_hudl._slug(p['video']['raw'])}.mp4" for p in disc["paired"]]
    game_ids = [p["game_id"] for p in disc["paired"]]
    assert len(set(stored)) == len(stored)
    assert len(set(game_ids)) == len(game_ids)


@pytest.mark.xfail(strict=True, reason="BUG: _parse_pointer reads a real binary .pt as UTF-8 and raises "
                   "UnicodeDecodeError instead of reporting 'already materialized'")
def test_materialize_accepts_real_weights(tmp_path, monkeypatch):
    import materialize_lfs_models as mat

    monkeypatch.setattr(mat, "ROOT", tmp_path)
    weights = tmp_path / "models" / "player_detector.pt"
    weights.parent.mkdir()
    weights.write_bytes(b"PK\x03\x04" + bytes(range(256)) * 100)
    ok, msg = mat.materialize_model(weights, fetch=False)
    assert ok and "already materialized" in msg
