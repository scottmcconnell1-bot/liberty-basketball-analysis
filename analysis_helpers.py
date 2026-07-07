"""Helpers for Analysis Results: roster context, event drill-down, period inference."""

from __future__ import annotations

from film_roster import list_film_roster_players

STAT_EVENT_TYPES = {
    "reb": ("rebound",),
    "ast": ("assist",),
    "stl": ("steal",),
    "blk": ("block",),
    "tov": ("turnover",),
    "pf": ("foul",),
    "foul": ("foul",),
    "pts": ("make", "made_two", "made_three", "made_free_throw", "shot"),
    "fgm": ("make", "made_two", "made_three", "made_free_throw"),
    "fga": ("shot", "make", "miss", "made_two", "made_three", "missed_two", "missed_three"),
}


def _normalize_film_level(level: str | None) -> str:
    value = (level or "varsity").strip().lower().replace("-", "_")
    if value in {"jr_high", "junior_high", "jrhigh"}:
        return "jrhigh"
    if value in {"jv", "varsity"}:
        return value
    return "varsity"


def _resolve_relational_game_id(db, game_id):
    from stats import _resolve_relational_game_id

    return _resolve_relational_game_id(db, game_id)


def resolve_analysis_game_context(db, game_id):
    """Resolve season, level, gender, opponent, and video metadata for an analysis key."""
    from helpers import resolve_analysis_run_for_progress

    row = resolve_analysis_run_for_progress(db, game_id)
    analysis_key = row["analysis_key"] if row and row["analysis_key"] else str(game_id)
    relational_game_id = _resolve_relational_game_id(db, analysis_key)

    context = {
        "analysis_key": analysis_key,
        "relational_game_id": relational_game_id,
        "season_id": None,
        "level": "varsity",
        "gender": "boys",
        "side": "our",
        "opponent_name": None,
        "stored_filename": None,
        "video_id": None,
        "our_team_id": None,
        "our_team_name": "Our team",
        "opponent_team_name": "Opponent",
    }

    if relational_game_id is not None:
        game_row = db.execute(
            """
            SELECT g.id, sg.season_id, sg.level, sg.gender, sg.opponent_name, sg.program_name
              FROM games g
              LEFT JOIN scheduled_games sg ON sg.id = g.scheduled_game_id
             WHERE g.id = ?
            """,
            (relational_game_id,),
        ).fetchone()
        if game_row:
            if game_row["season_id"]:
                context["season_id"] = game_row["season_id"]
            if game_row["level"]:
                context["level"] = _normalize_film_level(game_row["level"])
            if game_row["gender"]:
                context["gender"] = str(game_row["gender"]).lower()
            context["opponent_name"] = game_row["opponent_name"]
            if game_row["opponent_name"]:
                context["opponent_team_name"] = game_row["opponent_name"]
            if game_row["program_name"]:
                context["our_team_name"] = game_row["program_name"]

    video_row = db.execute(
        """
        SELECT v.id, v.stored_filename, v.opponent
          FROM videos v
          LEFT JOIN analysis_runs ar
            ON ar.source_video_id = v.id
            OR ar.analysis_key = v.game_id
            OR ar.base_analysis_key = v.game_id
            OR ar.video_path = v.file_path
         WHERE v.game_id = ?
            OR ar.analysis_key = ?
         ORDER BY v.id DESC
         LIMIT 1
        """,
        (analysis_key, analysis_key),
    ).fetchone()
    if video_row:
        context["video_id"] = video_row["id"]
        context["stored_filename"] = video_row["stored_filename"]
        if not context["opponent_name"] and video_row["opponent"]:
            context["opponent_name"] = video_row["opponent"]
            context["opponent_team_name"] = video_row["opponent"]

    team_row = db.execute(
        """
        SELECT id, team_name
          FROM teams
         WHERE lower(program_name) LIKE '%liberty%'
            OR lower(team_name) LIKE '%liberty%'
         ORDER BY id ASC
         LIMIT 1
        """
    ).fetchone()
    if team_row:
        context["our_team_id"] = team_row["id"]
        context["our_team_name"] = team_row["team_name"] or context["our_team_name"]

    return context


def lookup_film_roster_player(db, game_id, *, jersey_number=None, player_name=None):
    """Resolve a jersey or name against the game's Film Tool roster."""
    try:
        jersey_int = int(jersey_number) if jersey_number is not None else None
    except (TypeError, ValueError):
        jersey_int = None

    payload = get_analysis_roster_players(db, game_id)
    name_query = (player_name or "").strip().lower()
    for player in payload["players"]:
        player_jersey = player.get("jersey_number")
        try:
            player_jersey = int(player_jersey) if player_jersey is not None else None
        except (TypeError, ValueError):
            player_jersey = None
        player_name_value = (player.get("name") or player.get("label") or "").strip()
        if jersey_int is not None and player_jersey == jersey_int:
            return {
                "player_id": None,
                "name": player_name_value or None,
                "jersey_number": player_jersey,
                "roster_membership_id": None,
                "team_id": None,
            }
        if name_query and player_name_value.lower() == name_query:
            return {
                "player_id": None,
                "name": player_name_value,
                "jersey_number": player_jersey,
                "roster_membership_id": None,
                "team_id": None,
            }
    return None


