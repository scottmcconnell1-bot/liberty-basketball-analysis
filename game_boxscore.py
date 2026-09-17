"""Official basketball box: line score, team stats, then individuals.

Scott 2026-09-15: this is the product stats output. Film review is later.

Layout (same stats major programs keep):
  1) Line score — Q1–Q4 (+ OT) and running totals, Liberty vs opponent
  2) Team stats
  3) Individual stats for both teams

Counting columns: MIN, PTS, 2PM-A-%, 3PM-A-%, FTM-A-%, OReb, DReb, REB, AST, STL, BLK, TO, PF.

Player shooting/PTS use a confirmed scorebook cell when that cell is filled.
Empty book cells (REB/AST/STL/BLK/TO/PF and missed attempts) come from accepted
AI events. Duplicate jerseys are split by shirt color: Home = light (usually
white), Away = dark. Quarters without book cells are an even split of the final.
"""

from __future__ import annotations

import json
import re
from typing import Any

from analysis_helpers import infer_period_labels, resolve_video_duration_ms
from program_mode import (
    canonical_event_key,
    film_slots_from_scorebook,
    load_scorebook,
    scorebook_named_players,
)

COUNTING_KEYS = (
    "pts",
    "fgm2",
    "fga2",
    "fgm3",
    "fga3",
    "ftm",
    "fta",
    "oreb",
    "dreb",
    "reb",
    "ast",
    "stl",
    "blk",
    "tov",
    "pf",
    "pts_paint",
    "pts_2nd",
    "pts_off_to",
)


def empty_line() -> dict[str, Any]:
    line = {key: 0 for key in COUNTING_KEYS}
    line["min"] = 0.0
    return line


def shooting_pct(made: int, att: int):
    if not att:
        return None
    return round(100.0 * float(made) / float(att), 1)


def decorate_line(line: dict[str, Any]) -> dict[str, Any]:
    out = empty_line()
    out.update(line or {})
    out["fgm"] = int(out.get("fgm2") or 0) + int(out.get("fgm3") or 0)
    out["fga"] = int(out.get("fga2") or 0) + int(out.get("fga3") or 0)
    if not out.get("reb"):
        out["reb"] = int(out.get("oreb") or 0) + int(out.get("dreb") or 0)
    out["fg2_pct"] = shooting_pct(int(out.get("fgm2") or 0), int(out.get("fga2") or 0))
    out["fg3_pct"] = shooting_pct(int(out.get("fgm3") or 0), int(out.get("fga3") or 0))
    out["ft_pct"] = shooting_pct(int(out.get("ftm") or 0), int(out.get("fta") or 0))
    out["fg_pct"] = shooting_pct(int(out.get("fgm") or 0), int(out.get("fga") or 0))
    return out


def _add_into(target: dict[str, Any], delta: dict[str, Any]) -> None:
    for key in COUNTING_KEYS:
        target[key] = int(target.get(key) or 0) + int(delta.get(key) or 0)
    target["min"] = float(target.get("min") or 0) + float(delta.get("min") or 0)


def sum_lines(lines: list[dict[str, Any]]) -> dict[str, Any]:
    total = empty_line()
    for line in lines:
        _add_into(total, line)
    return decorate_line(total)


def apply_starter_roles(players: list[dict[str, Any]], starter_jerseys: set[str]) -> list[dict[str, Any]]:
    """Mark starter vs bench when a coach (or later, tip-off) named five jerseys."""
    if not starter_jerseys:
        for row in players:
            row["role"] = None
        players.sort(key=lambda r: (-int(r.get("pts") or 0), _jersey_key(r.get("jersey"))))
        return players
    for row in players:
        jersey = _jersey_key(row.get("jersey"))
        row["role"] = "starter" if jersey in starter_jerseys else "bench"
    players.sort(key=lambda r: (0 if r.get("role") == "starter" else 1, -int(r.get("pts") or 0), _jersey_key(r.get("jersey"))))
    return players


def bench_points(players: list[dict[str, Any]]) -> int | None:
    if not any(row.get("role") == "bench" for row in players):
        return None
    return sum(int(row.get("pts") or 0) for row in players if row.get("role") == "bench")


def starter_points(players: list[dict[str, Any]]) -> int | None:
    if not any(row.get("role") == "starter" for row in players):
        return None
    return sum(int(row.get("pts") or 0) for row in players if row.get("role") == "starter")


