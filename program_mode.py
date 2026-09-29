"""Program mode — AI counting stats first (not a play-by-play click queue).

Scott 2026-09-15: the product job is a box score. Film clip review is later.

  1) Promote useful AI drafts onto the ledger (not confidence auto-accept).
  2) Ignore noise types (e.g. possession_change) for counting stats.
  3) Compare ledger to confirmed scorebook → exception list only.
  4) Coach spot-checks exceptions only; does not walk every AI event.

This is intentionally separate from settings ``auto_accept_event_confidence``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stat_book.paths import sanitize_game_id
from stats import _shot_attempt_already_counted

PROGRAM_LEDGER_TYPES = (
    "shot",
    "miss",
    "make",
    "missed_two",
    "made_two",
    "missed_three",
    "made_three",
    "missed_free_throw",
    "made_free_throw",
    "rebound",
    "rebound_offensive",
    "rebound_defensive",
    "assist",
    "turnover",
    "steal",
    "block",
    "foul",
    "foul_personal",
    "foul_shooting",
    "foul_technical",
    "jump_ball",
    "tip_off",
)

NOISE_TYPES = ("possession_change", "bookmark")

PROVENANCE_VERSION = "program_auto_ledger_v1"

POINTS_BY_TYPE = {
    "make": 2,
    "made_two": 2,
    "made_three": 3,
    "made_free_throw": 1,
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def scorebook_path(game_id: str) -> Path:
    """Confirmed scorebook file for a game; raises ValueError for ids that could escape the dir."""
    return _repo_root() / "data" / "stat_books" / "confirmed" / f"{sanitize_game_id(game_id)}.json"


def load_scorebook(game_id: str) -> dict[str, Any] | None:
    try:
        path = scorebook_path(game_id)
        if not path.is_file() and "__rerun_" in game_id:
            path = scorebook_path(game_id.split("__rerun_", 1)[0])
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _jersey_sort_key(jersey: str) -> tuple:
    text = str(jersey or "").strip()
    if text.isdigit():
        return (0, int(text))
    return (1, text.lower())


def scorebook_named_players(scorebook: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Drop blank spiral rows; keep jersey/name pairs from a confirmed book."""
    players = []
    for row in (scorebook or {}).get("players") or []:
        jersey = str(row.get("jersey") if row.get("jersey") is not None else "").strip()
        name = (row.get("name") or "").strip()
        if not jersey and not name:
            continue
        team = str(row.get("team") or "").strip().lower()
        if team in {"h", "home"}:
            team = "home"
        elif team in {"a", "away"}:
            team = "away"
        else:
            team = team or "home"
        team_name = (
            (scorebook or {}).get("home_team")
            if team == "home"
            else (scorebook or {}).get("away_team")
        )
        players.append({
            "jersey": jersey,
            "jersey_number": jersey,
            "name": name or "Unknown",
            "team": team,
            "team_name": team_name,
            "label": f"{jersey} - {name or 'Unknown'}" if jersey else (name or "Unknown"),
            "pts": row.get("pts"),
            "fgm": row.get("fgm"),
            "fga": row.get("fga"),
            "tpm": row.get("tpm"),
            "tpa": row.get("tpa"),
            "ftm": row.get("ftm"),
            "fta": row.get("fta"),
            "reb": row.get("reb"),
            "ast": row.get("ast"),
            "stl": row.get("stl"),
            "blk": row.get("blk"),
            "to": row.get("to"),
            "fouls": row.get("fouls"),
            "min": row.get("min"),
            "extras": row.get("extras") if isinstance(row.get("extras"), dict) else {},
        })
    players.sort(key=lambda p: (_jersey_sort_key(p["jersey"]), p["name"].lower(), p["team"]))
    return players


def _liberty_is_home(scorebook: dict[str, Any] | None) -> bool | None:
    home = ((scorebook or {}).get("home_team") or "").lower()
    away = ((scorebook or {}).get("away_team") or "").lower()
    if "liberty" in home:
        return True
    if "liberty" in away:
        return False
    return None


