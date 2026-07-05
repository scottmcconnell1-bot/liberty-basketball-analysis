"""
Stage 10A read-only assistant query engine.

Answers coach questions from trusted (accepted/corrected) events, stats, and clips.
Heuristic-first; optional LLM layer can be added later.
"""

from stats import (
    TRUSTED_REVIEW_STATUSES,
    _resolve_relational_game_id,
    _trusted_event_review_clause,
    aggregate_stats,
    get_enhanced_stats,
    get_four_factors,
    get_team_stats,
)

REVIEW_SCOPE = "accepted_and_corrected_only"


def _response(answer, confidence, intent, citations, source="heuristic"):
    return {
        "answer": answer,
        "confidence": confidence,
        "source": source,
        "intent": intent,
        "review_scope": REVIEW_SCOPE,
        "trusted_review_statuses": list(TRUSTED_REVIEW_STATUSES),
        "citations": citations,
    }


def _unknown(answer, intent="unknown", citations=None):
    return _response(answer, "unknown", intent, citations or [])


def _detect_intent(question):
    text = (question or "").strip().lower()
    if not text:
        return "empty"

    if any(token in text for token in ("clip", "clips", "film", "video", "show me")):
        return "clips"
    if any(token in text for token in ("minute", "minutes", "playing time", "played the most")):
        return "minutes"
    if any(token in text for token in ("four factors", "efg", "effective field goal")):
        return "four_factors"
    if any(token in text for token in ("turnover", "turnovers", "tov")):
        return "turnovers"
    if any(token in text for token in ("team", "our team", "we score", "total points")):
        return "team_stats"
    if any(
        token in text
        for token in (
            "points",
            "point",
            "stats",
            "stat",
            "score",
            "scored",
            "box score",
            "assist",
            "rebound",
            "steal",
            "block",
            "leading scorer",
        )
    ):
        return "player_stats"
    return "general"


def _extract_player_hint(question, player):
    if player and str(player).strip():
        return str(player).strip()
    return None


def _match_player_name(name, hint):
    if not hint:
        return True
    if not name:
        return False
    hint_l = hint.lower()
    name_l = name.lower()
    return hint_l in name_l or name_l in hint_l


def _find_player_stat(stats, player_hint):
    if not stats:
        return None
    if player_hint:
        for row in stats:
            if _match_player_name(row.get("player"), player_hint):
                return row
        return None
    if len(stats) == 1:
        return stats[0]
    top = max(stats, key=lambda row: row.get("pts", 0))
    return top if top.get("pts", 0) > 0 else None


def _stat_citation(stat_row, game_id):
    return {
        "type": "stat",
        "game_id": game_id,
        "player": stat_row.get("player"),
        "pts": stat_row.get("pts", 0),
        "fgm": stat_row.get("fgm", 0),
        "fga": stat_row.get("fga", 0),
        "ast": stat_row.get("ast", 0),
        "reb": stat_row.get("reb", 0),
        "tov": stat_row.get("tov", 0),
        "stl": stat_row.get("stl", 0),
        "blk": stat_row.get("blk", 0),
    }


def _event_citation(row):
    return {
        "type": "event",
        "event_id": row["id"],
        "player": row["player"],
        "event_type": row["event_type"],
        "event_code": row.get("code"),
        "timestamp_ms": row["timestamp_ms"],
        "review_status": row["review_status"],
    }


def _clip_citation(row):
    return {
        "type": "clip",
        "clip_id": row["id"],
        "title": row["title"],
        "event_id": row["event_id"],
        "start_timestamp_ms": row["start_timestamp_ms"],
        "end_timestamp_ms": row["end_timestamp_ms"],
        "clip_type": row["clip_type"],
    }


