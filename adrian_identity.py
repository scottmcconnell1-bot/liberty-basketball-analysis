"""Adrian jersey lookaround: follow a track before/after an event until OCR is clear.

For each accepted ledger event:
  1) Resolve ByteTrack tracker_id near the event (not unstable cluster alone)
  2) Collect jersey OCR votes on that track in a time window around the event
  3) Match unique scorebook jersey → name + Home/Away team
  4) Rewrite the event player/details

Adrian-only. Does not change event_type or PTS.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from adrian_quality import (
    ADRIAN_BASE,
    QUALITY_NOTE,
    _details,
    is_adrian_game,
    load_adrian_scorebook,
    resolve_adrian_teams,
)

ROOT = Path(__file__).resolve().parent
LOOKAROUND_NOTE = "adrian_jersey_lookaround_v1"


def scorebook_roster_index(sb: dict[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
    """jersey_str → list of {name, team_side, team_name}."""
    book = sb if sb is not None else load_adrian_scorebook()
    teams = resolve_adrian_teams(book, ADRIAN_BASE)
    home_name = teams.get("home_team") or "Home"
    away_name = teams.get("away_team") or "Away"
    by_jersey: dict[str, list[dict[str, Any]]] = {}
    for p in book.get("players") or []:
        raw = str(p.get("jersey") or "").strip()
        if not raw:
            continue
        jersey = str(int(raw)) if raw.isdigit() else raw
        side = str(p.get("team") or "").strip().lower()
        team_name = home_name if side == "home" else (away_name if side == "away" else side)
        by_jersey.setdefault(jersey, []).append(
            {
                "jersey": jersey,
                "name": (p.get("name") or "").strip() or None,
                "team_side": side or None,
                "team_name": team_name,
            }
        )
    return by_jersey


def _dominant_tracker_near(
    conn: sqlite3.Connection,
    game_id: str,
    player_token: str,
    timestamp_ms: int,
    *,
    near_ms: int = 4_000,
) -> int | None:
    """Map event.player (cluster or track id) → ByteTrack tracker_id at event time."""
    if not str(player_token).strip().isdigit():
        return None
    slot = int(player_token)
    ts = int(timestamp_ms)
    lo, hi = max(0, ts - near_ms), ts + near_ms

    # Prefer exact tracker_id match near the play.
    row = conn.execute(
        """
        SELECT tracker_id, COUNT(*) AS c
          FROM detections
         WHERE game_id = ?
           AND object_class = 'person'
           AND tracker_id = ?
           AND timestamp_ms BETWEEN ? AND ?
         GROUP BY tracker_id
        """,
        (game_id, slot, lo, hi),
    ).fetchone()
    if row and row[0] is not None:
        return int(row[0])

    # Else: event.player was a court cluster — pick dominant tracker in that cluster near ts.
    row = conn.execute(
        """
        SELECT tracker_id, COUNT(*) AS c
          FROM detections
         WHERE game_id = ?
           AND object_class = 'person'
           AND player_cluster = ?
           AND tracker_id IS NOT NULL
           AND timestamp_ms BETWEEN ? AND ?
         GROUP BY tracker_id
         ORDER BY c DESC
         LIMIT 1
        """,
        (game_id, slot, lo, hi),
    ).fetchone()
    if row and row[0] is not None:
        return int(row[0])
    return None


def lookaround_jersey_votes(
    conn: sqlite3.Connection,
    game_id: str,
    tracker_id: int,
    timestamp_ms: int,
    *,
    window_ms: int = 90_000,
    min_confidence: float = 0.50,
) -> list[dict[str, Any]]:
    """Jersey OCR votes on this track before/after the event (expand if sparse)."""
    ts = int(timestamp_ms)
    windows = [window_ms, window_ms * 3, window_ms * 10]

    for win in windows:
        lo, hi = max(0, ts - win), ts + win
        rows = conn.execute(
            """
            SELECT jersey_read AS jersey_number,
                   COUNT(*) AS sample_count,
                   AVG(jersey_confidence) AS avg_confidence,
                   MIN(ABS(timestamp_ms - ?)) AS nearest_ms
              FROM detections
             WHERE game_id = ?
               AND object_class = 'person'
               AND tracker_id = ?
               AND jersey_read IS NOT NULL
               AND jersey_confidence >= ?
               AND timestamp_ms BETWEEN ? AND ?
             GROUP BY jersey_read
             ORDER BY sample_count DESC, avg_confidence DESC, nearest_ms ASC
            """,
            (ts, game_id, tracker_id, min_confidence, lo, hi),
        ).fetchall()
        if rows:
            return [
                {
                    "jersey_number": int(r[0]),
                    "sample_count": int(r[1]),
                    "confidence": round(float(r[2] or 0), 3),
                    "nearest_ms": int(r[3] or 0),
                    "window_ms": win,
                }
                for r in rows
            ]
    return []


def match_scorebook_player(
    jersey: int | str,
    roster_index: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    """Unique scorebook match only — skip jerseys that exist on both teams."""
    key = str(int(jersey)) if str(jersey).isdigit() else str(jersey)
    hits = roster_index.get(key) or []
    if len(hits) == 1:
        return dict(hits[0])
    return None


def _norm_name(text: str) -> str:
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def resolve_label_to_scorebook(
    label: str | None,
    sb: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Map coach correction text (#40, Dayley, Daly, 40 Dayley) → scorebook row.

    Unique jersey or unique normalized name (prefix OK: Daly→Dayley).
    """
    text = str(label or "").strip()
    if not text:
        return None
    book = sb if sb is not None else load_adrian_scorebook()
    roster_index = scorebook_roster_index(book)
    teams = resolve_adrian_teams(book, ADRIAN_BASE)

    # "#40" / "40" / "40 Dayley"
    jersey_match = None
    m = re.match(r"^#?\s*(\d+)\b", text)
    if m:
        jersey_match = match_scorebook_player(m.group(1), roster_index)
        if jersey_match:
            return jersey_match

    # Name-only or "Dayley" / "Daly" / "Hunter Colman"
    needle = _norm_name(re.sub(r"^#?\s*\d+\s*", "", text))
    if not needle:
        return jersey_match

    hits: list[dict[str, Any]] = []
    for entries in roster_index.values():
        for entry in entries:
            name = _norm_name(entry.get("name") or "")
            if not name:
                continue
            if name == needle or name.startswith(needle) or needle.startswith(name):
                hits.append(entry)

    # Dedupe by jersey+side
    uniq = {(h.get("jersey"), h.get("team_side")): h for h in hits}
    hits = list(uniq.values())
    if len(hits) == 1:
        return dict(hits[0])
    # Prefer exact name length closeness
    if len(hits) > 1:
        hits.sort(key=lambda h: abs(len(_norm_name(h.get("name") or "")) - len(needle)))
        # Only auto-pick if top is clearly closer and jersey unique in book
        top = hits[0]
        if match_scorebook_player(top["jersey"], roster_index):
            return dict(top)
    return None


