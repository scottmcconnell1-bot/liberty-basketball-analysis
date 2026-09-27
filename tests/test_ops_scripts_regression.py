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


def _daily_save_blocklist():
    """The belt-and-braces secret regexes daily_git_save.ps1 still checks after staging."""
    text = (SCRIPTS / "daily_git_save.ps1").read_text(encoding="utf-8")
    blocked_src = text.split("$blocked = $staged | Where-Object {", 1)[1].split("}", 1)[0]
    return [re.compile(p, re.IGNORECASE) for p in re.findall(r"-match '([^']+)'", blocked_src)]


def _git(repo: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=env
    ).stdout


# ---------------------------------------------------------------------------
# nightly daily_git_save.ps1 staging rules (allowlist via scripts/git_save_select.py)
# ---------------------------------------------------------------------------

def _temp_repo(tmp_path: Path, committed: dict[str, bytes] | None = None) -> Path:
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    repo = tmp_path / "repo dir, #1"  # Windows-style awkward path: space, comma, '#'
    repo.mkdir()
    _git(repo, "init", "-q")
    shutil.copy(ROOT / ".gitignore", repo / ".gitignore")
    for rel, data in (committed or {}).items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "base")
    return repo


def _run_daily_save_staging(repo: Path, files: dict[str, bytes | None]) -> list[str]:
    """Replay daily_git_save.ps1's staging exactly: reset, run the real helper, add its paths."""
    for rel, data in files.items():
        p = repo / rel
        if data is None:
            p.unlink()
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    _git(repo, "reset", "-q")
    path_file = repo.parent / "pathspec.bin"
    subprocess.run([sys.executable, str(SCRIPTS / "git_save_select.py"), "--repo", str(repo),
                    "--out", str(path_file)], check=True, capture_output=True, text=True)
    if path_file.stat().st_size:
        _git(repo, "--literal-pathspecs", "add", f"--pathspec-from-file={path_file}", "--pathspec-file-nul")
    staged = [s for s in _git(repo, "-c", "core.quotepath=off", "diff", "--cached", "--no-renames", "--name-only")
              .splitlines() if s]
    blocked = _daily_save_blocklist()
    assert not [s for s in staged if any(r.search(s) for r in blocked)], "blocklist would abort"
    return staged


def test_daily_save_unstages_known_runtime_files(tmp_path):
    repo = _temp_repo(tmp_path)
    staged = _run_daily_save_staging(
        repo,
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
    assert staged == ["app.py"]


def test_daily_save_does_not_stage_runtime_junk(tmp_path):
    """Fixed: allowlist instead of `git add -A` + denylist."""
    junk = {
        "data/flask_8080_restart.err.log": b"Traceback...",
        "tag-exports/_chrome_ls_q2/001297.ldb": b"\x00leveldb",
        "tag-exports/_chrome_ls_q2/LOG": b"leveldb log",
        "_tmp_game_page32_overlay.png": b"\x89PNG",
        "data/hudl/import_summary.json": b"{}",
        "test_output.txt.log": b"pytest",
        "scripts/backup.log": b"log",
        "models/new_weights.pt": b"\x00" * 10,
        "models/scratch_calibrator.json": b"{}",  # untracked model file: not auto-added
        "static/big.png": b"\x00" * 1_500_000,  # over the size cap
        ".env.production": b"SECRET=2",
    }
    repo = _temp_repo(tmp_path, {"models/boxscore_event_calibrator.json": b"{}"})
    staged = _run_daily_save_staging(repo, {"app.py": b"x\n", **junk})
    assert sorted(set(staged) & set(junk)) == []
    assert staged == ["app.py"]


def test_daily_save_stages_source_docs_and_learning_status(tmp_path):
    repo = _temp_repo(tmp_path, {
        "scripts/old name.py": b"# old\n",
        "blueprints/core.py": b"x = 1\n",
        "docs/obsolete.md": b"bye\n",
        "models/boxscore_event_calibrator.json": b"{}",
        "data/hoopsalytics/full_film_panel_targets.json": b"{}",
    })
    _git(repo, "mv", "scripts/old name.py", "scripts/new, name #2.py")  # pre-staged rename
    staged = _run_daily_save_staging(repo, {
        "blueprints/core.py": b"x = 2\n",
        "docs/obsolete.md": None,  # deletion of a tracked doc
        "docs/LEARNING_STATUS.md": b"# status\n",
        "templates/new page.html": b"<p>",
        "static/css/site.css": b"a{}",
        "tests/test_new.py": b"def test(): pass\n",
        "tag-exports/manual_vs_ai_q1_compare.py": b"# lib\n",
        "models/boxscore_event_calibrator.json": b'{"caps": 1}',  # tracked learned config
        "data/hoopsalytics/full_film_panel_targets.json": b'{"x": 1}',
        "requirements.txt": b"flask\n",
    })
    assert staged == sorted([
        "blueprints/core.py", "docs/LEARNING_STATUS.md", "docs/obsolete.md",
        "data/hoopsalytics/full_film_panel_targets.json",
        "models/boxscore_event_calibrator.json", "requirements.txt",
        "scripts/new, name #2.py", "scripts/old name.py", "static/css/site.css",
        "tag-exports/manual_vs_ai_q1_compare.py", "templates/new page.html", "tests/test_new.py",
    ])
    status = _git(repo, "-c", "core.quotepath=off", "status", "--porcelain")
    assert "D  docs/obsolete.md" in status


def test_daily_save_script_uses_allowlist_helper():
    text = (SCRIPTS / "daily_git_save.ps1").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("#"))
    assert '"add", "-A"' not in code and "add -A" not in code
    assert "git_save_select.py" in code
    assert '"--literal-pathspecs", "add", "--pathspec-from-file=$pathFile", "--pathspec-file-nul"' in code
    assert code.index('Invoke-Git @("reset", "-q")') < code.index("git_save_select.py")