def _jersey_key(value) -> str:
    text = str(value if value is not None else "").strip().lstrip("#").strip()
    m = re.match(r"^0*(\d+)", text)
    if m:
        return m.group(1)
    text = text.lstrip("0")
    return text or "0"


def scorebook_filled_keys(player: dict[str, Any]) -> set[str]:
    """Keys the spiral actually wrote, including explicit zeros."""
    filled: set[str] = set()
    extras = player.get("extras") if isinstance(player.get("extras"), dict) else {}
    if player.get("pts") is not None:
        filled.add("pts")
    if extras.get("fg2") is not None or player.get("fgm") is not None:
        filled.add("fgm2")
    if extras.get("fg3") is not None or player.get("tpm") is not None:
        filled.add("fgm3")
    if player.get("fga") is not None:
        filled.add("fga2")
        filled.add("fga3")
    if player.get("tpa") is not None:
        filled.add("fga3")
    if player.get("ftm") is not None:
        filled.add("ftm")
    if player.get("fta") is not None:
        filled.add("fta")
    mapping = (("reb", "reb"), ("ast", "ast"), ("stl", "stl"), ("blk", "blk"), ("to", "tov"), ("fouls", "pf"))
    for src, dest in mapping:
        if player.get(src) is not None:
            filled.add(dest)
    return filled


_HASH_JERSEY = re.compile(r"^#\s*(\d+)")
_NUM_NAME = re.compile(r"^(\d+)\s+\S")


def _event_jersey_and_tracker(player, extra: dict[str, Any] | None) -> tuple[str | None, int | None]:
    extra = extra or {}
    jersey = None
    tracker = None
    if extra.get("jersey_number") is not None:
        jersey = _jersey_key(extra.get("jersey_number"))
    raw_tracker = extra.get("tracker_id")
    if raw_tracker is not None and str(raw_tracker).lstrip("-").isdigit():
        tracker = int(raw_tracker)
    text = str(player or "").strip()
    if jersey is None:
        hashed = _HASH_JERSEY.match(text)
        named = _NUM_NAME.match(text)
        if hashed:
            jersey = _jersey_key(hashed.group(1))
        elif named:
            jersey = _jersey_key(named.group(1))
    if tracker is None and text.isdigit():
        tracker = int(text)
        if extra.get("jersey_number") is None:
            jersey = None
    return jersey, tracker


def _side_from_home_away(team_side: str, liberty_is_home: bool | None) -> str:
    if liberty_is_home is False:
        return "liberty" if team_side == "away" else "opponent"
    return "liberty" if team_side == "home" else "opponent"


def _merge_ai_into_book_line(book_line: dict[str, Any], delta: dict[str, Any], event_type: str, extra: dict[str, Any], filled: set[str]) -> None:
    """Fill unrecorded counting stats from film. Do not overwrite book PTS/makes."""
    for key_name in ("oreb", "dreb", "reb", "ast", "stl", "blk", "tov", "pf", "pts_paint", "pts_2nd", "pts_off_to"):
        if key_name in filled:
            continue
        book_line[key_name] = int(book_line.get(key_name) or 0) + int(delta.get(key_name) or 0)
    et = (event_type or "").lower()
    kind = str(extra.get("shot_kind") or "").lower()
    if et == "missed_two" or (et == "miss" and kind in ("", "2")):
        if "fga2" not in filled:
            book_line["fga2"] = int(book_line.get("fga2") or 0) + 1
    elif et == "missed_three" or (et == "miss" and kind == "3"):
        if "fga3" not in filled:
            book_line["fga3"] = int(book_line.get("fga3") or 0) + 1
    elif et == "missed_free_throw" or (et == "miss" and kind == "ft"):
        if "fta" not in filled:
            book_line["fta"] = int(book_line.get("fta") or 0) + 1