def film_slots_from_scorebook(scorebook: dict[str, Any] | None) -> dict[str, Any]:
    """Map a confirmed scorebook onto Liberty vs named-opponent Film Tool slots."""
    named = scorebook_named_players(scorebook)
    home = [p for p in named if p["team"] == "home"]
    away = [p for p in named if p["team"] == "away"]
    liberty_home = _liberty_is_home(scorebook)
    if liberty_home is True:
        our, opp = home, away
        opponent_name = (scorebook or {}).get("away_team") or "Opponent"
    else:
        our, opp = away, home
        opponent_name = (scorebook or {}).get("home_team") or "Opponent"
    return {"our": our, "opp": opp, "opponent_name": opponent_name}


def analysis_players_from_scorebook(scorebook: dict[str, Any] | None) -> list[dict[str, Any]]:
    players = []
    for index, row in enumerate(scorebook_named_players(scorebook)):
        jersey = row["jersey"]
        try:
            jersey_number = int(jersey) if jersey not in ("", None) and str(jersey).lstrip("-").isdigit() else None
        except (TypeError, ValueError):
            jersey_number = None
        liberty_home = _liberty_is_home(scorebook)
        if liberty_home is False:
            side = "liberty" if row["team"] == "away" else "opponent"
        else:
            side = "liberty" if row["team"] == "home" else "opponent"
        side_label = "Liberty" if side == "liberty" else (row.get("team_name") or "Opponent")
        players.append({
            "id": None,
            "jersey_number": jersey_number,
            "name": row["name"],
            "label": row["label"],
            "position": None,
            "grade": None,
            "sort_order": index,
            "team": row["team"],
            "team_name": row["team_name"],
            "side": side,
            "side_label": side_label,
        })
    return players


def import_scorebook_to_film_roster(db, game_id, *, season_id=None, level=None, gender=None) -> dict[str, Any]:
    """Write confirmed scorebook home/away lists into Film Tool roster slots."""
    from film_roster import save_film_roster

    book = load_scorebook(game_id)
    if not book:
        raise ValueError("No confirmed scorebook for this game")

    if season_id is None or level is None or gender is None:
        from analysis_helpers import resolve_analysis_game_context

        context = resolve_analysis_game_context(db, game_id)
        season_id = season_id or context.get("season_id")
        level = level or context.get("level") or "jrhigh"
        gender = gender or context.get("gender") or "boys"

    if not season_id:
        raise ValueError("season_id is required to import a scorebook roster")

    slots = film_slots_from_scorebook(book)
    saved = {
        "our": save_film_roster(
            db,
            season_id=season_id,
            level=level,
            gender=gender,
            side="our",
            players=slots["our"],
            replace=True,
        ),
        "opp": save_film_roster(
            db,
            season_id=season_id,
            level=level,
            gender=gender,
            side="opp",
            opponent_name=slots["opponent_name"],
            players=slots["opp"],
            replace=True,
        ),
    }
    return {
        "game_id": game_id,
        "season_id": season_id,
        "level": level,
        "gender": gender,
        "home_team": book.get("home_team"),
        "away_team": book.get("away_team"),
        "opponent_name": slots["opponent_name"],
        "slots": {side: result["count"] for side, result in saved.items()},
    }


def base_analysis_key(game_id: str) -> str:
    if "__rerun_" in (game_id or ""):
        return game_id.split("__rerun_", 1)[0]
    return game_id or ""


def related_game_keys(db, game_id: str) -> list[str]:
    base = base_analysis_key(game_id)
    keys = {base, game_id}
    rows = db.execute(
        """SELECT analysis_key FROM analysis_runs
            WHERE analysis_key = ? OR analysis_key LIKE ?
            ORDER BY id DESC LIMIT 20""",
        (base, f"{base}__rerun_%"),
    ).fetchall()
    for row in rows:
        key = row["analysis_key"] if hasattr(row, "keys") else row[0]
        if key:
            keys.add(key)
    return sorted(keys)


def _row_value(row, name: str, index: int):
    if row is None:
        return None
    if hasattr(row, "keys"):
        return row[name]
    return row[index]


def _trusted_event_count(db, key: str) -> int:
    row = db.execute(
        """SELECT COUNT(*) AS c FROM events
            WHERE game_id=? AND review_status IN ('pending','accepted','corrected')""",
        (key,),
    ).fetchone()
    return int(_row_value(row, "c", 0) or 0)


