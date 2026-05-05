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
    db.commit()
    return aggregated