def line_from_scorebook_player(player: dict[str, Any]) -> dict[str, Any]:
    """Fill counting cells the spiral book actually recorded; leave the rest 0."""
    line = empty_line()
    extras = player.get("extras") if isinstance(player.get("extras"), dict) else {}
    fgm2 = extras.get("fg2")
    fgm3 = extras.get("fg3")
    if fgm3 is None:
        fgm3 = player.get("tpm")
    if player.get("pts") is not None:
        line["pts"] = int(player.get("pts") or 0)
    if fgm2 is not None:
        line["fgm2"] = int(fgm2 or 0)
        line["fga2"] = int(fgm2 or 0)
    if fgm3 is not None:
        line["fgm3"] = int(fgm3 or 0)
        line["fga3"] = int(fgm3 or 0)
        if player.get("tpa") is not None:
            line["fga3"] = int(player.get("tpa") or 0)
    if player.get("ftm") is not None:
        line["ftm"] = int(player.get("ftm") or 0)
    if player.get("fta") is not None:
        line["fta"] = int(player.get("fta") or 0)
    elif line["ftm"]:
        line["fta"] = line["ftm"]
    if player.get("reb") is not None:
        line["reb"] = int(player.get("reb") or 0)
    if player.get("ast") is not None:
        line["ast"] = int(player.get("ast") or 0)
    if player.get("stl") is not None:
        line["stl"] = int(player.get("stl") or 0)
    if player.get("blk") is not None:
        line["blk"] = int(player.get("blk") or 0)
    if player.get("to") is not None:
        line["tov"] = int(player.get("to") or 0)
    if player.get("fouls") is not None:
        line["pf"] = int(player.get("fouls") or 0)
    if player.get("min") is not None:
        line["min"] = float(player.get("min") or 0)
    if line["pts"] == 0 and (line["fgm2"] or line["fgm3"] or line["ftm"]):
        line["pts"] = 2 * line["fgm2"] + 3 * line["fgm3"] + line["ftm"]
    return line


def _event_details(row) -> dict[str, Any]:
    raw = None
    if hasattr(row, "keys"):
        keys = row.keys()
        raw = row["details_json"] if "details_json" in keys else None
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def apply_ai_event(line: dict[str, Any], event_type: str, shot_result: str | None = None, details: dict | None = None) -> int:
    """Mutate line with one event. Returns points scored on this event."""
    et = (event_type or "").lower()
    extra = details if isinstance(details, dict) else {}
    kind = str(extra.get("shot_kind") or "").lower()
    if et in ("shot", "possession_change", "bookmark"):
        return 0
    if et == "made_two" or (et == "make" and kind in ("", "2")):
        line["fgm2"] += 1
        line["fga2"] += 1
        line["pts"] += 2
        return 2
    if et == "missed_two" or (et == "miss" and kind in ("", "2")):
        line["fga2"] += 1
        return 0
    if et == "made_three" or (et == "make" and kind == "3"):
        line["fgm3"] += 1
        line["fga3"] += 1
        line["pts"] += 3
        return 3
    if et == "missed_three" or (et == "miss" and kind == "3"):
        line["fga3"] += 1
        return 0
    if et == "made_free_throw" or (et == "make" and kind == "ft"):
        line["ftm"] += 1
        line["fta"] += 1
        line["pts"] += 1
        return 1
    if et == "missed_free_throw" or (et == "miss" and kind == "ft"):
        line["fta"] += 1
        return 0
    if et == "make":
        line["fgm2"] += 1
        line["fga2"] += 1
        line["pts"] += 2
        return 2
    if et == "miss":
        line["fga2"] += 1
        return 0
    if et in ("offensive_rebound", "rebound_offensive"):
        line["oreb"] += 1
        line["reb"] += 1
        return 0
    if et in ("defensive_rebound", "rebound_defensive"):
        line["dreb"] += 1
        line["reb"] += 1
        return 0
    if et == "rebound":
        line["reb"] += 1
        return 0
    if et == "assist":
        line["ast"] += 1
        return 0
    if et == "steal":
        line["stl"] += 1
        return 0
    if et == "block":
        line["blk"] += 1
        return 0
    if et == "turnover":
        line["tov"] += 1
        return 0
    if et == "foul":
        line["pf"] += 1
        return 0
    return 0


def _side_for_scorebook_player(player: dict[str, Any], liberty_is_home: bool | None) -> str:
    team = (player.get("team") or "").lower()
    if liberty_is_home is True:
        return "liberty" if team == "home" else "opponent"
    if liberty_is_home is False:
        return "liberty" if team == "away" else "opponent"
    return "liberty" if team == "home" else "opponent"


def _liberty_home_flag(scorebook: dict[str, Any] | None) -> bool | None:
    if not scorebook:
        return None
    home = (scorebook.get("home_team") or "").lower()
    away = (scorebook.get("away_team") or "").lower()
    if "liberty" in home:
        return True
    if "liberty" in away:
        return False
    return None


