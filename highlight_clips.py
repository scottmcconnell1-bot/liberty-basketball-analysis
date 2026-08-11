"""Highlight clip generation from the reviewed event ledger.

Source of truth: events with review_status IN ('accepted', 'corrected').
Does not auto-accept pending AI drafts.
"""

from __future__ import annotations

from urllib.parse import quote, urlencode

from stats import (
    TRUSTED_REVIEW_STATUSES,
    _resolve_relational_game_id,
    _trusted_event_review_clause,
)

DEFAULT_PAD_BEFORE_MS = 3000
DEFAULT_PAD_AFTER_MS = 5000
REVIEW_SCOPE = "accepted_and_corrected_only"


def _game_label(row: dict) -> str:
    opponent = row.get("opponent_name")
    source_key = row.get("source_key")
    game_date = row.get("game_date")
    parts = [f"Game #{row['id']}"]
    if opponent:
        parts.append(f"vs {opponent}")
    elif source_key:
        parts.append(source_key)
    if game_date:
        parts.append(str(game_date))
    return " — ".join(parts)


def resolve_video_for_game(db, game_id) -> dict | None:
    """Best-effort video row for a relational or analysis game id."""
    game_key = str(game_id)
    relational_game_id = _resolve_relational_game_id(db, game_id)

    row = db.execute(
        """SELECT v.*
             FROM videos v
             LEFT JOIN analysis_runs ar
               ON ar.source_video_id = v.id
               OR ar.analysis_key = v.game_id
               OR ar.base_analysis_key = v.game_id
               OR ar.video_path = v.file_path
            WHERE v.game_id = ?
               OR ar.analysis_key = ?
               OR (? IS NOT NULL AND v.relational_game_id = ?)
            ORDER BY v.id DESC
            LIMIT 1""",
        (game_key, game_key, relational_game_id, relational_game_id),
    ).fetchone()
    return dict(row) if row else None


def build_seek_url(stored_filename: str | None, game_id, timestamp_ms: int) -> str | None:
    if not stored_filename:
        return None
    query = urlencode({"game_id": str(game_id), "t": int(timestamp_ms)})
    return f"/film/{quote(stored_filename, safe='')}?{query}"


def clip_window_ms(
    timestamp_ms: int,
    *,
    pad_before_ms: int = DEFAULT_PAD_BEFORE_MS,
    pad_after_ms: int = DEFAULT_PAD_AFTER_MS,
) -> tuple[int, int]:
    start_ms = max(0, int(timestamp_ms) - int(pad_before_ms))
    end_ms = int(timestamp_ms) + int(pad_after_ms)
    if end_ms <= start_ms:
        end_ms = start_ms + 1000
    return start_ms, end_ms


def _jersey_match_clause(jersey: str) -> tuple[str, list]:
    """Match jersey stored as bare number or inside a player label."""
    raw = (jersey or "").strip()
    if not raw:
        return "", []
    # Exact player label, bare number, or digit token inside the label.
    return (
        "("
        "TRIM(COALESCE(e.player, '')) = ? OR "
        "LOWER(TRIM(COALESCE(e.player, ''))) = LOWER(?) OR "
        "e.player GLOB ? OR "
        "e.player LIKE ? OR "
        "e.player LIKE ? OR "
        "e.player LIKE ?"
        ")",
        [
            raw,
            raw,
            f"*[!0-9]{raw}",
            f"{raw} %",
            f"% {raw}",
            f"% {raw} %",
        ],
    )


def list_highlight_games(db, limit: int = 100) -> list[dict]:
    review_clause = _trusted_event_review_clause("e.review_status")
    rows = db.execute(
        f"""
        SELECT g.id,
               g.source_key,
               sg.opponent_name,
               sg.game_date,
               (
                   SELECT COUNT(*)
                     FROM events e
                    WHERE e.relational_game_id = g.id
                      AND {review_clause}
               ) AS reviewed_event_count
          FROM games g
          LEFT JOIN scheduled_games sg ON sg.id = g.scheduled_game_id
         ORDER BY g.id DESC
         LIMIT ?
        """,
        (limit,),
    ).fetchall()
    games = []
    for row in rows:
        payload = dict(row)
        payload["label"] = _game_label(payload)
        games.append(payload)
    return games


