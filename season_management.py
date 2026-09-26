"""
season_management.py – Pure-Python helper functions for seasons and
scheduled_games CRUD.  Accepts a sqlite3.Connection (or Flask g.db).

Deleting keeps recorded results safe:
  * delete_scheduled_game() removes the schedule entry but keeps its games rows
    (scores, film, analysis), unlinked from the schedule (still in /api/games).
  * delete_season() refuses (SeasonDeleteError) while any of its games has a
    recorded result, or while rosters/players/practices still point at it.
"""
import sqlite3


class SeasonDeleteError(ValueError):
    """The season cannot be deleted without losing linked data."""


def get_seasons(db):
    rows = db.execute("SELECT * FROM seasons ORDER BY start_date DESC").fetchall()
    return [dict(r) for r in rows]


def create_season(db, name, start_date, end_date):
    if not all([name, start_date, end_date]):
        raise ValueError("name, start_date, end_date are required")
    cur = db.execute(
        "INSERT INTO seasons (name, start_date, end_date) VALUES (?,?,?)",
        (name.strip(), start_date, end_date),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM seasons WHERE id=?", (cur.lastrowid,)).fetchone())


def update_season(db, season_id, **kwargs):
    row = db.execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone()
    if row is None:
        raise KeyError(f"Season {season_id} not found")
    name  = kwargs.get("name", row["name"])
    start = kwargs.get("start_date", row["start_date"])
    end   = kwargs.get("end_date", row["end_date"])
    db.execute(
        "UPDATE seasons SET name=?, start_date=?, end_date=? WHERE id=?",
        (name, start, end, season_id),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone())


def delete_season(db, season_id):
    scored = db.execute(
        """SELECT COUNT(DISTINCT sg.id) FROM scheduled_games sg
           JOIN games g ON g.scheduled_game_id = sg.id
           WHERE sg.season_id = ? AND g.result IS NOT NULL AND g.result != ''""",
        (season_id,),
    ).fetchone()[0]
    if scored:
        raise SeasonDeleteError(
            f"Season not deleted: {scored} of its games have recorded results. "
            "Archive the season, or delete those games first (their scores are kept, unlinked)."
        )
    in_season = "SELECT id FROM scheduled_games WHERE season_id = ?"
    try:
        db.execute(f"DELETE FROM nfhs_matches WHERE scheduled_game_id IN ({in_season})", (season_id,))
        db.execute(
            f"UPDATE games SET scheduled_game_id = NULL WHERE scheduled_game_id IN ({in_season})",
            (season_id,),
        )
        db.execute("DELETE FROM scheduled_games WHERE season_id=?", (season_id,))
        db.execute("DELETE FROM seasons WHERE id=?", (season_id,))
    except sqlite3.IntegrityError as exc:
        db.rollback()
        raise SeasonDeleteError(
            "Season not deleted: rosters, players, practices or clips are still linked to it."
        ) from exc
    db.commit()


def get_scheduled_games(db, season_id=None):
    if season_id:
        rows = db.execute(
            "SELECT * FROM scheduled_games WHERE season_id=? ORDER BY game_date, game_time",
            (season_id,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM scheduled_games ORDER BY game_date, game_time"
        ).fetchall()
    return [dict(r) for r in rows]


def create_scheduled_game(db, season_id, game_date, opponent_name, **kwargs):
    if not all([season_id, game_date, opponent_name]):
        raise ValueError("season_id, game_date, opponent_name are required")
    cur = db.execute(
        """INSERT INTO scheduled_games
           (season_id, program_name, gender, level, game_date, game_time,
            location_type, opponent_name, tournament_name, status, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            season_id,
            kwargs.get("program_name", "Liberty"),
            kwargs.get("gender", "boys"),
            kwargs.get("level", "jr_high"),
            game_date,
            kwargs.get("game_time"),
            kwargs.get("location_type", "home"),
            opponent_name,
            kwargs.get("tournament_name"),
            kwargs.get("status", "scheduled"),
            kwargs.get("notes"),
        ),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM scheduled_games WHERE id=?", (cur.lastrowid,)).fetchone())


def update_scheduled_game(db, game_id, **kwargs):
    row = db.execute("SELECT * FROM scheduled_games WHERE id=?", (game_id,)).fetchone()
    if row is None:
        raise KeyError(f"Scheduled game {game_id} not found")
    db.execute(
        """UPDATE scheduled_games SET
           season_id=?, program_name=?, gender=?, level=?, game_date=?, game_time=?,
           location_type=?, opponent_name=?, tournament_name=?, status=?, notes=?,
           updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (
            kwargs.get("season_id", row["season_id"]),
            kwargs.get("program_name", row["program_name"]),
            kwargs.get("gender", row["gender"]),
            kwargs.get("level", row["level"]),
            kwargs.get("game_date", row["game_date"]),
            kwargs.get("game_time", row["game_time"]),
            kwargs.get("location_type", row["location_type"]),
            kwargs.get("opponent_name", row["opponent_name"]),
            kwargs.get("tournament_name", row["tournament_name"]),
            kwargs.get("status", row["status"]),
            kwargs.get("notes", row["notes"]),
            game_id,
        ),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM scheduled_games WHERE id=?", (game_id,)).fetchone())


def delete_scheduled_game(db, game_id):
    """Delete a scheduled game; return how many linked games rows were kept (unlinked)."""
    db.execute("DELETE FROM nfhs_matches WHERE scheduled_game_id=?", (game_id,))
    kept = db.execute(
        "UPDATE games SET scheduled_game_id = NULL, updated_at = CURRENT_TIMESTAMP WHERE scheduled_game_id=?",
        (game_id,),
    ).rowcount
    db.execute("DELETE FROM scheduled_games WHERE id=?", (game_id,))
    db.commit()
    return kept
