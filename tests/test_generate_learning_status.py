"""Tests for generate_learning_status report rendering helpers."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from generate_learning_status import (  # noqa: E402
    _extract_analysis_key_from_cmdline,
    classify_live_vs_stale,
    compute_trend,
    find_prior_snapshot,
    gather,
    query_analysis_activity,
    query_hudl_queue,
    render_report,
)


def _sample_panel(*, prec: float, rec: float, generated_at: str) -> dict:
    games = []
    for name in ("Idaho City", "Harper", "Burns", "Nyssa", "Melba", "Camas"):
        games.append(
            {
                "name": name,
                "precision": prec,
                "recall": rec,
                "ok": True,
                "final_score_exact": False,
                "final_score_status": "partial",
                "player_points_exact": False,
                "player_points_status": "proven",
                "final_score": {
                    "truth": {"liberty": 70, "opponent": 50},
                    "ai": {"liberty": 60, "opponent": None},
                },
                "player_points": {"matched": 1, "should_have_count": 8},
            }
        )
    return {
        "generated_at": generated_at,
        "games": games,
        "evaluation": {
            "gates": {
                "final_score_exact": {
                    "required": 1.0,
                    "actual": 0.0,
                    "pass": False,
                },
                "player_points_exact": {
                    "required": 1.0,
                    "actual": 0.0,
                    "pass": False,
                },
                "event_precision_min": {
                    "required": 0.9,
                    "actual": prec,
                    "pass": prec >= 0.9,
                },
                "event_recall_min": {
                    "required": 0.9,
                    "actual": rec,
                    "pass": rec >= 0.9,
                },
            },
            "overall_pass": False,
            "mean_precision": prec,
            "mean_recall": rec,
        },
    }


def test_find_prior_snapshot_baseline_single():
    latest = _sample_panel(prec=0.7, rec=0.5, generated_at="2026-07-29T00:00:00+00:00")
    prior, note = find_prior_snapshot(latest, [latest])
    assert prior is None
    assert "baseline" in note.lower() or "no" in note.lower()


def test_find_prior_snapshot_distinct():
    older = _sample_panel(prec=0.6, rec=0.4, generated_at="2026-07-28T00:00:00+00:00")
    newer = _sample_panel(prec=0.7, rec=0.5, generated_at="2026-07-29T00:00:00+00:00")
    prior, note = find_prior_snapshot(newer, [older, newer])
    assert prior is not None
    assert prior["generated_at"] == older["generated_at"]
    assert "distinct" in note.lower()


def test_compute_trend_deltas():
    older = _sample_panel(prec=0.6, rec=0.4, generated_at="t0")
    newer = _sample_panel(prec=0.7, rec=0.5, generated_at="t1")
    trend = compute_trend(newer, older)
    assert trend["available"] is True
    assert trend["delta_mean_precision"] == 0.1
    assert abs(trend["delta_mean_recall"] - 0.1) < 1e-9


def test_extract_analysis_key_from_cmdline():
    cmd = (
        r"C:\Python\python.exe analysis_launcher.py film_analysis.db "
        r"C:\repo\uploads\hudl_x.mp4 hudl_demo_key__rerun_1"
    )
    assert _extract_analysis_key_from_cmdline(cmd) == "hudl_demo_key__rerun_1"
    assert _extract_analysis_key_from_cmdline("python hoops_teach_loop.py") is None


def test_classify_live_vs_stale_separates_workers():
    running = [
        {
            "id": 1,
            "analysis_key": "stale_a",
            "progress_pct": 50.0,
            "progress_step": "Regenerating events…",
            "started_at": "2026-07-20",
        },
        {
            "id": 2,
            "analysis_key": "live_key",
            "progress_pct": 42.0,
            "progress_step": "Detecting",
            "started_at": "2026-07-29",
        },
        {
            "id": 3,
            "analysis_key": "stale_b",
            "progress_pct": 50.0,
            "progress_step": "Regenerating events…",
            "started_at": "2026-07-21",
        },
    ]
    probe = {
        "ok": True,
        "status": "ok",
        "workers": [
            {
                "pid": 111,
                "kind": "analysis_launcher",
                "analysis_key": "live_key",
                "cmdline": "python analysis_launcher.py db vid live_key",
                "creation_date": None,
            },
            {
                "pid": 222,
                "kind": "teach_loop",
                "analysis_key": None,
                "cmdline": "python hoops_teach_loop.py",
                "creation_date": None,
            },
            {
                "pid": 333,
                "kind": "analysis_launcher",
                "analysis_key": "other_live",
                "cmdline": "python analysis_launcher.py db vid other_live",
                "creation_date": None,
            },
        ],
        "error": None,
    }
    classified = classify_live_vs_stale(
        running_rows=running, process_probe=probe, conn=None
    )
    assert classified["process_map_status"] == "ok"
    assert classified["stale_count"] == 2
    assert {s["analysis_key"] for s in classified["stale"]} == {"stale_a", "stale_b"}
    assert classified["live_launcher_count"] == 2
    keys = {a["analysis_key"] for a in classified["active"]}
    assert keys == {"live_key", "other_live"}
    assert classified["current"]["analysis_key"] == "live_key"  # higher progress
    assert sum(1 for a in classified["active"] if a.get("primary")) == 1
    assert 222 in classified["teach_loop_pids"]


def test_classify_unknown_on_probe_failure():
    classified = classify_live_vs_stale(
        running_rows=[
            {"analysis_key": "zombie", "progress_pct": 50, "progress_step": "x"}
        ],
        process_probe={
            "ok": False,
            "status": "unknown",
            "workers": [],
            "error": "access denied",
        },
        conn=None,
    )
    assert classified["process_map_status"] == "Unknown"
    assert classified["active"] == []
    assert classified["current"] is None
    assert any("Unknown" in n for n in classified["notes"])


def test_render_report_contains_sections(tmp_path: Path):
    latest = _sample_panel(prec=0.71, rec=0.52, generated_at="2026-07-29T12:00:00+00:00")
    prior = _sample_panel(prec=0.70, rec=0.50, generated_at="2026-07-28T12:00:00+00:00")
    trend = compute_trend(latest, prior)
    md = render_report(
        generated_local="2026-07-29 18:00:00 MDT",
        latest=latest,
        latest_err=None,
        prior=prior,
        trend_note="compared to previous distinct snapshot",
        trend=trend,
        teach_state={"taught_keys": ["hudl_a", "hoopsalytics_x"]},
        teach_err=None,
        activity={
            "available": True,
            "status_counts": {"running": 3, "completed": 2},
            "running": [],
            "process_map_status": "ok",
            "active": [
                {
                    "analysis_key": "hudl_demo",
                    "status": "Active (live worker)",
                    "progress_pct": 42,
                    "progress_step": "Detecting",
                    "pid": 999,
                    "kind": "analysis_launcher",
                    "primary": True,
                    "db_status": "running",
                    "source": "live process + analysis_runs",
                }
            ],
            "stale": [
                {
                    "analysis_key": "stale_key",
                    "progress_pct": 50,
                    "progress_step": "Regenerating events…",
                    "started_at": "2026-07-20",
                }
            ],
            "stale_count": 1,
            "live_launcher_count": 1,
            "teach_loop_pids": [888],
            "current": {
                "analysis_key": "hudl_demo",
                "status": "Active (live worker)",
                "progress_pct": 42,
                "progress_step": "Detecting",
                "source": "live process + analysis_runs",
                "pid": 999,
            },
            "notes": [],
            "provenance": "Proven",
        },
        queue={
            "hudl_film_tool_total": 10,
            "hudl_videos_total": 9,
            "hudl_taught_keys": 2,
            "remaining_vs_film_tool": 8,
            "remaining_vs_videos": 7,
            "failed_hudl_runs": 1,
            "notes": ["remaining is inferred"],
            "provenance": {
                "hudl_taught_keys": "Proven",
                "hudl_film_tool_total": "Proven",
                "hudl_videos_total": "Proven",
                "failed_hudl_runs": "Proven",
            },
        },
        db_err=None,
        history_err=None,
    )
    assert "# Learning Status" in md
    assert "Current learning activity" in md
    assert "hudl_demo" in md
    assert "Active (live worker-backed)" in md
    assert "Stale/zombie candidates" in md
    assert "stale_key" in md
    assert "PID=999" in md
    assert "Teach loop PID(s)" in md
    assert "888" in md
    assert "Fixed-panel gate summary" in md
    assert "Per-game panel" in md
    assert "Idaho City" in md
    assert "Trend vs prior" in md
    assert "Proven / Inferred / Unknown" in md
    assert "100%" in md
    assert "≥90%" in md or "90%" in md


def test_gather_with_fixture_json_and_temp_db(tmp_path: Path):
    latest = _sample_panel(prec=0.65, rec=0.45, generated_at="2026-07-29T01:00:00+00:00")
    older = _sample_panel(prec=0.60, rec=0.40, generated_at="2026-07-28T01:00:00+00:00")
    latest_path = tmp_path / "full_film_panel_latest.json"
    history_path = tmp_path / "full_film_panel_history.jsonl"
    teach_path = tmp_path / "teach_loop_state.json"
    db_path = tmp_path / "film_analysis.db"
    out_path = tmp_path / "LEARNING_STATUS.md"

    latest_path.write_text(json.dumps(latest), encoding="utf-8")
    with history_path.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps(older) + "\n")
        fh.write(json.dumps(latest) + "\n")
    teach_path.write_text(
        json.dumps(
            {
                "taught_keys": [
                    "hudl_carey_away_regular_carey",
                    "hoopsalytics_nyssa_2025-12-04",
                ]
            }
        ),
        encoding="utf-8",
    )

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
            error_message TEXT
        );
        CREATE TABLE film_tool_games (
            id INTEGER PRIMARY KEY,
            client_game_id TEXT,
            analysis_key TEXT
        );
        CREATE TABLE videos (
            id INTEGER PRIMARY KEY,
            game_id TEXT
        );
        INSERT INTO analysis_runs (analysis_key, status, progress_pct, progress_step, started_at)
        VALUES ('hudl_demo_key', 'running', 33.0, 'Detecting players', '2026-07-29 10:00:00');
        INSERT INTO analysis_runs (analysis_key, status, progress_pct, progress_step, started_at)
        VALUES ('stale_zombie_key', 'running', 50.0, 'Regenerating events…', '2026-07-20 10:00:00');
        INSERT INTO analysis_runs (analysis_key, status, progress_pct, progress_step)
        VALUES ('hudl_fail_key', 'failed', 6.0, 'Failed');
        INSERT INTO film_tool_games (client_game_id, analysis_key) VALUES
            ('hudl-carey', 'hudl_carey_away_regular_carey'),
            ('hudl-dietrich', 'hudl_dietrich_away_regular_dietrich'),
            ('hoopsalytics-nyssa', 'hoopsalytics_nyssa_2025-12-04');
        INSERT INTO videos (game_id) VALUES
            ('hudl_carey_away_regular_carey'),
            ('hudl_dietrich_away_regular_dietrich');
        """
    )
    conn.close()

    def fake_lister():
        return {
            "ok": True,
            "status": "ok",
            "workers": [
                {
                    "pid": 4242,
                    "kind": "analysis_launcher",
                    "analysis_key": "hudl_demo_key",
                    "cmdline": (
                        "python analysis_launcher.py film_analysis.db "
                        "vid.mp4 hudl_demo_key"
                    ),
                    "creation_date": None,
                },
                {
                    "pid": 5151,
                    "kind": "teach_loop",
                    "analysis_key": None,
                    "cmdline": "python scripts/hoops_teach_loop.py",
                    "creation_date": None,
                },
            ],
            "error": None,
        }

    result = gather(
        latest_path=latest_path,
        history_path=history_path,
        teach_path=teach_path,
        db_path=db_path,
        process_lister=fake_lister,
    )
    out_path.write_text(result["markdown"], encoding="utf-8")
    md = result["markdown"]
    assert "hudl_demo_key" in md
    assert "33" in md or "33.0" in md
    assert "Detecting players" in md
    assert "Active (live worker-backed)" in md
    assert "PID=4242" in md
    assert "stale_zombie_key" in md
    assert "Stale/zombie candidates" in md
    assert "FAIL" in md
    assert "Δ mean precision" in md or "delta" in md.lower() or "Trend" in md
    assert "Proven" in md


def test_query_helpers_missing_tables(tmp_path: Path):
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    activity = query_analysis_activity(
        conn,
        process_lister=lambda: {
            "ok": True,
            "status": "ok",
            "workers": [],
            "error": None,
        },
    )
    assert activity["available"] is False
    queue = query_hudl_queue(conn, {"taught_keys": ["hudl_a"]})
    assert queue["hudl_taught_keys"] == 1
    assert queue["hudl_film_tool_total"] is None
    conn.close()


def test_gather_missing_runtime_still_writes_unknowns(tmp_path: Path):
    result = gather(
        latest_path=tmp_path / "missing_latest.json",
        history_path=tmp_path / "missing_history.jsonl",
        teach_path=tmp_path / "missing_teach.json",
        db_path=tmp_path / "missing.db",
        process_lister=lambda: {
            "ok": True,
            "status": "ok",
            "workers": [],
            "error": None,
        },
    )
    md = result["markdown"]
    assert "Unknown" in md
    assert "# Learning Status" in md
