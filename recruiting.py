"""Recruiting Station — profile CRUD, share tokens, and stats summaries."""

from __future__ import annotations

import json
import secrets
from typing import Any, Optional


PROFILE_FIELDS = (
    "player_id",
    "display_name",
    "grad_year",
    "position",
    "height",
    "school_program",
    "program_level",
    "contact_email",
    "highlight_url",
    "film_links_json",
    "bio",
    "season_summary",
    "career_summary",
    "is_published",
)

LEVEL_LABELS = {
    "jr_high": "Jr High",
    "jv": "JV",
    "varsity": "Varsity",
}


def generate_share_token() -> str:
    return secrets.token_urlsafe(12)


def _parse_film_links(raw: Any) -> list[dict]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        try:
            items = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            # Plain multiline / comma-separated URLs
            items = [{"url": part.strip(), "label": ""} for part in raw.replace(",", "\n").splitlines() if part.strip()]
    else:
        return []
    out = []
    for item in items:
        if isinstance(item, str):
            url = item.strip()
            if url:
                out.append({"url": url, "label": ""})
            continue
        if isinstance(item, dict):
            url = (item.get("url") or "").strip()
            if not url:
                continue
            out.append({"url": url, "label": (item.get("label") or "").strip()})
    return out


def serialize_film_links(raw: Any) -> str:
    return json.dumps(_parse_film_links(raw))


def row_to_profile(row) -> Optional[dict]:
    if row is None:
        return None
    data = dict(row)
    data["film_links"] = _parse_film_links(data.get("film_links_json"))
    data["program_level_label"] = LEVEL_LABELS.get(data.get("program_level") or "", data.get("program_level") or "")
    data["is_published"] = bool(data.get("is_published"))
    return data


def list_profiles(db, program_level: Optional[str] = None) -> list[dict]:
    clauses = []
    params: list[Any] = []
    if program_level:
        clauses.append("rp.program_level = ?")
        params.append(program_level)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = db.execute(
        f"""SELECT rp.*, p.name AS player_name, p.jersey_number AS player_jersey,
                   p.level AS player_level, p.grade AS player_grade
              FROM recruiting_profiles rp
              LEFT JOIN players p ON p.id = rp.player_id
              {where}
             ORDER BY rp.updated_at DESC, rp.id DESC""",
        params,
    ).fetchall()
    return [row_to_profile(r) for r in rows]


def get_profile(db, profile_id: int) -> Optional[dict]:
    row = db.execute(
        """SELECT rp.*, p.name AS player_name, p.jersey_number AS player_jersey,
                  p.level AS player_level, p.grade AS player_grade,
                  p.position AS player_position, p.program_name AS player_program
             FROM recruiting_profiles rp
             LEFT JOIN players p ON p.id = rp.player_id
            WHERE rp.id = ?""",
        (profile_id,),
    ).fetchone()
    return row_to_profile(row)


def get_profile_by_share_token(db, token: str) -> Optional[dict]:
    if not token:
        return None
    row = db.execute(
        """SELECT rp.*, p.name AS player_name, p.jersey_number AS player_jersey,
                  p.level AS player_level, p.grade AS player_grade,
                  p.position AS player_position, p.program_name AS player_program
             FROM recruiting_profiles rp
             LEFT JOIN players p ON p.id = rp.player_id
            WHERE rp.share_token = ?""",
        (token.strip(),),
    ).fetchone()
    return row_to_profile(row)


def _coerce_int(value, default=None):
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_payload(data: dict) -> dict:
    payload = {}
    payload["player_id"] = _coerce_int(data.get("player_id"))
    payload["display_name"] = (data.get("display_name") or "").strip()
    payload["grad_year"] = _coerce_int(data.get("grad_year"))
    payload["position"] = (data.get("position") or "").strip() or None
    payload["height"] = (data.get("height") or "").strip() or None
    payload["school_program"] = (data.get("school_program") or "Liberty Charter").strip() or "Liberty Charter"
    level = (data.get("program_level") or "").strip() or None
    if level and level not in LEVEL_LABELS:
        level = None
    payload["program_level"] = level
    payload["contact_email"] = (data.get("contact_email") or "").strip() or None
    payload["highlight_url"] = (data.get("highlight_url") or "").strip() or None
    payload["film_links_json"] = serialize_film_links(data.get("film_links", data.get("film_links_json")))
    payload["bio"] = (data.get("bio") or "").strip() or None
    payload["season_summary"] = (data.get("season_summary") or "").strip() or None
    payload["career_summary"] = (data.get("career_summary") or "").strip() or None
    published = data.get("is_published", 0)
    if isinstance(published, str):
        payload["is_published"] = 1 if published.strip().lower() in {"1", "true", "on", "yes"} else 0
    else:
        payload["is_published"] = 1 if published else 0
    return payload


