"""
Stage 10B guided assistant workflow: game → player → clip list.

Read-only steps backed by trusted reviewed events and linked clips.
"""

from assistant_query import REVIEW_SCOPE, _clip_citation, _trusted_clips_for_game
from stats import (
    _resolve_relational_game_id,
    _trusted_event_review_clause,
    aggregate_stats,
)


def _game_label(row):
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


def list_workflow_games(db, limit=100):
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
               ) AS trusted_event_count
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


def list_workflow_players(db, game_id):
    relational_game_id = _resolve_relational_game_id(db, game_id)
    if relational_game_id is None and not db.execute(
        "SELECT 1 FROM events WHERE game_id=? LIMIT 1", (str(game_id),)
    ).fetchone():
        return None

    stats = aggregate_stats(db, game_id)
    players = []
    for row in sorted(stats, key=lambda item: (-item.get("pts", 0), item.get("player") or "")):
        players.append(
            {
                "player": row["player"],
                "pts": row.get("pts", 0),
                "reb": row.get("reb", 0),
                "ast": row.get("ast", 0),
                "tov": row.get("tov", 0),
                "stl": row.get("stl", 0),
                "blk": row.get("blk", 0),
            }
        )
    return players


def list_workflow_clips(db, game_id, player=None, limit=50):
    relational_game_id = _resolve_relational_game_id(db, game_id)
    if relational_game_id is None and not db.execute(
        "SELECT 1 FROM events WHERE game_id=? LIMIT 1", (str(game_id),)
    ).fetchone():
        return None

    player_hint = (player or "").strip() or None
    clips = _trusted_clips_for_game(db, game_id, player_hint=player_hint, limit=limit)
    return [_clip_citation(row) for row in clips]


def build_workflow_payload(step, db, game_id=None, player=None):
    if step == "games":
        return {
            "step": "games",
            "next_step": "players",
            "review_scope": REVIEW_SCOPE,
            "games": list_workflow_games(db),
        }

    if step == "players":
        if game_id is None:
            return {"error": "game_id is required for players step"}
        players = list_workflow_players(db, game_id)
        if players is None:
            return {"error": f"Game '{game_id}' was not found"}
        return {
            "step": "players",
            "next_step": "clips",
            "game_id": game_id,
            "review_scope": REVIEW_SCOPE,
            "players": players,
        }

    if step == "clips":
        if game_id is None:
            return {"error": "game_id is required for clips step"}
        clips = list_workflow_clips(db, game_id, player=player)
        if clips is None:
            return {"error": f"Game '{game_id}' was not found"}
        return {
            "step": "clips",
            "game_id": game_id,
            "player": player,
            "review_scope": REVIEW_SCOPE,
            "clips": clips,
        }

    return {"error": f"Unknown workflow step '{step}'"}
