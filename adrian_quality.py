"""Adrian JrHigh event quality — scorebook truth + temporal dedupe.

Only for game_id base ``jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334``.
AI currently emits a firehose (track IDs as players, thousands of false events).
Until jersey CV is fixed we:

  1) Collapse near-duplicate events in time
  2) Drop pass-like / low-arc false "shots" (high passes) before capping
  3) Drop tip-off shot tags, but keep a tip_off with who won the tip
  4) Keep rebound/block/assist only when linked to a kept make/miss
  5) Prefer steal over block when both fire on a contested pass
  6) Cap countable buckets to confirmed scorebook team totals
  7) Cap counting stats (REB/AST/…) with basketball-reasonable bounds
  8) Rewrite review_status: kept → accepted, rest → rejected

Per-player jersey assignment stays wrong until IDs map to #13/#40/etc.
Team totals should become believable.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from boxscore_constraints import (
    COUNT_BUCKETS,
    SHOT_BUCKETS,
    empty_caps,
    event_confidence,
)

ROOT = Path(__file__).resolve().parent
ADRIAN_BASE = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
SCOREBOOK_PATH = (
    ROOT / "data" / "stat_books" / "confirmed" / f"{ADRIAN_BASE}.json"
)
QUALITY_NOTE = "adrian_quality_v3"

# CV often tags a pass as a shot: ball leaves tracker A→B within ~300ms,
# and/or the arc is too flat for a real FG attempt.
PASS_OUTBOUND_WINDOW_MS = 300
MIN_SHOT_BALL_RISE = 120.0
# Opening tip / jump ball: ball goes high and CV stamps made_two (Scott: #8 @ ~3s).
# Still detect who gains first controlled possession — needed for jump/held balls.
TIPOFF_SHOT_GUARD_MS = 10_000
TIP_CONTROL_HOLD_MS = 800
TIP_STATE_DIR = ROOT / "data" / "adrian_possession"
# Make right after same-player rebound + quick outlet is often not a shot
# (Scott: made_two #9 @ 12.2s was rebound/outlet, not a basket).
POST_REBOUND_MAKE_WINDOW_MS = 2_500

# Film titles encode sides: LIBERTY_A_v_ADRIAN_H → Liberty Away, Adrian Home.
_TITLE_HA_RE = re.compile(
    r"(?P<left>[A-Za-z][A-Za-z0-9]*)_(?P<left_side>[AH])_v_"
    r"(?P<right>[A-Za-z][A-Za-z0-9]*)_(?P<right_side>[AH])",
    re.IGNORECASE,
)

SHOT_FAMILY = {
    "shot", "make", "miss", "made_two", "missed_two", "made_three",
    "missed_three", "made_free_throw", "missed_free_throw",
}


def is_adrian_game(game_id: str | None) -> bool:
    text = str(game_id or "")
    return text == ADRIAN_BASE or text.startswith(ADRIAN_BASE + "__rerun_")


def _title_team_name(token: str) -> str:
    return str(token or "").replace("_", " ").strip().title()


def parse_home_away_from_title(text: str | None) -> dict[str, str]:
    """Parse TEAM_A_v_TEAM_H (or H/A swapped) from film / game_id titles.

    Proven: ``LIBERTY_A_v_ADRIAN_H`` → Away Liberty, Home Adrian.
    """
    match = _TITLE_HA_RE.search(str(text or ""))
    if not match:
        return {}
    left = _title_team_name(match.group("left"))
    right = _title_team_name(match.group("right"))
    left_side = match.group("left_side").upper()
    right_side = match.group("right_side").upper()
    out: dict[str, str] = {}
    if left_side == "H":
        out["home"] = left
    elif left_side == "A":
        out["away"] = left
    if right_side == "H":
        out["home"] = right
    elif right_side == "A":
        out["away"] = right
    return out


def resolve_adrian_teams(
    sb: dict[str, Any] | None = None,
    game_id: str | None = ADRIAN_BASE,
) -> dict[str, Any]:
    """Home/away from scorebook labels + film title ``_H`` / ``_A`` markers."""
    book = sb if sb is not None else load_adrian_scorebook()
    from_title = parse_home_away_from_title(game_id or ADRIAN_BASE)
    home = (book.get("home_team") or from_title.get("home") or "").strip() or None
    away = (book.get("away_team") or from_title.get("away") or "").strip() or None
    return {
        "home_team": home,
        "away_team": away,
        "title_home": from_title.get("home"),
        "title_away": from_title.get("away"),
        "source": "scorebook+filename_HA",
        "label": (
            f"Home {home or '?'} / Away {away or '?'}"
            if (home or away)
            else None
        ),
    }


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


def build_possession_changes(events: list[dict]) -> list[tuple[int, str, str]]:
    """Sorted (timestamp_ms, from_player, to_player) for pass-like shot filtering."""
    out: list[tuple[int, str, str]] = []
    for event in events:
        if str(event.get("event_type") or "").lower() != "possession_change":
            continue
        details = _details(event)
        out.append(
            (
                int(event.get("timestamp_ms") or 0),
                str(details.get("from_player") or event.get("player") or ""),
                str(details.get("to_player") or ""),
            )
        )
    out.sort(key=lambda row: row[0])
    return out


def _outbound_pass_ms(
    timestamp_ms: int,
    player: str,
    possession_changes: list[tuple[int, str, str]],
    window_ms: int = PASS_OUTBOUND_WINDOW_MS,
) -> int | None:
    """Return gap_ms if ball leaves `player` to someone else near this clock."""
    if not player:
        return None
    for pts, from_p, to_p in possession_changes:
        if pts < timestamp_ms - 50:
            continue
        if pts > timestamp_ms + window_ms:
            break
        if from_p == player and to_p and to_p != player:
            return pts - timestamp_ms
    return None


def is_pass_like_shot(
    event: dict,
    possession_changes: list[tuple[int, str, str]],
    *,
    window_ms: int = PASS_OUTBOUND_WINDOW_MS,
    min_ball_rise: float = MIN_SHOT_BALL_RISE,
    rebounds: list[dict] | None = None,
) -> bool:
    """True when CV kinematics look like a pass, not a real shot/make.

    Scott's false `made_two · #5 @ 27.4s` had ball_rise=81 and an outbound
    possession_change 5→9 at +33ms — classic pass away from the basket.
    Also: make shortly after same-player rebound + quick outlet (#9 @ 12.2s).
    """
    et = str(event.get("event_type") or "").lower()
    if et not in SHOT_FAMILY:
        return False
    player = str(event.get("player") or "")
    ts = int(event.get("timestamp_ms") or 0)
    if _outbound_pass_ms(ts, player, possession_changes, window_ms=window_ms) is not None:
        return True
    details = _details(event)
    rise = details.get("ball_rise")
    if rise is not None:
        try:
            if float(rise) < min_ball_rise:
                return True
        except (TypeError, ValueError):
            pass
    if rebounds and player and _is_make_like_event(event):
        for reb in rebounds:
            if str(reb.get("player") or "") != player:
                continue
            gap = ts - int(reb.get("timestamp_ms") or 0)
            if 0 < gap <= POST_REBOUND_MAKE_WINDOW_MS:
                if _outbound_pass_ms(ts, player, possession_changes, window_ms=400) is not None:
                    return True
                break
    return False


def _is_make_like_event(event: dict) -> bool:
    et = str(event.get("event_type") or "").lower()
    sr = str(event.get("shot_result") or "").lower()
    return et in {"make", "made_two", "made_three", "made_free_throw"} or sr in {"make", "made"}


def drop_pass_like_shots(
    events: list[dict],
    possession_changes: list[tuple[int, str, str]] | None = None,
    raw_events: list[dict] | None = None,
) -> tuple[list[dict], int]:
    """Remove pass-like shot family rows; return (kept, dropped_count)."""
    source = raw_events if raw_events is not None else events
    pcs = possession_changes if possession_changes is not None else build_possession_changes(source)
    rebounds = [e for e in source if str(e.get("event_type") or "").lower() == "rebound"]
    kept: list[dict] = []
    dropped = 0
    for event in events:
        if is_pass_like_shot(event, pcs, rebounds=rebounds):
            dropped += 1
            continue
        kept.append(event)
    return kept, dropped


def promote_rebounds_before_fake_makes(
    counting: list[dict],
    raw_events: list[dict],
    possession_changes: list[tuple[int, str, str]],
    kept_shots: list[dict],
) -> tuple[list[dict], int]:
    """When a fake make after a rebound is dropped, keep the rebound instead."""
    kept_ids = {int(e["id"]) for e in kept_shots if e.get("id") is not None}
    kept_ids.update(int(e["id"]) for e in counting if e.get("id") is not None)
    rebounds = [e for e in raw_events if str(e.get("event_type") or "").lower() == "rebound"]
    promoted: list[dict] = []
    for event in raw_events:
        if not _is_make_like_event(event):
            continue
        # Opening tip scramble is tip_off — do not promote a rebound for it.
        if is_tipoff_shot(event):
            continue
        if event.get("id") is not None and int(event["id"]) in kept_ids:
            continue
        if not is_pass_like_shot(event, possession_changes, rebounds=rebounds):
            continue
        player = str(event.get("player") or "")
        ts = int(event.get("timestamp_ms") or 0)
        best = None
        best_gap = None
        for reb in rebounds:
            if str(reb.get("player") or "") != player:
                continue
            if reb.get("id") is not None and int(reb["id"]) in kept_ids:
                continue
            reb_ts = int(reb.get("timestamp_ms") or 0)
            # Tip-window rebounds stay dropped (tip is not a rebound).
            if reb_ts <= TIPOFF_SHOT_GUARD_MS:
                continue
            gap = ts - reb_ts
            if 0 < gap <= POST_REBOUND_MAKE_WINDOW_MS:
                if best_gap is None or gap < best_gap:
                    best = reb
                    best_gap = gap
        if best is None:
            continue
        row = dict(best)
        details = _details(row)
        details["adrian_promoted_from_fake_make"] = True
        details["fake_make_id"] = event.get("id")
        details["adrian_quality"] = QUALITY_NOTE
        row["details_json"] = json.dumps(details)
        promoted.append(row)
        if row.get("id") is not None:
            kept_ids.add(int(row["id"]))
    return counting + promoted, len(promoted)


def is_tipoff_shot(event: dict, *, guard_ms: int = TIPOFF_SHOT_GUARD_MS) -> bool:
    """True for shot-family tags during the opening jump-ball window."""
    if str(event.get("event_type") or "").lower() not in SHOT_FAMILY:
        return False
    return int(event.get("timestamp_ms") or 0) < guard_ms


def drop_tipoff_shots(events: list[dict], *, guard_ms: int = TIPOFF_SHOT_GUARD_MS) -> tuple[list[dict], int]:
    """Remove jump-ball / tip-window shot tags (not real FG/FT attempts)."""
    kept: list[dict] = []
    dropped = 0
    for event in events:
        if is_tipoff_shot(event, guard_ms=guard_ms):
            dropped += 1
            continue
        kept.append(event)
    return kept, dropped


def drop_tipoff_rebounds(
    events: list[dict],
    tip: dict[str, Any] | None = None,
    *,
    window_ms: int = 5_000,
    guard_ms: int = TIPOFF_SHOT_GUARD_MS,
) -> tuple[list[dict], int]:
    """Drop rebounds in the opening tip scramble — tip is tip_off, not a rebound."""
    tip_ms = int((tip or {}).get("tip_ms") or 0)
    kept: list[dict] = []
    dropped = 0
    for event in events:
        if str(event.get("event_type") or "").lower() != "rebound":
            kept.append(event)
            continue
        ts = int(event.get("timestamp_ms") or 0)
        if tip_ms and abs(ts - tip_ms) <= window_ms:
            dropped += 1
            continue
        if not tip_ms and ts <= guard_ms:
            dropped += 1
            continue
        kept.append(event)
    return kept, dropped


def _tip_toss_ms(raw_events: list[dict], *, guard_ms: int = TIPOFF_SHOT_GUARD_MS) -> int:
    """Timestamp of the opening tip toss.

    Prefer the *earliest* high-arc tip-window event (real toss ~2–5s), not the
    tallest arc later in the scramble — otherwise tip-winner inference starts
    too late and picks the wrong tracker.

    On re-refine, a prior pass may have rewritten the toss row to tip_off; honor
    that stamped tip_ms so we do not drift later in the scramble.
    """
    stamped: list[int] = []
    for event in raw_events:
        details = _details(event)
        et = str(event.get("event_type") or "").lower()
        if et == "tip_off" or details.get("kind") == "opening_tip":
            tip_ms = int(details.get("tip_ms") or event.get("timestamp_ms") or 0)
            if tip_ms:
                stamped.append(tip_ms)
    # Only trust prior tip stamps in the real toss window (~2–6s).
    early_stamped = [t for t in stamped if t <= 6_000]
    if early_stamped:
        return min(early_stamped)

    early: list[tuple[int, float]] = []
    all_tip: list[tuple[int, float]] = []
    for event in raw_events:
        if not is_tipoff_shot(event, guard_ms=guard_ms):
            continue
        details = _details(event)
        try:
            rise = float(details.get("ball_rise") or -1)
        except (TypeError, ValueError):
            rise = -1.0
        ts = int(event.get("timestamp_ms") or 0)
        all_tip.append((ts, rise))
        if ts <= 6_000 and rise >= 100:
            early.append((ts, rise))
    if early:
        return min(early, key=lambda row: row[0])[0]
    if all_tip:
        # Earliest high-arc in the tip window (not tallest later scramble).
        high = [row for row in all_tip if row[1] >= 100]
        pool = high or all_tip
        return min(pool, key=lambda row: row[0])[0]
    return 2500


def infer_opening_tip(
    raw_events: list[dict],
    *,
    guard_ms: int = TIPOFF_SHOT_GUARD_MS,
    min_hold_ms: int = TIP_CONTROL_HOLD_MS,
) -> dict[str, Any] | None:
    """Who wins the opening tip (first controlled possession after the toss).

    Fake made_two tags are dropped, but tip winner must be retained so later
    jump / held balls can follow alternating possession.
    """
    pcs = build_possession_changes(raw_events)
    if not pcs:
        return None
    tip_ms = _tip_toss_ms(raw_events, guard_ms=guard_ms)
    search_end = guard_ms + 8_000
    candidates: list[tuple[int, str, int, str]] = []
    for i, (ts, from_p, to_p) in enumerate(pcs):
        if ts < tip_ms - 150:
            continue
        if ts > search_end:
            break
        if not to_p:
            continue
        next_ts = pcs[i + 1][0] if i + 1 < len(pcs) else ts + 5_000
        hold = next_ts - ts
        candidates.append((hold, to_p, ts, from_p))

    if not candidates:
        return None

    for hold, winner, control_ms, from_p in candidates:
        if hold >= min_hold_ms:
            return {
                "tip_ms": tip_ms,
                "winner_tracker": winner,
                "control_ms": control_ms,
                "hold_ms": hold,
                "from_tracker": from_p,
                "method": f"first_hold_ge_{min_hold_ms}ms",
                "arrow_note": (
                    "NFHS alternating-possession arrow starts with the team "
                    "that did not gain the tip — needs jersey/team link."
                ),
            }

    hold, winner, control_ms, from_p = max(candidates, key=lambda row: row[0])
    return {
        "tip_ms": tip_ms,
        "winner_tracker": winner,
        "control_ms": control_ms,
        "hold_ms": hold,
        "from_tracker": from_p,
        "method": "longest_hold_in_tip_window",
        "arrow_note": (
            "NFHS alternating-possession arrow starts with the team "
            "that did not gain the tip — needs jersey/team link."
        ),
    }


def build_opening_jump_ball_event(
    raw_events: list[dict],
    tip: dict[str, Any],
) -> dict[str, Any] | None:
    """Rewrite a tip-window fake shot row into an accepted tip_off event.

    Named for history; event_type is tip_off (opening tip), not rebound or
    mid-game jump_ball.
    """
    tip_ms = int(tip.get("tip_ms") or 0)
    winner = str(tip.get("winner_tracker") or "")
    if not winner:
        return None

    best: dict | None = None
    # Prefer an existing tip_off / opening_tip row (stable across re-refines).
    for event in raw_events:
        details = _details(event)
        et = str(event.get("event_type") or "").lower()
        if et == "tip_off" or (et == "jump_ball" and details.get("kind") == "opening_tip"):
            if event.get("id") is not None:
                best = event
                break
    best_rise = -1.0
    if best is None:
        for event in raw_events:
            if not is_tipoff_shot(event):
                continue
            if event.get("id") is None:
                continue
            details = _details(event)
            try:
                rise = float(details.get("ball_rise") or -1)
            except (TypeError, ValueError):
                rise = -1.0
            if rise > best_rise:
                best_rise = rise
                best = event
    if best is None:
        control_ms = int(tip.get("control_ms") or tip_ms)
        for event in raw_events:
            if str(event.get("event_type") or "").lower() != "possession_change":
                continue
            if abs(int(event.get("timestamp_ms") or 0) - control_ms) <= 200:
                best = event
                break
    if best is None:
        return None

    details = {
        "kind": "opening_tip",
        "tip_winner": winner,
        "tip_ms": tip_ms,
        "control_ms": int(tip.get("control_ms") or tip_ms),
        "hold_ms": int(tip.get("hold_ms") or 0),
        "from_tracker": tip.get("from_tracker") or "",
        "method": tip.get("method") or "",
        "arrow_note": tip.get("arrow_note") or "",
        "adrian_quality": QUALITY_NOTE,
        "note": f"Opening tip — possession to tracker #{winner} (not a rebound)",
    }
    out = dict(best)
    out["event_type"] = "tip_off"
    out["player"] = winner
    out["shot_result"] = None
    out["confidence"] = 0.7
    out["timestamp_ms"] = int(tip.get("control_ms") or tip_ms)
    out["details_json"] = json.dumps(details)
    return out


def save_opening_tip_state(game_id: str, tip: dict[str, Any]) -> Path:
    """Persist tip winner for later jump / held-ball possession logic."""
    TIP_STATE_DIR.mkdir(parents=True, exist_ok=True)
    base = (game_id or "").split("__rerun_", 1)[0]
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in base)[:180]
    path = TIP_STATE_DIR / f"{safe}.json"
    payload = {
        "game_id": base,
        "opening_tip": tip,
        "quality_version": QUALITY_NOTE,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _is_make_event(event: dict) -> bool:
    et = str(event.get("event_type") or "").lower()
    sr = str(event.get("shot_result") or "").lower()
    return et in {"make", "made_two", "made_three", "made_free_throw"} or sr in {"make", "made"}


def _is_miss_event(event: dict) -> bool:
    et = str(event.get("event_type") or "").lower()
    sr = str(event.get("shot_result") or "").lower()
    return et in {"miss", "missed_two", "missed_three", "missed_free_throw"} or sr in {"miss", "missed"}


def counting_links_to_kept_shot(
    event: dict,
    kept_makes: list[dict],
    kept_misses: list[dict],
    *,
    window_ms: int = 2000,
) -> bool:
    """True if rebound/block/assist is tied to a real kept miss/make.

    CV invents block+rebound on every quick possession change after a fake
    "miss" (high pass contest). Only keep those when a kept miss/make anchors them.
    Steal/turnover/foul do not need a shot link.
    """
    et = str(event.get("event_type") or "").lower()
    details = _details(event)
    ts = int(event.get("timestamp_ms") or 0)

    if et in {"rebound", "block"}:
        shot_player = str(details.get("shot_player") or "")
        if not shot_player:
            return False
        for miss in kept_misses:
            if str(miss.get("player") or "") != shot_player:
                continue
            miss_ts = int(miss.get("timestamp_ms") or 0)
            # Block/rebound is stamped on the follow-up possession (at/after shot).
            if -200 <= (ts - miss_ts) <= window_ms:
                return True
        return False

    if et == "assist":
        scorer = str(details.get("scorer") or "")
        if not scorer:
            return False
        for make in kept_makes:
            if str(make.get("player") or "") != scorer:
                continue
            make_ts = int(make.get("timestamp_ms") or 0)
            if abs(ts - make_ts) <= 500:
                return True
        return False

    return True


def filter_counting_to_real_shots(
    counting: list[dict],
    kept_shots: list[dict],
) -> tuple[list[dict], int]:
    """Drop rebound/block/assist rows not anchored to a kept make/miss."""
    kept_makes = [e for e in kept_shots if _is_make_event(e)]
    kept_misses = [e for e in kept_shots if _is_miss_event(e)]
    kept: list[dict] = []
    dropped = 0
    for event in counting:
        et = str(event.get("event_type") or "").lower()
        if et in {"rebound", "block", "assist"}:
            if not counting_links_to_kept_shot(event, kept_makes, kept_misses):
                dropped += 1
                continue
        kept.append(event)
    return kept, dropped


def prefer_steal_over_block(
    counting: list[dict],
    *,
    window_ms: int = 800,
) -> tuple[list[dict], int]:
    """If a steal sits near a block, drop the block (contested pass, not a shot block)."""
    steals = [
        e for e in counting if str(e.get("event_type") or "").lower() == "steal"
    ]
    if not steals:
        return counting, 0
    steal_times = [int(e.get("timestamp_ms") or 0) for e in steals]
    kept: list[dict] = []
    dropped = 0
    for event in counting:
        if str(event.get("event_type") or "").lower() != "block":
            kept.append(event)
            continue
        ts = int(event.get("timestamp_ms") or 0)
        if any(abs(ts - st) <= window_ms for st in steal_times):
            dropped += 1
            continue
        kept.append(event)
    return kept, dropped


def _shot_rank_key(event: dict) -> tuple:
    """Prefer high confidence + real arc when picking among candidates."""
    details = _details(event)
    try:
        rise = float(details.get("ball_rise") or 0)
    except (TypeError, ValueError):
        rise = 0.0
    return (event_confidence(event), rise, -int(event.get("timestamp_ms") or 0))


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


def _event_priority(event: dict) -> int:
    """Higher = more primary when collapsing same-clock pileups."""
    et = str(event.get("event_type") or "").lower()
    if et in {
        "shot", "make", "miss", "made_two", "missed_two", "made_three",
        "missed_three", "made_free_throw", "missed_free_throw",
    }:
        return 50
    if et in {"steal", "turnover"}:
        return 40
    if et == "assist":
        return 35
    if et == "rebound":
        return 30
    if et == "block":
        return 20
    if et == "foul":
        return 10
    return 0


def collapse_same_timestamp(events: list[dict], window_ms: int = 50) -> list[dict]:
    """Keep at most one primary event per clock cluster.

    AI often stamps miss+rebound+block (or similar) on the exact same ms.
    Coach review saw three tags on one instant — collapse those.
    """
    if not events:
        return []
    ordered = sorted(
        events,
        key=lambda e: (
            int(e.get("timestamp_ms") or 0),
            -_event_priority(e),
            -event_confidence(e),
            int(e.get("id") or 0),
        ),
    )
    kept: list[dict] = []
    cluster_ts: int | None = None
    cluster: list[dict] = []

    def flush() -> None:
        nonlocal cluster, cluster_ts
        if not cluster:
            return
        # One winner in the cluster (highest priority then confidence).
        winner = cluster[0]
        kept.append(winner)
        w_et = str(winner.get("event_type") or "").lower()
        # Optional linked steal with a turnover (or vice versa) if different players.
        if w_et in {"steal", "turnover"}:
            partner_need = "turnover" if w_et == "steal" else "steal"
            w_player = str(winner.get("player") or "")
            for other in cluster[1:]:
                if str(other.get("event_type") or "").lower() != partner_need:
                    continue
                if str(other.get("player") or "") == w_player:
                    continue
                kept.append(other)
                break
        cluster = []
        cluster_ts = None

    for event in ordered:
        ts = int(event.get("timestamp_ms") or 0)
        if cluster_ts is None:
            cluster_ts = ts
            cluster = [event]
            continue
        if abs(ts - cluster_ts) <= window_ms:
            cluster.append(event)
            continue
        flush()
        cluster_ts = ts
        cluster = [event]
    flush()
    kept.sort(key=lambda e: (int(e.get("timestamp_ms") or 0), int(e.get("id") or 0)))
    return kept


def spread_pick(events: list[dict], limit: int, game_span_ms: int | None = None) -> list[dict]:
    """Pick up to `limit` events spread across the game, not just top confidence.

    Early CV firehose is high-confidence; taking top-N alone piles the ledger
    into the first 1–2 minutes. Bin the timeline and take the best event per bin.
    """
    if limit <= 0 or not events:
        return []
    if len(events) <= limit:
        return list(events)

    times = [int(e.get("timestamp_ms") or 0) for e in events]
    t_min = min(times)
    t_max = max(times)
    if game_span_ms is not None and game_span_ms > t_max:
        t_max = game_span_ms
    span = max(1, t_max - t_min)

    bins: dict[int, list[dict]] = {i: [] for i in range(limit)}
    for event in events:
        ts = int(event.get("timestamp_ms") or 0)
        idx = int((ts - t_min) / span * limit)
        if idx >= limit:
            idx = limit - 1
        if idx < 0:
            idx = 0
        bins[idx].append(event)

    picked: list[dict] = []
    used_ids: set[int] = set()
    for i in range(limit):
        candidates = bins.get(i) or []
        if not candidates:
            continue
        best = max(candidates, key=_shot_rank_key)
        eid = int(best["id"]) if best.get("id") is not None else None
        if eid is not None and eid in used_ids:
            continue
        picked.append(best)
        if eid is not None:
            used_ids.add(eid)

    # Fill remaining slots with highest-confidence leftovers, enforcing min gap.
    if len(picked) < limit:
        min_gap = max(15_000, span // max(limit * 2, 1))
        leftovers = sorted(
            (e for e in events if int(e.get("id") or -1) not in used_ids),
            key=_shot_rank_key,
            reverse=True,
        )
        for event in leftovers:
            if len(picked) >= limit:
                break
            ts = int(event.get("timestamp_ms") or 0)
            if any(abs(ts - int(p.get("timestamp_ms") or 0)) < min_gap for p in picked):
                continue
            picked.append(event)
            if event.get("id") is not None:
                used_ids.add(int(event["id"]))

    picked.sort(key=lambda e: (int(e.get("timestamp_ms") or 0), int(e.get("id") or 0)))
    return picked[:limit]


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


def _assign_shot_types_to_caps(
    shots: list[dict], team: dict, game_span_ms: int | None = None
) -> list[dict]:
    """AI shots rarely have shot_type; allocate spread makes/misses to book buckets."""
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

    need_makes = max(0, left["2pt_make"]) + max(0, left["3pt_make"]) + max(0, left["ft_make"])
    untyped_makes = spread_pick(untyped_makes, need_makes, game_span_ms=game_span_ms)
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

    untyped_misses = spread_pick(
        untyped_misses,
        max(0, left["ft_miss"]) + 80,
        game_span_ms=game_span_ms,
    )
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
    game_teams = resolve_adrian_teams(sb, ADRIAN_BASE)

    # Drop noise early
    usable = [
        e
        for e in raw_events
        if str(e.get("event_type") or "").lower()
        not in {"possession_change", "bookmark"}
    ]
    possession_changes = build_possession_changes(raw_events)
    tip_info = infer_opening_tip(raw_events)
    jump_ball_event = build_opening_jump_ball_event(raw_events, tip_info) if tip_info else None

    deduped = temporal_dedupe(usable, window_ms=2000)
    deduped = collapse_same_timestamp(deduped, window_ms=50)
    deduped, tipoff_dropped = drop_tipoff_shots(deduped)
    deduped, tipoff_reb_dropped = drop_tipoff_rebounds(deduped, tip_info)
    deduped, pass_like_dropped = drop_pass_like_shots(
        deduped, possession_changes, raw_events=raw_events
    )

    # Full detection span (~screencapture length) for spread bins
    game_span_ms = max((int(e.get("timestamp_ms") or 0) for e in raw_events), default=0)
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
    shot_pool = _assign_shot_types_to_caps(shot_pool, team, game_span_ms=game_span_ms)

    # Cap shot buckets with time-spread picks (not raw top-confidence).
    from boxscore_constraints import shot_bucket as _shot_bucket

    team_left = {
        "2pt_make": int(team.get("2pt_make") or 0),
        "3pt_make": int(team.get("3pt_make") or 0),
        "ft_make": int(team.get("ft_make") or 0),
        "ft_miss": int(team.get("ft_miss") or 0),
        "2pt_miss": 10_000,
        "3pt_miss": 10_000,
    }
    by_bucket: dict[str, list[dict]] = {}
    uncapped: list[dict] = []
    for e in shot_pool:
        probe = dict(e)
        if str(probe.get("event_type") or "").lower() != "shot":
            # normalize_event / assign already set shot for typed rows
            pass
        b = _shot_bucket(probe if str(probe.get("event_type") or "").lower() == "shot" else {
            **probe,
            "event_type": "shot",
            "shot_result": probe.get("shot_result") or (
                "make" if "made" in str(probe.get("event_type") or "").lower() else "miss"
            ),
        })
        if not b:
            uncapped.append(e)
            continue
        by_bucket.setdefault(b, []).append(e)

    capped_shots: list[dict] = list(uncapped)
    for bucket, limit in team_left.items():
        candidates = by_bucket.get(bucket) or []
        keep = spread_pick(candidates, int(limit), game_span_ms=game_span_ms)
        for event in keep:
            details = _details(event)
            details["boxscore_capped"] = True
            details["boxscore_bucket"] = bucket
            event["details_json"] = json.dumps(details)
            capped_shots.append(event)

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
    miss_events = spread_pick(miss_events, miss_cap, game_span_ms=game_span_ms)
    shots = make_events + miss_events + other_shots

    counting, orphan_counting_dropped = filter_counting_to_real_shots(counting_pool, shots)
    counting, promoted_rebounds = promote_rebounds_before_fake_makes(
        counting, raw_events, possession_changes, shots
    )
    counting, steal_over_block_dropped = prefer_steal_over_block(counting)

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
        counting_kept.extend(spread_pick(subset, int(limit), game_span_ms=game_span_ms))

    kept = collapse_same_timestamp(shots + counting_kept, window_ms=50)
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
        details["home_team"] = game_teams.get("home_team")
        details["away_team"] = game_teams.get("away_team")
        details["teams_label"] = game_teams.get("label")
        details["player_team"] = "unlinked"
        base = dict(orig) if orig else dict(e)
        # Carry shot_result from quality event when present
        if e.get("shot_result"):
            base["shot_result"] = e["shot_result"]
        # Prefer quality-pass details overlays (promoted rebound notes, etc.)
        for key in (
            "adrian_promoted_from_fake_make",
            "fake_make_id",
            "adrian_shot_type_assigned",
            "boxscore_bucket",
        ):
            if key in q_details:
                details[key] = q_details[key]
        stamped = _stamp_ledger_shot_type(base, details)
        stamped["details_json"] = json.dumps(details)
        restored.append(stamped)

    # Opening tip: keep tip_off with tip winner (not a fake make / rebound).
    if jump_ball_event is not None:
        jb_details = _details(jump_ball_event)
        jb_details["home_team"] = game_teams.get("home_team")
        jb_details["away_team"] = game_teams.get("away_team")
        jb_details["teams_label"] = game_teams.get("label")
        jb_details["player_team"] = "unlinked"
        jump_ball_event["details_json"] = json.dumps(jb_details)
        jb_id = int(jump_ball_event["id"]) if jump_ball_event.get("id") is not None else None
        restored = [e for e in restored if e.get("id") != jb_id]
        restored.append(jump_ball_event)
        restored.sort(key=lambda e: (int(e.get("timestamp_ms") or 0), int(e.get("id") or 0)))
        if tip_info:
            tip_payload = dict(tip_info)
            tip_payload["teams"] = game_teams
            save_opening_tip_state(ADRIAN_BASE, tip_payload)

    report = {
        "raw": len(raw_events),
        "after_dedupe": len(deduped),
        "pass_like_shots_dropped": pass_like_dropped,
        "tipoff_shots_dropped": tipoff_dropped,
        "tipoff_rebounds_dropped": tipoff_reb_dropped,
        "opening_tip": tip_info,
        "tip_off_kept": bool(jump_ball_event),
        "jump_ball_kept": bool(jump_ball_event),  # legacy alias
        "orphan_counting_dropped": orphan_counting_dropped,
        "promoted_rebounds": promoted_rebounds,
        "steal_over_block_dropped": steal_over_block_dropped,
        "game_teams": game_teams,
        "kept": len(restored),
        "quality_version": QUALITY_NOTE,
        "team_caps": team,
        "heuristic_count_caps": hcaps,
        "makes_kept": makes_n,
        "misses_kept": len(miss_events),
        "blocks_kept": sum(
            1 for e in restored if str(e.get("event_type") or "").lower() == "block"
        ),
        "scorebook_points": team.get("points"),
        "ledger_points_est": (
            2 * int(team.get("2pt_make") or 0)
            + 3 * int(team.get("3pt_make") or 0)
            + int(team.get("ft_make") or 0)
        ),
        "kept_ts_min_ms": min((int(e.get("timestamp_ms") or 0) for e in restored), default=None),
        "kept_ts_max_ms": max((int(e.get("timestamp_ms") or 0) for e in restored), default=None),
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
                WHERE game_id=?
                  AND COALESCE(review_status,'') != 'corrected'
                  AND COALESCE(review_notes,'') NOT LIKE '%Corrected in Film Tool%'""",
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
                              player=?,
                              timestamp_ms=?,
                              details_json=?
                        WHERE id=?""",
                    (
                        f"{QUALITY_NOTE}:keep",
                        row.get("event_type"),
                        row.get("shot_result"),
                        row.get("player"),
                        row.get("timestamp_ms"),
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