def create_profile(db, data: dict) -> dict:
    payload = _normalize_payload(data)
    if not payload["display_name"]:
        raise ValueError("display_name is required")
    cur = db.execute(
        """INSERT INTO recruiting_profiles
           (player_id, display_name, grad_year, position, height, school_program,
            program_level, contact_email, highlight_url, film_links_json, bio,
            season_summary, career_summary, is_published)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            payload["player_id"],
            payload["display_name"],
            payload["grad_year"],
            payload["position"],
            payload["height"],
            payload["school_program"],
            payload["program_level"],
            payload["contact_email"],
            payload["highlight_url"],
            payload["film_links_json"],
            payload["bio"],
            payload["season_summary"],
            payload["career_summary"],
            payload["is_published"],
        ),
    )
    db.commit()
    return get_profile(db, cur.lastrowid)


def update_profile(db, profile_id: int, data: dict) -> dict:
    existing = get_profile(db, profile_id)
    if not existing:
        raise KeyError("Profile not found")
    merged = {**existing, **data}
    # Prefer explicit film_links from request over stale parsed list
    if "film_links" in data or "film_links_json" in data:
        merged["film_links"] = data.get("film_links", data.get("film_links_json"))
    payload = _normalize_payload(merged)
    if not payload["display_name"]:
        raise ValueError("display_name is required")
    db.execute(
        """UPDATE recruiting_profiles SET
             player_id=?, display_name=?, grad_year=?, position=?, height=?,
             school_program=?, program_level=?, contact_email=?, highlight_url=?,
             film_links_json=?, bio=?, season_summary=?, career_summary=?,
             is_published=?, updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (
            payload["player_id"],
            payload["display_name"],
            payload["grad_year"],
            payload["position"],
            payload["height"],
            payload["school_program"],
            payload["program_level"],
            payload["contact_email"],
            payload["highlight_url"],
            payload["film_links_json"],
            payload["bio"],
            payload["season_summary"],
            payload["career_summary"],
            payload["is_published"],
            profile_id,
        ),
    )
    db.commit()
    return get_profile(db, profile_id)


def delete_profile(db, profile_id: int) -> None:
    db.execute("DELETE FROM recruiting_profiles WHERE id=?", (profile_id,))
    db.commit()


def ensure_share_token(db, profile_id: int) -> str:
    row = db.execute(
        "SELECT id, share_token FROM recruiting_profiles WHERE id=?",
        (profile_id,),
    ).fetchone()
    if not row:
        raise ValueError("Profile not found")
    if row["share_token"]:
        return row["share_token"]
    token = generate_share_token()
    db.execute(
        """UPDATE recruiting_profiles
              SET share_token=?, is_published=1, updated_at=CURRENT_TIMESTAMP
            WHERE id=?""",
        (token, profile_id),
    )
    db.commit()
    return token


def revoke_share_token(db, profile_id: int) -> None:
    db.execute(
        """UPDATE recruiting_profiles
              SET share_token=NULL, is_published=0, updated_at=CURRENT_TIMESTAMP
            WHERE id=?""",
        (profile_id,),
    )
    db.commit()