def list_highlight_moments(
    db,
    game_id,
    *,
    jersey: str | None = None,
    player: str | None = None,
    event_type: str | None = None,
    pad_before_ms: int = DEFAULT_PAD_BEFORE_MS,
    pad_after_ms: int = DEFAULT_PAD_AFTER_MS,
    limit: int = 500,
) -> dict:
    """List reviewed ledger moments for a game, with clip windows and seek links."""
    relational_game_id = _resolve_relational_game_id(db, game_id)
    review_clause = _trusted_event_review_clause("e.review_status")
    params: list = []
    filters = [review_clause]

    if relational_game_id is not None:
        filters.append("e.relational_game_id = ?")
        params.append(relational_game_id)
    else:
        filters.append("e.game_id = ?")
        params.append(str(game_id))

    jersey_clause, jersey_params = _jersey_match_clause(jersey or "")
    if jersey_clause:
        filters.append(jersey_clause)
        params.extend(jersey_params)

    player_hint = (player or "").strip()
    if player_hint:
        filters.append("LOWER(COALESCE(e.player, '')) LIKE ?")
        params.append(f"%{player_hint.lower()}%")

    event_type_hint = (event_type or "").strip()
    if event_type_hint:
        filters.append("LOWER(e.event_type) = LOWER(?)")
        params.append(event_type_hint)

    count_row = db.execute(
        f"SELECT COUNT(*) AS c FROM events e WHERE {' AND '.join(filters)}",
        params,
    ).fetchone()
    reviewed_count = int(count_row["c"] if count_row else 0)

    # Distinct filter options from all reviewed events for this game (pre-filter).
    option_filters = [review_clause]
    option_params: list = []
    if relational_game_id is not None:
        option_filters.append("e.relational_game_id = ?")
        option_params.append(relational_game_id)
    else:
        option_filters.append("e.game_id = ?")
        option_params.append(str(game_id))

    player_rows = db.execute(
        f"""SELECT DISTINCT e.player
              FROM events e
             WHERE {' AND '.join(option_filters)}
               AND e.player IS NOT NULL AND TRIM(e.player) != ''
             ORDER BY e.player""",
        option_params,
    ).fetchall()
    type_rows = db.execute(
        f"""SELECT DISTINCT e.event_type
              FROM events e
             WHERE {' AND '.join(option_filters)}
               AND e.event_type IS NOT NULL AND TRIM(e.event_type) != ''
             ORDER BY e.event_type""",
        option_params,
    ).fetchall()

    video = resolve_video_for_game(db, game_id)
    stored_filename = video["stored_filename"] if video else None
    analysis_key = None
    if video:
        analysis_key = video.get("game_id")
    seek_game_id = analysis_key or str(game_id)

    params_limited = list(params)
    params_limited.append(limit)
    rows = db.execute(
        f"""SELECT e.id, e.game_id, e.relational_game_id, e.player, e.event_type,
                  e.shot_result, e.timestamp_ms, e.review_status, e.human_verified,
                  e.confidence, e.source_type
             FROM events e
            WHERE {' AND '.join(filters)}
            ORDER BY e.timestamp_ms ASC, e.id ASC
            LIMIT ?""",
        params_limited,
    ).fetchall()

    moments = []
    for row in rows:
        item = dict(row)
        start_ms, end_ms = clip_window_ms(
            item["timestamp_ms"] or 0,
            pad_before_ms=pad_before_ms,
            pad_after_ms=pad_after_ms,
        )
        item["clip_start_ms"] = start_ms
        item["clip_end_ms"] = end_ms
        item["seek_url"] = build_seek_url(stored_filename, seek_game_id, item["timestamp_ms"] or 0)
        item["clip_label"] = _moment_label(item)
        moments.append(item)

    return {
        "game_id": int(relational_game_id) if relational_game_id is not None else game_id,
        "review_scope": REVIEW_SCOPE,
        "trusted_review_statuses": list(TRUSTED_REVIEW_STATUSES),
        "reviewed_event_count": reviewed_count,
        "filters": {
            "jersey": (jersey or "").strip() or None,
            "player": player_hint or None,
            "event_type": event_type_hint or None,
            "pad_before_ms": pad_before_ms,
            "pad_after_ms": pad_after_ms,
        },
        "filter_options": {
            "players": [r["player"] for r in player_rows],
            "event_types": [r["event_type"] for r in type_rows],
        },
        "video": (
            {
                "id": video["id"],
                "stored_filename": video["stored_filename"],
                "original_filename": video.get("original_filename"),
                "game_id": video.get("game_id"),
            }
            if video
            else None
        ),
        "moments": moments,
        "empty_reason": (
            "no_reviewed_events"
            if reviewed_count == 0
            else ("no_matches" if not moments else None)
        ),
    }


