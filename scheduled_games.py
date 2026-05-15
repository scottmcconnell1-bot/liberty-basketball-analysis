"""scheduled_games.py — CRUD operations for the scheduled_games table.

Functions:
    create_scheduled_game(conn, season_id, program_name, gender, level,
                          game_date, game_time, location_type, opponent_name,
                          tournament_name=None, notes=None)
    list_scheduled_games(conn, season_id=None, level=None, gender=None)
    get_scheduled_game(conn, game_id)
    edit_scheduled_game(conn, game_id, **kwargs)
    delete_scheduled_game(conn, game_id)
"""

import sqlite3


def create_scheduled_game(conn, season_id, program_name, gender, level,
                          game_date, game_time, location_type, opponent_name,
                          tournament_name=None, notes=None):
    """Insert a new scheduled game. Returns the new row id."""
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO scheduled_games
           (season_id, program_name, gender, level, game_date, game_time,
            location_type, opponent_name, tournament_name, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (season_id, program_name, gender, level, game_date, game_time,
         location_type, opponent_name, tournament_name, notes),
    )
    conn.commit()
    return cur.lastrowid


def list_scheduled_games(conn, season_id=None, level=None, gender=None):
    """Return scheduled games as a list of dicts, filtered by optional params."""
    query = "SELECT * FROM scheduled_games WHERE 1=1"
    params = []
    if season_id is not None:
        query += " AND season_id = ?"
        params.append(season_id)
    if level is not None:
        query += " AND level = ?"
        params.append(level)
    if gender is not None:
        query += " AND gender = ?"
        params.append(gender)
    query += " ORDER BY game_date ASC, game_time ASC"

    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def get_scheduled_game(conn, game_id):
    """Return a single scheduled game by id, or None."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM scheduled_games WHERE id = ?", (game_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def edit_scheduled_game(conn, game_id, **kwargs):
    """Update fields on a scheduled game. Pass only the fields to change."""
    allowed = {
        "season_id", "program_name", "gender", "level", "game_date",
        "game_time", "location_type", "opponent_name", "tournament_name",
        "status", "notes",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [game_id]
    cur = conn.cursor()
    cur.execute(
        f"UPDATE scheduled_games SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        values,
    )
    conn.commit()
    return cur.rowcount > 0


def delete_scheduled_game(conn, game_id):
    """Delete a scheduled game by id."""
    cur = conn.cursor()
    cur.execute("DELETE FROM scheduled_games WHERE id = ?", (game_id,))
    conn.commit()
    return cur.rowcount > 0
