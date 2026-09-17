"""Film Tool tags become verified events and grade nearby AI plays."""

from event_generator import persist_events
from helpers import get_db, normalize_analysis_game_id
from manual_tag_teach import map_manual_row, teach_from_film_tool_rows


def test_normalize_analysis_game_id_unquotes_comma():
    raw = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
    encoded = "jrhigh_adrian%2C_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
    double = "jrhigh_adrian%252C_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
    assert normalize_analysis_game_id(encoded) == raw
    assert normalize_analysis_game_id(double) == raw
    assert normalize_analysis_game_id(raw) == raw


def test_map_manual_row_skips_flow_tags():
    assert map_manual_row({"eventtype": "StartQTR", "start": "0:00"}) is None
    shot = map_manual_row({
        "eventtype": "2PT",
        "result": "Make",
        "player": "0 Sullivan",
        "team": "Liberty",
        "start": "0:40.7",
        "label": "2PT Make",
    })
    assert shot["event_type"] == "shot"
    assert shot["shot_result"] == "make"
    assert shot["timestamp_ms"] == 40700
    assert shot["player"] == "0 Sullivan"


def test_empty_rows_do_not_wipe_prior_teach(app):
    game_id = "jrhigh_teach_empty"
    with app.app_context():
        db = get_db()
        first = teach_from_film_tool_rows(db, game_id, [{
            "eventtype": "2PT",
            "result": "Make",
            "player": "21 Colman",
            "team": "Liberty",
            "start": "0:10.0",
        }])
        assert first["manual_saved"] == 1
        empty = teach_from_film_tool_rows(db, game_id, [{"eventtype": "StartQTR", "start": "0:00"}])
        assert empty["manual_saved"] == 0
        kept = db.execute(
            "SELECT COUNT(*) AS n FROM events WHERE game_id=? AND source_type='manual'",
            (game_id,),
        ).fetchone()
        assert kept["n"] == 1


def test_teach_manual_corrects_and_rejects_nearby_ai(client, app):
    game_id = "jrhigh_adrian,_or_TEACH"
    with app.app_context():
        db = get_db()
        db.execute(
            """INSERT INTO events
                  (game_id, player, event_type, shot_result, timestamp_ms,
                   human_verified, source_type, review_status, confidence)
               VALUES (?, 'Mendoza', 'made_two', 'make', 40700, 0, 'ai', 'pending', 0.9)""",
            (game_id,),
        )
        db.execute(
            """INSERT INTO events
                  (game_id, player, event_type, shot_result, timestamp_ms,
                   human_verified, source_type, review_status, confidence)
               VALUES (?, 'Foster', 'made_two', 'make', 44000, 0, 'ai', 'pending', 0.9)""",
            (game_id,),
        )
        db.commit()

    response = client.post(
        f"/api/film/{game_id}/teach-manual",
        json={
            "rows": [{
                "eventtype": "2PT",
                "result": "Make",
                "player": "0 Sullivan",
                "team": "Liberty",
                "start": "0:40.7",
                "label": "2PT Make",
            }]
        },
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["ok"] is True
    assert data["manual_saved"] == 1
    assert data["corrected"] == 1
    assert data["rejected"] == 1

    with app.app_context():
        db = get_db()
        manual = db.execute(
            "SELECT player, human_verified, source_type FROM events WHERE game_id=? AND source_type='manual'",
            (game_id,),
        ).fetchone()
        assert manual["player"] == "0 Sullivan"
        assert manual["human_verified"] == 1
        corrected = db.execute(
            """SELECT player, review_status FROM events
                WHERE game_id=? AND source_type='ai' AND review_status='corrected'""",
            (game_id,),
        ).fetchone()
        assert "Sullivan" in (corrected["player"] or "")
        rejected = db.execute(
            """SELECT player FROM events
                WHERE game_id=? AND source_type='ai' AND review_status='rejected'""",
            (game_id,),
        ).fetchone()
        assert rejected["player"] == "Foster"
        notes = db.execute(
            "SELECT COUNT(*) AS n FROM human_corrections WHERE game_id=? AND notes LIKE '%Film Tool teach%'",
            (game_id,),
        ).fetchone()
        assert notes["n"] >= 2


def test_persist_events_keeps_manual_and_regrades_ai(app):
    game_id = "teach-persist-game"
    with app.app_context():
        db = get_db()
        teach_from_film_tool_rows(db, game_id, [{
            "eventtype": "2PT",
            "result": "Make",
            "player": "21 Colman",
            "team": "Liberty",
            "start": "0:10.0",
        }])
        persist_events(db, game_id, [{
            "game_id": game_id,
            "player": "track 5",
            "event_type": "made_two",
            "shot_result": "make",
            "timestamp_ms": 10000,
            "details_json": "{}",
            "confidence": 0.5,
        }])
        manuals = db.execute(
            "SELECT player FROM events WHERE game_id=? AND source_type='manual'",
            (game_id,),
        ).fetchall()
        assert len(manuals) == 1
        assert "Colman" in manuals[0]["player"]
        ai = db.execute(
            "SELECT player, review_status, human_verified FROM events WHERE game_id=? AND source_type='ai'",
            (game_id,),
        ).fetchone()
        assert ai["review_status"] == "corrected"
        assert ai["human_verified"] == 1
        assert "Colman" in (ai["player"] or "")


def test_manual_tags_sidecar_roundtrip(client, tmp_path, monkeypatch):
    import film_tool_tags

    monkeypatch.setattr(film_tool_tags, "TAGS_ROOT", tmp_path)
    game_id = "jrhigh_adrian,_or_TEST_TAGS"
    payload = {
        "rows": [{
            "eventtype": "2PT",
            "player": "0 Sullivan",
            "start": "0:40.7",
            "result": "Make",
            "label": "2PT Make",
        }],
        "ourTeam": "Liberty",
        "opponent": "Adrian",
    }
    posted = client.post(f"/api/film/{game_id}/manual-tags", json=payload)
    assert posted.status_code == 200
    body = posted.get_json()
    assert body["analysisGameId"] == game_id
    assert body["rows"][0]["player"] == "0 Sullivan"
    got = client.get(f"/api/film/{game_id}/manual-tags")
    assert got.status_code == 200
    assert got.get_json()["rows"][0]["player"] == "0 Sullivan"
