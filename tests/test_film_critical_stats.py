"""Film-tool steals and fouls become accepted events and count on the box."""

import json

from film_critical_stats import write_film_tool_critical_stats
from game_boxscore import build_official_box


def test_steal_and_personal_tags_count_stl_and_pf(db, monkeypatch):
    game_id = "critical_stl_pf"
    book = {
        "home_team": "Adrian",
        "away_team": "Liberty",
        "final_score_home": 26,
        "final_score_away": 51,
        "players": [
            {"team": "home", "jersey": "22", "name": "Foster", "pts": 8},
            {"team": "home", "jersey": "11", "name": "Linkhart", "pts": 0},
            {"team": "away", "jersey": "11", "name": "Flores", "pts": 0},
            {"team": "away", "jersey": "40", "name": "Dayley", "pts": 99},
        ],
    }
    monkeypatch.setattr("program_mode.load_scorebook", lambda gid: book)
    monkeypatch.setattr("game_boxscore.load_scorebook", lambda gid: book)

    db.execute(
        """INSERT INTO analysis_runs (game_id, analysis_key, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (None, game_id, "uploads/demo.mp4"),
    )
    db.execute(
        """INSERT INTO events
              (game_id, player, event_type, shot_result, timestamp_ms,
               human_verified, source_type, review_status, confidence)
           VALUES (?, '40 - Dayley', 'made_two', 'make', 120000, 0, 'ai', 'accepted', 0.9)""",
        (game_id,),
    )
    db.execute(
        """INSERT INTO events
              (game_id, player, event_type, timestamp_ms,
               human_verified, source_type, review_status, confidence)
           VALUES (?, '22 - Foster', 'block', 9000, 0, 'ai', 'pending', 0.4)""",
        (game_id,),
    )
    db.commit()
    before = build_official_box(db, game_id, event_counts=True)
    assert before["final"]["liberty"] == 2
    assert before["team"]["liberty"]["stl"] == 0
    assert before["team"]["liberty"]["pf"] == 0

    rows = [
        {
            "eventtype": "Steal",
            "category": "Defense",
            "player": "22 - Foster",
            "team": "Adrian",
            "start": "0:08.9",
            "label": "Steal",
            "notes": "",
        },
        {
            "eventtype": "Turnover",
            "category": "Offense",
            "player": "0 - Sullivan",
            "team": "Liberty",
            "start": "0:08.9",
            "label": "Turnover",
            "notes": "Linked to steal by 22 - Foster",
        },
        {
            "eventtype": "Turnover",
            "category": "Offense",
            "player": "23 - Rodus",
            "team": "Adrian",
            "start": "0:56.7",
            "label": "Turnover",
            "notes": "",
        },
        {
            "eventtype": "Personal",
            "category": "Foul",
            "player": "11 - Flores",
            "team": "Liberty",
            "start": "1:41.2",
            "label": "Personal foul",
            "notes": "",
        },
        {
            "eventtype": "2PT",
            "result": "Make",
            "category": "Offense",
            "player": "40 - Dayley",
            "team": "Liberty",
            "start": "2:00.0",
            "label": "2PT Make",
        },
    ]

    first = write_film_tool_critical_stats(db, game_id, rows)
    assert first["ok"] is True
    assert first["inserted"] == 3
    assert first["updated"] == 0
    steal_id = next(item["id"] for item in first["events"] if item["event_type"] == "steal")

    second = write_film_tool_critical_stats(db, game_id, rows)
    assert second["inserted"] == 0
    assert second["updated"] == 3
    assert next(item["id"] for item in second["events"] if item["event_type"] == "steal") == steal_id

    saved = db.execute(
        """SELECT event_type, player, human_verified, confidence, review_status,
                  source_type, review_notes, details_json
             FROM events
            WHERE game_id=? AND source_type='manual'
            ORDER BY timestamp_ms, event_type""",
        (game_id,),
    ).fetchall()
    assert [row["event_type"] for row in saved] == ["steal", "turnover", "foul_personal"]
    for row in saved:
        assert row["human_verified"] == 1
        assert row["confidence"] == 1.0
        assert row["review_status"] == "accepted"
        assert row["source_type"] == "manual"
        assert row["review_notes"] == "Film Tool teach"
        details = json.loads(row["details_json"])
        assert details["film_tool_teach"] is True
        assert details["player"]
        assert details["team"]
        assert details["label"]

    personal = next(row for row in saved if row["event_type"] == "foul_personal")
    assert personal["player"] == "11 - Flores"
    assert json.loads(personal["details_json"])["team_side"] == "away"

    shots = db.execute(
        "SELECT COUNT(*) AS n FROM events WHERE game_id=? AND event_type='shot'",
        (game_id,),
    ).fetchone()
    assert shots["n"] == 0
    bare_turnovers = db.execute(
        """SELECT COUNT(*) AS n FROM events
            WHERE game_id=? AND event_type='turnover' AND player='23 - Rodus'""",
        (game_id,),
    ).fetchone()
    assert bare_turnovers["n"] == 0

    pending = db.execute(
        """SELECT review_status FROM events
            WHERE game_id=? AND source_type='ai' AND event_type='block'""",
        (game_id,),
    ).fetchone()
    assert pending["review_status"] == "pending"

    box = build_official_box(db, game_id, event_counts=True)
    assert box["team"]["opponent"]["stl"] == 1
    assert box["team"]["liberty"]["stl"] == 0
    assert box["team"]["liberty"]["pf"] == 1
    assert box["team"]["opponent"]["pf"] == 0
    assert box["final"]["liberty"] == 2
    assert box["final"]["opponent"] == 0
    flores = next(p for p in box["players"]["liberty"] if p["name"] == "Flores")
    foster = next(p for p in box["players"]["opponent"] if p["name"] == "Foster")
    assert flores["pf"] == 1
    assert foster["stl"] == 1
    dayley = next(p for p in box["players"]["liberty"] if p["name"] == "Dayley")
    assert dayley["pts"] == 2