def even_split_line_score(liberty_pts: int, opponent_pts: int, periods: int = 4) -> list[dict[str, Any]]:
    """Placeholder quarters when the book has a final but no Q1–Q4 cells."""
    n = max(int(periods or 4), 1)

    def parts(total: int) -> list[int]:
        total = int(total or 0)
        base, rem = divmod(total, n)
        return [base + (1 if i >= n - rem else 0) for i in range(n)]

    return running_line_score(list(zip(parts(liberty_pts), parts(opponent_pts))))


def running_line_score(period_pts: list[tuple[int, int]]) -> list[dict[str, Any]]:
    """period_pts is [(liberty, opponent), ...] for Q1..Q4 (and OT)."""
    lib_run = 0
    opp_run = 0
    rows = []
    labels = ["Q1", "Q2", "Q3", "Q4", "OT"]
    for index, (liberty, opponent) in enumerate(period_pts):
        lib_run += int(liberty or 0)
        opp_run += int(opponent or 0)
        label = labels[index] if index < len(labels) else f"P{index + 1}"
        rows.append({
            "period": label,
            "liberty": int(liberty or 0),
            "opponent": int(opponent or 0),
            "liberty_running": lib_run,
            "opponent_running": opp_run,
        })
    return rows


def _line_score_from_scorebook(scorebook: dict[str, Any], liberty_is_home: bool | None) -> list[dict[str, Any]] | None:
    quarters = list(scorebook.get("quarters") or [])
    if not quarters:
        return None
    pairs = []
    for row in quarters:
        home_pts = int(row.get("home_pts") or row.get("home") or 0)
        away_pts = int(row.get("away_pts") or row.get("away") or 0)
        if liberty_is_home is False:
            pairs.append((away_pts, home_pts))
        else:
            pairs.append((home_pts, away_pts))
    return running_line_score(pairs)