def get_analysis_roster_players(db, game_id):
    """Return roster players for court-slot mapping, preferring Film Tool rosters."""
    context = resolve_analysis_game_context(db, game_id)
    players = []
    source = "empty"

    if context["season_id"]:
        try:
            film_players = list_film_roster_players(
                db,
                season_id=context["season_id"],
                level=context["level"],
                gender=context["gender"],
                side=context["side"],
            )
        except ValueError:
            film_players = []
        if film_players:
            source = "film_roster"
            for index, player in enumerate(film_players):
                jersey = player.get("jersey_number")
                name = (player.get("name") or "").strip()
                label = player.get("label") or player.get("player_label") or ""
                players.append({
                    "id": None,
                    "jersey_number": int(jersey) if jersey not in (None, "") else None,
                    "name": name or label,
                    "label": label,
                    "position": player.get("position"),
                    "grade": player.get("grade"),
                    "sort_order": index,
                })

    if not players:
        rows = db.execute(
            """
            SELECT p.id, p.name, p.jersey_number, p.position, p.grade
              FROM players p
             ORDER BY p.jersey_number ASC, p.name ASC
            """
        ).fetchall()
        if rows:
            source = "global_players"
            players = [dict(row) for row in rows]

    return {
        "players": players,
        "source": source,
        "roster_context": {
            "season_id": context["season_id"],
            "level": context["level"],
            "gender": context["gender"],
            "side": context["side"],
            "opponent_name": context["opponent_name"],
        },
    }


def resolve_video_duration_ms(db, game_id, relational_game_id=None, analysis_key=None):
    relational_game_id = relational_game_id or _resolve_relational_game_id(db, game_id)
    analysis_key = analysis_key or str(game_id)
    duration_ms = 0

    if relational_game_id is not None:
        row = db.execute(
            """
            SELECT MAX(timestamp_ms) AS max_ts
              FROM events
             WHERE relational_game_id = ?
                OR (relational_game_id IS NULL AND game_id = ?)
            """,
            (relational_game_id, analysis_key),
        ).fetchone()
        duration_ms = max(duration_ms, row["max_ts"] or 0)
        row = db.execute(
            """
            SELECT MAX(timestamp_ms) AS max_ts
              FROM detections
             WHERE relational_game_id = ?
                OR (relational_game_id IS NULL AND game_id = ?)
            """,
            (relational_game_id, analysis_key),
        ).fetchone()
        duration_ms = max(duration_ms, row["max_ts"] or 0)
    else:
        row = db.execute(
            "SELECT MAX(timestamp_ms) AS max_ts FROM events WHERE game_id = ?",
            (analysis_key,),
        ).fetchone()
        duration_ms = max(duration_ms, row["max_ts"] or 0)

    return max(duration_ms, 1)


def infer_period_labels(timestamp_ms, duration_ms):
    """Infer quarter (1-4, 5=OT) and half (1-2) from timestamp and video duration."""
    ts = max(0, int(timestamp_ms or 0))
    duration = max(1, int(duration_ms or 1))
    quarter_len = duration / 4.0
    quarter_index = int(ts / quarter_len)
    if quarter_index >= 4:
        quarter = 4 if ts <= duration else 5
    else:
        quarter = quarter_index + 1
    half = 1 if ts < (duration / 2.0) else 2
    return {
        "quarter": quarter,
        "half": half,
        "quarter_label": f"Q{quarter}" if quarter <= 4 else "OT",
        "half_label": "1st half" if half == 1 else "2nd half",
    }


def _parse_event_types(event_type=None, stat=None):
    types = []
    if stat:
        key = str(stat).strip().lower()
        types.extend(STAT_EVENT_TYPES.get(key, (key,)))
    if event_type:
        for part in str(event_type).split(","):
            value = part.strip().lower()
            if value:
                types.append(value)
    deduped = []
    seen = set()
    for value in types:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def _player_matches_filter(player_value, player_filter, tracker_filter):
    if tracker_filter is not None and str(player_value or "") == str(tracker_filter):
        return True
    if not player_filter:
        return True
    player_text = str(player_value or "")
    if player_text == player_filter:
        return True
    if player_filter.startswith("Pos ") and player_text == player_filter.replace("Pos ", "", 1):
        return True
    return player_filter.lower() in player_text.lower()