def _moment_label(moment: dict) -> str:
    player = (moment.get("player") or "Unknown").strip() or "Unknown"
    event_type = (moment.get("event_type") or "event").strip() or "event"
    shot = (moment.get("shot_result") or "").strip()
    if shot:
        return f"{player} — {event_type} ({shot})"
    return f"{player} — {event_type}"


def generate_highlight_clips(
    db,
    game_id,
    event_ids: list[int],
    *,
    pad_before_ms: int = DEFAULT_PAD_BEFORE_MS,
    pad_after_ms: int = DEFAULT_PAD_AFTER_MS,
    save_clips: bool = True,
    cut_video: bool = True,
    app=None,
) -> dict:
    """Save clip ledger rows and optionally start ffmpeg trim jobs."""
    import player_development as pd_helpers
    from video_trim import ffmpeg_available, start_trim_job

    if not event_ids:
        return {"error": "event_ids required", "status": 400}

    parsed_ids = []
    invalid_ids = []
    for eid in event_ids:
        try:
            parsed_ids.append(int(eid))
        except (TypeError, ValueError):
            invalid_ids.append(eid)

    video = resolve_video_for_game(db, game_id)
    selected, missing = _fetch_trusted_moments_by_ids(
        db,
        game_id,
        parsed_ids,
        pad_before_ms=pad_before_ms,
        pad_after_ms=pad_after_ms,
        video=video,
    )
    missing = invalid_ids + missing

    relational_game_id = _resolve_relational_game_id(db, game_id)
    ffmpeg_ok = ffmpeg_available()
    clip_rows = []
    trim_jobs = []
    export_list = []

    for moment in selected:
        start_ms = moment["clip_start_ms"]
        end_ms = moment["clip_end_ms"]
        label = moment["clip_label"]
        export_item = {
            "event_id": moment["id"],
            "player": moment.get("player"),
            "event_type": moment.get("event_type"),
            "timestamp_ms": moment.get("timestamp_ms"),
            "clip_start_ms": start_ms,
            "clip_end_ms": end_ms,
            "clip_label": label,
            "seek_url": moment.get("seek_url"),
            "review_status": moment.get("review_status"),
        }

        saved = None
        if save_clips:
            saved = pd_helpers.create_clip(
                db,
                clip_label=label,
                clip_start_ms=start_ms,
                clip_end_ms=end_ms,
                game_id=str(game_id),
                event_id=moment["id"],
                clip_category="highlight",
                notes=f"highlight from reviewed event #{moment['id']}",
                auto_link_canonical=True,
                canonical_clip_type="highlight",
            )
            clip_rows.append(saved)
            export_item["development_clip_id"] = saved.get("id")
            export_item["canonical_clip_id"] = saved.get("canonical_clip_id")

        if cut_video and ffmpeg_ok and video and app is not None:
            job_id = start_trim_job(
                app=app,
                video_row=video,
                start_ms=start_ms,
                end_ms=end_ms,
                label=label[:80],
            )
            trim_jobs.append(
                {
                    "event_id": moment["id"],
                    "job_id": job_id,
                    "status_url": f"/api/videos/trim/{job_id}",
                }
            )
            export_item["trim_job_id"] = job_id

        export_list.append(export_item)

    cut_mode = "seek_export"
    if cut_video and ffmpeg_ok and video and trim_jobs:
        cut_mode = "ffmpeg"

    return {
        "game_id": int(relational_game_id) if relational_game_id is not None else game_id,
        "review_scope": REVIEW_SCOPE,
        "ffmpeg_available": ffmpeg_ok,
        "video": (
            {
                "id": video["id"],
                "stored_filename": video["stored_filename"],
                "original_filename": video.get("original_filename"),
                "game_id": video.get("game_id"),
            }
            if video
            else None
        ),
        "saved_clips": clip_rows,
        "trim_jobs": trim_jobs,
        "export": export_list,
        "missing_event_ids": missing,
        "cut_mode": cut_mode,
        "message": _generate_message(
            len(export_list),
            ffmpeg_ok=ffmpeg_ok,
            has_video=bool(video),
            cut_video=cut_video,
            save_clips=save_clips,
        ),
    }


