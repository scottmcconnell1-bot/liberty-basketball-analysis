"""Box-score constrained teaching for AI events.

Hoopsalytics / MaxPreps exports give exact player totals (no timestamps).
If AI event counts disagree with those totals, the AI is wrong — use the
box score as hard constraints:

  - Over-detect → keep the highest-confidence events up to the box-score cap,
    drop the rest (false-positive teaching).
  - Under-detect → record recall debt (need more candidates / lower floors);
    cannot invent timestamps from a box score alone.

Caps are stored per game_id in models/boxscore_event_calibrator.json and
applied after the manual event calibrator in postprocess.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_BOXSCORE_MODEL = ROOT / "models" / "boxscore_event_calibrator.json"
HOOPS_DIR = ROOT / "data" / "hoopsalytics"

_MODEL_CACHE: dict | None = None
_MODEL_MTIME: float | None = None


def _base_game_id(game_id: str | None) -> str:
    text = str(game_id or "")
    if "__rerun_" in text:
        return text.split("__rerun_", 1)[0]
    return text

# Buckets we can constrain from MaxPreps jersey lines
SHOT_BUCKETS = (
    "2pt_make",
    "2pt_miss",
    "3pt_make",
    "3pt_miss",
    "ft_make",
    "ft_miss",
)
COUNT_BUCKETS = (
    "reb",
    "ast",
    "stl",
    "blk",
    "to",
    "pf",
)


def extract_jersey(player) -> str | None:
    text = str(player or "").strip()
    if not text:
        return None
    m = re.match(r"^(\d{1,2})\b", text)
    if m:
        return str(int(m.group(1)))  # normalize "07" → "7"
    m = re.search(r"#\s*(\d{1,2})\b", text)
    if m:
        return str(int(m.group(1)))
    return None


def _details(event: dict) -> dict:
    raw = event.get("details_json") or "{}"
    if isinstance(raw, dict):
        return dict(raw)
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _set_details(event: dict, details: dict) -> None:
    event["details_json"] = json.dumps(details)


def shot_bucket(event: dict) -> str | None:
    if str(event.get("event_type") or "").lower() != "shot":
        return None
    details = _details(event)
    kind = str(details.get("shot_type") or details.get("shotType") or "2pt").lower()
    result = str(event.get("shot_result") or "").lower()
    is_make = result in {"make", "made"}
    if "3" in kind:
        base = "3pt"
    elif "ft" in kind or "free" in kind:
        base = "ft"
    else:
        base = "2pt"
    return f"{base}_{'make' if is_make else 'miss'}"


def count_bucket(event: dict) -> str | None:
    et = str(event.get("event_type") or "").lower()
    return {
        "rebound": "reb",
        "assist": "ast",
        "steal": "stl",
        "block": "blk",
        "turnover": "to",
        "foul": "pf",
    }.get(et)


def empty_caps() -> dict:
    caps = {k: 0 for k in SHOT_BUCKETS + COUNT_BUCKETS}
    return caps


def caps_from_maxpreps_player(p: dict) -> dict:
    """Build per-player caps from a MaxPreps/Hoopsalytics player line."""
    twopm = int(p.get("twopm") or 0)
    twopa = int(p.get("twopa") or 0)
    threepm = int(p.get("threepm") or 0)
    threepa = int(p.get("threepa") or 0)
    ftm = int(p.get("ftm") or 0)
    fta = int(p.get("fta") or 0)
    return {
        "2pt_make": twopm,
        "2pt_miss": max(0, twopa - twopm),
        "3pt_make": threepm,
        "3pt_miss": max(0, threepa - threepm),
        "ft_make": ftm,
        "ft_miss": max(0, fta - ftm),
        "reb": int(p.get("reb") or 0),
        "ast": int(p.get("ast") or 0),
        "stl": int(p.get("stl") or 0),
        "blk": int(p.get("blk") or 0),
        "to": int(p.get("to") or 0),
        "pf": int(p.get("pf") or 0),
        "points": int(p.get("points") or 0),
        "minutes": int(p.get("minutes") or 0),
    }


def team_caps_from_players(players: list[dict]) -> dict:
    team = empty_caps()
    points = 0
    for p in players or []:
        c = caps_from_maxpreps_player(p)
        points += int(c.get("points") or 0)
        for k in SHOT_BUCKETS + COUNT_BUCKETS:
            team[k] = int(team.get(k) or 0) + int(c.get(k) or 0)
    team["points"] = points
    return team


def reference_to_game_caps(box: dict) -> dict:
    """Convert imported referenceBoxScore → {team, by_jersey}."""
    players = (box or {}).get("players") or []
    by_jersey = {}
    for p in players:
        jersey = str(p.get("jersey") or "").strip()
        if not jersey:
            continue
        jersey = str(int(jersey)) if jersey.isdigit() else jersey
        by_jersey[jersey] = caps_from_maxpreps_player(p)
    return {
        "team": team_caps_from_players(players),
        "by_jersey": by_jersey,
        "source_file": (box or {}).get("source_file"),
        "team_token": (box or {}).get("team_token"),
    }


def load_boxscore_model(path: Path | None = None) -> dict | None:
    global _MODEL_CACHE, _MODEL_MTIME
    model_path = Path(path) if path else DEFAULT_BOXSCORE_MODEL
    if not model_path.exists():
        return None
    mtime = model_path.stat().st_mtime
    if _MODEL_CACHE is not None and _MODEL_MTIME == mtime:
        return _MODEL_CACHE
    try:
        data = json.loads(model_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    _MODEL_CACHE = data
    _MODEL_MTIME = mtime
    return data


def event_confidence(event: dict) -> float:
    return float(event.get("confidence") or 0.0)


def _cap_list(events: list[dict], limit: int) -> tuple[list[dict], list[dict]]:
    """Keep top-`limit` by confidence; return (kept, dropped)."""
    if limit < 0:
        return events, []
    ranked = sorted(events, key=event_confidence, reverse=True)
    return ranked[:limit], ranked[limit:]


def apply_boxscore_constraints(events: list[dict], model: dict | None = None) -> list[dict]:
    """Trim AI events so counts cannot exceed box-score caps for that game.

    Strategy:
      1) Prefer jersey-level caps when the event has a jersey.
      2) Fall back to team caps for unassigned / leftover events.
      3) Never invent events for undercounts (recorded separately by teach script).
    """
    if model is None:
        model = load_boxscore_model()
    if not model or not events:
        return events

    by_game = model.get("boxscore_by_game") or {}
    if not by_game:
        return events

    # Group events by boxscore game key (primary or stripped __rerun_ key).
    groups: dict[str, list[dict]] = {}
    passthrough: list[dict] = []
    for event in events:
        gid = str(event.get("game_id") or "")
        lookup = gid if gid in by_game else _base_game_id(gid)
        if lookup in by_game:
            groups.setdefault(lookup, []).append(dict(event))
        else:
            passthrough.append(event)

    out: list[dict] = list(passthrough)
    for gid, group in groups.items():
        caps_block = by_game[gid]
        team_caps = dict(caps_block.get("team") or {})
        jersey_caps = {str(k): dict(v) for k, v in (caps_block.get("by_jersey") or {}).items()}

        # Remaining capacity trackers (copy)
        team_left = {k: int(team_caps.get(k) or 0) for k in SHOT_BUCKETS + COUNT_BUCKETS}
        jersey_left = {
            j: {k: int(c.get(k) or 0) for k in SHOT_BUCKETS + COUNT_BUCKETS}
            for j, c in jersey_caps.items()
        }

        # Bucket events
        buckets: dict[tuple[str | None, str], list[dict]] = {}
        other: list[dict] = []
        for event in group:
            sb = shot_bucket(event)
            cb = count_bucket(event) if sb is None else None
            bucket = sb or cb
            if not bucket:
                other.append(event)
                continue
            jersey = extract_jersey(event.get("player"))
            buckets.setdefault((jersey, bucket), []).append(event)

        kept: list[dict] = list(other)
        dropped_n = 0

        # Process jersey-assigned first, then unassigned (jersey=None)
        ordered_keys = sorted(buckets.keys(), key=lambda x: (x[0] is None, x[0] or "", x[1]))
        for jersey, bucket in ordered_keys:
            candidates = buckets[(jersey, bucket)]
            if jersey and jersey in jersey_left:
                limit = int(jersey_left[jersey].get(bucket) or 0)
                keep, drop = _cap_list(candidates, limit)
                jersey_left[jersey][bucket] = max(0, limit - len(keep))
                team_left[bucket] = max(0, int(team_left.get(bucket) or 0) - len(keep))
            else:
                # Unassigned or unknown jersey — use remaining team capacity
                limit = int(team_left.get(bucket) or 0)
                keep, drop = _cap_list(candidates, limit)
                team_left[bucket] = max(0, limit - len(keep))

            for event in keep:
                details = _details(event)
                details["boxscore_capped"] = True
                details["boxscore_bucket"] = bucket
                if jersey:
                    details["boxscore_jersey"] = jersey
                _set_details(event, details)
                kept.append(event)
            dropped_n += len(drop)

        kept.sort(key=lambda e: (int(e.get("timestamp_ms") or 0), str(e.get("event_type") or "")))
        out.extend(kept)

    out.sort(key=lambda e: (int(e.get("timestamp_ms") or 0), str(e.get("event_type") or "")))
    return out


def aggregate_ai_caps(events: list[dict]) -> dict:
    """Summarize AI events into the same cap schema (team + by_jersey)."""
    team = empty_caps()
    by_jersey: dict[str, dict] = {}
    for event in events or []:
        sb = shot_bucket(event)
        cb = count_bucket(event) if sb is None else None
        bucket = sb or cb
        if not bucket:
            continue
        jersey = extract_jersey(event.get("player"))
        team[bucket] = int(team.get(bucket) or 0) + 1
        if jersey:
            slot = by_jersey.setdefault(jersey, empty_caps())
            slot[bucket] = int(slot.get(bucket) or 0) + 1
    return {"team": team, "by_jersey": by_jersey}


def compare_caps(truth: dict, ai: dict) -> dict:
    """Diff truth vs AI caps → overcounts (FP) and undercounts (FN / recall debt)."""
    truth_team = truth.get("team") or {}
    ai_team = ai.get("team") or {}
    over = {}
    under = {}
    for k in SHOT_BUCKETS + COUNT_BUCKETS:
        t = int(truth_team.get(k) or 0)
        a = int(ai_team.get(k) or 0)
        if a > t:
            over[k] = a - t
        elif a < t:
            under[k] = t - a

    jersey_over = {}
    jersey_under = {}
    jerseys = set((truth.get("by_jersey") or {}).keys()) | set((ai.get("by_jersey") or {}).keys())
    for j in sorted(jerseys, key=lambda x: int(x) if str(x).isdigit() else 999):
        tj = (truth.get("by_jersey") or {}).get(j) or {}
        aj = (ai.get("by_jersey") or {}).get(j) or {}
        jo, ju = {}, {}
        for k in SHOT_BUCKETS + COUNT_BUCKETS:
            t = int(tj.get(k) or 0)
            a = int(aj.get(k) or 0)
            if a > t:
                jo[k] = a - t
            elif a < t:
                ju[k] = t - a
        if jo:
            jersey_over[j] = jo
        if ju:
            jersey_under[j] = ju

    return {
        "team_overcount": over,
        "team_undercount": under,
        "jersey_overcount": jersey_over,
        "jersey_undercount": jersey_under,
        "ai_wrong": bool(over or under or jersey_over or jersey_under),
    }


def build_model_from_hoops_dir(hoops_dir: Path | None = None) -> dict:
    """Build boxscore_by_game model from data/hoopsalytics/*.json imports."""
    folder = Path(hoops_dir) if hoops_dir else HOOPS_DIR
    by_game = {}
    for path in sorted(folder.glob("*.json")):
        if path.name == "import_summary.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        game_id = data.get("game_id")
        box = data.get("box")
        if not game_id or not box:
            continue
        by_game[str(game_id)] = {
            **reference_to_game_caps(box),
            "opponent": data.get("opponent"),
            "date": data.get("date"),
            "stored_filename": data.get("stored_filename"),
        }
    return {
        "source": "teach_from_boxscore",
        "principle": (
            "If AI event totals disagree with the Hoopsalytics/MaxPreps box score, "
            "the AI is wrong. Cap detections to box-score counts (keep highest confidence)."
        ),
        "boxscore_by_game": by_game,
        "game_count": len(by_game),
    }