def canonical_event_key(db, game_id: str) -> str:
    """One key only — primary+rerun copies must not double-count.

    The newest finished run that still has events is the stat source. An older
    copy with more leftover events must not hide it. If nothing has finished,
    use the copy with the most reviewable events.
    """
    base = base_analysis_key(game_id)
    keys = list(related_game_keys(db, game_id))
    if not keys:
        return game_id or base

    completed: list[tuple[int, str]] = []
    for key in keys:
        run = db.execute(
            """SELECT id, status FROM analysis_runs
                WHERE analysis_key=?
                ORDER BY id DESC
                LIMIT 1""",
            (key,),
        ).fetchone()
        if _row_value(run, "status", 1) != "completed":
            continue
        if _trusted_event_count(db, key) <= 0:
            continue
        completed.append((int(_row_value(run, "id", 0)), key))
    if completed:
        completed.sort()
        return completed[-1][1]

    best_key = game_id or base
    best_n = -1
    for key in keys:
        n = _trusted_event_count(db, key)
        if n > best_n or (n == best_n and key == base):
            best_n = n
            best_key = key
    return best_key


def promote_useful_events_to_ledger(db, game_id: str, *, commit: bool = True) -> dict[str, Any]:
    """Promote pending useful AI events → accepted (system), not confidence-gated."""
    key = canonical_event_key(db, game_id)
    type_ph = ",".join("?" for _ in PROGRAM_LEDGER_TYPES)
    before = db.execute(
        f"""SELECT COUNT(*) AS c FROM events
             WHERE game_id=? AND review_status='pending'
               AND event_type IN ({type_ph})""",
        (key, *PROGRAM_LEDGER_TYPES),
    ).fetchone()["c"]

    db.execute(
        f"""UPDATE events
               SET review_status='accepted',
                   human_verified=0,
                   reviewed_at=CURRENT_TIMESTAMP,
                   review_notes=COALESCE(review_notes, ?)
             WHERE game_id=? AND review_status='pending'
               AND event_type IN ({type_ph})""",
        (PROVENANCE_VERSION, key, *PROGRAM_LEDGER_TYPES),
    )

    noise_ph = ",".join("?" for _ in NOISE_TYPES)
    noise_pending = db.execute(
        f"""SELECT COUNT(*) AS c FROM events
             WHERE game_id=? AND review_status='pending'
               AND event_type IN ({noise_ph})""",
        (key, *NOISE_TYPES),
    ).fetchone()["c"]
    db.execute(
        f"""UPDATE events
               SET review_status='rejected',
                   human_verified=0,
                   reviewed_at=CURRENT_TIMESTAMP,
                   review_notes=COALESCE(review_notes, ?)
             WHERE game_id=? AND review_status='pending'
               AND event_type IN ({noise_ph})""",
        (f"{PROVENANCE_VERSION}:noise", key, *NOISE_TYPES),
    )

    if commit:
        db.commit()
        # Skip heavy refresh_stats on bulk promote — box comes from events query.
        # Callers that need derived stats tables can refresh later.

    return {
        "game_id": game_id,
        "canonical_key": key,
        "keys": [key],
        "promoted_useful": int(before or 0),
        "rejected_noise": int(noise_pending or 0),
        "version": PROVENANCE_VERSION,
    }


def _player_key(player: str | None) -> str:
    text = (player or "").strip()
    if not text:
        return "?"
    digits = "".join(ch for ch in text if ch.isdigit())
    if digits:
        return digits.lstrip("0") or "0"
    return text.lower()


def _points_for_event(event_type: str, shot_result: str | None = None) -> int:
    et = (event_type or "").lower()
    if et in POINTS_BY_TYPE:
        return POINTS_BY_TYPE[et]
    if et == "shot" and (shot_result or "").lower() == "make":
        return 2
    return 0


