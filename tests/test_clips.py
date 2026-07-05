"""Tests for blueprints/clips.py"""
import os
import tempfile
import sqlite3

from unittest.mock import patch, MagicMock

import pytest


def test_update_event_preserves_relational_identity():
    from blueprints.clips import update_event

    # Create an in-memory database
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Create events table with the columns we need
        cursor.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, game_id TEXT, relational_game_id INTEGER, player TEXT, event_type TEXT, shot_result TEXT, timestamp_ms INTEGER, details_json TEXT, confidence REAL, human_verified INTEGER)")
        # Insert a test event
        cursor.execute("INSERT INTO events (id, game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (1, "game123", 123, "Player 1", "shot", None, 1000, "{}", 0.5, 0))
        conn.commit()

        # Mock the dependencies
        with patch('blueprints.clips.get_db') as mock_get_db, \
             patch('blueprints.clips.request') as mock_request, \
             patch('blueprints.clips.require_feature') as mock_require_feature, \
             patch('blueprints.clips.refresh_game_stats') as mock_refresh:

            # Setup mocks
            mock_get_db.return_value = conn
            mock_request.get_json.return_value = {
                "player": "Player 2",
                "event_type": "rebound",
                "shot_result": "offensive",
                "timestamp_ms": 2000,
                "details_json": "{\"new\": \"data\"}",
                "human_verified": True,
                "confidence": 0.8
            }
            # Make require_feature a no-op decorator
            mock_require_feature.return_value = lambda f: f
            mock_refresh.return_value = None

            # Call the function
            response = update_event(1)
            # We don't really care about the response for this test, but we can check it's not an error
            # Actually, the function returns a JSON response, but we are more interested in the database state.

        # Check the database
        cursor.execute("SELECT * FROM events WHERE id=1")
        row = cursor.fetchone()
        # Unpack the row
        id_, game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified = row

        # Check that the game_id and relational_game_id are unchanged
        assert game_id == "game123"
        assert relational_game_id == 123

        # Check that the other fields are updated
        assert player == "Player 2"
        assert event_type == "rebound"
        assert shot_result == "offensive"
        assert timestamp_ms == 2000
        assert details_json == "{\"new\": \"data\"}"
        assert confidence == 0.8
        assert human_verified == 1

    finally:
        os.unlink(db_path)


def test_delete_event_does_not_disturb_relationally_linked_events():
    from blueprints.clips import delete_event

    # Create an in-memory database
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Create events table
        cursor.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, game_id TEXT, relational_game_id INTEGER, player TEXT, event_type TEXT, shot_result TEXT, timestamp_ms INTEGER, details_json TEXT, confidence REAL, human_verified INTEGER)")
        # Insert two events for the same game
        cursor.execute("INSERT INTO events (id, game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (1, "game123", 123, "Player 1", "shot", None, 1000, "{}", 0.5, 0))
        cursor.execute("INSERT INTO events (id, game_id, relational_game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (2, "game123", 123, "Player 2", "rebound", None, 2000, "{}", 0.6, 0))
        conn.commit()

        # Mock the dependencies
        with patch('blueprints.clips.get_db') as mock_get_db, \
             patch('blueprints.clips.request') as mock_request, \
             patch('blueprints.clips.require_feature') as mock_require_feature, \
             patch('blueprints.clips.refresh_game_stats') as mock_refresh:

            # Setup mocks
            mock_get_db.return_value = conn
            mock_request.get_json.return_value = {}
            # Make require_feature a no-op decorator
            mock_require_feature.return_value = lambda f: f
            mock_refresh.return_value = None

            # Call the function to delete event with id=1
            response = delete_event(1)

        # Check the database
        cursor.execute("SELECT COUNT(*) FROM events")
        count = cursor.fetchone()[0]
        assert count == 1  # Only one event should remain

        cursor.execute("SELECT * FROM events WHERE id=2")
        row = cursor.fetchone()
        assert row is not None
        id_, game_id, relational_gid, player, event_type, shot_result, timestamp_ms, details_json, confidence, human_verified = row

        # Check that the remaining event's game_id and relational_game_id are unchanged
        assert game_id == "game123"
        assert relational_gid == 123

        # Also check that the other fields are as expected (they should be unchanged)
        assert player == "Player 2"
        assert event_type == "rebound"
        assert shot_result is None
        assert timestamp_ms == 2000
        assert details_json == "{}"
        assert confidence == 0.6
        assert human_verified == 0

    finally:
        os.unlink(db_path)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])