def _fetch_trusted_moments_by_ids(
    db,
    game_id,
    event_ids: list[int],
    *,
    pad_before_ms: int,
    pad_after_ms: int,
    video: dict | None,
) -> tuple[list[dict], list[int]]:
    if not event_ids:
        return [], []
    relational_game_id = _resolve_relational_game_id(db, game_id)
    review_clause = _trusted_event_review_clause("e.review_status")
    placeholders = ", ".join("?" for _ in event_ids)
    params: list = list(event_ids)
    filters = [f"e.id IN ({placeholders})", review_clause]
    if relational_game_id is not None:
        filters.append("e.relational_game_id = ?")
        params.append(relational_game_id)
    else:
        filters.append("e.game_id = ?")
        params.append(str(game_id))

    rows = db.execute(
        f"""SELECT e.id, e.game_id, e.relational_game_id, e.player, e.event_type,
                  e.shot_result, e.timestamp_ms, e.review_status, e.human_verified,
                  e.confidence, e.source_type
             FROM events e
            WHERE {' AND '.join(filters)}
            ORDER BY e.timestamp_ms ASC, e.id ASC""",
        params,
    ).fetchall()
    found_ids = set()
    moments = []
    stored_filename = video["stored_filename"] if video else None
    seek_game_id = (video.get("game_id") if video else None) or str(game_id)
    for row in rows:
        item = dict(row)
        found_ids.add(item["id"])
        start_ms, end_ms = clip_window_ms(
            item["timestamp_ms"] or 0,
            pad_before_ms=pad_before_ms,
            pad_after_ms=pad_after_ms,
        )
        item["clip_start_ms"] = start_ms
        item["clip_end_ms"] = end_ms
        item["seek_url"] = build_seek_url(stored_filename, seek_game_id, item["timestamp_ms"] or 0)
        item["clip_label"] = _moment_label(item)
        moments.append(item)
    missing = [eid for eid in event_ids if eid not in found_ids]
    return moments, missing


def _generate_message(count, *, ffmpeg_ok, has_video, cut_video, save_clips) -> str:
    parts = [f"Prepared {count} highlight moment(s)."]
    if save_clips:
        parts.append("Saved clip ledger rows.")
    if cut_video and ffmpeg_ok and has_video:
        parts.append("Started ffmpeg trim jobs for downloadable segments.")
    elif cut_video and not ffmpeg_ok:
        parts.append("ffmpeg not available — export includes seek links instead.")
    elif cut_video and not has_video:
        parts.append("No linked video found — export includes clip list only.")
    return " ".join(parts)
