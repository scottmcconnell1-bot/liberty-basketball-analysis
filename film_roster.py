"""Season-scoped Film Tool rosters stored in the database."""

from __future__ import annotations

VALID_LEVELS = frozenset({"jrhigh", "jv", "varsity"})
VALID_GENDERS = frozenset({"boys", "girls", "coed"})
VALID_SIDES = frozenset({"our", "opp", "home", "away"})


def _validate_slot(*, season_id, level, gender, side) -> tuple[int, str, str, str]:
    try:
        season_id = int(season_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("season_id is required") from exc
    if season_id <= 0:
        raise ValueError("season_id is required")

    level = (level or "").strip().lower()
    gender = (gender or "").strip().lower()
    side = (side or "").strip().lower()
    if level not in VALID_LEVELS:
        raise ValueError(f"Invalid level. Use one of: {', '.join(sorted(VALID_LEVELS))}")
    if gender not in VALID_GENDERS:
        raise ValueError(f"Invalid gender. Use one of: {', '.join(sorted(VALID_GENDERS))}")
    if side not in VALID_SIDES:
        raise ValueError(f"Invalid side. Use one of: {', '.join(sorted(VALID_SIDES))}")
    return season_id, level, gender, side


def _player_label(player: dict) -> str:
    label = (player.get("label") or player.get("player_label") or "").strip()
    if not label:
        raise ValueError("Each player must have a label")
    return label


def list_film_roster_players(db, *, season_id, level, gender, side) -> list[dict]:
    season_id, level, gender, side = _validate_slot(
        season_id=season_id, level=level, gender=gender, side=side
    )
    rows = db.execute(
        """
        SELECT player_label, jersey_number, name, grade, position, sort_order
          FROM film_roster_players
         WHERE season_id = ? AND level = ? AND gender = ? AND side = ?
         ORDER BY sort_order ASC, id ASC
        """,
        (season_id, level, gender, side),
    ).fetchall()
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


def delete_film_roster(db, *, season_id, level, gender, side) -> int:
    season_id, level, gender, side = _validate_slot(
        season_id=season_id, level=level, gender=gender, side=side
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
) -> dict:
    season_id, level, gender, side = _validate_slot(
        season_id=season_id, level=level, gender=gender, side=side
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
        delete_film_roster(db, season_id=season_id, level=level, gender=gender, side=side)
        final_players = normalized
    else:
        existing = list_film_roster_players(
            db, season_id=season_id, level=level, gender=gender, side=side
        )
        existing_labels = {row["label"] for row in existing}
        final_players = existing + [
            player for player in normalized if player["label"] not in existing_labels
        ]
        delete_film_roster(db, season_id=season_id, level=level, gender=gender, side=side)

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
        "count": len(final_players),
        "players": final_players,
    }
