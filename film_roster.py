"""Season-scoped Film Tool rosters stored in the database.

Liberty lives in the `our` slot. Each opponent has its own `opp__<slug>` slot
so coaches can pick Adrian, Vale, etc. Legacy `home` / `away` / `opp` rows
are still readable.
"""

from __future__ import annotations

import re

VALID_LEVELS = frozenset({"jrhigh", "jv", "varsity"})
VALID_GENDERS = frozenset({"boys", "girls", "coed"})
OPP_PREFIX = "opp__"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def opponent_slug(name: str | None) -> str:
    text = _SLUG_RE.sub("_", (name or "").strip().lower()).strip("_")
    return text[:64] or "opponent"


def opponent_side_key(name: str | None) -> str:
    return f"{OPP_PREFIX}{opponent_slug(name)}"


def display_name_from_side(side: str) -> str | None:
    if not str(side or "").startswith(OPP_PREFIX):
        return None
    return str(side)[len(OPP_PREFIX):].replace("_", " ").title()


def resolve_roster_side(side: str | None, opponent_name: str | None = None) -> str:
    value = (side or "our").strip().lower()
    if value in {"our", "liberty"}:
        return "our"
    if value.startswith(OPP_PREFIX):
        slug = opponent_slug(value[len(OPP_PREFIX):])
        return f"{OPP_PREFIX}{slug}"
    if value in {"opp", "opponent"}:
        if (opponent_name or "").strip():
            return opponent_side_key(opponent_name)
        return "opp"
    if value in {"home", "away"}:
        return value
    raise ValueError("Invalid roster. Use Liberty or an opponent name.")