def test_gitignore_covers_chrome_profile_copy():
    rules = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "tag-exports/_chrome*/" in rules


# ---------------------------------------------------------------------------
# teach loop: process-probe failure must not reclaim a live run
# ---------------------------------------------------------------------------

def _running_row(conn):
    conn.execute(
        "INSERT INTO analysis_runs (id, analysis_key, status, progress_pct, progress_step, started_at)"
        " VALUES (1, 'hoopsalytics_melba_2025-12-09', 'running', 40, 'Detecting frame 9000', "
        " datetime('now','-30 minutes'))"
    )
    conn.commit()


def test_probe_failure_does_not_reclaim_live_run(tmp_path, monkeypatch):
    conn = _runs_db(tmp_path / "film.db")
    _running_row(conn)

    def _boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=20)

    monkeypatch.setattr(teach.subprocess, "run", _boom)
    assert teach.list_live_analysis_workers()["ok"] is False  # probe says "unknown"
    assert teach.analysis_worker_alive() is True  # unknown is treated as alive
    teach.reclaim_zombie_runs(conn, stale_minutes=0)  # what main() does when no worker is seen
    teach.recover_interrupted_runs(conn)  # startup path
    assert teach.restart_hung_analysis(conn, run_id=1, key="hoopsalytics_melba_2025-12-09",
                                       fingerprint="40|x", stale_sec=1) is False
    status = conn.execute("SELECT status FROM analysis_runs WHERE id=1").fetchone()[0]
    assert status == "running"


def test_probe_nonzero_exit_is_unknown_but_success_still_reclaims(tmp_path, monkeypatch):
    conn = _runs_db(tmp_path / "film.db")
    _running_row(conn)
    result = {"rc": 1}

    def _run(cmd, **k):  # PowerShell/CIM error: exit 1, no output
        return subprocess.CompletedProcess(cmd, result["rc"], "", "Get-CimInstance : Access denied")

    monkeypatch.setattr(teach.subprocess, "run", _run)
    assert teach.list_live_analysis_workers()["ok"] is False
    teach.reclaim_zombie_runs(conn, stale_minutes=0)
    assert conn.execute("SELECT status FROM analysis_runs WHERE id=1").fetchone()[0] == "running"
    # a SUCCESSFUL probe that sees no worker still reclaims the zombie (behaviour kept)
    result["rc"] = 0
    assert teach.list_live_analysis_workers()["ok"] is True
    teach.reclaim_zombie_runs(conn, stale_minutes=0)
    assert conn.execute("SELECT status FROM analysis_runs WHERE id=1").fetchone()[0] == "failed"


# ---------------------------------------------------------------------------
# teach loop: failed teach/compare must not be recorded as taught with a stale score
# ---------------------------------------------------------------------------

def _teach_env(tmp_path, monkeypatch):
    db = tmp_path / "film.db"
    c = _runs_db(db)
    c.execute("INSERT INTO detections VALUES ('hoopsalytics_melba_2025-12-09', 900000)")
    c.commit()
    c.close()
    hoops = tmp_path / "data" / "hoopsalytics"
    hoops.mkdir(parents=True)
    film = "hoopsalytics-melba-2025-12-09"
    stale = hoops / f"compare_{film.replace('-', '_')}.json"
    stale.write_text(json.dumps({"analysis_key": "hoopsalytics_melba_2025-12-09__rerun_OLD",
                                 "precision": 0.99, "recall": 0.99, "stale": True}), encoding="utf-8")
    monkeypatch.setattr(teach, "ROOT", tmp_path)
    monkeypatch.setattr(teach, "DB", db)
    monkeypatch.setattr(teach, "STATE_PATH", hoops / "teach_loop_state.json")
    monkeypatch.setattr(teach, "PANEL_SCRIPT", tmp_path / "scripts" / "score_full_film_panel.py")
    return film, stale


def test_failed_teach_is_not_marked_taught(tmp_path, monkeypatch):
    film, _ = _teach_env(tmp_path, monkeypatch)
    monkeypatch.setattr(teach, "run", lambda cmd: 1)  # every child script crashes
    state = {"taught_keys": [], "scores": []}
    assert teach.teach_and_score("hoopsalytics_melba_2025-12-09", film, "Melba", state) is False
    assert "hoopsalytics_melba_2025-12-09" not in state["taught_keys"]
    assert not state["scores"][-1].get("stale")
    assert state["scores"][-1]["ok"] is False
    assert state["teach_failures"] == {"hoopsalytics_melba_2025-12-09": 1}
    # persisted, so a watchdog restart does not forget the failure count
    assert json.loads(teach.STATE_PATH.read_text())["teach_failures"] == state["teach_failures"]


def test_failed_compare_does_not_reuse_stale_scorecard(tmp_path, monkeypatch):
    film, _ = _teach_env(tmp_path, monkeypatch)
    # teach + regenerate succeed; only the compare crashes (e.g. DB locked)
    monkeypatch.setattr(teach, "run", lambda cmd: 1 if "compare_ai_to_hoops_pbp.py" in " ".join(cmd) else 0)
    state = {"taught_keys": [], "scores": []}
    assert teach.teach_and_score("hoopsalytics_melba_2025-12-09", film, "Melba", state) is False
    assert "hoopsalytics_melba_2025-12-09" not in state["taught_keys"]
    assert state["scores"][-1].get("precision") is None


