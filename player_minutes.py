"""
player_minutes.py — Idempotent backfill of per-game per-player minutes.

Derives player_minutes rows from the existing detections table using
tracker_id (stable schema column) instead of player_cluster
(runtime-derived, not in DDL).

Idempotency: uses INSERT OR REPLACE on the UNIQUE(game_id, tracker_id)
constraint, so re-running the backfill for the same game produces the
same output without duplicates.
"""

import sqlite3


def _resolve_relational_game_id(db, game_id):
    try:
        game_id_int = int(game_id)
    except (TypeError, ValueError):
        return None

    row = db.execute("SELECT id FROM games WHERE id=?", (game_id_int,)).fetchone()
    return row["id"] if row else None


def backfill_player_minutes(db, game_id, fps=30.0, detect_stride=1):
    """Recompute player_minutes for a single game from detection presence.

    Conservative calculation:
        seconds_played = total_detected_frames / effective_fps
        minutes_played = seconds_played / 60.0

    A detection row for a tracker_id in a frame counts as "present".
    Distinct frames (not raw rows) guard against duplicate detections
    in the same frame. The effective_fps accounts for detection stride.

    Idempotent: calling twice for the same game overwrites prior rows.

    Returns list of dicts with keys:
        game_id, tracker_id, first_frame, last_frame, total_frames,
        seconds_played, minutes_played
    """
    effective_fps = fps / detect_stride
    relational_game_id = _resolve_relational_game_id(db, game_id)

    rows = db.execute(
        """
        SELECT tracker_id,
               MIN(frame_number) AS first_frame,
               MAX(frame_number) AS last_frame,
               COUNT(DISTINCT frame_number) AS total_frames
        FROM detections
        WHERE game_id = ?
          AND object_class = 'person'
          AND tracker_id IS NOT NULL
        GROUP BY tracker_id
        ORDER BY total_frames DESC
        """,
        (game_id,),
    ).fetchall()

    results = []
    for row in rows:
        total_frames = row["total_frames"]
        seconds_played = total_frames / effective_fps
        minutes_played = seconds_played / 60.0

        results.append({
            "game_id": str(game_id),
            "relational_game_id": relational_game_id,
            "tracker_id": row["tracker_id"],
            "first_frame": row["first_frame"],
            "last_frame": row["last_frame"],
            "total_frames": total_frames,
            "seconds_played": round(seconds_played, 2),
            "minutes_played": round(minutes_played, 2),
        })

    db.executemany(
        """
        INSERT OR REPLACE INTO player_minutes
            (game_id, relational_game_id, tracker_id, first_frame, last_frame,
             total_frames, minutes_played, jersey_number, player_name)
        VALUES (:game_id, :relational_game_id, :tracker_id, :first_frame,
                :last_frame, :total_frames, :minutes_played, NULL, NULL)
        """,
        results,
    )
    db.commit()

    return results


def backfill_all_games(db, fps=30.0, detect_stride=1):
    """Backfill player_minutes for every game that has person detections.

    Returns dict mapping game_id -> list of player minute dicts.
    """
    game_rows = db.execute(
        """
        SELECT DISTINCT game_id
        FROM detections
        WHERE object_class = 'person' AND tracker_id IS NOT NULL
        """,
    ).fetchall()

    output = {}
    for grow in game_rows:
        gid = grow["game_id"]
        output[gid] = backfill_player_minutes(db, gid, fps, detect_stride)

    return output


def get_player_minutes(db, game_id):
    """Query player_minutes for a given game.

    Returns rows sorted by minutes_played descending.
    """
    from analysis_helpers import dedupe_player_minute_rows, resolve_analysis_key

    analysis_key = resolve_analysis_key(db, game_id)
    relational_game_id = _resolve_relational_game_id(db, game_id)
    if relational_game_id is not None:
        rows = db.execute(
            """
            SELECT pm.game_id, pm.tracker_id, pm.first_frame, pm.last_frame,
                   pm.total_frames, pm.minutes_played,
                   pm.jersey_number, pm.player_name, pm.relational_game_id,
                   p.id AS player_id, p.name AS resolved_name
            FROM player_minutes pm
            LEFT JOIN players p ON p.tracker_id = pm.tracker_id
            WHERE pm.relational_game_id = ?
               OR (pm.relational_game_id IS NULL AND pm.game_id = ?)
            ORDER BY pm.minutes_played DESC
            """,
            (relational_game_id, analysis_key),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT pm.game_id, pm.tracker_id, pm.first_frame, pm.last_frame,
                   pm.total_frames, pm.minutes_played,
                   pm.jersey_number, pm.player_name, pm.relational_game_id,
                   p.id AS player_id, p.name AS resolved_name
            FROM player_minutes pm
            LEFT JOIN players p ON p.tracker_id = pm.tracker_id
            WHERE pm.game_id = ?
            ORDER BY pm.minutes_played DESC
            """,
            (analysis_key,),
        ).fetchall()

    return dedupe_player_minute_rows(rows, preferred_game_id=analysis_key)


def get_player_minutes_for_player(db, tracker_id):
    """Query all player_minutes rows for a given tracker_id across games."""
    return db.execute(
        """
        SELECT pm.game_id, pm.first_frame, pm.last_frame,
               pm.total_frames, pm.minutes_played
        FROM player_minutes pm
        WHERE pm.tracker_id = ?
        ORDER BY pm.game_id
        """,
        (tracker_id,),
    ).fetchall()