def _trusted_events_for_game(db, game_id, *, player_hint=None, event_codes=None, limit=25):
    relational_game_id = _resolve_relational_game_id(db, game_id)
    review_clause = _trusted_event_review_clause()
    params = []
    filters = [review_clause, "et.counts_for_stats = 1"]

    if relational_game_id is not None:
        filters.insert(0, "e.relational_game_id = ?")
        params.append(relational_game_id)
    else:
        filters.insert(0, "e.game_id = ?")
        params.append(str(game_id))

    if player_hint:
        filters.append("LOWER(e.player) LIKE ?")
        params.append(f"%{player_hint.lower()}%")

    if event_codes:
        placeholders = ", ".join("?" for _ in event_codes)
        filters.append(f"LOWER(et.code) IN ({placeholders})")
        params.extend(code.lower() for code in event_codes)

    params.append(limit)
    query = f"""
        SELECT e.id, e.player, e.event_type, e.timestamp_ms, e.review_status, et.code
        FROM events e
        JOIN event_types et ON et.id = e.event_type_id
        WHERE {' AND '.join(filters)}
        ORDER BY e.timestamp_ms ASC
        LIMIT ?
    """
    rows = db.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def _trusted_clips_for_game(db, game_id, *, player_hint=None, limit=10):
    relational_game_id = _resolve_relational_game_id(db, game_id)
    review_clause = _trusted_event_review_clause("ev.review_status")
    params = []
    filters = []

    if relational_game_id is not None:
        filters.append("c.game_id = ?")
        params.append(relational_game_id)
    else:
        filters.append("c.game_id = ?")
        params.append(game_id)

    if player_hint:
        filters.append("LOWER(ev.player) LIKE ?")
        params.append(f"%{player_hint.lower()}%")

    params.append(limit)
    query = f"""
        SELECT c.id, c.title, c.event_id, c.start_timestamp_ms, c.end_timestamp_ms, c.clip_type
        FROM clips c
        LEFT JOIN events ev ON ev.id = c.event_id
        WHERE {' AND '.join(filters)}
          AND (
            c.event_id IS NULL
            OR {review_clause}
          )
        ORDER BY c.start_timestamp_ms ASC
        LIMIT ?
    """
    rows = db.execute(query, tuple(params)).fetchall()
    return [dict(row) for row in rows]


def _answer_player_stats(db, game_id, player_hint):
    stats = aggregate_stats(db, game_id)
    if not stats:
        return _unknown(
            "No reviewed stats are available for this game yet.",
            intent="player_stats",
        )

    if player_hint:
        row = _find_player_stat(stats, player_hint)
        if row is None:
            return _unknown(
                f"No reviewed stats found for player matching '{player_hint}'.",
                intent="player_stats",
            )
        answer = (
            f"{row['player']} has {row['pts']} points on {row['fgm']}/{row['fga']} FG, "
            f"{row['ast']} assists, {row['reb']} rebounds, and {row['tov']} turnovers "
            f"(reviewed events only)."
        )
        return _response(
            answer,
            "proven",
            "player_stats",
            [_stat_citation(row, game_id)],
        )

    top = max(stats, key=lambda row: row.get("pts", 0))
    if top.get("pts", 0) <= 0:
        return _unknown(
            "Reviewed events exist but no scoring stats were recorded yet.",
            intent="player_stats",
            citations=[_stat_citation(row, game_id) for row in stats[:5]],
        )

    answer = (
        f"{top['player']} leads scoring with {top['pts']} points "
        f"({top['fgm']}/{top['fga']} FG) from reviewed events."
    )
    return _response(
        answer,
        "proven",
        "player_stats",
        [_stat_citation(top, game_id)],
    )


def _answer_team_stats(db, game_id):
    team = get_team_stats(db, game_id)
    if not any(team.values()):
        return _unknown("No reviewed team stats are available for this game yet.", intent="team_stats")

    answer = (
        f"Team totals from reviewed events: {team['points']} points, "
        f"{team['rebounds']} rebounds, {team['assists']} assists, "
        f"{team['turnovers']} turnovers."
    )
    citation = {"type": "team_stat", "game_id": game_id, **team}
    return _response(answer, "proven", "team_stats", [citation])


def _answer_four_factors(db, game_id):
    factors = get_four_factors(db, game_id)
    if not any(factors.values()):
        return _unknown(
            "Not enough reviewed events to compute Four Factors for this game.",
            intent="four_factors",
        )
    answer = (
        "Four Factors from reviewed events: "
        f"eFG% {factors['efg_pct']:.1%}, TOV% {factors['tov_pct']:.1%}, "
        f"ORB% {factors['orb_pct']:.1%}, FT rate {factors['ft_rate']:.1%}."
    )
    citation = {"type": "four_factors", "game_id": game_id, **factors}
    return _response(answer, "proven", "four_factors", [citation])


