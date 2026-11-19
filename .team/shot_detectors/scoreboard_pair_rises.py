"""Stage C — pair Adrian scoreboard rises with the 140 build-set shots (measurement only).

Spec: .team/specs/20_c_job_spec.md (v2, VETTED, Muse AGREE).
Reads the saved Adrian scoreboard track through scoreboard_clock.py (read only; no rebuild).
Changes nothing in the program. applied_to_core stays false. The scoreboard is a checker only:
a make is still ball_through_rim or net_moved_after_shot.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# --- fixed numbers from the spec, set before anything runs — no tuning ---
HOLD_SAMPLES = 3  # ACTIVE.md: the new value holds for 3 one-second samples
WINDOW_MS = 25_000  # BINDING NOTE d; after the shot only: shot t <= rise t <= shot t + 25 s
FREE_THROW_POINTS = 1  # a 1-point rise is a free throw; never a CLEAN make
GAME_ID = "jrhigh_adrian__or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
FILM = "adrian"
# Board columns: Adrian is home ("mustangs"), Liberty is the guest (final 26-51, ACTIVE.md 51-26).
TEAM_OF_COLUMN = {"mustangs": "Adrian", "guest": "Liberty"}
# Recorded results the reading must reproduce before any pairing (ACTIVE.md lines 11-13).
EXPECTED_RISES = 43
EXPECTED_VALUES = {"Liberty": {2: 17, 3: 5, 1: 2}, "Adrian": {2: 5, 3: 1, 1: 13}}
EXPECTED_FINAL = {"Liberty": 51, "Adrian": 26}
# Spec section 6 counts (d1_results.json, 2026-10-31); the script recomputes them and stops if they differ.
EXPECTED_ADRIAN = {"shots": 109, "makes": 38, "misses": 71, "makes_right": 27, "makes_missed": 11}

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (ROOT, HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

OUT_DIRS = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\scoreboard"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/scoreboard"),
]
D1_RESULTS = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_arc\d1_results.json"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/ball_arc/d1_results.json"),
]


def find_rises(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Each team's confirmed score changes. A value is confirmed when it holds for HOLD_SAMPLES
    readable samples in a row (unreadable samples are skipped). A rise's time is the FIRST
    sample that shows the new value (spec section 5 binding note)."""
    rises: List[Dict[str, Any]] = []
    drops: List[Dict[str, Any]] = []
    final: Dict[str, int] = {}
    for column, team in TEAM_OF_COLUMN.items():
        confirmed = 0
        run_value: Optional[int] = None
        run_count = 0
        run_start = 0
        for row in sorted(samples, key=lambda r: int(r.get("timestamp_ms") or 0)):
            value = row.get(column)
            if value is None:
                continue
            value = int(value)
            if value == run_value:
                run_count += 1
            else:
                run_value, run_count, run_start = value, 1, int(row.get("timestamp_ms") or 0)
            if run_count == HOLD_SAMPLES and run_value != confirmed:
                change = {"team": team, "t": run_start, "from": confirmed, "to": run_value,
                          "points": run_value - confirmed}
                (rises if run_value > confirmed else drops).append(change)
                confirmed = run_value
        final[team] = confirmed
    rises.sort(key=lambda r: (r["t"], r["team"]))
    return {"rises": rises, "drops": drops, "final": final}


def check_reading(reading: Dict[str, Any]) -> None:
    """The reading must reproduce the recorded result before any pairing, or the run stops."""
    problems = []
    if len(reading["rises"]) != EXPECTED_RISES:
        problems.append(f"rises {len(reading['rises'])} != {EXPECTED_RISES}")
    if reading["drops"]:
        problems.append(f"{len(reading['drops'])} score drops")
    if reading["final"] != EXPECTED_FINAL:
        problems.append(f"final {reading['final']} != {EXPECTED_FINAL}")
    for team, want in EXPECTED_VALUES.items():
        got: Dict[int, int] = {}
        for r in reading["rises"]:
            if r["team"] == team:
                got[r["points"]] = got.get(r["points"], 0) + 1
        if got != want:
            problems.append(f"{team} rise values {got} != {want}")
    if problems:
        raise SystemExit("READING STOP: " + "; ".join(problems) + ". Stopping for Scott.")


def in_window(shot_t: int, rise_t: int) -> bool:
    return shot_t <= rise_t <= shot_t + WINDOW_MS


