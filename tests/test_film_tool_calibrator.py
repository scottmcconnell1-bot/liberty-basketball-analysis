"""Film Tool sidecar trains the event calibrator without a GPU pass."""
from __future__ import annotations

import json
import sqlite3

from film_tool_calibrator import build_film_tool_calibrator
from film_tool_tags import save_manual_tags


def test_build_film_tool_calibrator_from_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr("film_tool_tags.TAGS_ROOT", tmp_path)
    game_id = "jrhigh_adrian,_or_CALIB_TEST"
    save_manual_tags(
        game_id,
        {
            "rows": [
                {
                    "eventtype": "2PT",
                    "result": "Make",
                    "player": "40 Dayley",
                    "team": "Liberty",
                    "start": "0:40.0",
                },
                {
                    "eventtype": "FT",
                    "result": "Miss",
                    "player": "13 Mendoza",
                    "team": "Adrian",
                    "start": "1:10.0",
                },
            ]
        },
    )
    db_path = tmp_path / "events.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """CREATE TABLE events (
            id INTEGER PRIMARY KEY,
            game_id TEXT,
            player TEXT,
            event_type TEXT,
            shot_result TEXT,
            timestamp_ms INTEGER,
            details_json TEXT,
            confidence REAL,
            source_type TEXT
        )"""
    )
    conn.execute(
        """INSERT INTO events
           (game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, source_type)
           VALUES (?, 'track-1', 'shot', 'make', 40000, ?, 0.7, 'ai')""",
        (game_id, json.dumps({"lateral_travel": 80.0, "ball_rise": 220.0})),
    )
    conn.execute(
        """INSERT INTO events
           (game_id, player, event_type, shot_result, timestamp_ms, details_json, confidence, source_type)
           VALUES (?, 'track-2', 'shot', 'miss', 70000, ?, 0.6, 'ai')""",
        (game_id, json.dumps({"lateral_travel": 40.0, "ball_rise": 40.0})),
    )
    conn.commit()
    conn.close()

    model = build_film_tool_calibrator(game_id, db_path=db_path, window_end_ms=960700)
    assert model["source"] == "teach_from_film_tags"
    assert model["analysis_key"] == game_id
    assert model["train_snapshot"]["manual_tags"] == 2
    assert model["train_snapshot"]["shot_anchors"] == 2
    assert model["train_snapshot"]["shot_train_rows"] == 2
    assert any(a["shot_type"] == "ft" for a in model["shot_label_anchors"])
    assert any(a["shot_type"] == "2pt" for a in model["shot_label_anchors"])
