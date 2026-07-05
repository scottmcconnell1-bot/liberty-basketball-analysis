from datetime import datetime, timedelta

from helpers import DEFAULT_TEAM_SEED
from module_entitlements import (
    audit_team_entitlements,
    build_preview_entitlements_view,
    get_team_entitlements,
    is_module_accessible,
    is_module_entitled,
    list_enabled_module_keys,
    seed_demo_module_entitlements,
)
from module_keys import (
    ADVANCED_TRACKING,
    ALL_MODULE_KEYS,
    BASE_PLATFORM,
    FILM_ROOM,
    LEGACY_BASE_ALIAS,
    SCOUTING,
    STATS,
    canonicalize_module_key,
)


def _default_team_id(db):
    row = db.execute(
        """SELECT id FROM teams
           WHERE organization_name=?
             AND team_name=?
             AND program_name=?
             AND gender=?
             AND level=?""",
        (
            DEFAULT_TEAM_SEED["organization_name"],
            DEFAULT_TEAM_SEED["team_name"],
            DEFAULT_TEAM_SEED["program_name"],
            DEFAULT_TEAM_SEED["gender"],
            DEFAULT_TEAM_SEED["level"],
        ),
    ).fetchone()
    assert row is not None
    return row["id"]


def test_module_keys_match_seed():
    assert BASE_PLATFORM == "base_platform"
    assert canonicalize_module_key(LEGACY_BASE_ALIAS) == BASE_PLATFORM
    assert BASE_PLATFORM in ALL_MODULE_KEYS


def test_is_module_entitled_enabled(db):
    team_id = _default_team_id(db)
    assert is_module_entitled(db, team_id, BASE_PLATFORM) is True


def test_is_module_entitled_unknown_key(db):
    team_id = _default_team_id(db)
    assert is_module_entitled(db, team_id, "unknown_module") is False


def test_is_module_entitled_disabled_row(db):
    team_id = _default_team_id(db)
    db.execute(
        """INSERT OR REPLACE INTO module_entitlements
           (team_id, module_key, enabled, notes)
           VALUES (?, ?, ?, ?)""",
        (team_id, STATS, 0, "disabled in test"),
    )
    db.commit()
    assert is_module_entitled(db, team_id, STATS) is False


def test_is_module_entitled_date_window(db):
    team_id = _default_team_id(db)
    now = datetime.utcnow().replace(microsecond=0)
    starts_at = (now - timedelta(days=1)).isoformat(sep=" ")
    ends_at = (now + timedelta(days=1)).isoformat(sep=" ")
    db.execute(
        """INSERT OR REPLACE INTO module_entitlements
           (team_id, module_key, enabled, starts_at, ends_at, notes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (team_id, STATS, 1, starts_at, ends_at, "active window"),
    )
    db.commit()
    assert is_module_entitled(db, team_id, STATS, at=now) is True
    assert is_module_entitled(db, team_id, STATS, at=now - timedelta(days=2)) is False
    assert is_module_entitled(db, team_id, STATS, at=now + timedelta(days=2)) is False


def test_list_enabled_module_keys(db):
    team_id = _default_team_id(db)
    db.execute(
        """INSERT OR REPLACE INTO module_entitlements
           (team_id, module_key, enabled, notes)
           VALUES (?, ?, ?, ?)""",
        (team_id, STATS, 1, "enabled in test"),
    )
    db.execute(
        """INSERT OR REPLACE INTO module_entitlements
           (team_id, module_key, enabled, notes)
           VALUES (?, ?, ?, ?)""",
        (team_id, ADVANCED_TRACKING, 0, "disabled in test"),
    )
    db.commit()
    enabled = list_enabled_module_keys(db, team_id)
    assert BASE_PLATFORM in enabled
    assert STATS in enabled
    assert ADVANCED_TRACKING not in enabled


def test_audit_team_entitlements(db):
    team_id = _default_team_id(db)
    report = audit_team_entitlements(db, team_id)
    assert report["team_count"] == 1
    assert report["teams"][0]["team_id"] == team_id
    assert BASE_PLATFORM in report["teams"][0]["enabled_module_keys"]
    assert STATS in report["teams"][0]["enabled_module_keys"]
    assert SCOUTING in report["teams"][0]["enabled_module_keys"]


def test_seed_demo_module_entitlements_is_idempotent(db):
    team_id = _default_team_id(db)
    keys_first = seed_demo_module_entitlements(db, team_id)
    keys_second = seed_demo_module_entitlements(db, team_id)
    assert STATS in keys_first
    assert SCOUTING in keys_first
    assert keys_second == keys_first
    row_count = db.execute(
        """SELECT COUNT(*) AS cnt FROM module_entitlements
            WHERE team_id=? AND module_key IN (?, ?)""",
        (team_id, STATS, SCOUTING),
    ).fetchone()["cnt"]
    assert row_count == 2


def test_build_preview_entitlements_view_marks_modules(db):
    team_id = _default_team_id(db)
    preview_modules = [
        {"title": "Film Room", "module_keys": [FILM_ROOM]},
        {"title": "Scouting", "module_keys": [SCOUTING]},
    ]
    view = build_preview_entitlements_view(db, preview_modules, team_id=team_id)
    assert view["enabled_module_count"] >= 1
    assert view["preview_modules"][0]["access_state"] == "available"

    db.execute(
        """INSERT OR REPLACE INTO module_entitlements
           (team_id, module_key, enabled, notes)
           VALUES (?, ?, ?, ?)""",
        (team_id, SCOUTING, 0, "disabled in test"),
    )
    db.commit()
    view = build_preview_entitlements_view(db, preview_modules, team_id=team_id)
    assert view["preview_modules"][1]["access_state"] == "unavailable"
    assert SCOUTING in view["module_entitlement_report"]["teams"][0]["disabled_module_keys"]


def test_get_team_entitlements_ordered(db):
    team_id = _default_team_id(db)
    db.execute(
        """INSERT OR REPLACE INTO module_entitlements
           (team_id, module_key, enabled, notes)
           VALUES (?, ?, ?, ?)""",
        (team_id, STATS, 1, "enabled in test"),
    )
    db.commit()
    rows = get_team_entitlements(db, team_id)
    keys = [row["module_key"] for row in rows]
    assert keys == sorted(keys)


def test_is_module_accessible_allows_unconfigured_addon(db):
    team_id = _default_team_id(db)
    assert is_module_accessible(db, team_id, SCOUTING) is True


def test_is_module_accessible_blocks_disabled_addon(db):
    team_id = _default_team_id(db)
    db.execute(
        """INSERT OR REPLACE INTO module_entitlements
           (team_id, module_key, enabled, notes)
           VALUES (?, ?, ?, ?)""",
        (team_id, SCOUTING, 0, "disabled in test"),
    )
    db.commit()
    assert is_module_accessible(db, team_id, SCOUTING) is False


def test_scouting_page_soft_gate_allows_base_only(client, db):
    team_id = _default_team_id(db)
    assert is_module_accessible(db, team_id, SCOUTING) is True
    r = client.get("/scouting")
    assert r.status_code == 200


def test_scouting_page_blocked_when_module_disabled(client, db):
    team_id = _default_team_id(db)
    db.execute(
        """INSERT OR REPLACE INTO module_entitlements
           (team_id, module_key, enabled, notes)
           VALUES (?, ?, ?, ?)""",
        (team_id, SCOUTING, 0, "disabled in test"),
    )
    db.commit()
    r = client.get("/scouting")
    assert r.status_code == 404