def _answer_minutes(db, game_id, player_hint):
    enhanced = get_enhanced_stats(db, game_id)
    minutes_rows = enhanced.get("minutes") or []
    if not minutes_rows:
        return _unknown("No player minutes are recorded for this game yet.", intent="minutes")

    if player_hint:
        matched = [
            row
            for row in minutes_rows
            if _match_player_name(row.get("name") or row.get("jersey_number"), player_hint)
        ]
        if not matched:
            return _unknown(
                f"No minutes found for player matching '{player_hint}'.",
                intent="minutes",
            )
        row = matched[0]
        label = row.get("name") or f"#{row.get('jersey_number')}"
        answer = f"{label} played {row['minutes_played']:.1f} minutes."
        citation = {
            "type": "minutes",
            "game_id": game_id,
            "tracker_id": row.get("tracker_id"),
            "player": label,
            "minutes_played": row.get("minutes_played"),
        }
        return _response(answer, "proven", "minutes", [citation])

    top = max(minutes_rows, key=lambda row: row.get("minutes_played") or 0)
    label = top.get("name") or f"#{top.get('jersey_number')}"
    answer = f"{label} played the most minutes ({top['minutes_played']:.1f})."
    citation = {
        "type": "minutes",
        "game_id": game_id,
        "tracker_id": top.get("tracker_id"),
        "player": label,
        "minutes_played": top.get("minutes_played"),
    }
    return _response(answer, "proven", "minutes", [citation])


def _answer_turnovers(db, game_id, player_hint):
    events = _trusted_events_for_game(
        db,
        game_id,
        player_hint=player_hint,
        event_codes=["turnover"],
        limit=50,
    )
    count = len(events)
    if count == 0:
        scope = f" for {player_hint}" if player_hint else ""
        return _unknown(
            f"No reviewed turnovers found{scope} in this game.",
            intent="turnovers",
        )

    if player_hint:
        answer = f"{player_hint} has {count} reviewed turnover(s) in this game."
    else:
        answer = f"The team has {count} reviewed turnover(s) in this game."
    citations = [_event_citation(row) for row in events[:10]]
    return _response(answer, "proven", "turnovers", citations)


def _answer_clips(db, game_id, player_hint):
    clips = _trusted_clips_for_game(db, game_id, player_hint=player_hint, limit=10)
    if not clips:
        return _unknown(
            "No clips linked to reviewed events were found for this game.",
            intent="clips",
        )

    answer = f"Found {len(clips)} clip(s) tied to reviewed events."
    if player_hint:
        answer = f"Found {len(clips)} clip(s) for players matching '{player_hint}'."
    citations = [_clip_citation(row) for row in clips]
    return _response(answer, "proven", "clips", citations)


def answer_question(db, question, game_id=None, player=None):
    """Return a structured assistant answer with citations from trusted data only."""
    intent = _detect_intent(question)
    if intent == "empty":
        return _unknown("Ask a question about reviewed stats, events, or clips.")

    if game_id is None:
        return _unknown("Provide game_id to query reviewed game data.", intent=intent)

    relational_game_id = _resolve_relational_game_id(db, game_id)
    if relational_game_id is None and not db.execute(
        "SELECT 1 FROM events WHERE game_id=? LIMIT 1", (str(game_id),)
    ).fetchone():
        return _unknown(f"Game '{game_id}' was not found.", intent=intent)

    player_hint = _extract_player_hint(question, player)

    if intent == "clips":
        return _answer_clips(db, game_id, player_hint)
    if intent == "minutes":
        return _answer_minutes(db, game_id, player_hint)
    if intent == "four_factors":
        return _answer_four_factors(db, game_id)
    if intent == "turnovers":
        return _answer_turnovers(db, game_id, player_hint)
    if intent == "team_stats":
        return _answer_team_stats(db, game_id)
    if intent == "player_stats":
        return _answer_player_stats(db, game_id, player_hint)

    stats = aggregate_stats(db, game_id)
    if stats:
        return _answer_player_stats(db, game_id, player_hint)
    return _unknown(
        "I could not match that question to reviewed stats, events, or clips yet. "
        "Try asking about points, turnovers, minutes, team totals, or clips.",
        intent="general",
    )