def build_official_box(db, game_id: str) -> dict[str, Any]:
    key = canonical_event_key(db, game_id)
    scorebook = load_scorebook(game_id)
    liberty_is_home = _liberty_home_flag(scorebook)
    slots = film_slots_from_scorebook(scorebook) if scorebook else {}
    liberty_name = "Liberty"
    opponent_name = (slots.get("opponent_name") if slots else None) or (
        (scorebook or {}).get("home_team") if liberty_is_home is False else (scorebook or {}).get("away_team")
    ) or "Opponent"

    roster: dict[str, dict[str, Any]] = {}
    for person in scorebook_named_players(scorebook):
        jersey = _jersey_key(person.get("jersey"))
        side = _side_for_scorebook_player(person, liberty_is_home)
        roster[f"{side}:{jersey}"] = {
            "jersey": str(person.get("jersey") or jersey),
            "name": person.get("name") or "Unknown",
            "side": side,
            "line": line_from_scorebook_player(person),
            "source": "scorebook",
            "book_filled": scorebook_filled_keys(person),
        }

    shades: dict[int, dict[str, Any]] = {}
    roster_index: dict[str, list[dict[str, Any]]] = {}
    try:
        from jersey_shade import ensure_tracker_shades
        shades = ensure_tracker_shades(db, key)
    except Exception:
        shades = {}
    try:
        from adrian_identity import scorebook_roster_index
        roster_index = scorebook_roster_index(scorebook) if scorebook else {}
    except Exception:
        roster_index = {}

    duration_ms = resolve_video_duration_ms(db, game_id, analysis_key=key)
    try:
        events = db.execute(
            """SELECT player, event_type, shot_result, timestamp_ms, review_status, details_json
                 FROM events
                WHERE game_id=?
                  AND review_status IN ('accepted', 'corrected')
                ORDER BY timestamp_ms ASC""",
            (key,),
        ).fetchall()
    except Exception:
        events = db.execute(
            """SELECT player, event_type, shot_result, timestamp_ms, review_status
                 FROM events
                WHERE game_id=?
                  AND review_status IN ('accepted', 'corrected')
                ORDER BY timestamp_ms ASC""",
            (key,),
        ).fetchall()

    lib_q = [0, 0, 0, 0, 0]
    opp_q = [0, 0, 0, 0, 0]
    unassigned: dict[str, dict[str, Any]] = {}
    last_reb_kind = None
    last_reb_side = None
    last_to_side = None

    identity_by_tracker: dict[int, dict[str, Any] | None] = {}
    for row in events:
        raw_player = row["player"] if hasattr(row, "keys") else row[0]
        event_type = row["event_type"] if hasattr(row, "keys") else row[1]
        shot_result = row["shot_result"] if hasattr(row, "keys") else row[2]
        timestamp_ms = row["timestamp_ms"] if hasattr(row, "keys") else row[3]
        extra = _event_details(row)
        period = infer_period_labels(timestamp_ms, duration_ms)
        q_index = min(max(int(period["quarter"]) - 1, 0), 4)
        delta = empty_line()
        pts = apply_ai_event(delta, event_type, shot_result, extra)
        jersey, tracker = _event_jersey_and_tracker(raw_player, extra)
        team_side = extra.get("team_side")
        if not team_side and tracker is not None:
            team_side = (shades.get(int(tracker)) or {}).get("side")
        if jersey is None and tracker is not None and roster_index:
            if tracker not in identity_by_tracker:
                try:
                    from adrian_identity import resolve_event_identity
                    identity_by_tracker[tracker] = resolve_event_identity(
                        db,
                        key,
                        {"player": raw_player, "timestamp_ms": timestamp_ms},
                        roster_index,
                        shades=shades,
                    )
                except Exception:
                    identity_by_tracker[tracker] = None
            identity = identity_by_tracker.get(tracker)
            if identity and identity.get("status") == "matched":
                jersey = _jersey_key(identity.get("jersey_number"))
                team_side = identity.get("team_side") or team_side
                extra["jersey_number"] = identity.get("jersey_number")
                extra["team_side"] = team_side
        side = None
        target = None
        if jersey and team_side in ("home", "away"):
            side = _side_from_home_away(team_side, liberty_is_home)
            target = roster.get(f"{side}:{_jersey_key(jersey)}")
        if target is None and jersey:
            lib_key = f"liberty:{_jersey_key(jersey)}"
            opp_key = f"opponent:{_jersey_key(jersey)}"
            if lib_key in roster and opp_key not in roster:
                target, side = roster[lib_key], "liberty"
            elif opp_key in roster and lib_key not in roster:
                target, side = roster[opp_key], "opponent"
        if target is None:
            bucket_key = f"{team_side or 'unk'}:{jersey or raw_player}"
            bucket = unassigned.setdefault(str(bucket_key), {
                "jersey": jersey or str(raw_player or ""),
                "name": f"AI #{jersey or raw_player}",
                "side": "unassigned",
                "line": empty_line(),
                "source": "ai",
            })
            _add_into(bucket["line"], delta)
            continue
        book_line = target["line"]
        et = (event_type or "").lower()
        if pts and extra.get("in_paint"):
            delta["pts_paint"] = pts
        if pts and last_reb_kind == "oreb" and last_reb_side == side:
            delta["pts_2nd"] = pts
        if pts and last_to_side and last_to_side != side:
            delta["pts_off_to"] = pts
        if target["source"] == "scorebook":
            _merge_ai_into_book_line(book_line, delta, event_type, extra, target.get("book_filled") or set())
        else:
            _add_into(book_line, delta)
        if et in ("rebound_offensive", "offensive_rebound") or extra.get("rebound_kind") == "oreb":
            last_reb_kind, last_reb_side = "oreb", side
        elif et in ("rebound_defensive", "defensive_rebound") or extra.get("rebound_kind") == "dreb":
            last_reb_kind, last_reb_side = "dreb", side
        if et == "turnover":
            last_to_side = side
        if pts:
            last_to_side = None
            if last_reb_kind == "oreb" and last_reb_side == side:
                last_reb_kind = None
        if pts and side == "liberty":
            lib_q[q_index] += pts
        elif pts and side == "opponent":
            opp_q[q_index] += pts

    period_pairs = list(zip(lib_q[:4], opp_q[:4]))
    if lib_q[4] or opp_q[4]:
        period_pairs.append((lib_q[4], opp_q[4]))

    book_line = _line_score_from_scorebook(scorebook or {}, liberty_is_home)
    if book_line:
        line_score = book_line
        line_source = "scorebook"
    elif scorebook and (
        scorebook.get("final_score_home") is not None
        or scorebook.get("final_score_away") is not None
    ):
        if liberty_is_home is False:
            lib_final = int(scorebook.get("final_score_away") or 0)
            opp_final = int(scorebook.get("final_score_home") or 0)
        else:
            lib_final = int(scorebook.get("final_score_home") or 0)
            opp_final = int(scorebook.get("final_score_away") or 0)
        line_score = even_split_line_score(lib_final, opp_final)
        line_source = "scorebook_even_split"
    else:
        line_score = running_line_score(period_pairs or [(0, 0), (0, 0), (0, 0), (0, 0)])
        line_source = "ai_video_split"

    liberty_players = []
    opponent_players = []
    for item in roster.values():
        decorated = decorate_line(item["line"])
        row = {
            "jersey": item["jersey"],
            "name": item["name"],
            "side": item["side"],
            "source": item["source"],
            **decorated,
        }
        if item["side"] == "liberty":
            liberty_players.append(row)
        else:
            opponent_players.append(row)

    from game_lineups import jersey_set, safe_load_starters

    starters = safe_load_starters(game_id)
    liberty_players = apply_starter_roles(liberty_players, jersey_set(starters.get("liberty")))
    opponent_players = apply_starter_roles(opponent_players, jersey_set(starters.get("opponent")))

    unassigned_rows = []
    for item in unassigned.values():
        decorated = decorate_line(item["line"])
        if decorated["pts"] or decorated["fga"] or decorated["reb"] or decorated["stl"] or decorated["tov"]:
            unassigned_rows.append({
                "jersey": item["jersey"],
                "name": item["name"],
                "side": "unassigned",
                "source": "ai",
                **decorated,
            })
    unassigned_rows.sort(key=lambda r: (-int(r["pts"]), r["jersey"]))

    liberty_team = sum_lines(liberty_players)
    opponent_team = sum_lines(opponent_players)
    if line_score:
        liberty_team["pts"] = line_score[-1]["liberty_running"] if line_source == "scorebook" else liberty_team["pts"]
        opponent_team["pts"] = line_score[-1]["opponent_running"] if line_source == "scorebook" else opponent_team["pts"]
    if scorebook:
        if liberty_is_home is False:
            liberty_team["pts"] = int(scorebook.get("final_score_away") or liberty_team["pts"])
            opponent_team["pts"] = int(scorebook.get("final_score_home") or opponent_team["pts"])
        elif liberty_is_home is True:
            liberty_team["pts"] = int(scorebook.get("final_score_home") or liberty_team["pts"])
            opponent_team["pts"] = int(scorebook.get("final_score_away") or opponent_team["pts"])
        else:
            liberty_team["pts"] = int(scorebook.get("final_score_away") or liberty_team["pts"])
            opponent_team["pts"] = int(scorebook.get("final_score_home") or opponent_team["pts"])
        liberty_team = decorate_line(liberty_team)
        opponent_team = decorate_line(opponent_team)

    liberty_team["bench_pts"] = bench_points(liberty_players)
    opponent_team["bench_pts"] = bench_points(opponent_players)
    liberty_team["starter_pts"] = starter_points(liberty_players)
    opponent_team["starter_pts"] = starter_points(opponent_players)

    if line_source == "scorebook":
        line_note = (
            "Quarter scores from the confirmed scorebook. PTS/makes in the book stay; "
            "REB/AST/STL/BLK/TO/PF and missed shots come from film. Same jersey on both "
            "teams is split by color: Home light (usually white), Away dark."
        )
    elif line_source == "scorebook_even_split":
        line_note = (
            "This scorebook has a final score but no Q1–Q4 cells, so the line score is an even "
            "split of that final — not the referee's periods. PTS/makes follow the book. "
            "REB/AST/STL/BLK/TO/PF and misses come from film. Home = light jersey, Away = dark."
        )
    else:
        line_note = (
            "No confirmed scorebook quarters or final, so Q1–Q4 are detector counts in four "
            "equal time slices of the video file. They are not the referee's period endings. "
            "Home = light jersey, Away = dark."
        )

    return {
        "game_id": game_id,
        "canonical_key": key,
        "liberty_name": liberty_name,
        "opponent_name": opponent_name,
        "line_score": line_score,
        "line_score_source": line_source,
        "line_score_note": line_note,
        "starters": starters,
        "team": {"liberty": liberty_team, "opponent": opponent_team},
        "players": {"liberty": liberty_players, "opponent": opponent_players},
        "unassigned": unassigned_rows,
        "scorebook_present": bool(scorebook),
        "final": {
            "liberty": liberty_team.get("pts") or 0,
            "opponent": opponent_team.get("pts") or 0,
        },
    }
