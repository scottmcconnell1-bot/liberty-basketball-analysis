"""stats.py – Aggregate and persist per-game stats from the events table."""


def _resolve_relational_game_id(db, game_id):
    try:
        game_id_int = int(game_id)
    except (TypeError, ValueError):
        return None

    row = db.execute("SELECT id FROM games WHERE id=?", (game_id_int,)).fetchone()
    return row["id"] if row else None


def _fetch_shot_rows(db, relational_game_id, game_id, query):
    if relational_game_id is not None:
        return db.execute(query, (relational_game_id, str(game_id))).fetchall()
    return db.execute(query, (game_id,)).fetchall()


def _eligible_event_rows(db, game_id):
    """Return only events eligible for stats derivation.

    Eligible = events resolved to a known event_type_id AND not rejected.
    Manual events (human_verified=1) and accepted AI events
    (human_verified=0 AND review_status='accepted') are included;
    everything else (pending/corrected/rejected) is filtered out here so
    aggregation only sees canonical, approved events.
    """
    relational_game_id = _resolve_relational_game_id(db, game_id)
    if relational_game_id is not None:
        return db.execute(
            """SELECT e.player, e.event_type, e.shot_result, et.code,
                      et.counts_for_stats, et.is_scoring_event
               FROM events e
               JOIN event_types et ON et.id = e.event_type_id
               WHERE e.relational_game_id = ?
                 AND e.review_status != 'rejected'
                 AND et.counts_for_stats = 1""",
            (relational_game_id,),
        ).fetchall()

    return db.execute(
        """SELECT e.player, e.event_type, e.shot_result, et.code,
                  et.counts_for_stats, et.is_scoring_event
           FROM events e
           JOIN event_types et ON et.id = e.event_type_id
           WHERE e.game_id = ?
             AND e.review_status != 'rejected'
             AND et.counts_for_stats = 1""",
        (game_id,),
    ).fetchall()


def _aggregate_rows(rows):
    players = {}
    for row in rows:
        p = row["player"] or "Unknown"
        if p not in players:
            players[p] = {
                "player": p,
                "pts": 0, "fgm": 0, "fga": 0,
                "threes_made": 0, "threes_att": 0,
                "ast": 0, "reb": 0, "tov": 0,
                "stl": 0, "blk": 0, "events": 0,
            }
        s = players[p]
        s["events"] += 1
        et = (row["code"] or "").lower()
        sr = (row["shot_result"] or "").lower()

        if et in ("made_two", "two_attempt", "2pt", "shot"):
            s["fga"] += 1
            if sr == "made":
                s["fgm"] += 1
                s["pts"] += 2
        elif et in ("missed_two",):
            s["fga"] += 1
        elif et in ("made_three", "three_attempt", "3pt"):
            s["fga"] += 1
            s["threes_att"] += 1
            if sr == "made":
                s["fgm"] += 1
                s["threes_made"] += 1
                s["pts"] += 3
        elif et in ("missed_three",):
            s["fga"] += 1
            s["threes_att"] += 1
        elif et == "made_free_throw":
            s["fga"] += 1
            if sr == "made":
                s["fgm"] += 1
                s["pts"] += 1
        elif et == "missed_free_throw":
            s["fga"] += 1
        elif et == "assist":
            s["ast"] += 1
        elif et in ("rebound", "rebound_offensive", "rebound_defensive"):
            s["reb"] += 1
        elif et == "turnover":
            s["tov"] += 1
        elif et == "steal":
            s["stl"] += 1
        elif et == "block":
            s["blk"] += 1

    return list(players.values())


def aggregate_stats(db, game_id):
    """Return a list of per-player stat dicts for the given game_id.

    Implementation reads stats relationally from the event_types taxonomy:
    - JOIN event_types by events.event_type_id
    - filter where counts_for_stats = 1
    - exclude events with review_status = 'rejected'
    Branching uses the seeded event_types.code (made_two, made_three, ...)
    while still recognizing legacy free-text event_type strings.
    """
    rows = _eligible_event_rows(db, game_id)
    return _aggregate_rows(rows)