def _validate_slot(*, season_id, level, gender, side, opponent_name=None) -> tuple[int, str, str, str]:
    try:
        season_id = int(season_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("season_id is required") from exc
    if season_id <= 0:
        raise ValueError("season_id is required")

    level = (level or "").strip().lower()
    gender = (gender or "").strip().lower()
    if level not in VALID_LEVELS:
        raise ValueError(f"Invalid level. Use one of: {', '.join(sorted(VALID_LEVELS))}")
    if gender not in VALID_GENDERS:
        raise ValueError(f"Invalid gender. Use one of: {', '.join(sorted(VALID_GENDERS))}")
    side = resolve_roster_side(side, opponent_name)
    return season_id, level, gender, side


def _player_label(player: dict) -> str:
    label = (player.get("label") or player.get("player_label") or "").strip()
    if not label:
        raise ValueError("Each player must have a label")
    return label


def _player_identity(player: dict) -> tuple:
    jersey = str(player.get("jersey_number") or "").strip()
    name = " ".join(str(player.get("name") or "").split()).lower()
    if name:
        return ("player", jersey, name)
    return ("label", player["label"])


def _schedule_levels(level: str) -> list[str]:
    if level == "jrhigh":
        return ["jr_high", "jrhigh", "junior_high"]
    return [level]


def list_film_roster_players(db, *, season_id, level, gender, side, opponent_name=None) -> list[dict]:
    season_id, level, gender, side = _validate_slot(
        season_id=season_id,
        level=level,
        gender=gender,
        side=side,
        opponent_name=opponent_name,
    )
    sides = [side]
    rows = []
    seen = set()
    for candidate in sides:
        found = db.execute(
            """
            SELECT player_label, jersey_number, name, grade, position, sort_order
              FROM film_roster_players
             WHERE season_id = ? AND level = ? AND gender = ? AND side = ?
             ORDER BY sort_order ASC, id ASC
            """,
            (season_id, level, gender, candidate),
        ).fetchall()
        if not found:
            continue
        for row in found:
            label = row["player_label"]
            if label in seen:
                continue
            seen.add(label)
            rows.append(row)
        break
    return [
        {
            "label": row["player_label"],
            "player_label": row["player_label"],
            "jersey_number": row["jersey_number"],
            "name": row["name"],
            "grade": row["grade"],
            "position": row["position"],
        }
        for row in rows
    ]


def delete_film_roster(db, *, season_id, level, gender, side, opponent_name=None) -> int:
    season_id, level, gender, side = _validate_slot(
        season_id=season_id,
        level=level,
        gender=gender,
        side=side,
        opponent_name=opponent_name,
    )
    cur = db.execute(
        """
        DELETE FROM film_roster_players
         WHERE season_id = ? AND level = ? AND gender = ? AND side = ?
        """,
        (season_id, level, gender, side),
    )
    return cur.rowcount


def save_film_roster(
    db,
    *,
    season_id,
    level,
    gender,
    side,
    players,
    replace: bool = True,
    opponent_name=None,
) -> dict:
    season_id, level, gender, side = _validate_slot(
        season_id=season_id,
        level=level,
        gender=gender,
        side=side,
        opponent_name=opponent_name,
    )
    season_row = db.execute("SELECT id FROM seasons WHERE id=?", (season_id,)).fetchone()
    if not season_row:
        raise ValueError("Season not found")

    normalized: list[dict] = []
    seen: set[str] = set()
    for player in players or []:
        if isinstance(player, str):
            player = {"label": player}
        label = _player_label(player)
        if label in seen:
            continue
        seen.add(label)
        normalized.append({
            "label": label,
            "jersey_number": player.get("jersey_number"),
            "name": player.get("name"),
            "grade": player.get("grade"),
            "position": player.get("position"),
        })

    if replace:
        delete_film_roster(
            db,
            season_id=season_id,
            level=level,
            gender=gender,
            side=side,
        )
        final_players = normalized
    else:
        existing = list_film_roster_players(
            db,
            season_id=season_id,
            level=level,
            gender=gender,
            side=side,
            opponent_name=opponent_name,
        )
        # Match players by jersey + name (not the label, which embeds the grade), so a
        # re-import with a corrected grade/position updates the player in place.
        incoming = {_player_identity(player): player for player in normalized}
        final_players = []
        for row in existing:
            final_players.append(incoming.pop(_player_identity(row), row))
        final_players += list(incoming.values())
        delete_film_roster(
            db,
            season_id=season_id,
            level=level,
            gender=gender,
            side=side,
        )

    for index, player in enumerate(final_players):
        db.execute(
            """
            INSERT INTO film_roster_players
                (season_id, level, gender, side, player_label,
                 jersey_number, name, grade, position, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                season_id,
                level,
                gender,
                side,
                player["label"],
                player.get("jersey_number"),
                player.get("name"),
                player.get("grade"),
                player.get("position"),
                index,
            ),
        )

    return {
        "season_id": season_id,
        "level": level,
        "gender": gender,
        "side": side,
        "opponent_name": display_name_from_side(side) or opponent_name,
        "count": len(final_players),
        "players": final_players,
    }


def _scorebook_matches_opponent(book: dict, opponent_name: str) -> str | None:
    target = opponent_slug(opponent_name)
    home = book.get("home_team") or ""
    away = book.get("away_team") or ""
    if opponent_slug(home) == target or target in home.lower():
        if "liberty" not in home.lower():
            return "home"
    if opponent_slug(away) == target or target in away.lower():
        if "liberty" not in away.lower():
            return "away"
    return None


def _scorebook_opponent_box(opponent_name: str | None) -> dict | None:
    if not (opponent_name or "").strip():
        return None
    try:
        from program_mode import load_scorebook, scorebook_named_players
        from stat_book.paths import list_confirmed
    except Exception:
        return None

    for game_id in list_confirmed():
        book = load_scorebook(game_id)
        if not book:
            continue
        side = _scorebook_matches_opponent(book, opponent_name)
        if not side:
            continue
        home = book.get("home_team") or ""
        away = book.get("away_team") or ""
        liberty_home = "liberty" in home.lower()
        pts_by_key = {}
        for row in book.get("players") or []:
            jersey = str(row.get("jersey") if row.get("jersey") is not None else "").strip()
            name = (row.get("name") or "").strip()
            if not jersey and not name:
                continue
            pts_by_key[(jersey, name)] = int(row.get("pts") or 0)
        players = []
        for person in scorebook_named_players(book):
            if person["team"] != side:
                continue
            players.append({
                "jersey": person["jersey"],
                "name": person["name"],
                "pts": pts_by_key.get((person["jersey"], person["name"]), 0),
            })
        return {
            "game_id": game_id,
            "team_name": home if side == "home" else away,
            "liberty_pts": book.get("final_score_home") if liberty_home else book.get("final_score_away"),
            "opponent_pts": book.get("final_score_away") if liberty_home else book.get("final_score_home"),
            "players": players,
        }
    return None


def opponent_schedule_stats(db, *, season_id, level, opponent_name) -> dict:
    name = (opponent_name or "").strip()
    games = []
    if season_id and name:
        levels = _schedule_levels(level)
        placeholders = ",".join("?" * len(levels))
        rows = db.execute(
            f"""
            SELECT sg.game_date, sg.location_type, sg.opponent_name,
                   g.home_score, g.away_score, g.result
              FROM scheduled_games sg
              LEFT JOIN games g ON g.scheduled_game_id = sg.id
             WHERE sg.season_id = ?
               AND sg.level IN ({placeholders})
               AND (
                    lower(trim(sg.opponent_name)) = lower(trim(?))
                    OR instr(lower(?), lower(trim(sg.opponent_name))) > 0
               )
             ORDER BY sg.game_date DESC
            """,
            (season_id, *levels, name, name),
        ).fetchall()
        games = [dict(row) for row in rows]

    wins = sum(1 for game in games if (game.get("result") or "").lower() == "win")
    losses = sum(1 for game in games if (game.get("result") or "").lower() == "loss")
    box = _scorebook_opponent_box(name)
    last = games[0] if games else None
    last_score = None
    if box and box.get("liberty_pts") is not None and box.get("opponent_pts") is not None:
        last_score = f"Liberty {box['liberty_pts']}-{box.get('team_name') or name} {box['opponent_pts']}"
    elif last and last.get("home_score") is not None and last.get("away_score") is not None:
        last_score = f"{last['home_score']}–{last['away_score']}"

    return {
        "opponent_name": name,
        "games": len(games),
        "wins": wins,
        "losses": losses,
        "record": f"{wins}-{losses}" if games else None,
        "last_game": last,
        "last_score": last_score,
        "box": box,
    }


def list_roster_opponents(db, *, season_id, level, gender) -> list[dict]:
    season_id, level, gender, _side = _validate_slot(
        season_id=season_id, level=level, gender=gender, side="our"
    )
    by_name: dict[str, dict] = {}

    def add(name: str, *, player_count=0, side=None):
        label = (name or "").strip()
        if not label or label.lower() in {"tbd", "tba"}:
            return
        key = opponent_slug(label)
        current = by_name.get(key)
        if current:
            current["player_count"] = max(current["player_count"], player_count)
            if side:
                current["side"] = side
            return
        by_name[key] = {
            "name": label,
            "slug": key,
            "side": side or opponent_side_key(label),
            "player_count": player_count,
        }

    levels = _schedule_levels(level)
    placeholders = ",".join("?" * len(levels))
    for row in db.execute(
        f"""
        SELECT opponent_name, COUNT(*) AS game_count
          FROM scheduled_games
         WHERE season_id = ? AND level IN ({placeholders})
         GROUP BY opponent_name
         ORDER BY opponent_name COLLATE NOCASE
        """,
        (season_id, *levels),
    ).fetchall():
        add(row["opponent_name"])

    for row in db.execute(
        """
        SELECT side, COUNT(*) AS player_count
          FROM film_roster_players
         WHERE season_id = ? AND level = ? AND gender = ?
           AND (side LIKE 'opp__%' OR side = 'opp')
         GROUP BY side
        """,
        (season_id, level, gender),
    ).fetchall():
        side = row["side"]
        if side == "opp":
            add("Opponent", player_count=row["player_count"], side="opp")
        else:
            add(display_name_from_side(side) or side, player_count=row["player_count"], side=side)

    opponents = []
    for item in sorted(by_name.values(), key=lambda row: row["name"].lower()):
        stats = opponent_schedule_stats(
            db,
            season_id=season_id,
            level=level,
            opponent_name=item["name"],
        )
        if not item["player_count"]:
            item["player_count"] = len(list_film_roster_players(
                db,
                season_id=season_id,
                level=level,
                gender=gender,
                side="opp",
                opponent_name=item["name"],
            ))
        opponents.append({**item, **{k: stats[k] for k in ("games", "wins", "losses", "record", "last_score")}})
    return opponents


def attach_player_stats(players: list[dict], opponent_name: str | None) -> list[dict]:
    box = _scorebook_opponent_box(opponent_name) if opponent_name else None
    if not box:
        return players
    pts_by_jersey = {
        str(row.get("jersey") or ""): row.get("pts")
        for row in box.get("players") or []
    }
    pts_by_name = {
        (row.get("name") or "").strip().lower(): row.get("pts")
        for row in box.get("players") or []
    }
    enriched = []
    for player in players:
        jersey = str(player.get("jersey_number") or "")
        name = (player.get("name") or "").strip().lower()
        pts = pts_by_jersey.get(jersey)
        if pts is None:
            pts = pts_by_name.get(name)
        row = dict(player)
        if pts is not None:
            row["pts"] = pts
        enriched.append(row)
    return enriched
