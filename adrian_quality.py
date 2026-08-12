"""Adrian JrHigh event quality — scorebook truth + temporal dedupe.

Only for game_id base ``jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334``.
AI currently emits a firehose (track IDs as players, thousands of false events).
Until jersey CV is fixed we:

  1) Collapse near-duplicate events in time
  2) Cap countable buckets to confirmed scorebook team totals
  3) Cap counting stats (REB/AST/…) with basketball-reasonable bounds
  4) Rewrite review_status: kept → accepted, rest → rejected

Per-player jersey assignment stays wrong until IDs map to #13/#40/etc.
Team totals should become believable.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from boxscore_constraints import (
    COUNT_BUCKETS,
    SHOT_BUCKETS,
    apply_boxscore_constraints,
    empty_caps,
    event_confidence,
)

ROOT = Path(__file__).resolve().parent
ADRIAN_BASE = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
SCOREBOOK_PATH = (
    ROOT / "data" / "stat_books" / "confirmed" / f"{ADRIAN_BASE}.json"
)
QUALITY_NOTE = "adrian_quality_v1"


def is_adrian_game(game_id: str | None) -> bool:
    text = str(game_id or "")
    return text == ADRIAN_BASE or text.startswith(ADRIAN_BASE + "__rerun_")


def load_adrian_scorebook() -> dict[str, Any]:
    return json.loads(SCOREBOOK_PATH.read_text(encoding="utf-8"))


def caps_from_stat_book(sb: dict[str, Any]) -> dict[str, Any]:
    """Build boxscore_constraints model entry from confirmed spiral scorebook."""
    team = empty_caps()
    by_jersey: dict[str, dict] = {}
    points = 0

    for p in sb.get("players") or []:
        jersey_raw = str(p.get("jersey") or "").strip()
        if not jersey_raw:
            continue
        jersey = str(int(jersey_raw)) if jersey_raw.isdigit() else jersey_raw
        extras = p.get("extras") or {}
        fg2 = int(extras.get("fg2") or 0)
        tpm = int(p.get("tpm") or 0)
        ftm = int(p.get("ftm") or 0)
        fta = int(p.get("fta") or 0)
        pts = int(p.get("pts") or 0)
        # Misses: only FT known when fta present; FG misses unknown (fga null).
        caps = empty_caps()
        caps["2pt_make"] = fg2
        caps["3pt_make"] = tpm
        caps["ft_make"] = ftm
        caps["ft_miss"] = max(0, fta - ftm)
        # Optional counting stats when filled
        for src, bucket in (
            ("reb", "reb"),
            ("ast", "ast"),
            ("stl", "stl"),
            ("blk", "blk"),
            ("to", "to"),
            ("fouls", "pf"),
        ):
            val = p.get(src)
            if val is not None:
                caps[bucket] = int(val)
        caps["points"] = pts
        by_jersey[jersey] = caps
        points += pts
        for k in SHOT_BUCKETS + COUNT_BUCKETS:
            team[k] = int(team.get(k) or 0) + int(caps.get(k) or 0)

    # Prefer summed player points over possibly-swapped final_score_* fields.
    team["points"] = points or (
        int(sb.get("final_score_home") or 0) + int(sb.get("final_score_away") or 0)
    )
    return {
        "team": team,
        "by_jersey": by_jersey,
        "source": "stat_book_confirmed",
        "game_id": ADRIAN_BASE,
    }


def _details(event: dict) -> dict:
    raw = event.get("details_json") or "{}"
    if isinstance(raw, dict):
        return dict(raw)
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def normalize_event_for_caps(event: dict) -> dict:
    """Map make/miss/made_* into shot-shaped events boxscore_constraints understands."""
    e = dict(event)
    et = str(e.get("event_type") or "").lower()
    details = _details(e)
    if et == "make":
        e["event_type"] = "shot"
        e["shot_result"] = "make"
        # Do not invent shot_type here — allocation fills book buckets.
    elif et == "miss":
        e["event_type"] = "shot"
        e["shot_result"] = "miss"
    elif et == "made_two":
        e["event_type"] = "shot"
        e["shot_result"] = "make"
        details["shot_type"] = "2pt"
    elif et == "missed_two":
        e["event_type"] = "shot"
        e["shot_result"] = "miss"
        details["shot_type"] = "2pt"
    elif et == "made_three":
        e["event_type"] = "shot"
        e["shot_result"] = "make"
        details["shot_type"] = "3pt"
    elif et == "missed_three":
        e["event_type"] = "shot"
        e["shot_result"] = "miss"
        details["shot_type"] = "3pt"
    elif et == "made_free_throw":
        e["event_type"] = "shot"
        e["shot_result"] = "make"
        details["shot_type"] = "ft"
    elif et == "missed_free_throw":
        e["event_type"] = "shot"
        e["shot_result"] = "miss"
        details["shot_type"] = "ft"
    elif et == "shot":
        # leave existing shot_type alone (may be empty → untyped)
        if not e.get("shot_result"):
            e["shot_result"] = "miss"
    e["details_json"] = json.dumps(details)
    return e


def temporal_dedupe(events: list[dict], window_ms: int = 2000) -> list[dict]:
    """Keep highest-confidence event per (family, player) inside a time window."""
    def family(e: dict) -> str:
        et = str(e.get("event_type") or "").lower()
        if et in {"shot", "make", "miss", "made_two", "missed_two", "made_three",
                  "missed_three", "made_free_throw", "missed_free_throw"}:
            sr = str(e.get("shot_result") or "").lower()
            if et in {"make", "made_two", "made_three", "made_free_throw"} or sr in {"make", "made"}:
                return "shot_make"
            if et in {"miss", "missed_two", "missed_three", "missed_free_throw"} or sr in {"miss", "missed"}:
                return "shot_miss"
            return "shot"
        return et

    ranked = sorted(
        events,
        key=lambda e: (-event_confidence(e), int(e.get("timestamp_ms") or 0), int(e.get("id") or 0)),
    )
    kept: list[dict] = []
    last_kept: dict[tuple[str, str], int] = {}
    for event in ranked:
        fam = family(event)
        if fam == "possession_change":
            continue
        player = str(event.get("player") or "")
        ts = int(event.get("timestamp_ms") or 0)
        key = (fam, player)
        prev = last_kept.get(key)
        if prev is not None and abs(ts - prev) <= window_ms:
            continue
        key2 = (fam, "")
        prev2 = last_kept.get(key2)
        if not player and prev2 is not None and abs(ts - prev2) <= window_ms:
            continue
        kept.append(event)
        last_kept[key] = ts
        if not player:
            last_kept[key2] = ts
    kept.sort(key=lambda e: (int(e.get("timestamp_ms") or 0), int(e.get("id") or 0)))
    return kept


def heuristic_count_caps(shot_kept: list[dict], team_caps: dict) -> dict[str, int]:
    """When scorebook lacks REB/AST/… use tight JH-reasonable caps from kept shots."""
    makes = sum(
        1
        for e in shot_kept
        if str(e.get("shot_result") or "").lower() in {"make", "made"}
        or str(e.get("event_type") or "").lower() in {"make", "made_two", "made_three", "made_free_throw"}
    )
    misses = sum(
        1
        for e in shot_kept
        if str(e.get("shot_result") or "").lower() in {"miss", "missed"}
        or str(e.get("event_type") or "").lower() in {"miss", "missed_two", "missed_three", "missed_free_throw"}
    )
    reb = int(team_caps.get("reb") or 0) or (misses if misses else 12)
    if not int(team_caps.get("reb") or 0):
        reb = max(8, min(reb, 40))
    ast = int(team_caps.get("ast") or 0) or min(makes, max(0, makes // 2))
    stl = int(team_caps.get("stl") or 0) or min(12, max(0, makes // 3))
    blk = int(team_caps.get("blk") or 0) or min(8, max(0, misses // 5))
    to = int(team_caps.get("to") or 0) or stl
    pf = int(team_caps.get("pf") or 0) or 16
    return {"reb": reb, "ast": ast, "stl": stl, "blk": blk, "to": to, "pf": pf}


def _assign_shot_types_to_caps(shots: list[dict], team: dict) -> list[dict]:
    """AI shots rarely have shot_type; allocate top-confidence makes/misses to book buckets."""
    from boxscore_constraints import shot_bucket

    typed: list[dict] = []
    untyped_makes: list[dict] = []
    untyped_misses: list[dict] = []
    other: list[dict] = []

    for e in shots:
        details = _details(e)
        kind = str(details.get("shot_type") or details.get("shotType") or "").lower().strip()
        result = str(e.get("shot_result") or "").lower()
        is_make = result in {"make", "made"}
        is_miss = result in {"miss", "missed"}
        has_type = bool(kind) and (
            "3" in kind or "ft" in kind or "free" in kind or kind in {"2pt", "2", "two"}
        )
        if has_type:
            typed.append(e)
        elif is_make:
            untyped_makes.append(e)
        elif is_miss:
            untyped_misses.append(e)
        else:
            other.append(e)

    left = {
        "2pt_make": int(team.get("2pt_make") or 0),
        "3pt_make": int(team.get("3pt_make") or 0),
        "ft_make": int(team.get("ft_make") or 0),
        "ft_miss": int(team.get("ft_miss") or 0),
        "2pt_miss": 10_000,
        "3pt_miss": 10_000,
    }
    out: list[dict] = []
    for e in typed:
        probe = dict(e)
        if str(probe.get("event_type") or "").lower() != "shot":
            probe["event_type"] = "shot"
        b = shot_bucket(probe)
        if b and b in left:
            if left[b] <= 0:
                continue
            left[b] -= 1
        out.append(e)

    untyped_makes = sorted(untyped_makes, key=event_confidence, reverse=True)
    fill_order = (
        [("2pt_make", "2pt")] * max(0, left["2pt_make"])
        + [("3pt_make", "3pt")] * max(0, left["3pt_make"])
        + [("ft_make", "ft")] * max(0, left["ft_make"])
    )
    for e, (bucket, shot_type) in zip(untyped_makes, fill_order):
        details = _details(e)
        details["shot_type"] = shot_type
        details["adrian_shot_type_assigned"] = True
        row = dict(e)
        row["event_type"] = "shot"
        row["shot_result"] = "make"
        row["details_json"] = json.dumps(details)
        out.append(row)
        left[bucket] = max(0, left[bucket] - 1)

    untyped_misses = sorted(untyped_misses, key=event_confidence, reverse=True)
    ft_miss_n = max(0, left["ft_miss"])
    for e in untyped_misses[:ft_miss_n]:
        details = _details(e)
        details["shot_type"] = "ft"
        details["adrian_shot_type_assigned"] = True
        row = dict(e)
        row["event_type"] = "shot"
        row["shot_result"] = "miss"
        row["details_json"] = json.dumps(details)
        out.append(row)
    # Remaining misses: invent 2pt so shot_bucket can count them before FG miss trim
    for e in untyped_misses[ft_miss_n:]:
        details = _details(e)
        details.setdefault("shot_type", "2pt")
        row = dict(e)
        row["event_type"] = "shot"
        row["shot_result"] = "miss"
        row["details_json"] = json.dumps(details)
        out.append(row)
    out.extend(other)
    return out


def _stamp_ledger_shot_type(event: dict, details: dict) -> dict:
    """Rewrite event_type so program_mode ledger points/TPM/FTM are correct."""
    out = dict(event)
    kind = str(details.get("shot_type") or details.get("shotType") or "2pt").lower()
    result = str(out.get("shot_result") or "").lower()
    et = str(out.get("event_type") or "").lower()
    is_make = result in {"make", "made"} or et in {
        "make", "made_two", "made_three", "made_free_throw"
    }
    is_miss = result in {"miss", "missed"} or et in {
        "miss", "missed_two", "missed_three", "missed_free_throw"
    }
    if not (is_make or is_miss):
        return out
    if "ft" in kind or "free" in kind:
        out["event_type"] = "made_free_throw" if is_make else "missed_free_throw"
        out["shot_result"] = "make" if is_make else "miss"
    elif "3" in kind:
        out["event_type"] = "made_three" if is_make else "missed_three"
        out["shot_result"] = "make" if is_make else "miss"
    else:
        out["event_type"] = "made_two" if is_make else "missed_two"
        out["shot_result"] = "make" if is_make else "miss"
    return out


def refine_adrian_events(raw_events: list[dict]) -> tuple[list[dict], dict[str, Any]]:
    """Return (kept_events, report)."""
    sb = load_adrian_scorebook()
    caps_block = caps_from_stat_book(sb)
    team = dict(caps_block["team"])

    # Drop noise early
    usable = [
        e
        for e in raw_events
        if str(e.get("event_type") or "").lower()
        not in {"possession_change", "bookmark"}
    ]
    deduped = temporal_dedupe(usable, window_ms=2000)

    # Normalize for shot caps; keep original event_type for counting stats
    normalized = []
    for e in deduped:
        et = str(e.get("event_type") or "").lower()
        if et in {
            "shot", "make", "miss", "made_two", "missed_two", "made_three",
            "missed_three", "made_free_throw", "missed_free_throw",
        }:
            normalized.append(normalize_event_for_caps(e))
        else:
            normalized.append(dict(e))

    # Assign untyped makes/misses into scorebook shot buckets before capping
    count_types = {"rebound", "assist", "steal", "block", "turnover", "foul"}
    counting_pool = [
        e for e in normalized if str(e.get("event_type") or "").lower() in count_types
    ]
    shot_pool = [
        e for e in normalized if str(e.get("event_type") or "").lower() not in count_types
    ]
    shot_pool = _assign_shot_types_to_caps(shot_pool, team)

    # Strip FG miss caps (unknown) — only cap makes + FT from book
    model = {
        "boxscore_by_game": {
            ADRIAN_BASE: {
                "team": {
                    **team,
                    "2pt_miss": 10_000,
                    "3pt_miss": 10_000,
                    "reb": 0,
                    "ast": 0,
                    "stl": 0,
                    "blk": 0,
                    "to": 0,
                    "pf": int(team.get("pf") or 0),
                },
                "by_jersey": {},
            }
        }
    }

    for e in shot_pool:
        e["game_id"] = ADRIAN_BASE

    capped_shots = apply_boxscore_constraints(shot_pool, model)

    shots = [
        e
        for e in capped_shots
        if str(e.get("event_type") or "").lower() == "shot"
        or str(e.get("event_type") or "").lower()
        in {"make", "miss", "made_two", "missed_two", "made_three", "missed_three",
            "made_free_throw", "missed_free_throw"}
    ]
    counting = counting_pool

    # Bound FG misses: allow up to ~1.5x makes (rough JH) if book lacks FGA
    makes_n = sum(
        1
        for e in shots
        if str(e.get("shot_result") or "").lower() in {"make", "made"}
    )
    miss_cap = max(makes_n + 5, int(makes_n * 1.8) if makes_n else 15)
    miss_events = [
        e for e in shots if str(e.get("shot_result") or "").lower() in {"miss", "missed"}
    ]
    make_events = [
        e for e in shots if str(e.get("shot_result") or "").lower() in {"make", "made"}
    ]
    other_shots = [
        e
        for e in shots
        if str(e.get("shot_result") or "").lower() not in {"make", "made", "miss", "missed"}
    ]
    # Prefer keeping FT misses already typed; then FG misses
    miss_events = sorted(miss_events, key=event_confidence, reverse=True)[:miss_cap]
    shots = make_events + miss_events + other_shots

    hcaps = heuristic_count_caps(shots, team)
    counting_kept: list[dict] = []
    for etype, limit in (
        ("rebound", hcaps["reb"]),
        ("assist", hcaps["ast"]),
        ("steal", hcaps["stl"]),
        ("block", hcaps["blk"]),
        ("turnover", hcaps["to"]),
        ("foul", hcaps["pf"]),
    ):
        subset = [e for e in counting if str(e.get("event_type") or "").lower() == etype]
        subset = sorted(subset, key=event_confidence, reverse=True)[:limit]
        counting_kept.extend(subset)

    kept = shots + counting_kept
    kept.sort(key=lambda e: (int(e.get("timestamp_ms") or 0), int(e.get("id") or 0)))

    # Restore base row, then stamp ledger-friendly shot types + quality notes
    by_id = {int(e["id"]): e for e in raw_events if e.get("id") is not None}
    restored = []
    for e in kept:
        orig = by_id.get(int(e["id"]))
        details = _details(orig if orig else e)
        # Prefer assigned shot_type from quality pass
        q_details = _details(e)
        if q_details.get("shot_type"):
            details["shot_type"] = q_details["shot_type"]
        if q_details.get("adrian_shot_type_assigned"):
            details["adrian_shot_type_assigned"] = True
        details["adrian_quality"] = QUALITY_NOTE
        details["boxscore_capped"] = True
        base = dict(orig) if orig else dict(e)
        # Carry shot_result from quality event when present
        if e.get("shot_result"):
            base["shot_result"] = e["shot_result"]
        stamped = _stamp_ledger_shot_type(base, details)
        stamped["details_json"] = json.dumps(details)
        restored.append(stamped)

    report = {
        "raw": len(raw_events),
        "after_dedupe": len(deduped),
        "kept": len(restored),
        "team_caps": team,
        "heuristic_count_caps": hcaps,
        "makes_kept": makes_n,
        "misses_kept": len(miss_events),
        "scorebook_points": team.get("points"),
        "ledger_points_est": (
            2 * int(team.get("2pt_make") or 0)
            + 3 * int(team.get("3pt_make") or 0)
            + int(team.get("ft_make") or 0)
        ),
    }
    return restored, report


def load_events_from_db(conn: sqlite3.Connection, game_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT id, game_id, event_type, player, shot_result, timestamp_ms,
                  confidence, details_json, source_type, review_status
             FROM events
            WHERE game_id = ?
            ORDER BY timestamp_ms ASC, id ASC""",
        (game_id,),
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": r[0],
                "game_id": r[1],
                "event_type": r[2],
                "player": r[3],
                "shot_result": r[4],
                "timestamp_ms": r[5],
                "confidence": r[6],
                "details_json": r[7],
                "source_type": r[8] or "ai",
                "review_status": r[9],
            }
        )
    return out