def enrich_details_with_identity(
    details: dict[str, Any],
    identity: dict[str, Any],
    *,
    teams: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stamp jersey/name/team onto event details_json."""
    out = dict(details or {})
    team_info = teams or resolve_adrian_teams()
    out["jersey_number"] = identity.get("jersey")
    out["player_name"] = identity.get("name")
    out["team_side"] = identity.get("team_side")
    out["team_name"] = identity.get("team_name")
    out["player_team"] = identity.get("team_name")
    out["home_team"] = team_info.get("home_team")
    out["away_team"] = team_info.get("away_team")
    out["teams_label"] = team_info.get("label")
    return out


def resolve_event_identity(
    conn: sqlite3.Connection,
    game_id: str,
    event: dict[str, Any],
    roster_index: dict[str, list[dict[str, Any]]],
    *,
    min_samples: int = 2,
    min_confidence: float = 0.50,
) -> dict[str, Any] | None:
    """Follow the player around the event until jersey OCR is usable."""
    player = str(event.get("player") or "").strip()
    ts = int(event.get("timestamp_ms") or 0)
    tracker_id = _dominant_tracker_near(conn, game_id, player, ts)
    if tracker_id is None:
        return None
    votes = lookaround_jersey_votes(
        conn, game_id, tracker_id, ts, min_confidence=min_confidence
    )
    if not votes:
        return None
    top = votes[0]
    if int(top["sample_count"]) < min_samples:
        return None
    matched = match_scorebook_player(top["jersey_number"], roster_index)
    if not matched:
        return {
            "status": "ambiguous_or_unknown_jersey",
            "tracker_id": tracker_id,
            "jersey_number": top["jersey_number"],
            "sample_count": top["sample_count"],
            "confidence": top["confidence"],
            "nearest_ms": top["nearest_ms"],
            "alternates": votes[1:3],
        }
    return {
        "status": "matched",
        "tracker_id": tracker_id,
        "jersey_number": matched["jersey"],
        "player_name": matched.get("name"),
        "team_side": matched.get("team_side"),
        "team_name": matched.get("team_name"),
        "sample_count": top["sample_count"],
        "confidence": top["confidence"],
        "nearest_ms": top["nearest_ms"],
        "window_ms": top["window_ms"],
        "alternates": votes[1:3],
    }


def apply_lookaround_to_accepted(
    conn: sqlite3.Connection,
    game_id: str = ADRIAN_BASE,
    *,
    commit: bool = True,
) -> dict[str, Any]:
    """Rewrite accepted Adrian events with lookaround jersey/name/team when unique."""
    if not is_adrian_game(game_id):
        raise ValueError(f"Refusing non-Adrian game_id: {game_id}")

    sb = load_adrian_scorebook()
    teams = resolve_adrian_teams(sb, game_id)
    roster_index = scorebook_roster_index(sb)

    rows = conn.execute(
        """
        SELECT id, player, event_type, timestamp_ms, details_json, review_notes
          FROM events
         WHERE game_id = ?
           AND review_status IN ('accepted', 'corrected')
         ORDER BY timestamp_ms ASC, id ASC
        """,
        (ADRIAN_BASE,),
    ).fetchall()

    matched = 0
    ambiguous = 0
    unresolved = 0
    skipped = 0

    for row in rows:
        event = {
            "id": row[0],
            "player": row[1],
            "event_type": row[2],
            "timestamp_ms": row[3],
            "details_json": row[4],
        }
        notes = row[5] or ""
        if "Corrected in Film Tool" in notes:
            skipped += 1
            continue

        result = resolve_event_identity(conn, ADRIAN_BASE, event, roster_index)
        if result is None:
            unresolved += 1
            continue
        if result.get("status") != "matched":
            ambiguous += 1
            details = _details(event)
            details["identity_lookaround"] = result
            details["home_team"] = teams.get("home_team")
            details["away_team"] = teams.get("away_team")
            details["teams_label"] = teams.get("label")
            conn.execute(
                """UPDATE events SET details_json=?, review_notes=? WHERE id=?""",
                (
                    json.dumps(details),
                    f"{LOOKAROUND_NOTE}:ambiguous",
                    event["id"],
                ),
            )
            continue

        details = _details(event)
        details["jersey_number"] = result["jersey_number"]
        details["player_name"] = result.get("player_name")
        details["team_side"] = result.get("team_side")
        details["team_name"] = result.get("team_name")
        details["player_team"] = result.get("team_name")
        details["home_team"] = teams.get("home_team")
        details["away_team"] = teams.get("away_team")
        details["teams_label"] = teams.get("label")
        details["identity_method"] = LOOKAROUND_NOTE
        details["identity_lookaround"] = {
            "tracker_id": result["tracker_id"],
            "sample_count": result["sample_count"],
            "confidence": result["confidence"],
            "nearest_ms": result["nearest_ms"],
            "window_ms": result["window_ms"],
        }
        details["adrian_quality"] = details.get("adrian_quality") or QUALITY_NOTE

        # Store jersey as player so box/exceptions can align; name lives in details.
        new_player = str(result["jersey_number"])
        conn.execute(
            """
            UPDATE events
               SET player=?,
                   details_json=?,
                   review_notes=?
             WHERE id=?
            """,
            (
                new_player,
                json.dumps(details),
                f"{LOOKAROUND_NOTE}:matched",
                event["id"],
            ),
        )
        matched += 1

    if commit:
        conn.commit()

    return {
        "ok": True,
        "game_id": ADRIAN_BASE,
        "accepted_rows": len(rows),
        "matched": matched,
        "ambiguous": ambiguous,
        "unresolved": unresolved,
        "skipped_corrected": skipped,
        "game_teams": teams,
        "method": LOOKAROUND_NOTE,
    }
