"""
Read-only entitlement helpers for Stage 6A.
"""

from datetime import datetime, timezone

from module_keys import ALL_MODULE_KEYS, BASE_PLATFORM, canonicalize_module_key


def _normalize_at(at):
    if at is None:
        return datetime.now(timezone.utc).replace(tzinfo=None)
    if isinstance(at, datetime):
        if at.tzinfo is not None:
            return at.astimezone(timezone.utc).replace(tzinfo=None)
        return at
    text = str(at).strip()
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None) if ("+" in text or text.endswith("Z")) else datetime.fromisoformat(text)


def _normalize_bound(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    text = str(value).strip()
    if not text:
        return None
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None) if ("+" in text or text.endswith("Z")) else datetime.fromisoformat(text)


def _row_is_active(row, at):
    starts_at = _normalize_bound(row["starts_at"])
    ends_at = _normalize_bound(row["ends_at"])
    if starts_at is not None and at < starts_at:
        return False
    if ends_at is not None and at > ends_at:
        return False
    return True


def get_team_entitlements(db, team_id):
    if team_id is None:
        return []
    rows = db.execute(
        """SELECT * FROM module_entitlements
           WHERE team_id = ?
           ORDER BY module_key ASC""",
        (team_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def is_module_entitled(db, team_id, module_key, *, at=None):
    normalized_key = canonicalize_module_key(module_key)
    if team_id is None or normalized_key not in ALL_MODULE_KEYS:
        return False
    row = db.execute(
        """SELECT * FROM module_entitlements
           WHERE team_id = ? AND module_key = ?""",
        (team_id, normalized_key),
    ).fetchone()
    if row is None or not bool(row["enabled"]):
        return False
    effective_at = _normalize_at(at)
    return _row_is_active(row, effective_at)


def list_enabled_module_keys(db, team_id, *, at=None):
    effective_at = _normalize_at(at)
    enabled_keys = []
    for row in get_team_entitlements(db, team_id):
        if bool(row["enabled"]) and _row_is_active(row, effective_at):
            enabled_keys.append(row["module_key"])
    return enabled_keys


def audit_team_entitlements(db, team_id=None, *, at=None):
    effective_at = _normalize_at(at)
    if team_id is None:
        team_ids = [
            row["id"]
            for row in db.execute("SELECT id FROM teams ORDER BY id ASC").fetchall()
        ]
    else:
        team_ids = [team_id]

    teams = []
    for current_team_id in team_ids:
        rows = get_team_entitlements(db, current_team_id)
        present_keys = [row["module_key"] for row in rows]
        enabled_keys = list_enabled_module_keys(db, current_team_id, at=effective_at)
        disabled_keys = [
            row["module_key"]
            for row in rows
            if row["module_key"] not in enabled_keys
        ]
        missing_keys = [key for key in ALL_MODULE_KEYS if key not in present_keys]
        teams.append(
            {
                "team_id": current_team_id,
                "row_count": len(rows),
                "enabled_module_keys": enabled_keys,
                "disabled_module_keys": disabled_keys,
                "missing_module_keys": missing_keys,
                "has_base_platform": BASE_PLATFORM in enabled_keys,
            }
        )

    return {
        "team_count": len(teams),
        "teams": teams,
    }


def is_module_accessible(db, team_id, module_key, *, at=None):
    """Soft add-on gate: base platform required; missing add-on rows stay accessible."""
    normalized = canonicalize_module_key(module_key)
    if team_id is None or normalized not in ALL_MODULE_KEYS:
        return False
    if not is_module_entitled(db, team_id, BASE_PLATFORM, at=at):
        return False
    if normalized == BASE_PLATFORM:
        return True
    row = db.execute(
        """SELECT * FROM module_entitlements
           WHERE team_id = ? AND module_key = ?""",
        (team_id, normalized),
    ).fetchone()
    if row is None:
        return True
    return is_module_entitled(db, team_id, normalized, at=at)


def enforce_module_access(db, team_id, module_key, *, at=None):
    from flask import abort

    if not is_module_accessible(db, team_id, module_key, at=at):
        abort(404)


def build_preview_entitlements_view(db, preview_modules, *, team_id=None):
    """Coach-facing module packaging state for /preview."""
    from helpers import get_default_team_id
    from module_keys import MODULE_KEY_LABELS

    if team_id is None:
        team_id = get_default_team_id(db)

    report = audit_team_entitlements(db, team_id)
    team = report["teams"][0] if report["teams"] else None

    enriched_modules = []
    for module in preview_modules:
        keys = module.get("module_keys", [])
        accessible = bool(
            team_id
            and keys
            and all(is_module_accessible(db, team_id, key) for key in keys)
        )
        enriched_modules.append(
            {
                **module,
                "access_state": "available" if accessible else "unavailable",
                "module_keys": keys,
            }
        )

    labeled_teams = []
    for current_team in report["teams"]:
        labeled_teams.append(
            {
                **current_team,
                "enabled_labels": [
                    MODULE_KEY_LABELS.get(key, key)
                    for key in current_team["enabled_module_keys"]
                ],
                "disabled_labels": [
                    MODULE_KEY_LABELS.get(key, key)
                    for key in current_team["disabled_module_keys"]
                ],
                "missing_labels": [
                    MODULE_KEY_LABELS.get(key, key)
                    for key in current_team["missing_module_keys"]
                ],
            }
        )

    return {
        "team_id": team_id,
        "module_entitlement_report": {**report, "teams": labeled_teams},
        "preview_modules": enriched_modules,
        "enabled_module_count": len(team["enabled_module_keys"]) if team else 0,
        "disabled_module_count": len(team["disabled_module_keys"]) if team else 0,
        "missing_module_count": len(team["missing_module_keys"]) if team else 0,
        "module_key_labels": MODULE_KEY_LABELS,
    }


def seed_demo_module_entitlements(db, team_id=None):
    """Public helper to seed demo stats/scouting entitlements (idempotent)."""
    from helpers import _seed_demo_module_entitlements, get_default_team_id

    if team_id is None:
        team_id = get_default_team_id(db)
    return _seed_demo_module_entitlements(db, team_id)