def test_successful_teach_is_marked_taught_with_fresh_score(tmp_path, monkeypatch):
    film, stale = _teach_env(tmp_path, monkeypatch)
    key = "hoopsalytics_melba_2025-12-09"

    def _run(cmd):
        if "compare_ai_to_hoops_pbp.py" in " ".join(cmd):
            stale.write_text(json.dumps({"analysis_key": key, "precision": 0.5, "recall": 0.4}))
        return 0

    monkeypatch.setattr(teach, "run", _run)
    state = {"taught_keys": [], "scores": [], "teach_failures": {key: 2}}
    assert teach.teach_and_score(key, film, "Melba", state) is True
    assert key in state["taught_keys"]
    assert state["scores"][-1]["precision"] == 0.5
    assert state["teach_failures"] == {}


def test_teach_retry_is_capped():
    state = {"teach_failures": {"k": teach.MAX_TEACH_FAILURES - 1}}
    assert not teach.teach_given_up(state, "k")
    state["teach_failures"]["k"] += 1
    assert teach.teach_given_up(state, "k")


def test_panel_rank_puts_worst_panel_game_first():
    games = [(1, "f", "hudl_a", "A"), (2, "f", "hoopsalytics_melba_2025-12-09", "Melba"),
             (3, "f", "hoopsalytics_nyssa_2025-12-04", "Nyssa")]
    out = teach.games_panel_first(games, fail_scores={"hoopsalytics_melba_2025-12-09": 0.2,
                                                      "hoopsalytics_nyssa_2025-12-04": 0.6})
    assert [g[3] for g in out] == ["Melba", "Nyssa", "A"]


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


def test_needs_full_still_retries_below_the_cap(tmp_path):
    conn = _runs_db(tmp_path / "film.db")
    gid = "hoopsalytics_melba_2025-12-09"
    conn.execute("INSERT INTO analysis_runs (id, analysis_key, source_video_id, status)"
                 " VALUES (1, ?, 12, 'completed')", (gid,))
    for i in range(2, 2 + teach.MAX_ANALYZE_FAILURES - 1):
        conn.execute("INSERT INTO analysis_runs (id, analysis_key, source_video_id, status)"
                     " VALUES (?, ?, 12, 'failed')", (i, gid))
    conn.commit()
    assert teach.needs_full(conn, 12, gid) is True  # under the cap: try again
    conn.execute("INSERT INTO analysis_runs (id, analysis_key, source_video_id, status)"
                 " VALUES (50, ?, 12, 'failed')", (gid,))
    conn.commit()
    assert teach.needs_full(conn, 12, gid) is False  # cap reached
    # never-analysed game is still queued; an Idaho City run that failed is retried
    assert teach.needs_full(conn, 17, "hoopsalytics_marsing_2025-12-02") is True
    conn.execute("INSERT INTO analysis_runs (id, analysis_key, source_video_id, status)"
                 " VALUES (60, 'hoopsalytics_idaho_city_2026-01-05', 20, 'failed')")
    conn.commit()
    assert teach.needs_full(conn, 20, "hoopsalytics_idaho_city_2026-01-05") is True


def test_corrupt_state_file_does_not_crash(tmp_path, monkeypatch):
    p = tmp_path / "teach_loop_state.json"
    p.write_text('{"taught_keys": ["hoopsalytics_mel', encoding="utf-8")
    monkeypatch.setattr(teach, "STATE_PATH", p)
    state = teach.load_state()
    assert state == {"taught_keys": [], "scores": []}
    # the unreadable file is kept aside for the owner, not silently destroyed
    (aside,) = tmp_path.glob("teach_loop_state.json.corrupt-*")
    assert aside.read_text(encoding="utf-8").startswith('{"taught_keys"')
    # and save_state is atomic: no temp files left, content round-trips
    teach.save_state({"taught_keys": ["k"], "scores": []})
    assert teach.load_state() == {"taught_keys": ["k"], "scores": []}
    assert sorted(x.name for x in tmp_path.iterdir() if ".tmp" in x.name) == []


# ---------------------------------------------------------------------------
# teach loop: TEACH_LOOP_PAUSED is honoured; a finished loop is not restarted by the watchdog
# ---------------------------------------------------------------------------

def test_teach_loop_honours_pause_marker(tmp_path, monkeypatch):
    pause = tmp_path / "TEACH_LOOP_PAUSED"
    pause.write_text("PAUSED by coach", encoding="utf-8")
    monkeypatch.setattr(teach, "PAUSE_MARKER", pause)
    monkeypatch.setattr(teach, "DONE_MARKER", tmp_path / "TEACH_LOOP_DONE")

    def _no_db():
        raise AssertionError("paused loop must not touch the DB or queue work")

    monkeypatch.setattr(teach, "_connect_db", _no_db)
    monkeypatch.setattr(teach, "post_analyze", lambda *a: (_ for _ in ()).throw(AssertionError("queued")))
    assert teach.main() == 0


