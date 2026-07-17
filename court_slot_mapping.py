"""Map AI court slots (Pos 0-9) to roster jersey numbers for a game."""

from analysis_helpers import dedupe_player_minute_rows
from stats import _resolve_relational_game_id, aggregate_stats_preview, refresh_stats


def _game_scope(db, game_id):
    relational_game_id = _resolve_relational_game_id(db, game_id)
    analysis_key = str(game_id)
    return relational_game_id, analysis_key


def _player_label(jersey_number, player_name):
    jersey = int(jersey_number) if jersey_number is not None else None
    name = (player_name or "").strip()
    if jersey is not None and name:
        return f"#{jersey} {name}"
    if jersey is not None:
        return f"#{jersey}"
    return name or None


def _resolve_roster_player(db, jersey_number=None, player_name=None, player_id=None, game_id=None):
    if player_id is not None:
        row = db.execute(
            """SELECT p.id AS player_id, p.name, p.jersey_number,
                      rm.id AS roster_membership_id, rm.team_id
                 FROM players p
                 LEFT JOIN roster_memberships rm
                   ON rm.player_id = p.id AND rm.status = 'active'
                WHERE p.id = ?
                ORDER BY rm.created_at DESC
                LIMIT 1""",
            (player_id,),
        ).fetchone()
        if row:
            return dict(row)

    if game_id and jersey_number is not None:
        from analysis_helpers import lookup_film_roster_player, resolve_analysis_game_context

        context = resolve_analysis_game_context(db, game_id)
        if context.get("season_id"):
            film_player = lookup_film_roster_player(db, game_id, jersey_number=jersey_number)
            if film_player:
                return film_player

    if jersey_number is not None:
        row = db.execute(
            """SELECT p.id AS player_id, p.name, p.jersey_number,
                      rm.id AS roster_membership_id, rm.team_id
                 FROM players p
                 LEFT JOIN roster_memberships rm
                   ON rm.player_id = p.id AND rm.status = 'active'
                WHERE p.jersey_number = ?
                ORDER BY rm.created_at DESC
                LIMIT 1""",
            (int(jersey_number),),
        ).fetchone()
        if row:
            return dict(row)

    if player_name:
        row = db.execute(
            """SELECT p.id AS player_id, p.name, p.jersey_number,
                      rm.id AS roster_membership_id, rm.team_id
                 FROM players p
                 LEFT JOIN roster_memberships rm
                   ON rm.player_id = p.id AND rm.status = 'active'
                WHERE lower(trim(p.name)) = lower(trim(?))
                ORDER BY rm.created_at DESC
                LIMIT 1""",
            (player_name,),
        ).fetchone()
        if row:
            return dict(row)

    return {
        "player_id": player_id,
        "name": (player_name or "").strip() or None,
        "jersey_number": int(jersey_number) if jersey_number is not None else None,
        "roster_membership_id": None,
        "team_id": None,
    }