def pair(rises: List[Dict[str, Any]], shots: List[Dict[str, Any]], use_team: bool) -> Dict[str, Any]:
    """CLEAN only when a 2/3-point rise has exactly one shot in its window AND that shot has
    exactly one rise (of any value) in its window. Everything else is AMBIGUOUS or NO RISE."""
    def match(rise, shot):
        return in_window(shot["t"], rise["t"]) and (not use_team or shot.get("team") == rise["team"])

    shots_of_rise = [[s["t"] for s in shots if match(r, s)] for r in rises]
    rises_of_shot = {s["t"]: [i for i, r in enumerate(rises) if match(r, s)] for s in shots}
    per_shot: Dict[int, Dict[str, Any]] = {}
    for s in shots:
        idx = rises_of_shot[s["t"]]
        if not idx:
            per_shot[s["t"]] = {"status": "NO RISE", "rises": []}
            continue
        status = "AMBIGUOUS"
        if len(idx) == 1 and len(shots_of_rise[idx[0]]) == 1:
            status = "CLEAN" if rises[idx[0]]["points"] != FREE_THROW_POINTS else "CLEAN_FT"
        per_shot[s["t"]] = {"status": status, "rises": [rises[i] for i in idx]}
    multi = [dict(r, shots=shots_of_rise[i]) for i, r in enumerate(rises) if len(shots_of_rise[i]) > 1]
    unpaired = [r for i, r in enumerate(rises) if not shots_of_rise[i]]
    return {"per_shot": per_shot, "rises_with_many_shots": multi, "rises_with_no_shot": unpaired}


def tally(paired: Dict[str, Any], shots: List[Dict[str, Any]]) -> Dict[str, Any]:
    groups = {
        "makes_still_missed": [s for s in shots if s["gt_make"] and not s["new_pred"]],
        "real_misses": [s for s in shots if not s["gt_make"]],
        "makes_already_right": [s for s in shots if s["gt_make"] and s["new_pred"]],
    }
    out: Dict[str, Any] = {}
    for name, group in groups.items():
        counts = {"CLEAN": 0, "CLEAN_FT": 0, "AMBIGUOUS": 0, "NO RISE": 0}
        for s in group:
            counts[paired["per_shot"][s["t"]]["status"]] += 1
        out[name] = counts
    out["false_makes"] = [s["t"] for s in groups["real_misses"] if paired["per_shot"][s["t"]]["status"] == "CLEAN"]
    out["recovered"] = [s["t"] for s in groups["makes_still_missed"] if paired["per_shot"][s["t"]]["status"] == "CLEAN"]
    return out


def load_adrian_shots(d1_path: Path) -> List[Dict[str, Any]]:
    """The D1 140-shot list (same loader, exactly 140), Adrian only, with D1's verdicts and the
    tag row's team and shot type."""
    from keep_ball_detections import load_build_shot_list
    from measure_net_moved import FILMS

    shots, _, _ = load_build_shot_list()
    d1 = {(r["film"], int(r["t"])): r for r in json.loads(d1_path.read_text(encoding="utf-8"))["shots"]}
    film = next(f for f in FILMS if f["name"] == FILM)
    tag_rows = json.loads((ROOT / film["tags_rel"]).read_text(encoding="utf-8")).get("rows") or []
    from measure_net_moved import clock_ms
    tag_by_t = {}
    for row in tag_rows:
        if row.get("eventtype") in {"2PT", "3PT", "FT"} and row.get("start"):
            tag_by_t.setdefault(clock_ms(row["start"]), row)
    out = []
    for s in shots:
        if s["film"] != FILM:
            continue
        row = tag_by_t.get(s["t"], {})
        out.append({"t": s["t"], "gt_make": s["gt_make"], "new_pred": bool(d1[(FILM, s["t"])]["new_pred"]),
                    "team": row.get("team"), "eventtype": row.get("eventtype"), "label": s.get("label")})
    return out


def check_counts(shots: List[Dict[str, Any]]) -> None:
    got = {
        "shots": len(shots),
        "makes": sum(s["gt_make"] for s in shots),
        "misses": sum(not s["gt_make"] for s in shots),
        "makes_right": sum(s["gt_make"] and s["new_pred"] for s in shots),
        "makes_missed": sum(s["gt_make"] and not s["new_pred"] for s in shots),
    }
    if got != EXPECTED_ADRIAN:
        raise SystemExit(f"COUNT STOP: {got} != {EXPECTED_ADRIAN}. Stopping for Scott.")


