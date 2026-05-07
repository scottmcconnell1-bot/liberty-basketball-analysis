"""
player_development.py — Helper functions for Phase 7:
  - Player development clips CRUD
  - Practice playlists CRUD
  - Practice plan items CRUD
"""

from datetime import datetime


# ── Development Clips ──────────────────────────────────────────────

def get_clips(db, player_id=None, season_id=None, category=None, game_id=None):
    clauses = []
    params = []
    if player_id:
        clauses.append("c.player_id = ?")
        params.append(player_id)
    if season_id:
        clauses.append("c.season_id = ?")
        params.append(season_id)
    if category:
        clauses.append("c.clip_category = ?")
        params.append(category)
    if game_id:
        clauses.append("c.game_id = ?")
        params.append(game_id)

    query = """
        SELECT c.*, p.name AS player_name, s.name AS season_name
        FROM player_development_clips c
        LEFT JOIN players p ON p.id = c.player_id
        LEFT JOIN seasons s ON s.id = c.season_id
    """
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY c.created_at DESC"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def create_clip(db, clip_label, clip_start_ms, clip_end_ms, **kwargs):
    if not clip_label:
        raise ValueError("clip_label is required")
    if clip_start_ms is None or clip_end_ms is None:
        raise ValueError("clip_start_ms and clip_end_ms are required")
    if clip_end_ms <= clip_start_ms:
        raise ValueError("clip_end_ms must be greater than clip_start_ms")

    cur = db.execute(
        """INSERT INTO player_development_clips
           (player_id, game_id, event_id, clip_start_ms, clip_end_ms,
            clip_label, clip_category, season_id, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            kwargs.get("player_id"),
            kwargs.get("game_id"),
            kwargs.get("event_id"),
            clip_start_ms,
            clip_end_ms,
            clip_label.strip(),
            kwargs.get("clip_category", "general"),
            kwargs.get("season_id"),
            kwargs.get("notes"),
        ),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM player_development_clips WHERE id=?", (cur.lastrowid,)).fetchone())


def update_clip(db, clip_id, **kwargs):
    row = db.execute("SELECT * FROM player_development_clips WHERE id=?", (clip_id,)).fetchone()
    if row is None:
        raise KeyError(f"Clip {clip_id} not found")
    db.execute(
        """UPDATE player_development_clips SET
           player_id=?, game_id=?, event_id=?, clip_start_ms=?, clip_end_ms=?,
           clip_label=?, clip_category=?, season_id=?, notes=?,
           updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (
            kwargs.get("player_id", row["player_id"]),
            kwargs.get("game_id", row["game_id"]),
            kwargs.get("event_id", row["event_id"]),
            kwargs.get("clip_start_ms", row["clip_start_ms"]),
            kwargs.get("clip_end_ms", row["clip_end_ms"]),
            kwargs.get("clip_label", row["clip_label"]),
            kwargs.get("clip_category", row["clip_category"]),
            kwargs.get("season_id", row["season_id"]),
            kwargs.get("notes", row["notes"]),
            clip_id,
        ),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM player_development_clips WHERE id=?", (clip_id,)).fetchone())


def delete_clip(db, clip_id):
    db.execute("DELETE FROM practice_playlist_clips WHERE clip_id=?", (clip_id,))
    db.execute("DELETE FROM player_development_clips WHERE id=?", (clip_id,))
    db.commit()


# ── Practice Playlists ─────────────────────────────────────────────

def get_playlists(db, season_id=None, level=None, status=None):
    clauses = []
    params = []
    if season_id:
        clauses.append("pp.season_id = ?")
        params.append(season_id)
    if level:
        clauses.append("pp.level = ?")
        params.append(level)
    if status:
        clauses.append("pp.status = ?")
        params.append(status)

    query = """
        SELECT pp.*, s.name AS season_name
        FROM practice_playlists pp
        LEFT JOIN seasons s ON s.id = pp.season_id
    """
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY pp.updated_at DESC"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def create_playlist(db, name, **kwargs):
    if not name:
        raise ValueError("name is required")
    cur = db.execute(
        "INSERT INTO practice_playlists (name, season_id, level, status) VALUES (?,?,?,?)",
        (
            name.strip(),
            kwargs.get("season_id"),
            kwargs.get("level", "jr_high"),
            kwargs.get("status", "draft"),
        ),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM practice_playlists WHERE id=?", (cur.lastrowid,)).fetchone())


def update_playlist(db, playlist_id, **kwargs):
    row = db.execute("SELECT * FROM practice_playlists WHERE id=?", (playlist_id,)).fetchone()
    if row is None:
        raise KeyError(f"Playlist {playlist_id} not found")
    db.execute(
        """UPDATE practice_playlists SET
           name=?, season_id=?, level=?, status=?, updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (
            kwargs.get("name", row["name"]),
            kwargs.get("season_id", row["season_id"]),
            kwargs.get("level", row["level"]),
            kwargs.get("status", row["status"]),
            playlist_id,
        ),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM practice_playlists WHERE id=?", (playlist_id,)).fetchone())


def delete_playlist(db, playlist_id):
    db.execute("DELETE FROM practice_playlist_clips WHERE playlist_id=?", (playlist_id,))
    db.execute("DELETE FROM practice_playlists WHERE id=?", (playlist_id,))
    db.commit()


# ── Playlist Clips ─────────────────────────────────────────────────

def get_playlist_clips(db, playlist_id):
    rows = db.execute(
        """
        SELECT plc.*, c.clip_label, c.clip_category, c.clip_start_ms, c.clip_end_ms,
               c.game_id, c.notes AS clip_notes, p.name AS player_name
        FROM practice_playlist_clips plc
        JOIN player_development_clips c ON c.id = plc.clip_id
        LEFT JOIN players p ON p.id = c.player_id
        WHERE plc.playlist_id = ?
        ORDER BY plc.sort_order, plc.id
        """,
        (playlist_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_clip_to_playlist(db, playlist_id, clip_id, sort_order=0):
    db.execute(
        "INSERT OR IGNORE INTO practice_playlist_clips (playlist_id, clip_id, sort_order) VALUES (?,?,?)",
        (playlist_id, clip_id, sort_order),
    )
    db.commit()


def remove_clip_from_playlist(db, playlist_id, clip_id):
    db.execute(
        "DELETE FROM practice_playlist_clips WHERE playlist_id=? AND clip_id=?",
        (playlist_id, clip_id),
    )
    db.commit()


def reorder_playlist_clip(db, playlist_id, clip_id, sort_order):
    db.execute(
        "UPDATE practice_playlist_clips SET sort_order=? WHERE playlist_id=? AND clip_id=?",
        (sort_order, playlist_id, clip_id),
    )
    db.commit()


# ── Practice Plan Items ────────────────────────────────────────────

def get_plan_items(db, practice_id):
    rows = db.execute(
        """
        SELECT pi.*, pp.name AS playlist_name
        FROM practice_plan_items pi
        LEFT JOIN practice_playlists pp ON pp.id = pi.playlist_id
        WHERE pi.practice_id = ?
        ORDER BY pi.sort_order, pi.id
        """,
        (practice_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def create_plan_item(db, practice_id, title, **kwargs):
    if not title:
        raise ValueError("title is required")
    cur = db.execute(
        """INSERT INTO practice_plan_items
           (practice_id, playlist_id, item_type, title, description, duration_min, sort_order)
           VALUES (?,?,?,?,?,?,?)""",
        (
            practice_id,
            kwargs.get("playlist_id"),
            kwargs.get("item_type", "drill"),
            title.strip(),
            kwargs.get("description"),
            kwargs.get("duration_min"),
            kwargs.get("sort_order", 0),
        ),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM practice_plan_items WHERE id=?", (cur.lastrowid,)).fetchone())


def update_plan_item(db, item_id, **kwargs):
    row = db.execute("SELECT * FROM practice_plan_items WHERE id=?", (item_id,)).fetchone()
    if row is None:
        raise KeyError(f"Plan item {item_id} not found")
    db.execute(
        """UPDATE practice_plan_items SET
           playlist_id=?, item_type=?, title=?, description=?, duration_min=?,
           sort_order=?, updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (
            kwargs.get("playlist_id", row["playlist_id"]),
            kwargs.get("item_type", row["item_type"]),
            kwargs.get("title", row["title"]),
            kwargs.get("description", row["description"]),
            kwargs.get("duration_min", row["duration_min"]),
            kwargs.get("sort_order", row["sort_order"]),
            item_id,
        ),
    )
    db.commit()
    return dict(db.execute("SELECT * FROM practice_plan_items WHERE id=?", (item_id,)).fetchone())


def delete_plan_item(db, item_id):
    db.execute("DELETE FROM practice_plan_items WHERE id=?", (item_id,))
    db.commit()