def test_teach_loop_stops_when_paused_mid_run(tmp_path, monkeypatch):
    pause = tmp_path / "TEACH_LOOP_PAUSED"
    monkeypatch.setattr(teach, "PAUSE_MARKER", pause)
    monkeypatch.setattr(teach, "DONE_MARKER", tmp_path / "TEACH_LOOP_DONE")
    monkeypatch.setattr(teach, "STATE_PATH", tmp_path / "state.json")
    calls = []

    def _recover(conn):
        pause.write_text("PAUSED", encoding="utf-8")  # coach pauses right after startup
        calls.append("recover")
        return 0

    monkeypatch.setattr(teach, "_connect_db", lambda: sqlite3.connect(":memory:"))
    monkeypatch.setattr(teach, "recover_interrupted_runs", _recover)
    monkeypatch.setattr(teach, "reclaim_zombie_runs",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("loop body ran")))
    assert teach.main() == 0
    assert calls == ["recover"]
    assert not (tmp_path / "TEACH_LOOP_DONE").exists()


def test_finished_teach_loop_leaves_done_marker(tmp_path, monkeypatch):
    db = tmp_path / "film.db"
    c = _runs_db(db)
    c.execute("CREATE TABLE videos (id INTEGER, game_id TEXT, opponent TEXT)")
    c.execute("CREATE TABLE film_tool_games (client_game_id TEXT, analysis_key TEXT)")
    c.commit()
    c.close()
    done = tmp_path / "TEACH_LOOP_DONE"
    done.write_text("stale DONE from an earlier run", encoding="utf-8")
    monkeypatch.setattr(teach, "DB", db)
    monkeypatch.setattr(teach, "GAMES", [])
    monkeypatch.setattr(teach, "PAUSE_MARKER", tmp_path / "TEACH_LOOP_PAUSED")
    monkeypatch.setattr(teach, "DONE_MARKER", done)
    monkeypatch.setattr(teach, "STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(teach, "PANEL_LATEST", tmp_path / "none.json")
    monkeypatch.setattr(teach, "list_live_analysis_workers",
                        lambda: {"ok": True, "any_worker": False, "keys": set(), "pid_by_key": {},
                                 "unkeyed_workers": 0, "unkeyed_pids": []})
    ran = []
    monkeypatch.setattr(teach, "run", lambda cmd: ran.append(cmd) or 0)
    assert teach.main() == 0
    assert done.read_text(encoding="utf-8").startswith("DONE ")
    assert len(ran) == 2  # final teach_from_hoops_pbp + teach_from_boxscore


def test_watchdog_script_checks_pause_and_done_markers_before_restart():
    """No pwsh in CI: check the watchdog's control flow textually."""
    text = (SCRIPTS / "watchdog_teach_loop.ps1").read_text(encoding="utf-8")
    start = text.index("start_hoops_teach_detached.py")
    for marker in ("TEACH_LOOP_PAUSED", "TEACH_LOOP_DONE"):
        i = text.index(f'"{marker}"')
        assert i < start, f"{marker} must be checked before the loop is restarted"
        assert "Test-Path -LiteralPath" in text[i:start]
        block = text[i:text.index("}", i)]
        assert "exit 0" in block
    # the Python side uses the same file names / folder
    assert teach.PAUSE_MARKER.name == "TEACH_LOOP_PAUSED" and teach.DONE_MARKER.name == "TEACH_LOOP_DONE"
    assert teach.PAUSE_MARKER.parent == teach.ROOT / "data" / "hoopsalytics"
    assert '$LogDir = Join-Path $RepoRoot "data\\hoopsalytics"' in text


def test_detached_starter_honours_pause_marker(tmp_path, monkeypatch):
    import start_hoops_teach_detached as starter

    monkeypatch.setattr(starter, "LOG_DIR", tmp_path)
    (tmp_path / "TEACH_LOOP_PAUSED").write_text("PAUSED", encoding="utf-8")
    monkeypatch.setattr(starter, "_spawn", lambda *a, **k: (_ for _ in ()).throw(AssertionError("spawned")))
    assert starter.ensure_teach_loop({}) == {}


# ---------------------------------------------------------------------------
# box-score model: HUDL caps survive a teach_from_boxscore --write-model
# ---------------------------------------------------------------------------

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
    written = json.loads(model.read_text())
    assert written["boxscore_by_game"]["hudl_marsing_away_regular_marsing"]["team"]["points"] == 51
    assert written["game_count"] == 1
    # the HUDL game is also scored in the report the teach loop reads
    report = json.loads((tmp_path / "report.json").read_text())
    assert [g["game_id"] for g in report["games"]] == ["hudl_marsing_away_regular_marsing"]


# ---------------------------------------------------------------------------
# teach_from_hoops_pbp trains on the key the loop just analysed
# ---------------------------------------------------------------------------

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


def test_pbp_teach_prefers_latest_completed_run(tmp_path):
    """A newer rerun that FAILED must not beat the completed analysis."""
    import teach_from_hoops_pbp as pbp

    base = "hoopsalytics_grace_2026-01-10"
    old_rerun = base + "__rerun_20260801_000000"
    new_rerun = base + "__rerun_20260915_193718"
    conn = _runs_db(tmp_path / "film.db")
    conn.execute("INSERT INTO analysis_runs (id, analysis_key, status) VALUES (1, ?, 'completed')", (base,))
    conn.execute("INSERT INTO analysis_runs (id, analysis_key, status) VALUES (2, ?, 'completed')", (old_rerun,))
    conn.execute("INSERT INTO analysis_runs (id, analysis_key, status) VALUES (3, ?, 'failed')", (new_rerun,))
    assert pbp._pick_analysis_key(conn, base, [base, old_rerun, new_rerun]) == old_rerun
    # no run history at all -> newest rerun stamp; no rerun -> the primary key
    empty = sqlite3.connect(":memory:")
    assert pbp._pick_analysis_key(empty, base, [base, old_rerun, new_rerun]) == new_rerun
    assert pbp._pick_analysis_key(empty, base, [base]) == base


# ---------------------------------------------------------------------------
# backup / archive / wipe DB targeting
# ---------------------------------------------------------------------------

def _py_eval(code: str, env: dict) -> str:
    return subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env={**os.environ, **env},
                          capture_output=True, text=True, check=True).stdout.strip()