def _event_matches_team(event, team_filter, our_team_id, our_player_labels):
    if not team_filter or team_filter == "all":
        return True

    team_id = event.get("team_id")
    player = str(event.get("player") or "")

    if team_filter == "our":
        if our_team_id is not None and team_id == our_team_id:
            return True
        if team_id is None and our_player_labels:
            return any(label and label.lower() in player.lower() for label in our_player_labels)
        return team_id is None
    if team_filter == "opp":
        if our_team_id is not None and team_id is not None and team_id != our_team_id:
            return True
        if our_player_labels and player:
            return not any(label and label.lower() in player.lower() for label in our_player_labels)
        return team_id is not None and team_id != our_team_id
    if str(team_filter).isdigit():
        return team_id == int(team_filter)
    return True


def list_analysis_events(
    db,
    game_id,
    *,
    event_type=None,
    stat=None,
    player=None,
    tracker_id=None,
    team=None,
    quarter=None,
    half=None,
    limit=500,
):
    """Return filtered AI/manual events with period labels and film seek metadata."""
    from helpers import resolve_analysis_run_for_progress

    row = resolve_analysis_run_for_progress(db, game_id)
    analysis_key = row["analysis_key"] if row and row["analysis_key"] else str(game_id)
    relational_game_id = _resolve_relational_game_id(db, analysis_key)
    context = resolve_analysis_game_context(db, analysis_key)
    duration_ms = resolve_video_duration_ms(
        db, analysis_key, relational_game_id=relational_game_id, analysis_key=analysis_key
    )

    roster_payload = get_analysis_roster_players(db, analysis_key)
    our_player_labels = []
    for roster_player in roster_payload["players"]:
        jersey = roster_player.get("jersey_number")
        name = roster_player.get("name") or ""
        label = roster_player.get("label") or ""
        if jersey is not None:
            our_player_labels.append(f"#{jersey}")
        if name:
            our_player_labels.append(name)
        if label:
            our_player_labels.append(label)

    event_types = _parse_event_types(event_type=event_type, stat=stat)
    if relational_game_id is not None:
        rows = db.execute(
            """
            SELECT e.id, e.player, e.event_type, e.shot_result, e.timestamp_ms,
                   e.details_json, e.team_id, e.review_status, e.source_type,
                   t.team_name
              FROM events e
              LEFT JOIN teams t ON t.id = e.team_id
             WHERE e.relational_game_id = ?
                OR (e.relational_game_id IS NULL AND e.game_id = ?)
             ORDER BY e.timestamp_ms ASC
            """,
            (relational_game_id, analysis_key),
        ).fetchall()
    else:
        rows = db.execute(
            """
            SELECT e.id, e.player, e.event_type, e.shot_result, e.timestamp_ms,
                   e.details_json, e.team_id, e.review_status, e.source_type,
                   t.team_name
              FROM events e
              LEFT JOIN teams t ON t.id = e.team_id
             WHERE e.game_id = ?
             ORDER BY e.timestamp_ms ASC
            """,
            (analysis_key,),
        ).fetchall()

    quarter_filter = int(quarter) if quarter not in (None, "", "all") else None
    half_filter = int(half) if half not in (None, "", "all") else None
    team_filter = (team or "all").strip().lower()
    tracker_filter = str(tracker_id) if tracker_id not in (None, "") else None
    player_filter = (player or "").strip() or None
    safe_limit = max(1, min(int(limit or 500), 2000))

    events = []
    for row in rows:
        payload = dict(row)
        et = (payload.get("event_type") or "").lower()
        shot_result = (payload.get("shot_result") or "").lower()

        if event_types:
            matched = et in event_types
            if not matched and stat in {"pts", "fgm"} and et == "shot":
                if stat == "pts" and shot_result in ("make", "made"):
                    matched = True
                elif stat == "fgm" and shot_result in ("make", "made"):
                    matched = True
            if not matched:
                continue

        if stat == "pts":
            scoring = et in {"make", "made_two", "made_three", "made_free_throw"}
            if et == "shot" and shot_result not in ("make", "made"):
                continue
            if not scoring and et != "shot":
                continue
        if stat == "fgm":
            made = et in {"make", "made_two", "made_three", "made_free_throw"}
            if et == "shot" and shot_result not in ("make", "made"):
                continue
            if not made and et != "shot":
                continue

        if not _player_matches_filter(payload.get("player"), player_filter, tracker_filter):
            continue
        if not _event_matches_team(payload, team_filter, context["our_team_id"], our_player_labels):
            continue

        period = infer_period_labels(payload["timestamp_ms"], duration_ms)
        payload.update(period)
        if quarter_filter is not None and payload["quarter"] != quarter_filter:
            continue
        if half_filter is not None and payload["half"] != half_filter:
            continue
        events.append(payload)
        if len(events) >= safe_limit:
            break

    return {
        "game_id": analysis_key,
        "count": len(events),
        "duration_ms": duration_ms,
        "stored_filename": context["stored_filename"],
        "video_id": context["video_id"],
        "teams": {
            "our_team_id": context["our_team_id"],
            "our_team_name": context["our_team_name"],
            "opponent_team_name": context["opponent_team_name"],
        },
        "events": events,
    }