def refresh_stats(db, game_id):
    """Rebuild persisted stats rows for a game and return the computed payload."""
    aggregated = aggregate_stats(db, game_id)
    relational_game_id = _resolve_relational_game_id(db, game_id)
    if relational_game_id is not None:
        db.execute(
            "DELETE FROM stats WHERE relational_game_id=? OR game_id=?",
            (relational_game_id, str(game_id)),
        )
    else:
        db.execute("DELETE FROM stats WHERE game_id=?", (game_id,))
    for stat in aggregated:
        db.execute(
            """INSERT INTO stats
               (game_id, relational_game_id, player_name, pts, fgm, fga, threes_made, threes_att, ast, reb, tov, stl, blk)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                str(game_id),
                relational_game_id,
                stat["player"],
                stat["pts"],
                stat["fgm"],
                stat["fga"],
                stat["threes_made"],
                stat["threes_att"],
                stat["ast"],
                stat["reb"],
                stat["tov"],
                stat["stl"],
                stat["blk"],
            ),
        )

    # Enhance with minutes played and shot type breakdowns from enhanced analysis tables
    _enhance_stats_from_analysis(db, game_id)

    db.commit()
    return aggregated


def _enhance_stats_from_analysis(db, game_id):
    """Add minutes played and shot type breakdowns from enhanced analysis."""
    relational_game_id = _resolve_relational_game_id(db, game_id)

    # Add minutes played from player_minutes table
    if relational_game_id is not None:
        minutes_rows = db.execute(
            """SELECT tracker_id, minutes_played
               FROM player_minutes
               WHERE relational_game_id=? OR (relational_game_id IS NULL AND game_id=?)""",
            (relational_game_id, str(game_id)),
        ).fetchall()
    else:
        minutes_rows = db.execute(
            "SELECT tracker_id, minutes_played FROM player_minutes WHERE game_id=?",
            (game_id,),
        ).fetchall()

    for mrow in minutes_rows:
        tracker_id = mrow["tracker_id"]
        minutes = mrow["minutes_played"]
        # Find the player_id for this tracker_id in this game's detections
        player = db.execute(
            "SELECT DISTINCT tracker_id FROM detections "
            "WHERE game_id=? AND tracker_id=? AND object_class='person' "
            "LIMIT 1",
            (game_id, tracker_id)
        ).fetchone()
        if player:
            db.execute(
                "UPDATE stats SET minutes=? WHERE game_id=? AND tracker_id=?",
                (minutes, str(game_id), tracker_id)
            )

    # Add shot type breakdowns from shot_classifications table
    shot_rows = _fetch_shot_rows(
        db,
        relational_game_id,
        game_id,
        """
        SELECT tracker_id, shot_type, shot_result, COUNT(*) as cnt
        FROM shot_classifications
        WHERE relational_game_id = ?
           OR (relational_game_id IS NULL AND game_id = ?)
        GROUP BY tracker_id, shot_type, shot_result
        """,
    ) if relational_game_id is not None else _fetch_shot_rows(
        db,
        relational_game_id,
        game_id,
        """
        SELECT tracker_id, shot_type, shot_result, COUNT(*) as cnt
        FROM shot_classifications
        WHERE game_id = ?
        GROUP BY tracker_id, shot_type, shot_result
        """,
    )

    for srow in shot_rows:
        tracker_id = srow["tracker_id"]
        shot_type = srow["shot_type"]
        shot_result = srow["shot_result"]
        cnt = srow["cnt"]

        # Find matching stats row
        player = db.execute(
            "SELECT id FROM players WHERE tracker_id=? LIMIT 1", (tracker_id,)
        ).fetchone()
        if not player:
            continue

        player_id = player["id"]

        # Update appropriate columns based on shot type
        if shot_type == "3pt":
            if shot_result == "make":
                db.execute("UPDATE stats SET threes_made=threes_made+? WHERE game_id=? AND player_id=?", (cnt, game_id, player_id))
            db.execute("UPDATE stats SET threes_att=threes_att+? WHERE game_id=? AND player_id=?", (cnt, game_id, player_id))
        elif shot_type == "2pt":
            if shot_result == "make":
                db.execute("UPDATE stats SET fgm=fgm+? WHERE game_id=? AND player_id=?", (cnt, game_id, player_id))
            db.execute("UPDATE stats SET fga=fga+? WHERE game_id=? AND player_id=?", (cnt, game_id, player_id))


def get_enhanced_stats(db, game_id):
    """
    Get enhanced stats including minutes played, shot breakdowns, and player effect.

    Returns a dict with:
    - basic_stats: standard box score stats
    - minutes: minutes played per player
    - shot_breakdown: 2pt/3pt/FT per player
    - player_effect: possessions, points scored, and offensive rating per position
    - plays: recognized plays summary
    """
    basic = aggregate_stats(db, game_id)
    relational_game_id = _resolve_relational_game_id(db, game_id)

    # Minutes
    minutes = db.execute("""
        SELECT pm.tracker_id, pm.minutes_played, pm.jersey_number, p.name
        FROM player_minutes pm
        LEFT JOIN players p ON p.tracker_id = pm.tracker_id
        WHERE pm.game_id = ?
        ORDER BY pm.minutes_played DESC
    """, (game_id,)).fetchall()

    # Shot breakdown
    shots = _fetch_shot_rows(
        db,
        relational_game_id,
        game_id,
        """
        SELECT sc.tracker_id, sc.shot_type, sc.shot_result, COUNT(*) as cnt
        FROM shot_classifications sc
        WHERE sc.relational_game_id = ?
           OR (sc.relational_game_id IS NULL AND sc.game_id = ?)
        GROUP BY sc.tracker_id, sc.shot_type, sc.shot_result
        ORDER BY sc.tracker_id, sc.shot_type
        """,
    ) if relational_game_id is not None else _fetch_shot_rows(
        db,
        relational_game_id,
        game_id,
        """
        SELECT sc.tracker_id, sc.shot_type, sc.shot_result, COUNT(*) as cnt
        FROM shot_classifications sc
        WHERE sc.game_id = ?
        GROUP BY sc.tracker_id, sc.shot_type, sc.shot_result
        ORDER BY sc.tracker_id, sc.shot_type
        """,
    )

    # Player effect
    if relational_game_id is not None:
        effects = db.execute("""
            SELECT pe.tracker_id, pe.possessions_on AS possessions, pe.points_for AS points_scored,
                   pe.ortg, pe.drtg, pe.net_rating, pm.minutes_played, p.name
            FROM player_effect pe
            LEFT JOIN player_minutes pm
              ON pm.tracker_id = pe.tracker_id
             AND (
                   pm.relational_game_id = pe.relational_game_id
                   OR (pm.relational_game_id IS NULL AND pm.game_id = pe.game_id)
                 )
            LEFT JOIN players p ON p.tracker_id = pe.tracker_id
            WHERE pe.relational_game_id = ?
               OR (pe.relational_game_id IS NULL AND pe.game_id = ?)
            ORDER BY pe.ortg DESC
        """, (relational_game_id, str(game_id))).fetchall()
    else:
        effects = db.execute("""
            SELECT pe.tracker_id, pe.possessions_on AS possessions, pe.points_for AS points_scored,
                   pe.ortg, pe.drtg, pe.net_rating, pm.minutes_played, p.name
            FROM player_effect pe
            LEFT JOIN player_minutes pm ON pm.game_id = pe.game_id AND pm.tracker_id = pe.tracker_id
            LEFT JOIN players p ON p.tracker_id = pe.tracker_id
            WHERE pe.game_id = ?
            ORDER BY pe.ortg DESC
        """, (game_id,)).fetchall()

    # Plays summary
    if relational_game_id is not None:
        plays = db.execute("""
            SELECT play_type, COUNT(*) as cnt
            FROM play_recognitions
            WHERE relational_game_id = ?
               OR (relational_game_id IS NULL AND game_id = ?)
            GROUP BY play_type
            ORDER BY cnt DESC
        """, (relational_game_id, str(game_id))).fetchall()
    else:
        plays = db.execute("""
            SELECT play_type, COUNT(*) as cnt
            FROM play_recognitions
            WHERE game_id = ?
            GROUP BY play_type
            ORDER BY cnt DESC
        """, (game_id,)).fetchall()

    return {
        "basic_stats": [dict(s) for s in basic],
        "minutes": [dict(m) for m in minutes],
        "shot_breakdown": [dict(s) for s in shots],
        "player_effect": [dict(e) for e in effects],
        "plays_summary": [dict(p) for p in plays],
    }