def write_report(out_dir: Path, reading, shots, by_time, by_team) -> None:
    t_time, t_team = tally(by_time, shots), tally(by_team, shots)
    results = {"applied_to_core": False, "window_ms": WINDOW_MS, "hold_samples": HOLD_SAMPLES,
               "rises": reading["rises"], "final": reading["final"],
               "time_only": {"tally": t_time, **{k: v for k, v in by_time.items() if k != "per_shot"},
                             "per_shot": {str(k): v for k, v in by_time["per_shot"].items()}},
               "time_and_team": {"tally": t_team, **{k: v for k, v in by_team.items() if k != "per_shot"},
                                 "per_shot": {str(k): v for k, v in by_team["per_shot"].items()}}}
    (out_dir / "pairs_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    def clock(ms):
        return f"{ms // 60000}:{(ms % 60000) / 1000:04.1f}"

    lines = ["# Stage C — scoreboard pairing, Adrian (measurement only)", "",
             "Spec: .team/specs/20_c_job_spec.md v2. applied_to_core: false. Nothing in the program changed.",
             f"Window: shot t to shot t + {WINDOW_MS // 1000} s. Rise = new value held {HOLD_SAMPLES} samples; "
             "rise time = first sample showing it. 1-point rises (free throws) never count as a make.", "",
             f"Reading check: {len(reading['rises'])} rises, final Liberty {reading['final']['Liberty']} - "
             f"Adrian {reading['final']['Adrian']} (matches the recorded result).", ""]
    for title, t, p in (("Time only (the count that matters: a new game has no tag rows)", t_time, by_time),
                        ("Time plus shooting team from the tag rows", t_team, by_team)):
        lines += [f"## {title}", "", "| Group | CLEAN 2/3 | CLEAN 1-pt | AMBIGUOUS | NO RISE |", "|---|---|---|---|---|"]
        for g in ("makes_still_missed", "real_misses", "makes_already_right"):
            c = t[g]
            lines.append(f"| {g.replace('_', ' ')} | {c['CLEAN']} | {c['CLEAN_FT']} | {c['AMBIGUOUS']} | {c['NO RISE']} |")
        lines += ["", f"**Hard gate — real misses with a CLEAN 2/3-point rise (false makes): {len(t['false_makes'])}** "
                  + (", ".join(clock(x) for x in t["false_makes"]) if t["false_makes"] else ""),
                  f"Missed makes recovered (CLEAN): {len(t['recovered'])} " + ", ".join(clock(x) for x in t["recovered"]),
                  f"Rises matching more than one shot: {len(p['rises_with_many_shots'])}; rises with no shot: "
                  f"{len(p['rises_with_no_shot'])}", ""]
        lines += ["| Shot | Tag | D1 call | Status | Rise(s) |", "|---|---|---|---|---|"]
        for s in shots:
            if not s["gt_make"] or not s["new_pred"]:
                ps = p["per_shot"][s["t"]]
                rs = "; ".join(f"{r['team']} +{r['points']} at {clock(r['t'])}" for r in ps["rises"]) or "-"
                if s["gt_make"] or ps["status"] != "NO RISE":
                    lines.append(f"| {clock(s['t'])} | {s['label']} ({s['team']}) | "
                                 f"{'make' if s['new_pred'] else 'miss'} | {ps['status']} | {rs} |")
        lines.append("")
    lines += ["## Free-throw rises (1 point)", "", "| Rise | Team | Shots in window (time only) |", "|---|---|---|"]
    for r in reading["rises"]:
        if r["points"] == FREE_THROW_POINTS:
            near = [clock(s["t"]) for s in shots if in_window(s["t"], r["t"])]
            lines.append(f"| {clock(r['t'])} | {r['team']} | {', '.join(near) or '-'} |")
    lines += ["", "## Notus", "",
              "The Notus board reader is parked (.team/specs/09_notus_reader_v9_SHELVED.md). Scott decides any Notus work.",
              "", "Stop for Scott."]
    (out_dir / "pairs_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    from scoreboard_clock import load_scoreboard_track

    samples = load_scoreboard_track(GAME_ID)
    if not samples:
        raise SystemExit(f"No scoreboard track for {GAME_ID}. Stopping for Scott.")
    reading = find_rises(samples)
    check_reading(reading)
    d1_path = next((p for p in D1_RESULTS if p.exists()), None)
    if d1_path is None:
        raise SystemExit("d1_results.json not found. Stopping for Scott.")
    shots = load_adrian_shots(d1_path)
    check_counts(shots)
    by_time = pair(reading["rises"], shots, use_team=False)
    by_team = pair(reading["rises"], shots, use_team=True)
    out_dir = next((p for p in OUT_DIRS if p.parent.exists()), OUT_DIRS[0])
    out_dir.mkdir(parents=True, exist_ok=True)
    write_report(out_dir, reading, shots, by_time, by_team)
    t = tally(by_time, shots)
    print(f"TIME ONLY: recovered {len(t['recovered'])} of {EXPECTED_ADRIAN['makes_missed']}; "
          f"false makes {len(t['false_makes'])}; missed makes {t['makes_still_missed']}; misses {t['real_misses']}; "
          f"already right {t['makes_already_right']}")
    print(f"Wrote {out_dir / 'pairs_report.md'}")


if __name__ == "__main__":
    main()