def test_ops_scripts_follow_app_database_setting(tmp_path):
    """Fixed: every ops script resolves the DB through liberty_data_paths.live_db_path()."""
    live = str((tmp_path / "live.db").resolve())
    code = (
        "import sys; sys.path[:0]=['scripts','.']\n"
        "import liberty_data_paths, wipe_film_analysis, hoops_teach_loop, import_hudl, teach_from_boxscore\n"
        "import teach_from_hoops_pbp, queue_hoops_full_games, compare_ai_to_hoops_pbp, score_full_film_panel\n"
        "import generate_learning_status\n"
        "for v in (liberty_data_paths.LIVE_DB, wipe_film_analysis.DEFAULT_DB, hoops_teach_loop.DB,\n"
        "          import_hudl.DB_PATH, teach_from_boxscore.DB_PATH, teach_from_hoops_pbp.DB_PATH,\n"
        "          queue_hoops_full_games.DB_PATH, compare_ai_to_hoops_pbp.DB_PATH,\n"
        "          score_full_film_panel.DB_PATH, generate_learning_status.DB_PATH):\n"
        "    print(v)"
    )
    env = {"LIBERTY_DATABASE": live, "LIBERTY_DB_PATH": ""}
    out = _py_eval(code, env).splitlines()
    assert out == [live] * 10


def test_live_db_path_reads_dotenv_and_relative_paths(tmp_path, monkeypatch):
    import liberty_data_paths as ldp

    monkeypatch.setattr(ldp, "ROOT", tmp_path)
    monkeypatch.delenv("LIBERTY_DATABASE", raising=False)
    monkeypatch.delenv("LIBERTY_DB_PATH", raising=False)
    assert ldp.live_db_path() == tmp_path / "film_analysis.db"
    (tmp_path / ".env").write_text('# c\nLIBERTY_DATABASE="data dir/live #1.db"\n', encoding="utf-8")
    assert ldp.live_db_path() == (tmp_path / "data dir" / "live #1.db").resolve()
    # a real env var wins over .env, like app._load_dotenv
    monkeypatch.setenv("LIBERTY_DATABASE", str(tmp_path / "env.db"))
    assert ldp.live_db_path() == (tmp_path / "env.db").resolve()


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
    assert sqlite3.connect(str(snaps[0])).execute("SELECT x FROM t").fetchall() == [(1,)]
    # the '#'-truncated path must not have been created as a stray empty DB
    assert not (tmp_path / "Liberty ").exists()


def test_archive_season_reads_db_with_hash_in_path(tmp_path, monkeypatch, capsys):
    import archive_season

    folder = tmp_path / "Liberty #2"
    folder.mkdir()
    live = folder / "film_analysis.db"
    c = sqlite3.connect(str(live))
    c.execute("CREATE TABLE seasons(id INTEGER PRIMARY KEY, name TEXT)")
    c.execute("INSERT INTO seasons VALUES (7, '2025-26 Varsity')")
    c.commit()
    c.close()
    monkeypatch.setattr(sys, "argv", ["archive_season.py", "--db", str(live), "--list"])
    monkeypatch.setenv("LIBERTY_DATA_ROOT", str(tmp_path / "ld"))
    assert archive_season.main() == 0
    assert "2025-26 Varsity" in capsys.readouterr().out


def test_backup_failure_keeps_older_backups(tmp_path, monkeypatch):
    """An unusable source (here: a DB with no tables) fails loudly and never prunes."""
    import backup_db

    live = tmp_path / "empty.db"
    sqlite3.connect(str(live)).close()
    out = tmp_path / "backups"
    out.mkdir()
    olds = []
    for i in range(3):
        p = out / f"film_analysis_2026010{i}_000000.db"
        p.write_bytes(b"good backup")
        olds.append(p)
    monkeypatch.setattr(sys, "argv", ["backup_db.py", "--db", str(live), "--out-dir", str(out), "--keep", "1"])
    monkeypatch.setenv("LIBERTY_DATA_ROOT", str(tmp_path / "ld"))
    assert backup_db.main() == 1
    assert sorted(out.iterdir()) == olds


def test_backup_rejects_failed_integrity_check(tmp_path, monkeypatch):
    import backup_db

    live = tmp_path / "live.db"
    c = sqlite3.connect(str(live))
    c.execute("CREATE TABLE t(x)")
    c.commit()
    c.close()

    real_connect = sqlite3.connect

    class _CorruptCopy(sqlite3.Connection):
        def execute(self, sql, *a):
            if "integrity_check" in sql:
                return super().execute("SELECT '*** in database main *** page 3 bad'")
            return super().execute(sql, *a)

    dest = tmp_path / "out" / "film_analysis_x.db"

    def _connect(target, *a, **k):
        if str(target) == str(dest):
            k["factory"] = _CorruptCopy
        return real_connect(target, *a, **k)

    monkeypatch.setattr(backup_db.sqlite3, "connect", _connect)
    with pytest.raises(backup_db.BackupError, match="integrity_check"):
        backup_db.backup_database(live, dest)
    assert not dest.exists()