def ledger_box_from_events(db, game_id: str) -> dict[str, Any]:
    key = canonical_event_key(db, game_id)
    type_ph = ",".join("?" for _ in PROGRAM_LEDGER_TYPES)
    rows = db.execute(
        f"""SELECT player, event_type, shot_result, COUNT(*) AS n
              FROM events
             WHERE game_id=?
               AND review_status IN ('accepted', 'corrected')
               AND event_type IN ({type_ph})
             GROUP BY player, event_type, shot_result""",
        (key, *PROGRAM_LEDGER_TYPES),
    ).fetchall()

    by_player: dict[str, dict[str, Any]] = {}
    totals = {
        "pts": 0, "fgm": 0, "fga": 0, "tpm": 0, "tpa": 0, "ftm": 0, "fta": 0,
        "reb": 0, "ast": 0, "stl": 0, "blk": 0, "to": 0, "foul": 0, "events": 0,
    }

    def bucket(player: str) -> dict[str, Any]:
        if player not in by_player:
            by_player[player] = {
                "player": player,
                "pts": 0, "fgm": 0, "fga": 0, "tpm": 0, "tpa": 0, "ftm": 0, "fta": 0,
                "reb": 0, "ast": 0, "stl": 0, "blk": 0, "to": 0, "foul": 0,
            }
        return by_player[player]

    for row in rows:
        player = _player_key(row["player"])
        et = (row["event_type"] or "").lower()
        n = int(row["n"] or 0)
        b = bucket(player)
        totals["events"] += n
        # AI shot+make/miss pairs: the derived make/miss row carries the attempt (as in stats).
        if _shot_attempt_already_counted(et, (row["shot_result"] or "").lower()):
            continue
        pts = _points_for_event(et, row["shot_result"]) * n
        if pts:
            b["pts"] += pts
            totals["pts"] += pts
        if et in ("make", "made_two", "made_three", "miss", "missed_two", "missed_three", "shot"):
            b["fga"] += n
            totals["fga"] += n
        if et in ("make", "made_two", "made_three") or (
            et == "shot" and (row["shot_result"] or "").lower() == "make"
        ):
            b["fgm"] += n
            totals["fgm"] += n
        if et in ("made_three", "missed_three"):
            b["tpa"] += n
            totals["tpa"] += n
        if et == "made_three":
            b["tpm"] += n
            totals["tpm"] += n
        if et in ("made_free_throw", "missed_free_throw"):
            b["fta"] += n
            totals["fta"] += n
        if et == "made_free_throw":
            b["ftm"] += n
            totals["ftm"] += n
        if et in ("rebound", "rebound_offensive", "rebound_defensive"):
            b["reb"] += n
            totals["reb"] += n
        if et == "assist":
            b["ast"] += n
            totals["ast"] += n
        if et == "steal":
            b["stl"] += n
            totals["stl"] += n
        if et == "block":
            b["blk"] += n
            totals["blk"] += n
        if et == "turnover":
            b["to"] += n
            totals["to"] += n
        if et in ("foul", "foul_personal", "foul_shooting", "foul_technical"):
            b["foul"] += n
            totals["foul"] += n

    players = sorted(by_player.values(), key=lambda p: (-p["pts"], p["player"]))
    return {"players": players, "totals": totals, "canonical_key": key}


def scorebook_total_points(scorebook: dict[str, Any] | None) -> int:
    """Prefer player-sum points — final_score_* can disagree with home/away labels."""
    if not scorebook:
        return 0
    summed = 0
    for p in scorebook.get("players") or []:
        if p.get("pts") is not None:
            summed += int(p.get("pts") or 0)
    if summed:
        return summed
    return int(scorebook.get("final_score_home") or 0) + int(
        scorebook.get("final_score_away") or 0
    )


