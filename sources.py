"""sources.py — CRUD operations for the sources table.

Functions:
    create_source(conn, game_id, source_type, source_path)
    list_sources(conn, game_id=None)
    get_source(conn, source_id)
    delete_source(conn, source_id)
"""

import sqlite3


def create_source(conn, game_id, source_type, source_path):
    """Insert a new video source for a game. Returns the new row id."""
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO sources (game_id, source_type, source_path)
           VALUES (?, ?, ?)""",
        (game_id, source_type, source_path),
    )
    conn.commit()
    return cur.lastrowid


def list_sources(conn, game_id=None):
    """Return sources as a list of dicts, optionally filtered by game_id."""
    query = "SELECT * FROM sources WHERE 1=1"
    params = []
    if game_id is not None:
        query += " AND game_id = ?"
        params.append(game_id)
    query += " ORDER BY created_at DESC"

    cur = conn.cursor()
    cur.execute(query, params)
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def get_source(conn, source_id):
    """Return a single source by id, or None."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM sources WHERE id = ?", (source_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def delete_source(conn, source_id):
    """Delete a source by id."""
    cur = conn.cursor()
    cur.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    conn.commit()
    return cur.rowcount > 0