def apply_quality_to_db(conn: sqlite3.Connection, game_id: str = ADRIAN_BASE) -> dict[str, Any]:
    """Rewrite Adrian events review_status from quality pass. Adrian only."""
    if not is_adrian_game(game_id):
        raise ValueError(f"Refusing non-Adrian game_id: {game_id}")

    # Prefer base key rows
    raw = load_events_from_db(conn, ADRIAN_BASE)
    source_key = ADRIAN_BASE
    if not raw:
        # fall back to densest rerun
        rows = conn.execute(
            """SELECT game_id, COUNT(*) n FROM events
                WHERE game_id LIKE ? GROUP BY 1 ORDER BY n DESC LIMIT 1""",
            (ADRIAN_BASE + "%",),
        ).fetchone()
        if not rows:
            return {"ok": False, "error": "no events"}
        source_key = rows[0]
        raw = load_events_from_db(conn, source_key)

    kept, report = refine_adrian_events(raw)
    keep_ids = {int(e["id"]) for e in kept if e.get("id") is not None}

    # Park every related key (base + reruns) so program ledger cannot
    # double-count an old firehose copy.
    related = conn.execute(
        """SELECT DISTINCT game_id FROM events WHERE game_id = ? OR game_id LIKE ?""",
        (ADRIAN_BASE, ADRIAN_BASE + "__rerun_%"),
    ).fetchall()
    related_ids = [r[0] for r in related]
    for key in related_ids:
        conn.execute(
            """UPDATE events
                  SET review_status='rejected',
                      human_verified=0,
                      reviewed_at=CURRENT_TIMESTAMP,
                      review_notes=?
                WHERE game_id=?""",
            (f"{QUALITY_NOTE}:drop", key),
        )

    if keep_ids:
        by_kept = {int(e["id"]): e for e in kept if e.get("id") is not None}
        ids = sorted(keep_ids)
        for i in range(0, len(ids), 400):
            chunk = ids[i : i + 400]
            for eid in chunk:
                row = by_kept[eid]
                conn.execute(
                    """UPDATE events
                          SET review_status='accepted',
                              human_verified=0,
                              reviewed_at=CURRENT_TIMESTAMP,
                              review_notes=?,
                              event_type=?,
                              shot_result=?,
                              details_json=?
                        WHERE id=?""",
                    (
                        f"{QUALITY_NOTE}:keep",
                        row.get("event_type"),
                        row.get("shot_result"),
                        row.get("details_json"),
                        eid,
                    ),
                )
    conn.commit()
    report["ok"] = True
    report["game_id"] = ADRIAN_BASE
    report["source_key"] = source_key
    report["related_keys_cleared"] = related_ids
    report["kept_ids"] = len(keep_ids)
    return report