def test_wipe_keeps_coach_authored_rows(tmp_path, monkeypatch):
    """Fixed: wipe backs up first and deletes only AI analysis rows."""
    import wipe_film_analysis as wipe

    monkeypatch.setenv("LIBERTY_BACKUP_DIR", str(tmp_path / "backups"))
    db = tmp_path / "film.db"
    c = sqlite3.connect(str(db))
    c.executescript((ROOT / "schema.sql").read_text(encoding="utf-8-sig"))
    ev_cols = {r[1] for r in c.execute("PRAGMA table_info(events)")}
    assert "game_id" in ev_cols
    ev = ("INSERT INTO events (id, game_id, event_type, timestamp_ms, source_type, human_verified)"
          " VALUES (?, 'g1', 'shot', 1000, ?, ?)")
    c.execute(ev, (1, "ai", 0))       # plain AI event -> wiped
    c.execute(ev, (2, "manual", 0))   # coach-added -> kept
    c.execute(ev, (3, "ai", 1))       # AI event a coach verified -> kept
    c.execute(ev, (4, "ai", 0))       # AI event a dev clip points at -> kept
    c.execute("INSERT INTO human_corrections (game_id, event_id, correction_type, corrected_value, field_changed)"
              " VALUES ('g1', 1, 'add_event', '2PT make #12', 'event')")
    c.execute("INSERT INTO player_development_clips (id, game_id, event_id, clip_start_ms, clip_end_ms, clip_label)"
              " VALUES (10, 'g1', 4, 0, 5000, 'Closeout')")
    c.execute("INSERT INTO practice_playlists (id, name) VALUES (5, 'Monday')")
    c.execute("INSERT INTO practice_playlist_clips (playlist_id, clip_id) VALUES (5, 10)")
    c.execute("INSERT INTO detections (game_id, frame_number, timestamp_ms, object_class, confidence,"
              " x_center, y_center, width, height) VALUES ('g1', 1, 33, 'ball', 0.9, 1, 1, 1, 1)")
    c.commit()
    c.close()
    counts = wipe.wipe(db, apply=True)
    c = sqlite3.connect(str(db))
    assert c.execute("SELECT COUNT(*) FROM human_corrections").fetchone()[0] == 1
    # the correction's link to the wiped AI event is cleared (schema says ON DELETE SET NULL)
    assert c.execute("SELECT event_id FROM human_corrections").fetchone()[0] is None
    assert [r[0] for r in c.execute("SELECT id FROM events ORDER BY id")] == [2, 3, 4]
    assert c.execute("SELECT COUNT(*) FROM player_development_clips").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM practice_playlist_clips").fetchone()[0] == 1
    assert c.execute("SELECT COUNT(*) FROM detections").fetchone()[0] == 0
    # a consistent backup of the pre-wipe DB exists and still has everything
    snap = Path(counts["_backup"])
    assert snap.parent == tmp_path / "backups"
    assert sqlite3.connect(str(snap)).execute("SELECT COUNT(*) FROM events").fetchone()[0] == 4


def test_wipe_aborts_when_backup_fails(tmp_path, monkeypatch):
    import backup_db
    import wipe_film_analysis as wipe

    db = tmp_path / "film.db"
    c = sqlite3.connect(str(db))
    c.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, game_id TEXT)")
    c.execute("INSERT INTO events (game_id) VALUES ('g1')")
    c.commit()
    c.close()

    def _fail(*a, **k):
        raise backup_db.BackupError("disk full")

    monkeypatch.setattr(backup_db, "backup_database", _fail)
    assert wipe.main(["--db", str(db), "--yes", "--backup-dir", str(tmp_path / "b")]) == 1
    assert sqlite3.connect(str(db)).execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# HUDL import / LFS materialize
# ---------------------------------------------------------------------------

def test_hudl_stored_filenames_unique(tmp_path, monkeypatch):
    """Fixed: colliding slugs get a stable hash suffix; each import keeps its own upload + videos row."""
    import import_hudl

    src = tmp_path / "hudl src"
    src.mkdir()
    names = ("@ Marsing.mp4", "Marsing.mp4", "vs Kamiah.mp4", "vs. Kamiah.mp4", "Raft River.mp4")
    for name in names:
        (src / name).write_bytes(name.encode() * 10)
    disc = import_hudl.discover(src)
    stored = [p["stored_filename"] for p in disc["paired"]]
    game_ids = [p["game_id"] for p in disc["paired"]]
    film_ids = [p["film_id"] for p in disc["paired"]]
    assert len({s.lower() for s in stored}) == len(stored) == 5
    assert len(set(game_ids)) == len(game_ids)
    assert len(set(film_ids)) == len(film_ids)
    # a name that collides with nothing keeps its historical ids
    raft = next(p for p in disc["paired"] if p["video"]["raw"] == "Raft River")
    assert raft["stored_filename"] == "hudl_raft_river.mp4"
    assert raft["game_id"] == "hudl_raft_river_unknown_regular_raft_river"
    # deterministic across runs
    assert [p["stored_filename"] for p in import_hudl.discover(src)["paired"]] == stored

    # real import: every video keeps its own upload and its own videos row
    monkeypatch.setattr(import_hudl, "DB_PATH", tmp_path / "film.db")
    monkeypatch.setattr(import_hudl, "UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(import_hudl, "OUT_DIR", tmp_path / "out")
    done = tmp_path / "TEACH_LOOP_DONE"
    done.write_text("DONE", encoding="utf-8")
    monkeypatch.setattr(import_hudl, "TEACH_DONE_MARKER", done)
    import_hudl.import_all(src, force_copy=True, write_boxscore_model=False)
    assert not done.exists()  # new games -> the watchdog may restart a finished teach loop
    import_hudl.import_all(src, force_copy=True, write_boxscore_model=False)  # re-import is idempotent
    rows = sqlite3.connect(str(tmp_path / "film.db")).execute(
        "SELECT original_filename, stored_filename FROM videos ORDER BY id").fetchall()
    assert sorted(r[0] for r in rows) == sorted(names)
    for original, stored_name in rows:
        assert (tmp_path / "uploads" / stored_name).read_bytes() == (src / original).read_bytes()


def test_materialize_accepts_real_weights(tmp_path, monkeypatch):
    import materialize_lfs_models as mat

    monkeypatch.setattr(mat, "ROOT", tmp_path)
    weights = tmp_path / "models" / "player_detector.pt"
    weights.parent.mkdir()
    weights.write_bytes(b"PK\x03\x04" + bytes(range(256)) * 100)
    ok, msg = mat.materialize_model(weights, fetch=False)
    assert ok and "already materialized" in msg
    # a genuine LFS pointer is still recognised (and reported as needing its object)
    ptr = tmp_path / "models" / "ball.pt"
    ptr.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:" + "a" * 64 + "\nsize 123\n",
                   encoding="utf-8")
    assert mat._parse_pointer(ptr) == ("a" * 64, 123)
    ok, msg = mat.materialize_model(ptr, fetch=False)
    assert not ok and "needs Git LFS object" in msg


