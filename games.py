"""games.py — CRUD operations for the games table.

Functions:
    create_game(conn, source_type, source_key, scheduled_game_id=None, ...)
    list_games(conn, scheduled_game_id=None, source_type=None)
    get_game(conn, game_id)
    edit_game(conn, game_id, **kwargs)
    delete_game(conn, game_id)
"""

import sqlite3


def create_game(conn, source_type, source_key, scheduled_game_id=None,
                start_time=None, end_time=None, nfhs_game_id=None, nfhs_url=None,
                home_score=0, away_score=0, result=None, is_conference=0):
    """Insert a new game record. Returns the new row id."""
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO games
           (scheduled_game_id, start_time, end_time, source_type, source_key,
            nfhs_game_id, nfhs_url, home_score, away_score, result, is_conference)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (scheduled_game_id, start_time, end_time, source_type, source_key,
         nfhs_game_id, nfhs_url, home_score, away_score, result, is_conference),
    )
    conn.commit()
    return cur.lastrowid


def list_games(conn, scheduled_game_id=None, source_type=None):
    """Return games as a list of dicts, filtered by optional params."""
    query = "SELECT * FROM games WHERE 1=1"
    params = []
    if scheduled_game_id is not None:
        query += " AND scheduled_game_id = ?"
        params.append(scheduled_game_id)
    if source_type is not None:
        query += " AND source_type = ?"
        params.append(source_type)
    query += " ORDER BY start_time ASC, id ASC"

    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.row_factory = None
    return [dict(r) for r in rows]


def get_game(conn, game_id):
    """Return a single game by id, or None."""
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM games WHERE id = ?", (game_id,))
    row = cur.fetchone()
    conn.row_factory = None
    return dict(row) if row else None


def edit_game(conn, game_id, **kwargs):
    """Update fields on a game. Pass only the fields to change."""
    allowed = {
        "scheduled_game_id", "start_time", "end_time", "source_type", "source_key",
        "nfhs_game_id", "nfhs_url", "home_score", "away_score", "result", "is_conference",
    }
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [game_id]
    cur = conn.cursor()
    cur.execute(
        f"UPDATE games SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        values,
    )
    conn.commit()
    return cur.rowcount > 0


def delete_game(conn, game_id):
    """Delete a game by id."""
    cur = conn.cursor()
    cur.execute("DELETE FROM games WHERE id = ?", (game_id,))
    conn.commit()
    return cur.rowcount > 0
