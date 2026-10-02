"""Map AI court slots (Pos 0-9) to roster jersey numbers for a game."""

import json

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
            """SELECT tracker_id, minutes_played, jersey_number, player_name,
                      first_frame, last_frame, total_frames
                 FROM player_minutes
                WHERE relational_game_id = ?
                   OR (relational_game_id IS NULL AND game_id = ?)
                ORDER BY minutes_played DESC, tracker_id ASC""",
            (relational_game_id, analysis_key),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT tracker_id, minutes_played, jersey_number, player_name,
                      first_frame, last_frame, total_frames
                 FROM player_minutes
                WHERE game_id = ?
                ORDER BY minutes_played DESC, tracker_id ASC""",
            (analysis_key,),
        ).fetchall()

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
    try:
        from jersey_shade import ensure_tracker_shades, side_label
        shades = ensure_tracker_shades(db, analysis_key)
    except Exception:
        shades = {}
    for slot in slots:
        info = shades.get(int(slot["tracker_id"])) if slot.get("tracker_id") is not None else None
        if not info:
            continue
        slot["shade"] = info.get("shade")
        slot["team_side"] = info.get("side")
        slot["team_label"] = side_label(info.get("side") or "")
        slot["mean_v"] = info.get("mean_v")
    return slots


def save_court_slot_mappings(db, game_id, mappings, apply_to_events=False):
    relational_game_id, analysis_key = _game_scope(db, game_id)
    applied = []

    for entry in mappings or []:
        tracker_id = entry.get("tracker_id")
        if tracker_id is None:
            continue

        if entry.get("lock_name"):
            resolved = {}
            jersey_number = entry.get("jersey_number")
            player_name = entry.get("player_name")
        else:
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
            db.execute(
                """UPDATE player_minutes
                      SET jersey_number = ?, player_name = ?
                    WHERE tracker_id = ?
                      AND (relational_game_id = ? OR game_id = ?)""",
                (jersey_number, player_name, int(tracker_id), relational_game_id, analysis_key),
            )
        else:
            db.execute(
                """UPDATE player_minutes
                      SET jersey_number = ?, player_name = ?
                    WHERE tracker_id = ? AND game_id = ?""",
                (jersey_number, player_name, int(tracker_id), analysis_key),
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


def _player_match_keys(tracker_id, jersey_number, player_name):
    keys = {str(tracker_id)}
    name = (player_name or "").strip()
    if jersey_number is None:
        return keys
    jersey = int(jersey_number)
    keys.add(f"#{jersey}")
    if name:
        keys.add(f"#{jersey} {name}")
        keys.add(f"{jersey} - {name}")
    return keys


def _matching_player_row(db, jersey_number, player_name):
    """One players-table row when the scorebook name and jersey are the same person.

    A last name matches 'Hunter Colman' to Colman. A different spelling, such as
    Daly for Dayley, does not match.
    """
    name = (player_name or "").strip().lower()
    if jersey_number is None or not name:
        return None
    rows = db.execute(
        """SELECT p.id AS player_id, p.name,
                  rm.id AS roster_membership_id, rm.team_id, t.team_name
             FROM players p
             LEFT JOIN roster_memberships rm
               ON rm.player_id = p.id AND rm.status = 'active'
             LEFT JOIN teams t ON t.id = rm.team_id
            WHERE p.jersey_number = ?""",
        (int(jersey_number),),
    ).fetchall()
    hits = []
    for row in rows:
        stored = (row["name"] or "").strip().lower()
        if stored == name or stored.endswith(" " + name):
            hits.append(row)
    if len(hits) == 1:
        return hits[0]
    return None


def _liberty_team_id(db):
    rows = db.execute(
        "SELECT id FROM teams WHERE lower(team_name) = 'liberty'"
    ).fetchall()
    if len(rows) == 1:
        return rows[0]["id"]
    return None


def _merge_identity_details(raw, jersey_number, team_side, player_name):
    try:
        details = json.loads(raw) if raw else {}
    except (TypeError, json.JSONDecodeError):
        details = {}
    if not isinstance(details, dict):
        details = {}
    if jersey_number is not None:
        details["jersey_number"] = int(jersey_number)
    if team_side in ("home", "away"):
        details["team_side"] = team_side
    name = (player_name or "").strip()
    if name:
        details["player_name"] = name
    return json.dumps(details)


def stamp_scorebook_links(db, game_id):
    """Write the roster id and team onto events that already name a scorebook player.

    Naming stays pending. A players-table row is used only when the name matches,
    so jersey 13 stored as 'unkn' is not attached to Mendoza.
    """
    import re

    from program_mode import analysis_players_from_scorebook, load_scorebook

    people = analysis_players_from_scorebook(load_scorebook(str(game_id)))
    by_key = {}
    for person in people:
        jersey = person.get("jersey_number")
        name = (person.get("name") or "").strip()
        if jersey is None or not name:
            continue
        by_key[(int(jersey), name.lower())] = person
    if not by_key:
        return 0

    relational_game_id, analysis_key = _game_scope(db, game_id)
    if relational_game_id is not None:
        rows = db.execute(
            """SELECT id, player, details_json
                 FROM events
                WHERE source_type = 'ai'
                  AND (relational_game_id = ? OR game_id = ?)""",
            (relational_game_id, analysis_key),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT id, player, details_json
                 FROM events
                WHERE source_type = 'ai' AND game_id = ?""",
            (analysis_key,),
        ).fetchall()

    hashed = re.compile(r"^#(\d+)\s+(.+)$")
    named = re.compile(r"^(\d+)\s*-\s*(.+)$")
    updated = 0
    for row in rows:
        text = (row["player"] or "").strip()
        match = hashed.match(text) or named.match(text)
        if not match:
            continue
        person = by_key.get((int(match.group(1)), match.group(2).strip().lower()))
        if not person:
            continue
        jersey = int(person["jersey_number"])
        name = person["name"]
        side = person.get("side")
        team_side = person.get("team") if person.get("team") in ("home", "away") else None
        link = _matching_player_row(db, jersey, name)
        link_team = (link["team_name"] or "").strip().lower() if link else ""
        if link and side == "opponent" and link_team == "liberty":
            player_id = None
            roster_membership_id = None
            team_id = None
        elif link:
            player_id = link["player_id"]
            roster_membership_id = link["roster_membership_id"]
            team_id = link["team_id"]
        elif side == "liberty":
            player_id = None
            roster_membership_id = None
            team_id = _liberty_team_id(db)
        else:
            player_id = None
            roster_membership_id = None
            team_id = None
        db.execute(
            """UPDATE events
                  SET primary_player_id = COALESCE(?, primary_player_id),
                      primary_roster_membership_id = COALESCE(?, primary_roster_membership_id),
                      team_id = COALESCE(?, team_id),
                      details_json = ?,
                      updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
            (
                player_id,
                roster_membership_id,
                team_id,
                _merge_identity_details(row["details_json"], jersey, team_side, name),
                row["id"],
            ),
        )
        updated += 1
    return updated


def apply_court_slot_mappings(db, game_id, tracker_ids=None, mark_reviewed=True):
    """Rewrite AI events and derived tables to use mapped jersey labels.

    mark_reviewed stays on for a coach save. An OCR auto-apply passes False so
    naming a jersey is not stored as a coach correction.
    """
    relational_game_id, analysis_key = _game_scope(db, game_id)
    slots = get_court_slots(db, game_id)
    allowed = None if tracker_ids is None else {int(t) for t in tracker_ids}
    events_updated = 0
    from program_mode import _liberty_is_home, load_scorebook
    from track_identity import _pick_roster_player, _roster_jersey_index

    roster_by_jersey, _roster_source = _roster_jersey_index(db, game_id)
    liberty_is_home = _liberty_is_home(load_scorebook(str(game_id)))

    for slot in slots:
        if not slot.get("is_mapped"):
            continue
        if allowed is not None and int(slot["tracker_id"]) not in allowed:
            continue

        jersey_number = slot.get("jersey_number")
        shade_side = slot.get("team_side")
        picked = None
        if jersey_number is not None:
            picked = _pick_roster_player(
                (roster_by_jersey or {}).get(int(jersey_number)),
                shade_side,
                liberty_is_home,
            )
        if picked:
            saved_name = (picked.get("name") or picked.get("label") or "").strip()
            label = _player_label(jersey_number, saved_name)
            link = _matching_player_row(db, jersey_number, saved_name)
            roster_side = picked.get("side")
            link_team = (link["team_name"] or "").strip().lower() if link else ""
            if link and roster_side == "opponent" and link_team == "liberty":
                player_id = None
                roster_membership_id = None
                team_id = None
            elif link:
                player_id = link["player_id"]
                roster_membership_id = link["roster_membership_id"]
                team_id = link["team_id"]
            elif roster_side == "liberty":
                player_id = None
                roster_membership_id = None
                team_id = _liberty_team_id(db)
            else:
                player_id = None
                roster_membership_id = None
                team_id = None
        else:
            resolved = _resolve_roster_player(
                db,
                jersey_number=jersey_number,
                player_name=slot.get("player_name"),
                game_id=game_id,
            )
            label = slot["mapped_label"]
            saved_name = (slot.get("player_name") or "").strip()
            resolved_name = (resolved.get("name") or "").strip()
            names_match = bool(saved_name) and resolved_name.lower() == saved_name.lower()
            player_id = resolved.get("player_id") if names_match else None
            roster_membership_id = resolved.get("roster_membership_id") if names_match else None
            team_id = resolved.get("team_id") if names_match else None

        stamp_side = shade_side if picked else None
        keys = sorted(_player_match_keys(slot["tracker_id"], jersey_number, saved_name))
        placeholders = ",".join("?" for _ in keys)
        if relational_game_id is not None:
            scope_sql = "AND (relational_game_id = ? OR game_id = ?)"
            scope_args = (relational_game_id, analysis_key)
        else:
            scope_sql = "AND game_id = ?"
            scope_args = (analysis_key,)
        rows = db.execute(
            f"""SELECT id, review_status, details_json
                  FROM events
                 WHERE source_type = 'ai'
                   AND player IN ({placeholders})
                   {scope_sql}""",
            (*keys, *scope_args),
        ).fetchall()
        for row in rows:
            review_status = row["review_status"]
            if mark_reviewed and review_status == "pending":
                review_status = "corrected"
            db.execute(
                """UPDATE events
                      SET player = ?,
                          primary_player_id = COALESCE(?, primary_player_id),
                          primary_roster_membership_id = COALESCE(?, primary_roster_membership_id),
                          team_id = COALESCE(?, team_id),
                          review_status = ?,
                          details_json = ?,
                          updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?""",
                (
                    label,
                    player_id,
                    roster_membership_id,
                    team_id,
                    review_status,
                    _merge_identity_details(row["details_json"], jersey_number, stamp_side, saved_name),
                    row["id"],
                ),
            )
        events_updated += len(rows)
        if saved_name and jersey_number is not None:
            db.execute(
                """UPDATE track_identity_labels
                      SET player_name = ?,
                          player_id = COALESCE(?, player_id),
                          updated_at = CURRENT_TIMESTAMP
                    WHERE game_id = ?
                      AND tracker_id = ?
                      AND jersey_number = ?""",
                (saved_name, player_id, analysis_key, int(slot["tracker_id"]), int(jersey_number)),
            )

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