def get_court_slots(db, game_id):
    relational_game_id, analysis_key = _game_scope(db, game_id)
    if relational_game_id is not None:
        rows = db.execute(
            """SELECT game_id, tracker_id, minutes_played, jersey_number, player_name,
                      first_frame, last_frame, total_frames, relational_game_id
                 FROM player_minutes
                WHERE relational_game_id = ?
                   OR (relational_game_id IS NULL AND game_id = ?)
                ORDER BY minutes_played DESC, tracker_id ASC""",
            (relational_game_id, analysis_key),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT game_id, tracker_id, minutes_played, jersey_number, player_name,
                      first_frame, last_frame, total_frames, relational_game_id
                 FROM player_minutes
                WHERE game_id = ?
                ORDER BY minutes_played DESC, tracker_id ASC""",
            (analysis_key,),
        ).fetchall()

    rows = dedupe_player_minute_rows(rows, preferred_game_id=analysis_key)
    slots = []
    for row in rows:
        label = _player_label(row["jersey_number"], row["player_name"])
        slots.append({
            "tracker_id": row["tracker_id"],
            "minutes_played": row["minutes_played"],
            "jersey_number": row["jersey_number"],
            "player_name": row["player_name"],
            "mapped_label": label,
            "is_mapped": bool(label),
        })
    return slots


def save_court_slot_mappings(db, game_id, mappings, apply_to_events=False):
    relational_game_id, analysis_key = _game_scope(db, game_id)
    applied = []

    for entry in mappings or []:
        tracker_id = entry.get("tracker_id")
        if tracker_id is None:
            continue

        resolved = _resolve_roster_player(
            db,
            jersey_number=entry.get("jersey_number"),
            player_name=entry.get("player_name"),
            player_id=entry.get("player_id"),
            game_id=game_id,
        )
        jersey_number = resolved.get("jersey_number") if resolved.get("jersey_number") is not None else entry.get("jersey_number")
        player_name = resolved.get("name") or entry.get("player_name")
        label = _player_label(jersey_number, player_name)

        if relational_game_id is not None:
            cur = db.execute(
                """UPDATE player_minutes
                      SET jersey_number = ?, player_name = ?
                    WHERE tracker_id = ?
                      AND (relational_game_id = ? OR game_id = ?)""",
                (jersey_number, player_name, int(tracker_id), relational_game_id, analysis_key),
            )
            if cur.rowcount == 0:
                db.execute(
                    """INSERT INTO player_minutes
                           (game_id, relational_game_id, tracker_id, jersey_number, player_name,
                            first_frame, last_frame, total_frames, minutes_played)
                       VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0)""",
                    (analysis_key, relational_game_id, int(tracker_id), jersey_number, player_name),
                )
        else:
            cur = db.execute(
                """UPDATE player_minutes
                      SET jersey_number = ?, player_name = ?
                    WHERE tracker_id = ? AND game_id = ?""",
                (jersey_number, player_name, int(tracker_id), analysis_key),
            )
            if cur.rowcount == 0:
                db.execute(
                    """INSERT INTO player_minutes
                           (game_id, tracker_id, jersey_number, player_name,
                            first_frame, last_frame, total_frames, minutes_played)
                       VALUES (?, ?, ?, ?, 0, 0, 0, 0)""",
                    (analysis_key, int(tracker_id), jersey_number, player_name),
                )

        applied.append({
            "tracker_id": int(tracker_id),
            "jersey_number": jersey_number,
            "player_name": player_name,
            "mapped_label": label,
            "player_id": resolved.get("player_id"),
            "roster_membership_id": resolved.get("roster_membership_id"),
        })

    if apply_to_events:
        apply_court_slot_mappings(db, game_id)

    db.commit()
    return applied


def apply_court_slot_mappings(db, game_id):
    """Rewrite AI events and derived tables to use mapped jersey labels."""
    relational_game_id, analysis_key = _game_scope(db, game_id)
    slots = get_court_slots(db, game_id)
    events_updated = 0

    for slot in slots:
        if not slot.get("is_mapped"):
            continue

        resolved = _resolve_roster_player(
            db,
            jersey_number=slot.get("jersey_number"),
            player_name=slot.get("player_name"),
            game_id=game_id,
        )
        label = slot["mapped_label"]
        tracker_id = str(slot["tracker_id"])
        player_id = resolved.get("player_id")
        roster_membership_id = resolved.get("roster_membership_id")
        team_id = resolved.get("team_id")
        jersey_number = slot.get("jersey_number")

        if relational_game_id is not None:
            cur = db.execute(
                """UPDATE events
                      SET player = ?,
                          primary_player_id = COALESCE(?, primary_player_id),
                          primary_roster_membership_id = COALESCE(?, primary_roster_membership_id),
                          team_id = COALESCE(?, team_id),
                          review_status = CASE
                              WHEN review_status = 'pending' THEN 'corrected'
                              ELSE review_status
                          END,
                          updated_at = CURRENT_TIMESTAMP
                    WHERE player = ?
                      AND source_type = 'ai'
                      AND (relational_game_id = ? OR game_id = ?)""",
                (
                    label,
                    player_id,
                    roster_membership_id,
                    team_id,
                    tracker_id,
                    relational_game_id,
                    analysis_key,
                ),
            )
        else:
            cur = db.execute(
                """UPDATE events
                      SET player = ?,
                          primary_player_id = COALESCE(?, primary_player_id),
                          primary_roster_membership_id = COALESCE(?, primary_roster_membership_id),
                          team_id = COALESCE(?, team_id),
                          review_status = CASE
                              WHEN review_status = 'pending' THEN 'corrected'
                              ELSE review_status
                          END,
                          updated_at = CURRENT_TIMESTAMP
                    WHERE player = ?
                      AND source_type = 'ai'
                      AND game_id = ?""",
                (
                    label,
                    player_id,
                    roster_membership_id,
                    team_id,
                    tracker_id,
                    analysis_key,
                ),
            )
        events_updated += cur.rowcount

        if relational_game_id is not None:
            db.execute(
                """UPDATE shot_classifications
                      SET jersey_number = ?
                    WHERE tracker_id = ?
                      AND (relational_game_id = ? OR game_id = ?)""",
                (jersey_number, int(slot["tracker_id"]), relational_game_id, analysis_key),
            )
            db.execute(
                """UPDATE player_effect
                      SET jersey_number = ?
                    WHERE tracker_id = ?
                      AND (relational_game_id = ? OR game_id = ?)""",
                (jersey_number, int(slot["tracker_id"]), relational_game_id, analysis_key),
            )
        else:
            db.execute(
                """UPDATE shot_classifications
                      SET jersey_number = ?
                    WHERE tracker_id = ? AND game_id = ?""",
                (jersey_number, int(slot["tracker_id"]), analysis_key),
            )
            db.execute(
                """UPDATE player_effect
                      SET jersey_number = ?
                    WHERE tracker_id = ? AND game_id = ?""",
                (jersey_number, int(slot["tracker_id"]), analysis_key),
            )

    refresh_stats(db, game_id)
    db.commit()
    return {
        "slots_mapped": sum(1 for slot in slots if slot.get("is_mapped")),
        "events_updated": events_updated,
        "basic_stats": aggregate_stats_preview(db, game_id),
    }