def player_stats_summary(db, player_id: Optional[int], player_name: Optional[str] = None) -> dict:
    """Aggregate per-game stats for a linked player when available."""
    empty = {
        "games": 0,
        "pts": 0,
        "fgm": 0,
        "fga": 0,
        "threes_made": 0,
        "threes_att": 0,
        "ast": 0,
        "reb": 0,
        "tov": 0,
        "stl": 0,
        "blk": 0,
        "minutes": 0.0,
        "ppg": 0.0,
        "rpg": 0.0,
        "apg": 0.0,
        "source": None,
    }
    if not player_id and not player_name:
        return empty

    if player_id:
        row = db.execute(
            """SELECT COUNT(DISTINCT game_id) AS games,
                      COALESCE(SUM(pts), 0) AS pts,
                      COALESCE(SUM(fgm), 0) AS fgm,
                      COALESCE(SUM(fga), 0) AS fga,
                      COALESCE(SUM(threes_made), 0) AS threes_made,
                      COALESCE(SUM(threes_att), 0) AS threes_att,
                      COALESCE(SUM(ast), 0) AS ast,
                      COALESCE(SUM(reb), 0) AS reb,
                      COALESCE(SUM(tov), 0) AS tov,
                      COALESCE(SUM(stl), 0) AS stl,
                      COALESCE(SUM(blk), 0) AS blk,
                      COALESCE(SUM(minutes), 0) AS minutes
                 FROM stats
                WHERE player_id = ?""",
            (player_id,),
        ).fetchone()
        source = "player_id"
    else:
        row = None
        source = None

    if (not row or not row["games"]) and player_name:
        row = db.execute(
            """SELECT COUNT(DISTINCT game_id) AS games,
                      COALESCE(SUM(pts), 0) AS pts,
                      COALESCE(SUM(fgm), 0) AS fgm,
                      COALESCE(SUM(fga), 0) AS fga,
                      COALESCE(SUM(threes_made), 0) AS threes_made,
                      COALESCE(SUM(threes_att), 0) AS threes_att,
                      COALESCE(SUM(ast), 0) AS ast,
                      COALESCE(SUM(reb), 0) AS reb,
                      COALESCE(SUM(tov), 0) AS tov,
                      COALESCE(SUM(stl), 0) AS stl,
                      COALESCE(SUM(blk), 0) AS blk,
                      COALESCE(SUM(minutes), 0) AS minutes
                 FROM stats
                WHERE LOWER(TRIM(player_name)) = LOWER(TRIM(?))""",
            (player_name,),
        ).fetchone()
        source = "player_name"

    if not row or not row["games"]:
        return empty

    games = int(row["games"] or 0)
    pts = int(row["pts"] or 0)
    reb = int(row["reb"] or 0)
    ast = int(row["ast"] or 0)
    return {
        "games": games,
        "pts": pts,
        "fgm": int(row["fgm"] or 0),
        "fga": int(row["fga"] or 0),
        "threes_made": int(row["threes_made"] or 0),
        "threes_att": int(row["threes_att"] or 0),
        "ast": ast,
        "reb": reb,
        "tov": int(row["tov"] or 0),
        "stl": int(row["stl"] or 0),
        "blk": int(row["blk"] or 0),
        "minutes": round(float(row["minutes"] or 0), 1),
        "ppg": round(pts / games, 1) if games else 0.0,
        "rpg": round(reb / games, 1) if games else 0.0,
        "apg": round(ast / games, 1) if games else 0.0,
        "source": source,
    }


def format_stats_blurb(summary: dict) -> str:
    if not summary or not summary.get("games"):
        return ""
    return (
        f"{summary['games']} GP · {summary['ppg']} PPG · "
        f"{summary['rpg']} RPG · {summary['apg']} APG · "
        f"{summary['pts']} PTS · {summary['threes_made']} 3PM"
    )


def defaults_from_player(db, player_id: int) -> dict:
    row = db.execute("SELECT * FROM players WHERE id=?", (player_id,)).fetchone()
    if not row:
        return {}
    player = dict(row)
    stats = player_stats_summary(db, player_id, player.get("name"))
    blurb = format_stats_blurb(stats)
    return {
        "player_id": player_id,
        "display_name": player.get("name") or "",
        "position": player.get("position") or "",
        "school_program": player.get("program_name") or "Liberty Charter",
        "program_level": player.get("level") or "",
        "season_summary": blurb,
        "career_summary": blurb,
        "stats": stats,
    }
