"""Build Manual vs AI Q1 side-by-side table + JSON for canvas/markdown."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "film_analysis.db"
OUT_MD = Path(__file__).resolve().parent / "manual_vs_ai_q1_side_by_side.md"
OUT_JSON = Path(__file__).resolve().parent / "manual_vs_ai_q1_side_by_side.json"
CLIENT_GAME_ID = "game-1784304093435"
KEY = (
    "nfhs_gam30b09cbb4f_20260706_173156_trim_20260706_180340_"
    "trim_20260706_185339_trim_20260706_191311__rerun_20260718_215754"
)
Q1_END = 871
STAT_TYPES = {
    "2PT", "3PT", "FT", "Assist", "Steal", "Turnover", "Foul", "Block",
    "OffRebound", "DefRebound",
}
SKIP_AI = {"make", "miss", "possession_change"}
TOL_MS = 8000


def time_to_sec(value) -> float:
    s = str(value or "").strip()
    if not s:
        return 0.0
    parts = s.split(":")
    if len(parts) == 1:
        try:
            return float(parts[0])
        except ValueError:
            return 0.0
    try:
        return (int(parts[0]) or 0) * 60 + float(parts[1] or 0)
    except ValueError:
        return 0.0


def fmt_mmss(sec: float) -> str:
    total = int(round(sec))
    return f"{total // 60}:{total % 60:02d}"


def manual_label(row) -> str:
    et = str(row.get("eventtype") or "")
    res = str(row.get("result") or "NA")
    if et in ("2PT", "3PT", "FT"):
        return f"{et} {res}"
    if et == "DefRebound":
        return "DefRebound"
    if et == "OffRebound":
        return "OffRebound"
    return et or str(row.get("label") or "")


def ai_label(event) -> str:
    d = dict(event) if not isinstance(event, dict) else event
    et = str(d.get("event_type") or "")
    sr = str(d.get("shot_result") or "").strip()
    details = {}
    try:
        details = json.loads(d.get("details_json") or "{}")
    except Exception:
        details = {}
    if et == "shot":
        shot_kind = str(details.get("shot_type") or details.get("shotType") or "2pt").lower()
        prefix = "3PT" if "3" in shot_kind else ("FT" if ("ft" in shot_kind or "free" in shot_kind) else "2PT")
        if sr.lower() == "make":
            return f"{prefix} Make"
        if sr.lower() == "miss":
            return f"{prefix} Miss"
        return f"{prefix} {sr or '?'}"
    if et == "rebound":
        rebound_kind = str(details.get("rebound_type") or details.get("reboundType") or "").lower()
        return "OffRebound" if "off" in rebound_kind else "DefRebound"
    if et == "assist":
        return "Assist"
    if et == "foul":
        return "Foul"
    if et == "block":
        return "Block"
    if et == "steal":
        return "Steal"
    if et == "turnover":
        return "Turnover"
    return et


def team_fill(team: str) -> str:
    t = (team or "").strip()
    return t if t else "Liberty"


conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Manual from film_tool_games.state_json
fg = cur.execute(
    "SELECT state_json, analysis_key FROM film_tool_games WHERE client_game_id=?",
    (CLIENT_GAME_ID,),
).fetchone()
state = json.loads(fg["state_json"])
manual_all = state.get("rows") or []
manual = []
for row in manual_all:
    if row.get("quarter") and row.get("quarter") != "Q1":
        continue
    sec = time_to_sec(row.get("start"))
    if sec > Q1_END:
        continue
    et = str(row.get("eventtype") or "")
    if et in {"EndQTR", "StartQTR"}:
        continue
    cat = str(row.get("category") or "")
    if cat == "Quarter" and et not in STAT_TYPES:
        continue
    if et not in STAT_TYPES:
        continue
    manual.append({
        "time": fmt_mmss(sec),
        "time_sec": round(sec, 1),
        "time_ms": int(round(sec * 1000)),
        "team": team_fill(row.get("team")),
        "label": manual_label(row),
        "player": str(row.get("player") or "").strip() or "—",
        "eventtype": et,
        "result": str(row.get("result") or "NA"),
    })
manual.sort(key=lambda r: (r["time_ms"], r["label"], r["player"]))

# AI events
events = cur.execute(
    "SELECT id, event_type, shot_result, timestamp_ms, player FROM events WHERE game_id=? ORDER BY timestamp_ms, id",
    (KEY,),
).fetchall()
ai = []
for e in events:
    if e["event_type"] in SKIP_AI:
        continue
    ts = int(e["timestamp_ms"] or 0)
    if ts > Q1_END * 1000:
        continue
    ai.append({
        "time": fmt_mmss(ts / 1000),
        "time_sec": round(ts / 1000, 1),
        "time_ms": ts,
        "team": "—",  # Film Tool converter assigns Our Team; raw events lack team
        "label": ai_label(e),
        "player": str(e["player"] or "").strip() or "Unknown",
        "event_id": e["id"],
        "event_type": e["event_type"],
        "shot_result": e["shot_result"],
    })
ai.sort(key=lambda r: (r["time_ms"], r["label"], r["player"]))

# Greedy exact match: same label + |dt| <= 8s
ai_used = set()
pairs = []
exact = 0
for m in manual:
    best_i = None
    best_dt = None
    for i, a in enumerate(ai):
        if i in ai_used:
            continue
        if a["label"] != m["label"]:
            continue
        dt = abs(a["time_ms"] - m["time_ms"])
        if dt <= TOL_MS and (best_dt is None or dt < best_dt):
            best_i = i
            best_dt = dt
    if best_i is not None:
        ai_used.add(best_i)
        a = ai[best_i]
        exact += 1
        pairs.append({
            "status": "EXACT",
            "dt_sec": round(best_dt / 1000, 1),
            "manual": m,
            "ai": a,
        })
    else:
        pairs.append({
            "status": "MANUAL_ONLY",
            "dt_sec": None,
            "manual": m,
            "ai": None,
        })

for i, a in enumerate(ai):
    if i not in ai_used:
        pairs.append({
            "status": "AI_ONLY",
            "dt_sec": None,
            "manual": None,
            "ai": a,
        })

# Sort display: by manual time if present else AI time
def sort_key(p):
    if p["manual"]:
        return (0, p["manual"]["time_ms"], p["status"])
    return (1, p["ai"]["time_ms"], p["status"])

pairs.sort(key=sort_key)

manual_only = sum(1 for p in pairs if p["status"] == "MANUAL_ONLY")
ai_only = sum(1 for p in pairs if p["status"] == "AI_ONLY")
mismatches = manual_only + ai_only  # no near-miss label disagreements in this pass

# Detection / event span proof
det = cur.execute(
    "SELECT MIN(frame_number), MAX(frame_number), MIN(timestamp_ms), MAX(timestamp_ms), COUNT(*) FROM detections WHERE game_id=?",
    (KEY,),
).fetchone()
ev_span = cur.execute(
    "SELECT MIN(timestamp_ms), MAX(timestamp_ms), COUNT(*) FROM events WHERE game_id=?",
    (KEY,),
).fetchone()
run = cur.execute(
    "SELECT video_path, started_at, completed_at, status, error_message, run_label "
    "FROM analysis_runs WHERE analysis_key=?",
    (KEY,),
).fetchone()
vid = cur.execute("SELECT file_path, file_size_bytes, game_id FROM videos WHERE id=8").fetchone()

ai_ts_min = min((a["time_ms"] for a in ai), default=None)
ai_ts_max = max((a["time_ms"] for a in ai), default=None)
ai_span_sec = round((ai_ts_max - ai_ts_min) / 1000, 2) if ai_ts_min is not None and ai_ts_max is not None else 0.0
det_ts_max = det[3] if det and det[3] is not None else 0
covers_q1 = bool(det_ts_max >= Q1_END * 1000 * 0.95 and (ai_ts_max or 0) >= Q1_END * 1000 * 0.90)

if covers_q1:
    verdict = "Q1 TIME COVERAGE OK — compare event quality (exact / manual-only / AI-only)"
    root_bug = (
        f"GPU Q1 rerun `{KEY}` produced detections through {det_ts_max} ms "
        f"(frames {det[0]}–{det[1]}) and comparable AI events "
        f"{ai_ts_min}–{ai_ts_max} ms. Run status={run['status'] if run else '?'}"
        + (
            f" (post-process error after events: {run['error_message'][:120]}…)"
            if run and run["status"] == "failed" and run["error_message"]
            else ""
        )
        + ". Timestamp span now covers ~full Q1; remaining gaps are match quality, not missing timeline."
    )
    clock_offset_viable = True
    clock_offset_note = "AI timestamps span Q1; constant clock-offset search is no longer blocked by a ~20s window."
else:
    verdict = "EXACT_MATCH_FAILS — broken AI time base / incomplete analysis coverage"
    root_bug = (
        "AI rerun did not cover full Q1 timeline. "
        f"Detections max ts={det_ts_max} ms; comparable AI events "
        f"{ai_ts_min}–{ai_ts_max} ms."
    )
    clock_offset_viable = False
    clock_offset_note = (
        "No constant offset maps a short AI window onto a 14.5-minute manual Q1."
    )

diag = {
    "verdict": verdict,
    "root_bug": root_bug,
    "covers_q1": covers_q1,
    "ai_span_sec": ai_span_sec,
    "ai_ts_min_ms": ai_ts_min,
    "ai_ts_max_ms": ai_ts_max,
    "raw_event_ts_min_ms": ev_span[0],
    "raw_event_ts_max_ms": ev_span[1],
    "raw_event_count": ev_span[2],
    "det_frame_min": det[0],
    "det_frame_max": det[1],
    "det_ts_min_ms": det[2],
    "det_ts_max_ms": det[3],
    "det_count": det[4],
    "implied_fps": round(det[1] / (det[3] / 1000), 3) if det[3] else None,
    "analysis_video_path": run["video_path"] if run else None,
    "analysis_video_exists": bool(run and run["video_path"] and Path(run["video_path"]).exists()),
    "run_status": run["status"] if run else None,
    "run_error": run["error_message"] if run else None,
    "run_label": run["run_label"] if run else None,
    "videos_8_path": vid["file_path"] if vid else None,
    "videos_8_size": vid["file_size_bytes"] if vid else None,
    "videos_8_game_id": vid["game_id"] if vid else None,
    "full_video_duration_sec": 7290.037,
    "full_video_fps": 25,
    "clock_offset_viable": clock_offset_viable,
    "clock_offset_note": clock_offset_note,
    "duplicate_note": (
        "AI may emit duplicate shot rows at the same timestamp "
        "(e.g. multiple 2PT Make for the same player)."
    ),
}

kpis = {
    "exact_matches": exact,
    "mismatches_near_wrong_label": 0,
    "manual_only": manual_only,
    "ai_only": ai_only,
    "manual_action_tags": len(manual),
    "ai_comparable_events": len(ai),
    "match_tolerance_sec": TOL_MS / 1000,
}

payload = {
    "generated_for": "Manual Q1 ground truth vs GPU Q1 rerun 20260718_215754 (Wilder / video 8)",
    "analysis_key": KEY,
    "window": "Q1 0:00–14:31",
    "kpis": kpis,
    "diagnosis": diag,
    "pairs": pairs,
    "manual": manual,
    "ai": ai,
}

OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

# Markdown
lines = []
lines.append("# Manual vs AI — Q1 Side-by-Side (Wilder)")
lines.append("")
lines.append(f"**Verdict: {diag['verdict']}**")
lines.append("")
lines.append(f"**Analysis key:** `{KEY}`")
lines.append(f"**Run status:** `{diag.get('run_status')}` — {diag.get('run_label') or ''}")
lines.append("")
lines.append("## KPIs (time ±8s + identical label)")
lines.append("")
lines.append(f"| Metric | Value |")
lines.append(f"| --- | ---: |")
lines.append(f"| Exact matches | **{exact}** |")
lines.append(f"| Manual-only (AI miss) | **{manual_only}** |")
lines.append(f"| AI-only (false extra) | **{ai_only}** |")
lines.append(f"| Manual action tags | {len(manual)} |")
lines.append(f"| AI comparable events | {len(ai)} |")
lines.append("")
lines.append("## Coverage / diagnosis")
lines.append("")
lines.append(diag["root_bug"])
lines.append("")
lines.append(f"- Covers ~full Q1: **{diag['covers_q1']}**")
lines.append(f"- Comparable AI event span: **{diag['ai_ts_min_ms']}–{diag['ai_ts_max_ms']} ms** (~{diag['ai_span_sec']}s)")
lines.append(f"- Raw events: **{diag['raw_event_count']}** spanning **{diag['raw_event_ts_min_ms']}–{diag['raw_event_ts_max_ms']} ms**")
lines.append(f"- Detections: frames **{diag['det_frame_min']}–{diag['det_frame_max']}** / ts **{diag['det_ts_min_ms']}–{diag['det_ts_max_ms']} ms** @ implied **{diag['implied_fps']} fps** (n={diag['det_count']})")
lines.append(f"- Analysis `video_path` exists: **{diag['analysis_video_exists']}** (`{diag['analysis_video_path']}`)")
lines.append(f"- `videos.id=8`: `{diag['videos_8_path']}` ({diag['videos_8_size']} bytes, duration ~7290s)")
lines.append(f"- Clock offset viable: **{diag['clock_offset_viable']}** — {diag['clock_offset_note']}")
lines.append("")
lines.append("## Side-by-side")
lines.append("")
lines.append("| Status | Manual time | Manual team | Manual label | Manual player | AI time | AI label | AI player | Δs |")
lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
for p in pairs:
    st = p["status"]
    m, a = p["manual"], p["ai"]
    mt = m["time"] if m else "—"
    mteam = m["team"] if m else "—"
    ml = m["label"] if m else "—"
    mp = m["player"] if m else "—"
    at = a["time"] if a else "—"
    al = a["label"] if a else "—"
    ap = a["player"] if a else "—"
    dt = p["dt_sec"] if p["dt_sec"] is not None else "—"
    lines.append(f"| {st} | {mt} | {mteam} | {ml} | {mp} | {at} | {al} | {ap} | {dt} |")

lines.append("")
lines.append("## Top mismatch examples")
lines.append("")
lines.append("### Manual-only (first 8 chronologically)")
for p in [x for x in pairs if x["status"] == "MANUAL_ONLY"][:8]:
    m = p["manual"]
    lines.append(f"- `{m['time']}` {m['team']} **{m['label']}** — {m['player']}")
lines.append("")
lines.append("### AI-only (first 8 chronologically)")
for p in [x for x in pairs if x["status"] == "AI_ONLY"][:8]:
    a = p["ai"]
    lines.append(f"- `{a['time']}` **{a['label']}** — {a['player']} (event `{a['event_id']}`)")
lines.append("")
lines.append(f"JSON twin: `{OUT_JSON.name}`")
OUT_MD.write_text("\n".join(lines), encoding="utf-8")
print(json.dumps({
    "kpis": kpis,
    "covers_q1": diag["covers_q1"],
    "ai_span_ms": [diag["ai_ts_min_ms"], diag["ai_ts_max_ms"]],
    "det_span_ms": [diag["det_ts_min_ms"], diag["det_ts_max_ms"]],
    "run_status": diag.get("run_status"),
    "diag_summary": diag["verdict"],
    "out_md": str(OUT_MD),
    "out_json": str(OUT_JSON),
}, indent=2))