def build_exceptions(scorebook: dict[str, Any] | None, ledger_box: dict[str, Any]) -> list[dict[str, Any]]:
    exceptions: list[dict[str, Any]] = []
    if not scorebook:
        exceptions.append(
            {
                "severity": "medium",
                "code": "no_scorebook",
                "message": "No confirmed scorebook for this game. Confirm /stat-books so points can be checked.",
            }
        )
        return exceptions

    book_by_jersey: dict[str, dict] = {}
    for p in scorebook.get("players") or []:
        jersey = str(p.get("jersey") or "").strip().lstrip("0") or "0"
        book_by_jersey[jersey] = p

    ledger_by = {str(p["player"]): p for p in ledger_box.get("players") or []}
    ai_pts = int((ledger_box.get("totals") or {}).get("pts") or 0)
    book_pts = scorebook_total_points(scorebook)
    if book_pts and ai_pts:
        delta = abs(ai_pts - book_pts)
        if delta >= 4:
            exceptions.append(
                {
                    "severity": "high" if delta >= 10 else "medium",
                    "code": "points_scale",
                    "message": (
                        f"Scorebook team points {book_pts}, AI ledger points {ai_pts} "
                        f"(delta {delta}). Team-capped draft until jersey IDs map."
                    ),
                    "scorebook_pts": book_pts,
                    "ledger_pts": ai_pts,
                }
            )

    for jersey, bp in book_by_jersey.items():
        if bp.get("pts") is None:
            continue
        book_pts_p = int(bp.get("pts") or 0)
        ai_pts_p = int((ledger_by.get(jersey) or {}).get("pts") or 0)
        if book_pts_p == 0 and ai_pts_p == 0:
            continue
        if abs(ai_pts_p - book_pts_p) >= 4:
            exceptions.append(
                {
                    "severity": "high" if abs(ai_pts_p - book_pts_p) >= 8 else "medium",
                    "code": "player_pts_mismatch",
                    "jersey": jersey,
                    "name": bp.get("name"),
                    "team": bp.get("team"),
                    "scorebook_pts": book_pts_p,
                    "ledger_pts": ai_pts_p,
                    "message": (
                        f"#{jersey} {bp.get('name') or ''}: scorebook {book_pts_p} pts vs "
                        f"AI ledger {ai_pts_p} pts (IDs not jersey-linked yet)."
                    ),
                }
            )

    for jersey, lp in ledger_by.items():
        if jersey in book_by_jersey or jersey == "?":
            continue
        if int(lp.get("pts") or 0) >= 6 or int(lp.get("fga") or 0) >= 8:
            exceptions.append(
                {
                    "severity": "medium",
                    "code": "unknown_scorer",
                    "jersey": jersey,
                    "ledger_pts": lp.get("pts"),
                    "ledger_fga": lp.get("fga"),
                    "message": (
                        f"Tracker ID '{jersey}' has {lp.get('pts')} pts / {lp.get('fga')} FGA "
                        "on the ledger — not a scorebook jersey yet."
                    ),
                }
            )

    severity_rank = {"high": 0, "medium": 1, "low": 2}
    exceptions.sort(key=lambda e: (severity_rank.get(e.get("severity"), 9), e.get("code") or ""))
    return exceptions


def _safe_official_box(db, game_id: str) -> dict[str, Any] | None:
    try:
        from game_boxscore import build_official_box
        return build_official_box(db, game_id)
    except Exception:
        return None


def program_summary(db, game_id: str) -> dict[str, Any]:
    key = canonical_event_key(db, game_id)
    counts = {}
    for status in ("pending", "accepted", "corrected", "rejected"):
        counts[status] = db.execute(
            "SELECT COUNT(*) AS c FROM events WHERE game_id=? AND review_status=?",
            (key, status),
        ).fetchone()["c"]

    type_ph = ",".join("?" for _ in PROGRAM_LEDGER_TYPES)
    useful_pending = db.execute(
        f"""SELECT COUNT(*) AS c FROM events
             WHERE game_id=? AND review_status='pending'
               AND event_type IN ({type_ph})""",
        (key, *PROGRAM_LEDGER_TYPES),
    ).fetchone()["c"]

    ledger_box = ledger_box_from_events(db, game_id)
    scorebook = load_scorebook(game_id)
    exceptions = build_exceptions(scorebook, ledger_box)
    book_pts = scorebook_total_points(scorebook)

    return {
        "game_id": game_id,
        "base_game_id": base_analysis_key(game_id),
        "canonical_key": key,
        "keys": [key],
        "counts": counts,
        "useful_pending": int(useful_pending or 0),
        "ledger_box": ledger_box,
        "scorebook": {
            "present": bool(scorebook),
            "final_score_home": (scorebook or {}).get("final_score_home"),
            "final_score_away": (scorebook or {}).get("final_score_away"),
            "home_team": (scorebook or {}).get("home_team"),
            "away_team": (scorebook or {}).get("away_team"),
            "team_pts": book_pts,
            "players": [
                {
                    "jersey": p.get("jersey"),
                    "name": p.get("name"),
                    "team_name": (
                        (scorebook or {}).get("home_team")
                        if str(p.get("team") or "").lower() in ("home", "h")
                        else (scorebook or {}).get("away_team")
                        if str(p.get("team") or "").lower() in ("away", "a")
                        else (p.get("team_name") or p.get("team"))
                    ),
                    "team_side": p.get("team"),
                }
                for p in ((scorebook or {}).get("players") or [])
                if p.get("jersey") is not None or p.get("name")
            ],
        },
        "exceptions": exceptions,
        "exception_count": len(exceptions),
        "mode": "program",
        "hint": (
            "Box score first (quarters, then team, then individuals). "
            "Film clips are optional after the box is built."
        ),
        "official_box": _safe_official_box(db, game_id),
    }
