"""Tests for Adrian jersey lookaround matching."""

from __future__ import annotations

import sqlite3

from adrian_identity import (
    EARLY_GAME_MS,
    lookaround_jersey_votes,
    match_scorebook_player,
    resolve_event_identity,
    scorebook_roster_index,
)
from adrian_quality import ADRIAN_BASE


def test_unique_jersey_matches_scorebook():
    idx = scorebook_roster_index()
    # Dayley #40 is Liberty (away) only
    hit = match_scorebook_player(40, idx)
    assert hit is not None
    assert hit["jersey"] == "40"
    assert "Dayley" in (hit.get("name") or "")
    assert hit["team_name"] == "Liberty"


def test_ambiguous_jersey_skipped():
    idx = scorebook_roster_index()
    # #11 appears on both Adrian and Liberty in this book
    assert match_scorebook_player(11, idx) is None


def _seed_detections(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.execute(
        """
        CREATE TABLE detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL,
            frame_number INTEGER NOT NULL DEFAULT 0,
            timestamp_ms INTEGER NOT NULL,
            object_class TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.9,
            x_center INTEGER NOT NULL DEFAULT 0,
            y_center INTEGER NOT NULL DEFAULT 0,
            width INTEGER NOT NULL DEFAULT 40,
            height INTEGER NOT NULL DEFAULT 80,
            tracker_id INTEGER,
            player_cluster INTEGER,
            jersey_read INTEGER,
            jersey_confidence REAL
        )
        """
    )
    for row in rows:
        conn.execute(
            """
            INSERT INTO detections
              (game_id, timestamp_ms, object_class, tracker_id, player_cluster,
               jersey_read, jersey_confidence)
            VALUES (?, ?, 'person', ?, ?, ?, ?)
            """,
            row,
        )
    conn.commit()


def test_early_steal_accepts_single_high_confidence_ocr():
    """~13s steal: one clear OCR later on same track should name the player."""
    conn = sqlite3.connect(":memory:")
    tracker = 8
    event_ts = 13_000
    # Presence near the steal (no OCR yet) + one strong jersey read later.
    _seed_detections(
        conn,
        [
            (ADRIAN_BASE, event_ts, tracker, None, None, None),
            (ADRIAN_BASE, 45_000, tracker, None, 40, 0.60),
        ],
    )
    idx = scorebook_roster_index()
    result = resolve_event_identity(
        conn,
        ADRIAN_BASE,
        {"player": str(tracker), "timestamp_ms": event_ts},
        idx,
    )
    assert result is not None
    assert result["status"] == "matched"
    assert str(result["jersey_number"]) == "40"
    assert "Dayley" in (result.get("player_name") or "")
    conn.close()


def test_late_event_still_requires_two_samples():
    conn = sqlite3.connect(":memory:")
    tracker = 8
    event_ts = EARLY_GAME_MS + 5_000
    _seed_detections(
        conn,
        [
            (ADRIAN_BASE, event_ts, tracker, None, None, None),
            (ADRIAN_BASE, event_ts + 1_000, tracker, None, 40, 0.80),
        ],
    )
    idx = scorebook_roster_index()
    result = resolve_event_identity(
        conn,
        ADRIAN_BASE,
        {"player": str(tracker), "timestamp_ms": event_ts},
        idx,
    )
    assert result is None
    conn.close()


def test_early_lookaround_uses_extra_window_and_lower_floor():
    conn = sqlite3.connect(":memory:")
    tracker = 9
    event_ts = 3_300  # tip_off-ish
    # Weak OCR only at ~20 min — needs early extra 30-min window.
    _seed_detections(
        conn,
        [
            (ADRIAN_BASE, event_ts, tracker, None, None, None),
            (ADRIAN_BASE, 1_200_000, tracker, None, 40, 0.42),
            (ADRIAN_BASE, 1_200_500, tracker, None, 40, 0.41),
        ],
    )
    votes = lookaround_jersey_votes(
        conn, ADRIAN_BASE, tracker, event_ts, min_confidence=0.35, early_game=True
    )
    assert votes
    assert votes[0]["jersey_number"] == 40
    assert votes[0]["window_ms"] >= 1_800_000

    idx = scorebook_roster_index()
    result = resolve_event_identity(
        conn,
        ADRIAN_BASE,
        {"player": str(tracker), "timestamp_ms": event_ts},
        idx,
    )
    assert result is not None
    assert result["status"] == "matched"
    conn.close()
