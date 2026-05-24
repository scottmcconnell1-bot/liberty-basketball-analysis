"""stats.py – Aggregate and persist per-game stats from the events table."""


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
        et = (row["event_type"] or "").lower()
        sr = (row["shot_result"] or "").lower()

        if et in ("two_attempt", "2pt", "shot"):
            s["fga"] += 1
            if sr == "made":
                s["fgm"] += 1
                s["pts"] += 2
        elif et in ("three_attempt", "3pt"):
            s["fga"] += 1
            s["threes_att"] += 1
            if sr == "made":
                s["fgm"] += 1
                s["threes_made"] += 1
                s["pts"] += 3
        elif et == "assist":
            s["ast"] += 1
        elif et == "rebound":
            s["reb"] += 1
        elif et == "turnover":
            s["tov"] += 1
        elif et == "steal":
            s["stl"] += 1
        elif et == "block":
            s["blk"] += 1

    return list(players.values())


def aggregate_stats(db, game_id):
    """Return a list of per-player stat dicts for the given game_id."""
    rows = db.execute(
        "SELECT player, event_type, shot_result FROM events WHERE game_id=?",
        (game_id,),
    ).fetchall()
    return _aggregate_rows(rows)


def refresh_stats(db, game_id):
    """Rebuild persisted stats rows for a game and return the computed payload."""
    aggregated = aggregate_stats(db, game_id)
    db.execute("DELETE FROM stats WHERE game_id=?", (game_id,))
    for stat in aggregated:
        db.execute(
            """INSERT INTO stats
               (game_id, player_name, pts, fgm, fga, threes_made, threes_att, ast, reb, tov, stl, blk)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                game_id,
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

    # Add minutes played from player_minutes table
    minutes_rows = db.execute(
        "SELECT tracker_id, minutes_played FROM player_minutes WHERE game_id=?", (game_id,)
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
                (minutes, game_id, tracker_id)
            )

    # Add shot type breakdowns from shot_classifications table
    shot_rows = db.execute("""
        SELECT tracker_id, shot_type, shot_result, COUNT(*) as cnt
        FROM shot_classifications
        WHERE game_id=?
        GROUP BY tracker_id, shot_type, shot_result
    """, (game_id,)).fetchall()

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

    # Minutes
    minutes = db.execute("""
        SELECT pm.tracker_id, pm.minutes_played, pm.jersey_number, p.name
        FROM player_minutes pm
        LEFT JOIN players p ON p.tracker_id = pm.tracker_id
        WHERE pm.game_id = ?
        ORDER BY pm.minutes_played DESC
    """, (game_id,)).fetchall()

    # Shot breakdown
    shots = db.execute("""
        SELECT sc.tracker_id, sc.shot_type, sc.shot_result, COUNT(*) as cnt
        FROM shot_classifications sc
        WHERE sc.game_id = ?
        GROUP BY sc.tracker_id, sc.shot_type, sc.shot_result
        ORDER BY sc.tracker_id, sc.shot_type
    """, (game_id,)).fetchall()

    # Player effect
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
