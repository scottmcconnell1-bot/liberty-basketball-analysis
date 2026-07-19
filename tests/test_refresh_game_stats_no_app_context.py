"""Regression: AI worker has no Flask app context during post-process."""

from __future__ import annotations

import sqlite3


def test_refresh_game_stats_without_app_context_does_not_raise():
    """Mirrors AI subprocess: bare sqlite connection, no flask app_context."""
    from helpers import refresh_game_stats

    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    # feature off → early return; must not call feature_enabled()/current_app
    refresh_game_stats(conn, "worker-game-key")
    conn.close()


def test_persist_events_auto_accept_survives_missing_app_context(tmp_path):
    """Event persistence must complete even if auto-accept/stats need Flask."""
    from event_generator import persist_events

    db_path = tmp_path / "events.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT,
            relational_game_id INTEGER,
            player TEXT,
            event_type TEXT,
            event_type_id INTEGER,
            shot_result TEXT,
            timestamp_ms INTEGER,
            details_json TEXT,
            confidence REAL,
            source_type TEXT,
            human_verified INTEGER DEFAULT 0,
            review_status TEXT DEFAULT 'pending',
            reviewed_by_user_id INTEGER,
            reviewed_at TEXT,
            review_notes TEXT
        );
        CREATE TABLE event_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE
        );
        INSERT INTO event_types (code) VALUES ('2PT Make');
        CREATE TABLE app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT INTO app_settings (key, value)
        VALUES ('ai.auto_accept_event_confidence', '0.50');
        CREATE TABLE review_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT,
            entity_id INTEGER,
            game_id TEXT,
            relational_game_id INTEGER,
            review_status TEXT,
            reason TEXT,
            reviewed_by_user_id INTEGER,
            reviewed_at TEXT,
            notes TEXT,
            updated_at TEXT
        );
        CREATE TABLE provenance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT,
            entity_id INTEGER,
            source_type TEXT,
            source_id TEXT,
            confidence REAL,
            created_by_user_id INTEGER,
            details_json TEXT
        );
        """
    )
    conn.commit()

    events = [
        {
            "game_id": "worker-game",
            "player": "1",
            "event_type": "2PT Make",
            "shot_result": "made",
            "timestamp_ms": 1000,
            "details_json": "{}",
            "confidence": 0.9,
        }
    ]
    # Must not raise Working outside of application context
    persist_events(conn, "worker-game", events, relational_game_id=None)
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM events WHERE game_id=?", ("worker-game",)
    ).fetchone()
    assert row["c"] == 1
    conn.close()
