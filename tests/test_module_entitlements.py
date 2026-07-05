from datetime import datetime, timedelta

from helpers import DEFAULT_TEAM_SEED
from module_entitlements import (
    audit_team_entitlements,
    get_team_entitlements,
    is_module_entitled,
    list_enabled_module_keys,
)
from module_keys import (
    ADVANCED_TRACKING,
    ALL_MODULE_KEYS,
    BASE_PLATFORM,
    LEGACY_BASE_ALIAS,
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
