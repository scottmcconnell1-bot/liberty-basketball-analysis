"""Who may change the app, and which roster player a parent or player may see.

Coaches, managers, and admins edit. A signed-in parent or player is view-only,
may watch every game film, and may see stats only for the roster player linked
to that account. An unsigned session is unchanged while sign-in is not required,
so the home coach machine keeps working.

The link lives in ``data/audience_player_links.json`` (user id → player id).
That avoids a schema change. A player account whose display name matches a
roster name is used when no link is saved.
"""

from __future__ import annotations

import json
from pathlib import Path

FAMILY_ROLES = frozenset({"parent", "player"})
STAFF_ROLES = frozenset({"coach", "manager", "admin"})

_LINKS_PATH = Path(__file__).resolve().parent / "data" / "audience_player_links.json"

# Read-only playbook fetches are POST because they send the sheet image.
# Parents and players may run those so they can watch a play. Everything
# else that writes is refused.
FAMILY_POST_ALLOW = frozenset({
    "/logout",
    "/profile/edit",
    "/login",
    "/api/playbook/sheet-align",
    "/api/playbook/sheet-extract",
    "/api/playbook/sheet-paths",
})

# Coach tools and team stat boards. Game film stays open so a parent or
# player can watch every game. Tagging and other writes stay blocked.
FAMILY_REDIRECT_PREFIXES = (
    "/settings",
    "/users",
    "/debug",
    "/stat-books",
    "/assistant",
    "/player-development",
    "/recruiting",
    "/nfhs-matches",
    "/practice-playlists",
    "/games",
)


def _user_value(user, key):
    if not user:
        return None
    if isinstance(user, dict):
        return user.get(key)
    try:
        return user[key]
    except (KeyError, IndexError, TypeError):
        return None


def is_family_role(role) -> bool:
    return (role or "").strip().lower() in FAMILY_ROLES


def load_links() -> dict:
    try:
        raw = json.loads(_LINKS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def save_link(user_id, player_id) -> None:
    links = load_links()
    key = str(int(user_id))
    if player_id in (None, "", 0, "0"):
        links.pop(key, None)
    else:
        links[key] = int(player_id)
    _LINKS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _LINKS_PATH.write_text(json.dumps(links, indent=2) + "\n", encoding="utf-8")


def linked_player_id(user) -> int | None:
    raw = load_links().get(str(_user_value(user, "id") or ""))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value or None


def resolve_player_id(db, user):
    """Roster player this parent or player is allowed to see. None if unlinked."""
    if not user or not is_family_role(_user_value(user, "role")):
        return None
    linked = linked_player_id(user)
    if linked:
        row = db.execute("SELECT id FROM players WHERE id = ?", (linked,)).fetchone()
        if row:
            return row["id"]
    role = (_user_value(user, "role") or "").strip().lower()
    name = (_user_value(user, "display_name") or "").strip()
    if role != "player" or not name:
        return None
    row = db.execute(
        "SELECT id FROM players WHERE lower(trim(name)) = lower(trim(?)) ORDER BY id LIMIT 1",
        (name,),
    ).fetchone()
    return row["id"] if row else None
