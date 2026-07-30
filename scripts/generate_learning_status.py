#!/usr/bin/env python3
"""Generate docs/LEARNING_STATUS.md from panel JSON, teach state, and analysis_runs.

Reads runtime files under data/hoopsalytics/ and film_analysis.db (read-only-ish).
Missing inputs become Unknown — still writes a usable report and exits 0 when possible.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LATEST_PATH = ROOT / "data" / "hoopsalytics" / "full_film_panel_latest.json"
HISTORY_PATH = ROOT / "data" / "hoopsalytics" / "full_film_panel_history.jsonl"
TEACH_STATE_PATH = ROOT / "data" / "hoopsalytics" / "teach_loop_state.json"
DB_PATH = ROOT / "film_analysis.db"
OUT_PATH = ROOT / "docs" / "LEARNING_STATUS.md"

SCOTT_TARGETS = {
    "final_score_exact": "100%",
    "player_points_exact": "100%",
    "event_precision_min": "≥90%",
    "event_recall_min": "≥90%",
}


def _pct(value: Any) -> str:
    if value is None:
        return "Unknown"
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "Unknown"


def _fmt_score_pair(final_score: dict | None) -> str:
    if not isinstance(final_score, dict):
        return "Unknown"
    truth = final_score.get("truth") or {}
    ai = final_score.get("ai") or {}
    t_lib = truth.get("liberty")
    t_opp = truth.get("opponent")
    a_lib = ai.get("liberty")
    a_opp = ai.get("opponent")

    def _n(v: Any) -> str:
        return "—" if v is None else str(v)

    return f"{_n(t_lib)}-{_n(t_opp)} → {_n(a_lib)}-{_n(a_opp)}"


def load_json(path: Path) -> tuple[dict | list | None, str | None]:
    if not path.exists():
        return None, f"missing {path.name}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"unreadable {path.name}: {exc}"


def load_history(path: Path) -> tuple[list[dict], str | None]:
    if not path.exists():
        return [], f"missing {path.name}"
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    except OSError as exc:
        return [], f"unreadable {path.name}: {exc}"
    return rows, None


def _snapshot_fingerprint(payload: dict) -> str:
    """Stable-ish identity for distinct snapshots (ignore write timestamp noise if same gates/games)."""
    ev = payload.get("evaluation") or {}
    games = payload.get("games") or []
    key = {
        "mean_precision": ev.get("mean_precision"),
        "mean_recall": ev.get("mean_recall"),
        "overall_pass": ev.get("overall_pass"),
        "games": [
            {
                "name": g.get("name"),
                "precision": g.get("precision"),
                "recall": g.get("recall"),
                "final_score_exact": g.get("final_score_exact"),
                "player_points_exact": g.get("player_points_exact"),
            }
            for g in games
            if isinstance(g, dict)
        ],
    }
    return json.dumps(key, sort_keys=True, separators=(",", ":"))


def find_prior_snapshot(
    latest: dict | None, history: list[dict]
) -> tuple[dict | None, str]:
    """Return previous distinct history snapshot vs latest, plus trend label."""
    if not latest:
        return None, "no latest panel — trend Unknown"
    if not history:
        return None, "baseline / no prior history yet"
    latest_fp = _snapshot_fingerprint(latest)
    # Walk history newest→oldest; skip snapshots matching latest
    for row in reversed(history):
        if _snapshot_fingerprint(row) != latest_fp:
            return row, "compared to previous distinct snapshot"
    if len(history) <= 1:
        return None, "baseline / only one distinct snapshot (no trend yet)"
    return None, "baseline / no distinct prior snapshot yet"


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except sqlite3.Error:
        return set()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
        return bool(row)
    except sqlite3.Error:
        return False


def connect_db(db_path: Path, *, timeout: float = 30.0) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=timeout)
    conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
    return conn


def query_analysis_activity(conn: sqlite3.Connection) -> dict[str, Any]:
    """Current analysis_runs progress + status counts. Robust to missing schema."""
    out: dict[str, Any] = {
        "available": False,
        "status_counts": {},
        "running": [],
        "current": None,
        "failed_count": None,
        "notes": [],
        "provenance": "Unknown",
    }
    if not _table_exists(conn, "analysis_runs"):
        out["notes"].append("analysis_runs table missing")
        return out

    cols = _table_columns(conn, "analysis_runs")
    out["available"] = True
    out["provenance"] = "Proven"

    if "status" in cols:
        try:
            for status, n in conn.execute(
                "SELECT status, COUNT(*) FROM analysis_runs GROUP BY status"
            ).fetchall():
                out["status_counts"][str(status)] = int(n)
            out["failed_count"] = int(out["status_counts"].get("failed", 0))
        except sqlite3.Error as exc:
            out["notes"].append(f"status counts failed: {exc}")
            out["provenance"] = "Inferred"

    select_bits = ["rowid AS _rid"]
    for c in (
        "id",
        "analysis_key",
        "status",
        "progress_pct",
        "progress_step",
        "started_at",
        "error_message",
    ):
        if c in cols:
            select_bits.append(c)
    try:
        if "status" in cols:
            rows = conn.execute(
                f"SELECT {', '.join(select_bits)} FROM analysis_runs "
                f"WHERE status='running' "
                f"ORDER BY COALESCE(started_at, '') DESC, rowid DESC"
            ).fetchall()
        else:
            rows = []
            out["notes"].append("analysis_runs.status column missing")
    except sqlite3.Error as exc:
        rows = []
        out["notes"].append(f"running query failed: {exc}")
        out["provenance"] = "Inferred"

    colnames = [b.split(" AS ")[-1] if " AS " in b else b for b in select_bits]
    running = [dict(zip(colnames, r)) for r in rows]
    out["running"] = running
    if running:
        # Prefer highest progress_pct among running, else newest
        def _rank(r: dict) -> tuple:
            pct = r.get("progress_pct")
            try:
                pct_f = float(pct) if pct is not None else -1.0
            except (TypeError, ValueError):
                pct_f = -1.0
            return (pct_f, str(r.get("started_at") or ""))

        current = max(running, key=_rank)
        out["current"] = {
            "analysis_key": current.get("analysis_key"),
            "status": current.get("status"),
            "progress_pct": current.get("progress_pct"),
            "progress_step": current.get("progress_step"),
            "started_at": current.get("started_at"),
            "source": "analysis_runs",
        }
    return out


def query_hudl_queue(
    conn: sqlite3.Connection, teach_state: dict | None
) -> dict[str, Any]:
    """HUDL taught/total/remaining with clear labels; no fake precision."""
    out: dict[str, Any] = {
        "hudl_film_tool_total": None,
        "hudl_videos_total": None,
        "hudl_taught_keys": None,
        "remaining_vs_film_tool": None,
        "remaining_vs_videos": None,
        "failed_hudl_runs": None,
        "notes": [],
        "provenance": {},
    }

    taught_keys = []
    if isinstance(teach_state, dict):
        taught_keys = [
            k
            for k in (teach_state.get("taught_keys") or [])
            if isinstance(k, str) and k.startswith("hudl_")
        ]
        out["hudl_taught_keys"] = len(taught_keys)
        out["provenance"]["hudl_taught_keys"] = "Proven (teach_loop_state.json)"
    else:
        out["notes"].append("teach_loop_state unavailable — HUDL taught count Unknown")
        out["provenance"]["hudl_taught_keys"] = "Unknown"

    if _table_exists(conn, "film_tool_games"):
        cols = _table_columns(conn, "film_tool_games")
        if "client_game_id" in cols:
            try:
                n = conn.execute(
                    "SELECT COUNT(*) FROM film_tool_games "
                    "WHERE client_game_id LIKE 'hudl%' OR client_game_id LIKE 'HUDL%'"
                ).fetchone()[0]
                out["hudl_film_tool_total"] = int(n)
                out["provenance"]["hudl_film_tool_total"] = (
                    "Proven (film_tool_games.client_game_id LIKE hudl%)"
                )
            except sqlite3.Error as exc:
                out["notes"].append(f"film_tool_games count failed: {exc}")
                out["provenance"]["hudl_film_tool_total"] = "Unknown"
        else:
            out["notes"].append("film_tool_games.client_game_id missing")
            out["provenance"]["hudl_film_tool_total"] = "Unknown"
    else:
        out["notes"].append("film_tool_games missing")
        out["provenance"]["hudl_film_tool_total"] = "Unknown"

    if _table_exists(conn, "videos"):
        cols = _table_columns(conn, "videos")
        if "game_id" in cols:
            try:
                n = conn.execute(
                    "SELECT COUNT(*) FROM videos WHERE game_id LIKE 'hudl_%'"
                ).fetchone()[0]
                out["hudl_videos_total"] = int(n)
                out["provenance"]["hudl_videos_total"] = (
                    "Proven (videos.game_id LIKE hudl_%)"
                )
            except sqlite3.Error as exc:
                out["notes"].append(f"videos hudl count failed: {exc}")
                out["provenance"]["hudl_videos_total"] = "Unknown"
        else:
            out["provenance"]["hudl_videos_total"] = "Unknown"
    else:
        out["provenance"]["hudl_videos_total"] = "Unknown"

    taught_n = out["hudl_taught_keys"]
    if taught_n is not None and out["hudl_film_tool_total"] is not None:
        rem = out["hudl_film_tool_total"] - taught_n
        out["remaining_vs_film_tool"] = rem
        out["notes"].append(
            "remaining_vs_film_tool = film_tool HUDL games − taught hudl_* keys "
            "(keys/film ids are related but not guaranteed 1:1)"
        )
        out["provenance"]["remaining_vs_film_tool"] = "Inferred"
    if taught_n is not None and out["hudl_videos_total"] is not None:
        rem = out["hudl_videos_total"] - taught_n
        out["remaining_vs_videos"] = rem
        out["notes"].append(
            "remaining_vs_videos = videos hudl_* − taught hudl_* keys "
            "(closer to teach-loop queue, still not guaranteed 1:1 with reruns)"
        )
        out["provenance"]["remaining_vs_videos"] = "Inferred"

    if _table_exists(conn, "analysis_runs"):
        cols = _table_columns(conn, "analysis_runs")
        if {"status", "analysis_key"} <= cols:
            try:
                n = conn.execute(
                    "SELECT COUNT(*) FROM analysis_runs "
                    "WHERE status='failed' AND analysis_key LIKE 'hudl_%'"
                ).fetchone()[0]
                out["failed_hudl_runs"] = int(n)
                out["provenance"]["failed_hudl_runs"] = "Proven (analysis_runs)"
            except sqlite3.Error as exc:
                out["notes"].append(f"failed hudl runs query failed: {exc}")
                out["provenance"]["failed_hudl_runs"] = "Unknown"
        else:
            out["provenance"]["failed_hudl_runs"] = "Unknown"
    else:
        out["provenance"]["failed_hudl_runs"] = "Unknown"

    return out


def infer_activity_from_teach(
    teach_state: dict | None, activity: dict[str, Any]
) -> dict[str, Any]:
    """If no running analysis_runs, lightly infer from teach state."""
    if activity.get("current"):
        return activity
    if not isinstance(teach_state, dict):
        return activity
    scores = teach_state.get("scores") or []
    if not scores:
        activity["notes"] = list(activity.get("notes") or []) + [
            "no running analysis_runs; teach scores empty"
        ]
        return activity
    last = scores[-1] if isinstance(scores[-1], dict) else None
    if not last:
        return activity
    activity["current"] = {
        "analysis_key": last.get("analysis_key") or last.get("key"),
        "status": "inferred_from_teach_state (no running analysis_runs)",
        "progress_pct": None,
        "progress_step": f"last scored: {last.get('name') or last.get('key')}",
        "started_at": None,
        "source": "teach_loop_state (Inferred)",
    }
    activity["notes"] = list(activity.get("notes") or []) + [
        "process status unavailable — used last teach_loop score as hint only"
    ]
    if activity.get("provenance") == "Proven":
        activity["provenance"] = "Inferred"
    return activity


def compute_trend(latest: dict | None, prior: dict | None) -> dict[str, Any]:
    if not latest:
        return {"available": False, "note": "no latest panel"}
    if not prior:
        return {"available": False, "note": "baseline / no trend yet"}

    lev = latest.get("evaluation") or {}
    pev = prior.get("evaluation") or {}
    d_prec = None
    d_rec = None
    if lev.get("mean_precision") is not None and pev.get("mean_precision") is not None:
        d_prec = round(float(lev["mean_precision"]) - float(pev["mean_precision"]), 4)
    if lev.get("mean_recall") is not None and pev.get("mean_recall") is not None:
        d_rec = round(float(lev["mean_recall"]) - float(pev["mean_recall"]), 4)

    gate_changes: list[str] = []
    lg = (lev.get("gates") or {}) if isinstance(lev.get("gates"), dict) else {}
    pg = (pev.get("gates") or {}) if isinstance(pev.get("gates"), dict) else {}
    for key in sorted(set(lg) | set(pg)):
        lp = bool((lg.get(key) or {}).get("pass"))
        pp = bool((pg.get(key) or {}).get("pass"))
        if lp != pp:
            gate_changes.append(f"{key}: {'PASS' if pp else 'FAIL'} → {'PASS' if lp else 'FAIL'}")

    return {
        "available": True,
        "prior_generated_at": prior.get("generated_at"),
        "delta_mean_precision": d_prec,
        "delta_mean_recall": d_rec,
        "gate_changes": gate_changes,
        "prior_overall_pass": pev.get("overall_pass"),
        "latest_overall_pass": lev.get("overall_pass"),
    }


def build_verdict(latest: dict | None, trend: dict[str, Any]) -> list[str]:
    if not latest:
        return ["Panel latest missing — cannot judge learning progress."]
    ev = latest.get("evaluation") or {}
    gates = ev.get("gates") or {}
    lines: list[str] = []
    if ev.get("overall_pass"):
        lines.append("Overall panel gates PASS — Scott targets met on this snapshot.")
    else:
        lines.append("Overall panel gates FAIL — learning has not yet cleared Scott targets.")

    gaps: list[tuple[float, str]] = []
    for key, label, target in (
        ("event_precision_min", "event precision", 0.90),
        ("event_recall_min", "event recall", 0.90),
    ):
        g = gates.get(key) or {}
        actual = g.get("actual")
        if actual is None:
            continue
        try:
            shortfall = target - float(actual)
        except (TypeError, ValueError):
            continue
        if shortfall > 0:
            gaps.append((shortfall, f"{label} at {_pct(actual)} (need ≥{_pct(target)}; short {_pct(shortfall)})"))

    for key, label in (
        ("final_score_exact", "final score exactness"),
        ("player_points_exact", "player points exactness"),
    ):
        g = gates.get(key) or {}
        if not g.get("pass"):
            gaps.append((1.0, f"{label} not at 100% (gate FAIL)"))

    # Per-game recall holes
    game_gaps: list[tuple[float, str]] = []
    for g in latest.get("games") or []:
        if not isinstance(g, dict):
            continue
        name = g.get("name") or "?"
        rec = g.get("recall")
        prec = g.get("precision")
        if rec is not None:
            try:
                game_gaps.append((0.90 - float(rec), f"{name} recall {_pct(rec)}"))
            except (TypeError, ValueError):
                pass
        pp = g.get("player_points") or {}
        matched = pp.get("matched")
        need = pp.get("should_have_count")
        if matched is not None and need:
            game_gaps.append(
                (
                    1.0 - (float(matched) / float(need) if need else 0.0),
                    f"{name} player-point matches {matched}/{need}",
                )
            )
        if g.get("final_score_status") == "partial":
            game_gaps.append((0.5, f"{name} final score partial (opponent AI often Unknown)"))

    gaps.sort(key=lambda x: -x[0])
    game_gaps.sort(key=lambda x: -x[0])
    if gaps:
        lines.append("Largest gate gaps: " + "; ".join(g[1] for g in gaps[:4]) + ".")
    if game_gaps:
        lines.append("Largest per-game holes: " + "; ".join(g[1] for g in game_gaps[:4]) + ".")
    if trend.get("available"):
        dp = trend.get("delta_mean_precision")
        dr = trend.get("delta_mean_recall")
        lines.append(
            f"Trend vs prior: ΔP={dp if dp is not None else 'Unknown'}, "
            f"ΔR={dr if dr is not None else 'Unknown'}."
        )
    else:
        lines.append(f"Trend: {trend.get('note') or 'baseline / no trend yet'}.")
    return lines


def render_report(
    *,
    generated_local: str,
    latest: dict | None,
    latest_err: str | None,
    prior: dict | None,
    trend_note: str,
    trend: dict[str, Any],
    teach_state: dict | None,
    teach_err: str | None,
    activity: dict[str, Any],
    queue: dict[str, Any],
    db_err: str | None,
    history_err: str | None,
) -> str:
    lines: list[str] = []
    lines.append("# Learning Status")
    lines.append("")
    lines.append(f"Generated (local): **{generated_local}**")
    lines.append("")
    lines.append(
        "Nightly snapshot of how Liberty full-film learning is going "
        "(fixed panel gates + queue/activity). Runtime JSON/DB are not committed."
    )
    lines.append("")

    # Current activity
    lines.append("## Current learning activity")
    lines.append("")
    cur = activity.get("current")
    if cur:
        pct = cur.get("progress_pct")
        pct_s = "Unknown" if pct is None else f"{pct}%"
        lines.append(f"- **Game / key:** `{cur.get('analysis_key') or 'Unknown'}`")
        lines.append(f"- **Status:** {cur.get('status') or 'Unknown'}")
        lines.append(f"- **Progress:** {pct_s}")
        lines.append(f"- **Step:** {cur.get('progress_step') or 'Unknown'}")
        lines.append(f"- **Source:** {cur.get('source') or 'Unknown'}")
    else:
        lines.append("- **Status:** Unknown (no running analysis_runs and no teach hint)")
    if activity.get("status_counts"):
        counts = ", ".join(
            f"{k}={v}" for k, v in sorted(activity["status_counts"].items())
        )
        lines.append(f"- **analysis_runs counts:** {counts}")
    for n in activity.get("notes") or []:
        lines.append(f"- Note: {n}")
    if db_err:
        lines.append(f"- DB: {db_err}")
    lines.append("")

    # Queue
    lines.append("## Queue summary")
    lines.append("")
    taught = queue.get("hudl_taught_keys")
    ft = queue.get("hudl_film_tool_total")
    vids = queue.get("hudl_videos_total")
    lines.append(
        f"- **HUDL taught keys:** "
        f"{taught if taught is not None else 'Unknown'} "
        f"({queue.get('provenance', {}).get('hudl_taught_keys', 'Unknown')})"
    )
    lines.append(
        f"- **HUDL film_tool games (total):** "
        f"{ft if ft is not None else 'Unknown'} "
        f"({queue.get('provenance', {}).get('hudl_film_tool_total', 'Unknown')})"
    )
    lines.append(
        f"- **HUDL videos (total):** "
        f"{vids if vids is not None else 'Unknown'} "
        f"({queue.get('provenance', {}).get('hudl_videos_total', 'Unknown')})"
    )
    rem_v = queue.get("remaining_vs_videos")
    rem_f = queue.get("remaining_vs_film_tool")
    lines.append(
        f"- **Remaining (vs videos, inferred):** "
        f"{rem_v if rem_v is not None else 'Unknown'}"
    )
    lines.append(
        f"- **Remaining (vs film_tool, inferred):** "
        f"{rem_f if rem_f is not None else 'Unknown'}"
    )
    failed = queue.get("failed_hudl_runs")
    lines.append(
        f"- **Failed HUDL analysis_runs:** "
        f"{failed if failed is not None else 'Unknown'} "
        f"({queue.get('provenance', {}).get('failed_hudl_runs', 'Unknown')})"
    )
    if isinstance(teach_state, dict):
        all_taught = teach_state.get("taught_keys") or []
        lines.append(f"- **All taught keys (Hoops+HUDL):** {len(all_taught)}")
    elif teach_err:
        lines.append(f"- Teach state: {teach_err}")
    for n in queue.get("notes") or []:
        lines.append(f"- Note: {n}")
    lines.append("")

    # Gates
    lines.append("## Fixed-panel gate summary (Scott targets)")
    lines.append("")
    lines.append("| Gate | Target | Actual | Result |")
    lines.append("| --- | --- | --- | --- |")
    if latest and isinstance(latest.get("evaluation"), dict):
        ev = latest["evaluation"]
        gates = ev.get("gates") or {}
        order = [
            ("final_score_exact", SCOTT_TARGETS["final_score_exact"]),
            ("player_points_exact", SCOTT_TARGETS["player_points_exact"]),
            ("event_precision_min", SCOTT_TARGETS["event_precision_min"]),
            ("event_recall_min", SCOTT_TARGETS["event_recall_min"]),
        ]
        for key, target_label in order:
            g = gates.get(key) or {}
            actual = g.get("actual")
            if key.startswith("event_"):
                actual_s = _pct(actual)
            else:
                actual_s = _pct(actual) if actual is not None else "Unknown"
            result = "PASS" if g.get("pass") else "FAIL"
            lines.append(f"| {key} | {target_label} | {actual_s} | {result} |")
        overall = "PASS" if ev.get("overall_pass") else "FAIL"
        lines.append("")
        lines.append(
            f"**Overall:** {overall} "
            f"(mean P={_pct(ev.get('mean_precision'))}, "
            f"mean R={_pct(ev.get('mean_recall'))})"
        )
        gen = latest.get("generated_at")
        if gen:
            lines.append(f"- Panel snapshot: `{gen}`")
    else:
        lines.append("| (all) | 100% / 100% / ≥90% / ≥90% | Unknown | Unknown |")
        lines.append("")
        lines.append(f"**Overall:** Unknown — {latest_err or 'panel latest unavailable'}")
    lines.append("")

    # Per-game table
    lines.append("## Per-game panel")
    lines.append("")
    lines.append(
        "| Game | Precision | Recall | Liberty score truth→AI | "
        "Player point matches | Result |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- |")
    games = (latest or {}).get("games") if latest else None
    if games:
        for g in games:
            if not isinstance(g, dict):
                continue
            name = g.get("name") or "?"
            prec = _pct(g.get("precision"))
            rec = _pct(g.get("recall"))
            score_s = _fmt_score_pair(g.get("final_score"))
            pp = g.get("player_points") or {}
            matched = pp.get("matched")
            need = pp.get("should_have_count")
            if matched is None and need is None:
                pp_s = "Unknown"
            else:
                pp_s = f"{matched if matched is not None else '?'}/{need if need is not None else '?'}"
            ok_bits = []
            if g.get("ok") is False:
                ok_bits.append("error")
            ok_bits.append("final✓" if g.get("final_score_exact") else "final✗")
            ok_bits.append("pts✓" if g.get("player_points_exact") else "pts✗")
            prec_v, rec_v = g.get("precision"), g.get("recall")
            try:
                pr_ok = (
                    prec_v is not None
                    and rec_v is not None
                    and float(prec_v) >= 0.90
                    and float(rec_v) >= 0.90
                )
            except (TypeError, ValueError):
                pr_ok = False
            ok_bits.append("P/R✓" if pr_ok else "P/R✗")
            result = "PASS" if (
                g.get("final_score_exact")
                and g.get("player_points_exact")
                and pr_ok
            ) else "FAIL (" + ", ".join(ok_bits) + ")"
            lines.append(
                f"| {name} | {prec} | {rec} | {score_s} | {pp_s} | {result} |"
            )
    else:
        lines.append("| — | Unknown | Unknown | Unknown | Unknown | Unknown |")
    lines.append("")

    # Trend
    lines.append("## Trend vs prior panel snapshot")
    lines.append("")
    lines.append(f"- **Comparison:** {trend_note}")
    if trend.get("available"):
        lines.append(f"- **Prior generated_at:** `{trend.get('prior_generated_at')}`")
        dp = trend.get("delta_mean_precision")
        dr = trend.get("delta_mean_recall")
        lines.append(
            f"- **Δ mean precision:** {dp if dp is not None else 'Unknown'} "
            f"({_pct((latest or {}).get('evaluation', {}).get('mean_precision'))} now)"
        )
        lines.append(
            f"- **Δ mean recall:** {dr if dr is not None else 'Unknown'} "
            f"({_pct((latest or {}).get('evaluation', {}).get('mean_recall'))} now)"
        )
        changes = trend.get("gate_changes") or []
        if changes:
            lines.append("- **Gate changes:** " + "; ".join(changes))
        else:
            lines.append("- **Gate changes:** none (same PASS/FAIL pattern)")
    else:
        lines.append(f"- {trend.get('note') or 'baseline / no trend yet'}")
    if history_err:
        lines.append(f"- History: {history_err}")
    lines.append("")

    # Verdict
    lines.append("## Verdict / largest gaps")
    lines.append("")
    for v in build_verdict(latest, trend):
        lines.append(f"- {v}")
    lines.append("")

    # Proven / Inferred / Unknown
    lines.append("## Proven / Inferred / Unknown")
    lines.append("")
    lines.append("### Proven")
    lines.append("")
    if latest and not latest_err:
        lines.append("- Panel metrics from `full_film_panel_latest.json`")
    if activity.get("provenance") == "Proven" and activity.get("available"):
        lines.append("- `analysis_runs` status/progress from `film_analysis.db`")
    if queue.get("hudl_taught_keys") is not None:
        lines.append("- HUDL taught key count from `teach_loop_state.json`")
    if queue.get("hudl_film_tool_total") is not None:
        lines.append("- HUDL film_tool game count from DB")
    if queue.get("hudl_videos_total") is not None:
        lines.append("- HUDL video count from DB")
    if queue.get("failed_hudl_runs") is not None:
        lines.append("- Failed HUDL `analysis_runs` count from DB")
    if not any(
        [
            latest and not latest_err,
            activity.get("provenance") == "Proven",
            queue.get("hudl_taught_keys") is not None,
        ]
    ):
        lines.append("- (none this run)")
    lines.append("")
    lines.append("### Inferred")
    lines.append("")
    if cur and "Inferred" in str(cur.get("source") or ""):
        lines.append("- Current activity inferred from last teach score (no running row)")
    if queue.get("remaining_vs_videos") is not None or queue.get("remaining_vs_film_tool") is not None:
        lines.append("- Queue remaining = total − taught keys (not guaranteed 1:1 with reruns)")
    if trend.get("available"):
        lines.append("- Trend deltas from comparing two panel snapshots")
    if not any(
        [
            cur and "Inferred" in str(cur.get("source") or ""),
            queue.get("remaining_vs_videos") is not None,
            trend.get("available"),
        ]
    ):
        lines.append("- (none this run)")
    lines.append("")
    lines.append("### Unknown")
    lines.append("")
    unknowns: list[str] = []
    if latest_err:
        unknowns.append(f"Panel latest: {latest_err}")
    if teach_err:
        unknowns.append(f"Teach state: {teach_err}")
    if db_err:
        unknowns.append(f"DB: {db_err}")
    if history_err:
        unknowns.append(f"History: {history_err}")
    if not trend.get("available"):
        unknowns.append("Chronological trend (need ≥2 distinct panel snapshots)")
    # Opponent AI points commonly Unknown
    if latest:
        for g in latest.get("games") or []:
            if isinstance(g, dict) and g.get("final_score_status") == "partial":
                unknowns.append(
                    "Opponent final score from AI often unavailable "
                    "(final_score_status=partial on panel games)"
                )
                break
    if not unknowns:
        unknowns.append("(none flagged)")
    for u in unknowns:
        lines.append(f"- {u}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "*Generated by `scripts/generate_learning_status.py`. "
        "No secrets or raw event dumps included.*"
    )
    lines.append("")
    return "\n".join(lines)


def gather(
    *,
    latest_path: Path = LATEST_PATH,
    history_path: Path = HISTORY_PATH,
    teach_path: Path = TEACH_STATE_PATH,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    latest, latest_err = load_json(latest_path)
    if latest is not None and not isinstance(latest, dict):
        latest, latest_err = None, "latest panel JSON is not an object"

    history, history_err = load_history(history_path)
    prior, trend_note = find_prior_snapshot(latest if isinstance(latest, dict) else None, history)
    trend = compute_trend(latest if isinstance(latest, dict) else None, prior)

    teach_state, teach_err = load_json(teach_path)
    if teach_state is not None and not isinstance(teach_state, dict):
        teach_state, teach_err = None, "teach_loop_state.json is not an object"

    db_err = None
    activity: dict[str, Any] = {
        "available": False,
        "status_counts": {},
        "running": [],
        "current": None,
        "notes": [],
        "provenance": "Unknown",
    }
    queue: dict[str, Any] = {
        "hudl_film_tool_total": None,
        "hudl_videos_total": None,
        "hudl_taught_keys": None,
        "remaining_vs_film_tool": None,
        "remaining_vs_videos": None,
        "failed_hudl_runs": None,
        "notes": [],
        "provenance": {},
    }

    if not db_path.exists():
        db_err = f"missing {db_path.name}"
        activity = infer_activity_from_teach(
            teach_state if isinstance(teach_state, dict) else None, activity
        )
        # Still count taught from state
        if isinstance(teach_state, dict):
            taught_keys = [
                k
                for k in (teach_state.get("taught_keys") or [])
                if isinstance(k, str) and k.startswith("hudl_")
            ]
            queue["hudl_taught_keys"] = len(taught_keys)
            queue["provenance"]["hudl_taught_keys"] = "Proven (teach_loop_state.json)"
    else:
        try:
            conn = connect_db(db_path)
            try:
                activity = query_analysis_activity(conn)
                activity = infer_activity_from_teach(
                    teach_state if isinstance(teach_state, dict) else None, activity
                )
                queue = query_hudl_queue(
                    conn, teach_state if isinstance(teach_state, dict) else None
                )
            finally:
                conn.close()
        except sqlite3.Error as exc:
            db_err = f"sqlite error: {exc}"
            activity = infer_activity_from_teach(
                teach_state if isinstance(teach_state, dict) else None, activity
            )
            if isinstance(teach_state, dict):
                taught_keys = [
                    k
                    for k in (teach_state.get("taught_keys") or [])
                    if isinstance(k, str) and k.startswith("hudl_")
                ]
                queue["hudl_taught_keys"] = len(taught_keys)
                queue["provenance"]["hudl_taught_keys"] = "Proven (teach_loop_state.json)"

    generated_local = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    markdown = render_report(
        generated_local=generated_local,
        latest=latest if isinstance(latest, dict) else None,
        latest_err=latest_err,
        prior=prior,
        trend_note=trend_note,
        trend=trend,
        teach_state=teach_state if isinstance(teach_state, dict) else None,
        teach_err=teach_err,
        activity=activity,
        queue=queue,
        db_err=db_err,
        history_err=history_err,
    )
    return {
        "markdown": markdown,
        "generated_local": generated_local,
        "latest_err": latest_err,
        "db_err": db_err,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate docs/LEARNING_STATUS.md")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--latest", type=Path, default=LATEST_PATH)
    ap.add_argument("--history", type=Path, default=HISTORY_PATH)
    ap.add_argument("--teach-state", type=Path, default=TEACH_STATE_PATH)
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args(argv)

    try:
        result = gather(
            latest_path=args.latest,
            history_path=args.history,
            teach_path=args.teach_state,
            db_path=args.db,
        )
    except Exception as exc:  # noqa: BLE001 — keep nightly save alive
        # Last-resort stub report
        stub = (
            "# Learning Status\n\n"
            f"Generated (local): **{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}**\n\n"
            f"Report generation hit a hard error: `{exc}`\n\n"
            "## Proven / Inferred / Unknown\n\n### Unknown\n\n- Full report unavailable due to exception\n"
        )
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(stub, encoding="utf-8")
        except OSError:
            print(f"HARD ERROR: could not write {args.out}: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote stub {args.out} after error: {exc}", flush=True)
        return 0

    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(result["markdown"], encoding="utf-8")
    except OSError as exc:
        print(f"HARD ERROR: could not write {args.out}: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {args.out}", flush=True)
    if result.get("latest_err"):
        print(f"NOTE: {result['latest_err']}", flush=True)
    if result.get("db_err"):
        print(f"NOTE: {result['db_err']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
