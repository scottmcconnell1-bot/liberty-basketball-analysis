#!/usr/bin/env python3
"""Fixed full-film learning evaluation panel (Scott success criteria).

Hard gates:
  - final_score_exact == 100% (Liberty + opponent totals vs truth)
  - player_points_exact == 100% (each player who should have points)
  - event precision AND recall >= 90%

Usage:
  py -3.12 scripts/score_full_film_panel.py
  py -3.12 scripts/score_full_film_panel.py --db film_analysis.db

Exit code 0 on normal completion (including FAIL gates) so teach loops keep running.
Exit code 1 only on hard script errors (missing compare module, unreadable DB, etc.).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tag-exports"))

from boxscore_constraints import (  # noqa: E402
    aggregate_ai_caps,
    extract_jersey,
    reference_to_game_caps,
)
from compare_ai_to_hoops_pbp import (  # noqa: E402
    load_ai_events,
    load_truth_rows,
)
from manual_vs_ai_q1_compare import convert_ai_events_to_stat_rows  # noqa: E402

DB_PATH = ROOT / "film_analysis.db"
TARGETS_PATH = ROOT / "data" / "hoopsalytics" / "full_film_panel_targets.json"
LATEST_PATH = ROOT / "data" / "hoopsalytics" / "full_film_panel_latest.json"
HISTORY_PATH = ROOT / "data" / "hoopsalytics" / "full_film_panel_history.jsonl"
COMPARE_SCRIPT = ROOT / "scripts" / "compare_ai_to_hoops_pbp.py"
PY = sys.executable

# Fixed panel — full-film only (no --end-ms)
PANEL_GAMES: list[dict[str, str]] = [
    {
        "name": "Idaho City",
        "film_id": "hoopsalytics-idaho_city-2026-01-05",
        "analysis_key": "hoopsalytics_idaho_city_2026-01-05__rerun_20260727_030810",
    },
    {
        "name": "Harper",
        "film_id": "hoopsalytics-harper_or-2025-12-05",
        "analysis_key": "hoopsalytics_harper_or_2025-12-05",
    },
    {
        "name": "Burns",
        "film_id": "hoopsalytics-burns_or-2025-12-06",
        "analysis_key": "hoopsalytics_burns_or_2025-12-06",
    },
    {
        "name": "Nyssa",
        "film_id": "hoopsalytics-nyssa-2025-12-04",
        "analysis_key": "hoopsalytics_nyssa_2025-12-04",
    },
    {
        "name": "Melba",
        "film_id": "hoopsalytics-melba-2025-12-09",
        "analysis_key": "hoopsalytics_melba_2025-12-09__rerun_20260723_022331",
    },
    {
        "name": "Camas",
        "film_id": "hoopsalytics-camas_county-2025-12-13",
        "analysis_key": "hoopsalytics_camas_county_2025-12-13__rerun_20260723_022404",
    },
]

DEFAULT_TARGETS = {
    "final_score_exact": 1.0,
    "player_points_exact": 1.0,
    "event_precision_min": 0.90,
    "event_recall_min": 0.90,
}

POINTS_FOR = {"2PT": 2, "3PT": 3, "FT": 1}


def load_targets(path: Path = TARGETS_PATH) -> dict[str, float]:
    if not path.exists():
        return dict(DEFAULT_TARGETS)
    data = json.loads(path.read_text(encoding="utf-8"))
    out = dict(DEFAULT_TARGETS)
    for key in DEFAULT_TARGETS:
        if key in data:
            out[key] = float(data[key])
    return out


def _connect(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db), timeout=60.0)
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def _event_count(conn: sqlite3.Connection, analysis_key: str) -> int:
    row = conn.execute(
        """SELECT COUNT(*) FROM events
           WHERE game_id = ? AND COALESCE(source_type, 'ai') = 'ai'""",
        (analysis_key,),
    ).fetchone()
    return int(row[0] if row else 0)


def _fallback_analysis_key(conn: sqlite3.Connection, preferred: str) -> tuple[str, list[str]]:
    """If preferred key has no events, try base key (strip __rerun_)."""
    flags: list[str] = []
    n = _event_count(conn, preferred)
    if n > 0:
        return preferred, flags
    if "__rerun_" in preferred:
        base = preferred.split("__rerun_", 1)[0]
        n_base = _event_count(conn, base)
        if n_base > 0:
            flags.append(
                f"FLAG: preferred key {preferred!r} has 0 events; "
                f"fell back to {base!r} ({n_base} events)"
            )
            return base, flags
    flags.append(f"FLAG: no AI events for {preferred!r}")
    return preferred, flags


def _load_film_state(conn: sqlite3.Connection, film_id: str) -> dict:
    row = conn.execute(
        "SELECT state_json FROM film_tool_games WHERE client_game_id = ?",
        (film_id,),
    ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row[0] or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _points_from_pbp_rows(rows: list[dict], *, teams: set[str] | None = None) -> dict[str, int]:
    """Sum Make points by team from Film Tool PBP rows."""
    out: dict[str, int] = defaultdict(int)
    for r in rows or []:
        team = str(r.get("team") or "")
        if teams is not None and team not in teams:
            continue
        if str(r.get("result") or "") != "Make":
            continue
        add = POINTS_FOR.get(str(r.get("eventtype") or ""))
        if add:
            out[team] += add
    return dict(out)


def _player_points_from_pbp(rows: list[dict], *, liberty_teams: set[str]) -> dict[str, int]:
    """Jersey → points from Liberty Make rows."""
    out: dict[str, int] = defaultdict(int)
    for r in rows or []:
        if str(r.get("team") or "") not in liberty_teams:
            continue
        if str(r.get("result") or "") != "Make":
            continue
        add = POINTS_FOR.get(str(r.get("eventtype") or ""))
        if not add:
            continue
        jersey = extract_jersey(r.get("player"))
        if jersey:
            out[jersey] += add
    return dict(out)


def _ai_points_by_jersey(events: list[dict]) -> tuple[int, dict[str, int]]:
    """Liberty-oriented AI point totals from shot buckets."""
    caps = aggregate_ai_caps(events)
    team = caps.get("team") or {}
    team_pts = (
        2 * int(team.get("2pt_make") or 0)
        + 3 * int(team.get("3pt_make") or 0)
        + 1 * int(team.get("ft_make") or 0)
    )
    by_jersey: dict[str, int] = {}
    for jersey, slot in (caps.get("by_jersey") or {}).items():
        by_jersey[str(jersey)] = (
            2 * int(slot.get("2pt_make") or 0)
            + 3 * int(slot.get("3pt_make") or 0)
            + 1 * int(slot.get("ft_make") or 0)
        )
    return team_pts, by_jersey


def _truth_final_and_players(state: dict) -> dict[str, Any]:
    """Build truth final score + per-player points (Proven when box/PBP present)."""
    rows = state.get("rows") or []
    our = str(state.get("ourTeam") or "Liberty")
    opp_name = str(state.get("opponent") or state.get("homeTeam") or state.get("awayTeam") or "Opponent")
    if opp_name == our:
        # away/home may both be set; pick the non-Liberty side
        home = str(state.get("homeTeam") or "")
        away = str(state.get("awayTeam") or "")
        opp_name = home if home and home != our else away

    liberty_teams = {our, "Liberty", "Our Team"}
    pbp_team_pts = _points_from_pbp_rows(rows)
    liberty_pbp = sum(v for k, v in pbp_team_pts.items() if k in liberty_teams)
    opp_pbp = sum(v for k, v in pbp_team_pts.items() if k not in liberty_teams)

    box = state.get("referenceBoxScore") or {}
    box_caps = reference_to_game_caps(box) if box else {}
    box_team_pts = int((box_caps.get("team") or {}).get("points") or 0) if box_caps else None
    box_by_jersey: dict[str, int] = {}
    for jersey, caps in (box_caps.get("by_jersey") or {}).items():
        box_by_jersey[str(jersey)] = int(caps.get("points") or 0)

    # Prefer boxscore Liberty total when present; else PBP
    liberty_truth = box_team_pts if box_team_pts is not None and box_team_pts > 0 else liberty_pbp
    if box_team_pts is not None and box_team_pts > 0 and liberty_pbp and box_team_pts != liberty_pbp:
        # Keep box as authority; note mismatch for operators
        liberty_source = "referenceBoxScore.team_totals"
    elif box_team_pts is not None and box_team_pts > 0:
        liberty_source = "referenceBoxScore.team_totals"
    else:
        liberty_source = "pbp_makes"

    player_truth = box_by_jersey if box_by_jersey else _player_points_from_pbp(rows, liberty_teams=liberty_teams)
    player_source = "referenceBoxScore.players" if box_by_jersey else "pbp_makes"

    return {
        "our_team": our,
        "opponent_name": opp_name,
        "liberty_points": int(liberty_truth or 0),
        "opponent_points": int(opp_pbp or 0),
        "liberty_source": liberty_source,
        "opponent_source": "pbp_makes",
        "player_points": {k: int(v) for k, v in sorted(player_truth.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 999)},
        "player_source": player_source,
        "status": "proven" if (liberty_truth or player_truth) else "unknown",
    }


def score_final_and_players(
    *,
    truth: dict[str, Any],
    ai_events: list[dict],
) -> dict[str, Any]:
    ai_liberty_pts, ai_by_jersey = _ai_points_by_jersey(ai_events)
    # Opponent scoring is not reliably present on AI events (Liberty-oriented pipeline).
    ai_opponent_pts = None
    gaps: list[str] = []

    liberty_exact = int(ai_liberty_pts) == int(truth.get("liberty_points") or 0)
    if ai_opponent_pts is None:
        gaps.append("opponent_ai_points_unavailable")
        opponent_exact = None  # Unknown — do not fake PASS
    else:
        opponent_exact = int(ai_opponent_pts) == int(truth.get("opponent_points") or 0)

    if opponent_exact is True and liberty_exact:
        final_exact = True
        final_status = "proven"
    elif opponent_exact is None:
        final_exact = False
        final_status = "partial"
        gaps.append("final_score_requires_both_team_totals; opponent side Unknown from AI")
    else:
        final_exact = False
        final_status = "proven"

    # Player points: every truth player with points > 0 must match exactly
    truth_players = truth.get("player_points") or {}
    should_have = {j: p for j, p in truth_players.items() if int(p) > 0}
    mismatches: list[dict[str, Any]] = []
    matched = 0
    for jersey, tpts in sorted(should_have.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 999):
        apts = int(ai_by_jersey.get(jersey) or 0)
        if apts == int(tpts):
            matched += 1
        else:
            mismatches.append({"jersey": jersey, "truth": int(tpts), "ai": apts})

    # AI-only scorers (jersey with AI points but truth 0 / missing) — report, fail exact
    extra_ai = []
    for jersey, apts in ai_by_jersey.items():
        if int(apts) <= 0:
            continue
        if int(truth_players.get(jersey) or 0) == 0:
            extra_ai.append({"jersey": jersey, "ai": int(apts), "truth": int(truth_players.get(jersey) or 0)})

    player_exact = (
        bool(should_have)
        and matched == len(should_have)
        and not mismatches
        and not extra_ai
    )
    if not should_have:
        player_status = "unknown"
        gaps.append("no_truth_player_points_found")
        player_exact = False
    elif not ai_by_jersey and ai_liberty_pts == 0:
        player_status = "partial"
        gaps.append("ai_player_jersey_matching_empty")
        player_exact = False
    else:
        player_status = "proven"

    rate = (matched / len(should_have)) if should_have else 0.0

    return {
        "final_score_exact": bool(final_exact),
        "final_score_status": final_status,
        "final_score": {
            "truth": {
                "liberty": truth.get("liberty_points"),
                "opponent": truth.get("opponent_points"),
                "opponent_name": truth.get("opponent_name"),
            },
            "ai": {"liberty": ai_liberty_pts, "opponent": ai_opponent_pts},
            "liberty_exact": liberty_exact,
            "opponent_exact": opponent_exact,
        },
        "player_points_exact": bool(player_exact),
        "player_points_status": player_status,
        "player_points": {
            "truth": truth_players,
            "ai": {k: int(v) for k, v in sorted(ai_by_jersey.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 999)},
            "should_have_points": should_have,
            "matched": matched,
            "should_have_count": len(should_have),
            "match_rate": round(rate, 4),
            "mismatches": mismatches,
            "extra_ai_scorers": extra_ai,
        },
        "gaps": gaps,
    }


def run_compare(film_id: str, analysis_key: str, db: Path) -> dict[str, Any]:
    """Run compare_ai_to_hoops_pbp (full film, no --end-ms) and load JSON scorecard."""
    if not COMPARE_SCRIPT.exists():
        raise FileNotFoundError(f"Missing compare script: {COMPARE_SCRIPT}")
    cmd = [
        PY,
        str(COMPARE_SCRIPT),
        "--film-id",
        film_id,
        "--analysis-key",
        analysis_key,
        "--db",
        str(db),
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    score_path = ROOT / "data" / "hoopsalytics" / f"compare_{film_id.replace('-', '_')}.json"
    if not score_path.exists():
        raise RuntimeError(
            f"compare did not write {score_path}\n"
            f"exit={proc.returncode}\nstdout={proc.stdout[-2000:]}\nstderr={proc.stderr[-2000:]}"
        )
    payload = json.loads(score_path.read_text(encoding="utf-8"))
    payload["_compare_exit"] = proc.returncode
    return payload


def score_game(conn: sqlite3.Connection, game: dict[str, str], db: Path) -> dict[str, Any]:
    name = game["name"]
    film_id = game["film_id"]
    preferred_key = game["analysis_key"]
    analysis_key, flags = _fallback_analysis_key(conn, preferred_key)
    event_n = _event_count(conn, analysis_key)

    result: dict[str, Any] = {
        "name": name,
        "film_id": film_id,
        "analysis_key_preferred": preferred_key,
        "analysis_key": analysis_key,
        "event_count": event_n,
        "flags": flags,
    }

    if event_n <= 0:
        result.update(
            {
                "ok": False,
                "error": "no_events",
                "precision": None,
                "recall": None,
                "final_score_exact": False,
                "player_points_exact": False,
                "final_score_status": "unknown",
                "player_points_status": "unknown",
                "gaps": flags + ["no_ai_events"],
            }
        )
        return result

    compare = run_compare(film_id, analysis_key, db)
    state = _load_film_state(conn, film_id)
    truth = _truth_final_and_players(state)
    ai_events = load_ai_events(conn, analysis_key)
    score_bits = score_final_and_players(truth=truth, ai_events=ai_events)

    # Sanity: truth Liberty rows exist for compare
    try:
        truth_rows = load_truth_rows(conn, film_id)
        result["truth_stat_events"] = len(truth_rows)
        # Ensure convert path works (defensive)
        _ = convert_ai_events_to_stat_rows(ai_events[:1] if ai_events else [], team_name="Liberty")
    except SystemExit as exc:
        result["truth_load_error"] = str(exc)
        flags.append(f"truth_load_error: {exc}")

    result.update(
        {
            "ok": True,
            "precision": compare.get("precision"),
            "recall": compare.get("recall"),
            "exact": compare.get("exact"),
            "disagree": compare.get("disagree"),
            "miss": compare.get("miss"),
            "extra": compare.get("extra"),
            "truth_events": compare.get("truth"),
            "ai_stat_events": compare.get("ai"),
            "truth_meta": {
                "liberty_source": truth.get("liberty_source"),
                "opponent_source": truth.get("opponent_source"),
                "player_source": truth.get("player_source"),
                "status": truth.get("status"),
            },
            **score_bits,
            "flags": flags + list(score_bits.get("gaps") or []),
        }
    )
    return result


def evaluate_gates(games: list[dict[str, Any]], targets: dict[str, float]) -> dict[str, Any]:
    """Aggregate panel gates. Unknown/partial final_score or player_points → FAIL (never fake 100%)."""
    precisions = [g["precision"] for g in games if g.get("precision") is not None]
    recalls = [g["recall"] for g in games if g.get("recall") is not None]
    mean_prec = (sum(precisions) / len(precisions)) if precisions else 0.0
    mean_rec = (sum(recalls) / len(recalls)) if recalls else 0.0

    all_final = all(bool(g.get("final_score_exact")) for g in games) if games else False
    all_players = all(bool(g.get("player_points_exact")) for g in games) if games else False

    # Per-metric PASS/FAIL
    gates = {
        "final_score_exact": {
            "required": targets["final_score_exact"],
            "actual": 1.0 if all_final else 0.0,
            "pass": all_final,
            "note": "All panel games must match Liberty+opponent final totals exactly",
        },
        "player_points_exact": {
            "required": targets["player_points_exact"],
            "actual": 1.0 if all_players else 0.0,
            "pass": all_players,
            "note": "All scorers with truth points > 0 must match exactly",
        },
        "event_precision_min": {
            "required": targets["event_precision_min"],
            "actual": round(mean_prec, 4),
            "pass": mean_prec >= targets["event_precision_min"],
            "note": "Mean event precision across panel games",
        },
        "event_recall_min": {
            "required": targets["event_recall_min"],
            "actual": round(mean_rec, 4),
            "pass": mean_rec >= targets["event_recall_min"],
            "note": "Mean event recall across panel games",
        },
    }
    overall = all(g["pass"] for g in gates.values())
    return {
        "gates": gates,
        "overall_pass": overall,
        "mean_precision": round(mean_prec, 4),
        "mean_recall": round(mean_rec, 4),
    }


def print_summary(payload: dict[str, Any]) -> None:
    print("=" * 64)
    print("FULL-FILM PANEL GATE SUMMARY")
    print("=" * 64)
    print(f"Generated: {payload.get('generated_at')}")
    print(f"Games:     {len(payload.get('games') or [])}")
    print()
    for g in payload.get("games") or []:
        flags = g.get("flags") or []
        flag_s = f"  FLAGS={flags}" if flags else ""
        print(
            f"  {g.get('name'):12}  "
            f"prec={g.get('precision')}  rec={g.get('recall')}  "
            f"final_exact={g.get('final_score_exact')}({g.get('final_score_status')})  "
            f"player_exact={g.get('player_points_exact')}({g.get('player_points_status')})  "
            f"events={g.get('event_count')}{flag_s}"
        )
    print()
    eval_ = payload.get("evaluation") or {}
    for key, gate in (eval_.get("gates") or {}).items():
        status = "PASS" if gate.get("pass") else "FAIL"
        print(
            f"  [{status}] {key}: actual={gate.get('actual')}  "
            f"required={gate.get('required')}  ({gate.get('note')})"
        )
    overall = "PASS" if eval_.get("overall_pass") else "FAIL"
    print()
    print(f"OVERALL GATE: {overall}")
    print(f"Wrote {LATEST_PATH}")
    print(f"Appended {HISTORY_PATH}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Score fixed full-film learning panel")
    ap.add_argument("--db", type=Path, default=DB_PATH)
    ap.add_argument("--targets", type=Path, default=TARGETS_PATH)
    ap.add_argument(
        "--regen",
        action="store_true",
        help="Reserved: full regenerate before score (not default; keep panel minutes-fast)",
    )
    args = ap.parse_args()

    if args.regen:
        print("NOTE: --regen requested but panel default is compare-only; skipping regenerate.", flush=True)

    if not COMPARE_SCRIPT.exists():
        print(f"HARD ERROR: missing {COMPARE_SCRIPT}", file=sys.stderr)
        return 1
    if not args.db.exists():
        print(f"HARD ERROR: DB not found: {args.db}", file=sys.stderr)
        return 1

    try:
        targets = load_targets(args.targets)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"HARD ERROR: bad targets file: {exc}", file=sys.stderr)
        return 1

    try:
        conn = _connect(args.db)
    except sqlite3.Error as exc:
        print(f"HARD ERROR: cannot open DB: {exc}", file=sys.stderr)
        return 1

    games_out: list[dict[str, Any]] = []
    try:
        for game in PANEL_GAMES:
            print(f"PANEL scoring {game['name']}…", flush=True)
            try:
                games_out.append(score_game(conn, game, args.db))
            except Exception as exc:  # noqa: BLE001 — per-game isolation
                games_out.append(
                    {
                        "name": game["name"],
                        "film_id": game["film_id"],
                        "analysis_key": game["analysis_key"],
                        "ok": False,
                        "error": str(exc),
                        "precision": None,
                        "recall": None,
                        "final_score_exact": False,
                        "player_points_exact": False,
                        "final_score_status": "unknown",
                        "player_points_status": "unknown",
                        "flags": [f"score_error: {exc}"],
                    }
                )
    finally:
        conn.close()

    evaluation = evaluate_gates(games_out, targets)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "targets": targets,
        "panel": PANEL_GAMES,
        "games": games_out,
        "evaluation": evaluation,
        "criteria": {
            "final_score_exact": "1.0 (100%)",
            "player_points_exact": "1.0 (100%)",
            "event_precision_min": 0.90,
            "event_recall_min": 0.90,
            "note": "Do not use 80/75 targets — Scott corrected to 100/100/90/90",
        },
    }

    LATEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    LATEST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with HISTORY_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, separators=(",", ":")) + "\n")

    print_summary(payload)
    # Always 0 for ops — gate FAIL must not kill teach loop
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