# ---------------------------------------------------------------------------
# full-film panel gates / trend / compare scorecard (proof tests from the review, inverted)
# ---------------------------------------------------------------------------

def _panel_game(name, p, r):
    return {"name": name, "precision": p, "recall": r,
            "final_score_exact": False, "player_points_exact": False}


def test_pr_gates_fail_when_most_games_missing():
    import score_full_film_panel as sfp

    games = [_panel_game("A", 0.95, 0.95)] + [_panel_game(n, None, None) for n in "BCDEF"]
    ev = sfp.evaluate_gates(games, dict(sfp.DEFAULT_TARGETS))
    assert ev["gates"]["event_precision_min"]["pass"] is False
    assert ev["gates"]["event_recall_min"]["pass"] is False
    assert ev["gates"]["event_recall_min"]["games_scored"] == 1
    assert ev["gates"]["event_recall_min"]["games_total"] == 6
    # every game scored and above target -> the gates do pass
    full = [_panel_game(n, 0.95, 0.92) for n in "ABCDEF"]
    ev = sfp.evaluate_gates(full, dict(sfp.DEFAULT_TARGETS))
    assert ev["gates"]["event_precision_min"]["pass"] is True
    assert ev["gates"]["event_recall_min"]["pass"] is True


def test_all_missing_reports_unknown_not_zero():
    import generate_learning_status as gls
    import score_full_film_panel as sfp

    games = [_panel_game(n, None, None) for n in "ABCDEF"]
    ev = sfp.evaluate_gates(games, dict(sfp.DEFAULT_TARGETS))
    assert ev["mean_precision"] is None
    assert gls._pct(ev["mean_precision"]) == "Unknown"
    assert ev["gates"]["event_precision_min"]["pass"] is False


def test_trend_does_not_report_regression_as_improvement():
    import generate_learning_status as gls
    import score_full_film_panel as sfp

    t = dict(sfp.DEFAULT_TARGETS)
    prior_games = [_panel_game("A", 0.95, 0.95)] + [_panel_game(n, 0.50, 0.50) for n in "BCDEF"]
    # latest: A unchanged, B..F now crash / no events (strictly worse)
    latest_games = [_panel_game("A", 0.95, 0.95)] + [_panel_game(n, None, None) for n in "BCDEF"]
    prior = {"generated_at": "p", "games": prior_games, "evaluation": sfp.evaluate_gates(prior_games, t)}
    latest = {"generated_at": "l", "games": latest_games, "evaluation": sfp.evaluate_gates(latest_games, t)}
    tr = gls.compute_trend(latest, prior)
    assert tr["delta_mean_precision"] == 0.0
    assert tr["delta_mean_recall"] == 0.0
    assert not any("FAIL → PASS" in c for c in tr["gate_changes"])
    assert tr["games_lost_score"] == ["B", "C", "D", "E", "F"]
    # a genuine per-game improvement still shows up
    better = [_panel_game(n, 0.60, 0.70) for n in "ABCDEF"]
    worse = [_panel_game(n, 0.50, 0.50) for n in "ABCDEF"]
    tr = gls.compute_trend({"games": better, "evaluation": sfp.evaluate_gates(better, t)},
                           {"games": worse, "evaluation": sfp.evaluate_gates(worse, t)})
    assert tr["delta_mean_precision"] == 0.1 and tr["delta_mean_recall"] == 0.2


def _compare_db(tmp_path, film, rows, ai_events):
    db = tmp_path / "t.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE film_tool_games (client_game_id TEXT, state_json TEXT)")
    c.execute("CREATE TABLE events (id INTEGER, game_id TEXT, event_type TEXT, player TEXT, shot_result TEXT,"
              " timestamp_ms INTEGER, confidence REAL, details_json TEXT, source_type TEXT)")
    if rows is not None:
        c.execute("INSERT INTO film_tool_games VALUES (?,?)", (film, json.dumps({"rows": rows})))
    c.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)", ai_events)
    c.commit()
    c.close()
    return db


