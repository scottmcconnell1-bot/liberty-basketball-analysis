"""Confirmed-box helpers matching docs/stat_books/CONFIRMED_BOX_SCHEMA.md.

Spiral form extras: fg2 / fg3 (make counts) live under players[].extras.
Mapped foundation keys: tpm≈fg3, ftm, fta, pts; fgm≈fg2+fg3 when both present.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

PLAYER_KEYS = (
    "pts",
    "fouls",
    "fgm",
    "fga",
    "tpm",
    "tpa",
    "ftm",
    "fta",
    "reb",
    "ast",
    "stl",
    "blk",
    "to",
    "min",
)

SCHEMA_VERSION = 1


def _as_int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a valid stat")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _coerce_team(team: Any) -> str | None:
    if team is None or team == "":
        return None
    low = str(team).strip().lower()
    if low in ("home", "liberty", "us"):
        return "home"
    if low in ("away", "opp", "opponent"):
        return "away"
    if low in ("home", "away"):
        return low
    return None


def normalize_player(raw: dict | None) -> dict:
    src = dict(raw or {})
    extras_in = src.get("extras") if isinstance(src.get("extras"), dict) else {}
    extras = dict(extras_in)

    # Promote spiral OCR fields into extras + foundation keys
    for spiral_key in ("fg2", "fg3"):
        if spiral_key in src and src[spiral_key] is not None:
            extras[spiral_key] = _as_int_or_none(src.get(spiral_key))

    fg2 = _as_int_or_none(extras.get("fg2"))
    fg3 = _as_int_or_none(extras.get("fg3"))

    jersey = src.get("jersey")
    if jersey is not None:
        jersey = str(jersey).strip() or None
    name = src.get("name")
    if name is not None:
        name = str(name).strip() or None

    out: dict[str, Any] = {
        "jersey": jersey,
        "name": name,
        "team": _coerce_team(src.get("team")),
    }
    for key in PLAYER_KEYS:
        if key == "min":
            val = src.get("min")
            out["min"] = None if val in (None, "") else (val if isinstance(val, (int, float)) else str(val).strip() or None)
        elif key in src:
            out[key] = _as_int_or_none(src.get(key))
        else:
            out[key] = None

    if out.get("tpm") is None and fg3 is not None:
        out["tpm"] = fg3
    if out.get("fgm") is None and fg2 is not None and fg3 is not None:
        out["fgm"] = fg2 + fg3
    elif out.get("fgm") is None and fg2 is not None:
        out["fgm"] = fg2

    if extras:
        # drop nulls
        out["extras"] = {k: v for k, v in extras.items() if v is not None}

    return out


def build_confirmed_box(
    *,
    game_id: str,
    template_id: str,
    players: list[dict],
    home_team: str | None = "Liberty",
    away_team: str | None = None,
    final_score_home: int | None = None,
    final_score_away: int | None = None,
    quarters: list | None = None,
    checksums: dict | None = None,
    validation: dict | None = None,
    confirmed_by: str | None = None,
    confirmed_at: str | None = None,
) -> dict:
    box = {
        "schema_version": SCHEMA_VERSION,
        "game_id": str(game_id),
        "template_id": str(template_id),
        "final_score_home": final_score_home,
        "final_score_away": final_score_away,
        "home_team": home_team,
        "away_team": away_team,
        "players": [normalize_player(p) for p in players],
        "quarters": list(quarters or []),
        "checksums": dict(checksums or {}),
        "confirmed_at": confirmed_at,
        "confirmed_by": confirmed_by,
    }
    if validation is not None:
        box["validation"] = validation
    return box


def validate_confirmed_box(data: Any) -> list[str]:
    """Shape errors (empty = ok). Basketball math is in validation/."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["root must be an object"]
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    for key in ("game_id", "template_id"):
        if not isinstance(data.get(key), str) or not data.get(key):
            errors.append(f"{key} must be a non-empty string")
    for key in ("home_team", "away_team", "confirmed_at", "confirmed_by"):
        val = data.get(key)
        if val is not None and not isinstance(val, str):
            errors.append(f"{key} must be string or null")
    for key in ("final_score_home", "final_score_away"):
        val = data.get(key)
        if val is not None and not isinstance(val, int):
            errors.append(f"{key} must be int or null")
    players = data.get("players")
    if not isinstance(players, list):
        errors.append("players must be an array")
        players = []
    for i, player in enumerate(players):
        if not isinstance(player, dict):
            errors.append(f"players[{i}] must be an object")
            continue
        team = player.get("team")
        if team is not None and team not in ("home", "away"):
            errors.append(f"players[{i}].team must be home|away|null")
        for key in ("pts", "fouls", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "reb", "ast", "stl", "blk", "to"):
            if key in player and player[key] is not None and not isinstance(player[key], int):
                errors.append(f"players[{i}].{key} must be int or null")
    if not isinstance(data.get("quarters"), list):
        errors.append("quarters must be an array")
    if not isinstance(data.get("checksums"), dict):
        errors.append("checksums must be an object")
    return errors


def stamp_confirmed(box: dict, confirmed_by: str = "coach") -> dict:
    out = deepcopy(box)
    out["confirmed_by"] = confirmed_by
    out["confirmed_at"] = (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    return out
