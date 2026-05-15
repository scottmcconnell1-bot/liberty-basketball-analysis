"""season_management.py — CRUD operations for the seasons table.

Functions:
    create_season(conn, name, start_date, end_date)
    list_seasons(conn)
    get_season(conn, season_id)
    edit_season(conn, season_id, new_name=None, new_start_date=None, new_end_date=None)
    delete_season(conn, season_id)
"""

import sqlite3


def create_season(conn, name, start_date, end_date):
    """Insert a new season. Returns the new row id."""
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO seasons (name, start_date, end_date) VALUES (?, ?, ?)",
        (name, start_date, end_date),
    )
    conn.commit()
    return cur.lastrowid


def list_seasons(conn):
    """Return all seasons ordered by start_date DESC."""
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM seasons ORDER BY start_date DESC")
    rows = cur.fetchall()
    conn.row_factory = None
    return [dict(r) for r in rows]


def get_season(conn, season_id):
    """Return a single season by id, or None."""
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM seasons WHERE id = ?", (season_id,))
    row = cur.fetchone()
    conn.row_factory = None
    return dict(row) if row else None


def edit_season(conn, season_id, new_name=None, new_start_date=None, new_end_date=None):
    """Update fields on a season. Pass only the fields to change."""
    updates = {}
    if new_name is not None:
        updates["name"] = new_name
    if new_start_date is not None:
        updates["start_date"] = new_start_date
    if new_end_date is not None:
        updates["end_date"] = new_end_date
    if not updates:
        return False

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [season_id]
    cur = conn.cursor()
    cur.execute(f"UPDATE seasons SET {set_clause} WHERE id = ?", values)
    conn.commit()
    return cur.rowcount > 0


def delete_season(conn, season_id):
    """Delete a season by id."""
    cur = conn.cursor()
    cur.execute("DELETE FROM seasons WHERE id = ?", (season_id,))
    conn.commit()
    return cur.rowcount > 0