def test_compare_matching_is_type_aware(tmp_path, monkeypatch):
    """An AI steal 0.2s after a true 2PT must not take the 2PT's slot (P=R=0 before the fix)."""
    import compare_ai_to_hoops_pbp as cmp

    film = "hoopsalytics-k-2026-01-01"
    rows = [
        {"eventtype": "2PT", "result": "Make", "team": "Liberty", "start": "0:10.0", "player": "#5"},
        {"eventtype": "Steal", "result": "NA", "team": "Liberty", "start": "0:11.0", "player": "#5"},
    ]
    db = _compare_db(tmp_path, film, rows, [
        (1, "K", "steal", "#5", None, 10200, 0.9, "{}", "ai"),
        (2, "K", "shot", "#5", "make", 11000, 0.9, '{"shot_type":"2pt"}', "ai"),
    ])
    monkeypatch.setattr(cmp, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["x", "--film-id", film, "--analysis-key", "K", "--db", str(db)])
    cmp.main()
    out = json.loads((tmp_path / "data" / "hoopsalytics" / f"compare_{film.replace('-', '_')}.json").read_text())
    assert (out["exact"], out["disagree"], out["miss"], out["extra"]) == (2, 0, 0, 0)
    assert out["precision"] == 1.0 and out["recall"] == 1.0


def test_compare_failure_leaves_no_stale_scorecard(tmp_path, monkeypatch):
    import compare_ai_to_hoops_pbp as cmp

    film = "hoopsalytics-gone-2026-01-01"
    db = _compare_db(tmp_path, film, None, [])  # film missing from film_tool_games -> SystemExit
    out = tmp_path / "data" / "hoopsalytics" / f"compare_{film.replace('-', '_')}.json"
    out.parent.mkdir(parents=True)
    out.write_text(json.dumps({"analysis_key": "OLD", "precision": 0.9}))
    monkeypatch.setattr(cmp, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["x", "--film-id", film, "--analysis-key", "NEW", "--db", str(db)])
    with pytest.raises(SystemExit):
        cmp.main()
    assert not out.exists()


def test_panel_run_compare_rejects_failed_or_stale_compare(tmp_path, monkeypatch):
    import score_full_film_panel as sfp

    film = "hoopsalytics-x-2026-01-01"
    out = tmp_path / "data" / "hoopsalytics" / f"compare_{film.replace('-', '_')}.json"
    out.parent.mkdir(parents=True)
    out.write_text(json.dumps({"analysis_key": "OLD_KEY", "precision": 0.99, "recall": 0.99}))
    monkeypatch.setattr(sfp, "ROOT", tmp_path)
    rc = {"code": 1}

    def fake_run(cmd, **kw):  # compare crashed (e.g. DB locked): no new file written
        return subprocess.CompletedProcess(cmd, rc["code"], "", "sqlite3.OperationalError: database is locked")

    monkeypatch.setattr(sfp.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="compare failed"):
        sfp.run_compare(film, "NEW_KEY", tmp_path / "x.db")
    rc["code"] = 0  # exit 0 but the file on disk is another analysis's scorecard
    with pytest.raises(RuntimeError, match="OLD_KEY"):
        sfp.run_compare(film, "NEW_KEY", tmp_path / "x.db")
    out.write_text(json.dumps({"analysis_key": "NEW_KEY", "end_ms": None, "precision": 0.5, "recall": 0.4}))
    assert sfp.run_compare(film, "NEW_KEY", tmp_path / "x.db")["precision"] == 0.5


def _hammer_writes(path, text, n):
    import ops_io

    for _ in range(n):
        ops_io.atomic_write_text(Path(path), text)


def test_panel_latest_write_is_atomic(tmp_path, monkeypatch):
    """Concurrent readers never see a truncated panel file (proof: ~dozens of bad reads with write_text)."""
    import multiprocessing as mp

    import generate_learning_status as gls
    import score_full_film_panel as sfp

    # 1) main() publishes the panel through the atomic helper
    db = tmp_path / "film.db"
    sqlite3.connect(str(db)).close()
    monkeypatch.setattr(sfp, "PANEL_GAMES", [])
    monkeypatch.setattr(sfp, "LATEST_PATH", tmp_path / "full_film_panel_latest.json")
    monkeypatch.setattr(sfp, "HISTORY_PATH", tmp_path / "full_film_panel_history.jsonl")
    calls = []
    real = sfp.atomic_write_text
    monkeypatch.setattr(sfp, "atomic_write_text", lambda p, t: (calls.append(Path(p)), real(p, t)))
    monkeypatch.setattr(sys, "argv", ["score_full_film_panel.py", "--db", str(db),
                                      "--targets", str(tmp_path / "none.json")])
    assert sfp.main() == 0
    assert calls == [tmp_path / "full_film_panel_latest.json"]
    assert json.loads(calls[0].read_text())["games"] == []

    # 2) the helper itself: a concurrent reader never gets a partial file
    text = json.dumps({"games": [{"name": f"g{i}", "precision": 0.5} for i in range(300)]}, indent=2)
    target = tmp_path / "latest.json"
    target.write_text(text, encoding="utf-8")
    proc = mp.get_context("spawn").Process(target=_hammer_writes, args=(str(target), text, 1500))
    proc.start()
    bad = 0
    reads = 0
    while proc.is_alive():
        data, err = gls.load_json(target)
        reads += 1
        if err or data is None:
            bad += 1
    proc.join()
    assert proc.exitcode == 0
    assert bad == 0, f"{bad}/{reads} reads saw a partial file"
    assert not list(tmp_path.glob(".latest.json.*.tmp"))
