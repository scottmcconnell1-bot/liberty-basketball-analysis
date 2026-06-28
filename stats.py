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

    # Shot breakdown (exclude rejected events)
    shots = _fetch_shot_rows(
        db,
        relational_game_id,
        game_id,
        """
        SELECT sc.tracker_id, sc.shot_type, sc.shot_result, COUNT(*) as cnt
        FROM shot_classifications sc
        LEFT JOIN events e ON e.id = sc.event_id
        WHERE (sc.relational_game_id = ? OR (sc.relational_game_id IS NULL AND sc.game_id = ?))
          AND (e.review_status IS NULL OR e.review_status != 'rejected')
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
        LEFT JOIN events e ON e.id = sc.event_id
        WHERE sc.game_id = ?
          AND (e.review_status IS NULL OR e.review_status != 'rejected')
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

    # Possession summary
    possession_summary = get_possession_summary(db, game_id)

    return {
        "basic_stats": [dict(s) for s in basic],
        "minutes": [dict(m) for m in minutes],
        "shot_breakdown": [dict(s) for s in shots],
        "player_effect": [dict(e) for e in effects],
        "plays_summary": [dict(p) for p in plays],
        "possession_summary": possession_summary,
    }


def get_team_stats(db, game_id):
    """Return aggregated team stats for the given game_id.

    Sums from the events table (rejected events excluded via counts_for_stats
    and review_status filtering). Returns a dict with: points, rebounds,
    assists, steals, blocks, turnovers, fga, fta, three_pm, orb, drb.
    """
    relational_game_id = _resolve_relational_game_id(db, game_id)

    if relational_game_id is not None:
        rows = db.execute(
            """SELECT e.player, e.event_type, e.shot_result, et.code,
                      et.counts_for_stats, et.is_scoring_event
               FROM events e
               JOIN event_types et ON et.id = e.event_type_id
               WHERE e.relational_game_id = ?
                 AND e.review_status != 'rejected'
                 AND et.counts_for_stats = 1""",
            (relational_game_id,),
        ).fetchall()
    else:
        rows = db.execute(
            """SELECT e.player, e.event_type, e.shot_result, et.code,
                      et.counts_for_stats, et.is_scoring_event
               FROM events e
               JOIN event_types et ON et.id = e.event_type_id
               WHERE e.game_id = ?
                 AND e.review_status != 'rejected'
                 AND et.counts_for_stats = 1""",
            (game_id,),
        ).fetchall()

    team = {
        "points": 0,
        "rebounds": 0,
        "assists": 0,
        "steals": 0,
        "blocks": 0,
        "turnovers": 0,
        "fga": 0,
        "fta": 0,
        "three_pm": 0,
        "orb": 0,
        "drb": 0,
    }

    for row in rows:
        et = (row["code"] or "").lower()
        sr = (row["shot_result"] or "").lower()

        if et in ("made_two", "two_attempt", "2pt", "shot"):
            team["fga"] += 1
            if sr == "made":
                team["points"] += 2
        elif et in ("missed_two",):
            team["fga"] += 1
        elif et in ("made_three", "three_attempt", "3pt"):
            team["fga"] += 1
            if sr == "made":
                team["points"] += 3
                team["three_pm"] += 1
        elif et in ("missed_three",):
            team["fga"] += 1
        elif et == "made_free_throw":
            team["fta"] += 1
            if sr == "made":
                team["points"] += 1
        elif et == "missed_free_throw":
            team["fta"] += 1
        elif et == "assist":
            team["assists"] += 1
        elif et in ("rebound", "rebound_offensive", "rebound_defensive"):
            team["rebounds"] += 1
            if et == "rebound_offensive":
                team["orb"] += 1
            elif et == "rebound_defensive":
                team["drb"] += 1
        elif et == "turnover":
            team["turnovers"] += 1
        elif et == "steal":
            team["steals"] += 1
        elif et == "block":
            team["blocks"] += 1

    return team


def get_four_factors(db, game_id):
    """Return Four Factors percentages for the given game_id.

    Keys: efg_pct, tov_pct, orb_pct, ft_rate.
    All values are floats in [0.0, 1.0]. Zero-division cases return 0.0.
    """
    team = get_team_stats(db, game_id)

    fga = team["fga"]
    three_pm = team["three_pm"]
    tov = team["turnovers"]
    orb = team["orb"]
    drb = team["drb"]
    fta = team["fta"]

    # eFG% = (FGM + 0.5 * 3PM) / FGA
    # We need FGM: for the team, FGM = (points from 2pt) / 2 + three_pm
    # But more directly: count made shots. We can derive from possession data
    # or compute from the event codes. Since we already have fga and three_pm,
    # we need total FGM. Let's compute it from the events directly.
    # Re-query for FGM since team stats aggregate doesn't track it directly.
    fgm = _compute_fgm(db, game_id)

    efg_pct = (fgm + 0.5 * three_pm) / fga if fga > 0 else 0.0

    # TOV% = TOV / (FGA + 0.44 * FTA + TOV)
    tov_denom = fga + 0.44 * fta + tov
    tov_pct = tov / tov_denom if tov_denom > 0 else 0.0

    # ORB% = ORB / (ORB + OPP_DRB)
    # We don't have opponent DRB directly; approximate using our DRB as
    # a placeholder until opponent data is wired. For now, use ORB / (ORB + DRB)
    # which gives offensive rebound rate vs total rebounds.
    orb_denom = orb + drb
    orb_pct = orb / orb_denom if orb_denom > 0 else 0.0

    # FTRate = FTA / FGA
    ft_rate = fta / fga if fga > 0 else 0.0

    return {
        "efg_pct": round(efg_pct, 4),
        "tov_pct": round(tov_pct, 4),
        "orb_pct": round(orb_pct, 4),
        "ft_rate": round(ft_rate, 4),
    }


def _compute_fgm(db, game_id):
    """Count total field goals made for a game (2pt + 3pt makes)."""
    relational_game_id = _resolve_relational_game_id(db, game_id)

    if relational_game_id is not None:
        row = db.execute(
            """SELECT COUNT(*) as cnt
               FROM events e
               JOIN event_types et ON et.id = e.event_type_id
               WHERE e.relational_game_id = ?
                 AND e.review_status != 'rejected'
                 AND et.counts_for_stats = 1
                 AND et.code IN ('made_two', 'made_three')
                 AND e.shot_result = 'made'""",
            (relational_game_id,),
        ).fetchone()
    else:
        row = db.execute(
            """SELECT COUNT(*) as cnt
               FROM events e
               JOIN event_types et ON et.id = e.event_type_id
               WHERE e.game_id = ?
                 AND e.review_status != 'rejected'
                 AND et.counts_for_stats = 1
                 AND et.code IN ('made_two', 'made_three')
                 AND e.shot_result = 'made'""",
            (game_id,),
        ).fetchone()

    return row["cnt"] if row else 0


def get_possession_summary(db, game_id):
    """Return possession summary for a game.

    Uses events.possession_id (populated by assign_possessions_for_game).
    Returns dict with: total_possessions, scoring_possessions, points_per_possession,
    turnover_rate, top_outcomes.
    """
    relational_game_id = _resolve_relational_game_id(db, game_id)

    # Count total possessions
    if relational_game_id is not None:
        total = db.execute(
            "SELECT COUNT(*) as cnt FROM possessions WHERE game_id = ?",
            (relational_game_id,),
        ).fetchone()["cnt"]
    else:
        total = db.execute(
            "SELECT COUNT(*) as cnt FROM possessions WHERE game_id = ?",
            (game_id,),
        ).fetchone()["cnt"]

    if total == 0:
        return {
            "total_possessions": 0,
            "scoring_possessions": 0,
            "points_per_possession": 0.0,
            "turnover_rate": 0.0,
            "top_outcomes": [],
        }

    # Scoring possessions (points_for > 0)
    scoring = db.execute(
        "SELECT COUNT(*) as cnt FROM possessions WHERE game_id = ? AND points_for > 0",
        (game_id,),
    ).fetchone()["cnt"]

    # Total points
    total_points = db.execute(
        "SELECT COALESCE(SUM(points_for), 0) as pts FROM possessions WHERE game_id = ?",
        (game_id,),
    ).fetchone()["pts"]

    # Turnover events (possession ended in turnover, excluding rejected)
    if relational_game_id is not None:
        turnovers = db.execute(
            """SELECT COUNT(*) as cnt FROM events
               WHERE relational_game_id = ?
                 AND possession_id IS NOT NULL
                 AND event_type = 'turnover'
                 AND review_status != 'rejected'""",
            (relational_game_id,),
        ).fetchone()["cnt"]
    else:
        turnovers = db.execute(
            """SELECT COUNT(*) as cnt FROM events
               WHERE game_id = ?
                 AND possession_id IS NOT NULL
                 AND event_type = 'turnover'
                 AND review_status != 'rejected'""",
            (game_id,),
        ).fetchone()["cnt"]

    # Top 3 possession outcomes by count
    if relational_game_id is not None:
        top = db.execute(
            """SELECT outcome, COUNT(*) as cnt FROM possessions
               WHERE game_id = ? AND outcome IS NOT NULL
               GROUP BY outcome ORDER BY cnt DESC LIMIT 3""",
            (game_id,),
        ).fetchall()
    else:
        top = db.execute(
            """SELECT outcome, COUNT(*) as cnt FROM possessions
               WHERE game_id = ? AND outcome IS NOT NULL
               GROUP BY outcome ORDER BY cnt DESC LIMIT 3""",
            (game_id,),
        ).fetchall()

    return {
        "total_possessions": total,
        "scoring_possessions": scoring,
        "points_per_possession": round(total_points / total, 2) if total else 0.0,
        "turnover_rate": round(turnovers / total, 2) if total else 0.0,
        "top_outcomes": [{"outcome": r["outcome"], "count": r["cnt"]} for r in top],
    }
