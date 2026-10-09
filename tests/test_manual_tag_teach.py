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


def test_map_foul_category_and_subtypes():
    plain = map_manual_row({"eventtype": "Foul", "category": "Defense", "start": "1:00"})
    assert plain["event_type"] == "foul"
    assert plain["family"] == "foul"
    assert plain["foul_type"] is None
    personal = map_manual_row({
        "eventtype": "Personal", "category": "Foul", "start": "2:00", "player": "12",
    })
    assert personal["event_type"] == "foul_personal"
    assert personal["foul_type"] == "personal"
    assert map_manual_row({"eventtype": "Shooting", "category": "Foul", "start": "3:00"})["event_type"] == "foul_shooting"
    assert map_manual_row({"eventtype": "Technical", "category": "Foul", "start": "4:00"})["event_type"] == "foul_technical"
    assert map_manual_row({"eventtype": "Shooting", "category": "Offense", "start": "5:00"}) is None


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
    assert data["corrected"] == 0
    assert data["rejected"] == 0

    with app.app_context():
        db = get_db()
        manual = db.execute(
            "SELECT player, human_verified, source_type FROM events WHERE game_id=? AND source_type='manual'",
            (game_id,),
        ).fetchone()
        assert manual["player"] == "0 Sullivan"
        assert manual["human_verified"] == 1
        players = db.execute(
            """SELECT player, review_status FROM events
                WHERE game_id=? AND source_type='ai' ORDER BY timestamp_ms""",
            (game_id,),
        ).fetchall()
        assert [row["player"] for row in players] == ["Mendoza", "Foster"]
        assert {row["review_status"] for row in players} == {"pending"}


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


def test_a_shot_between_quarters_is_rejected(app):
    from manual_tag_teach import reject_shots_when_the_ball_is_not_in_play

    game_id = "teach-between-quarters"
    with app.app_context():
        db = get_db()
        db.execute(
            """INSERT INTO events
                  (game_id, player, event_type, shot_result, timestamp_ms,
                   human_verified, source_type, review_status, confidence)
               VALUES (?, '#40 Dayley', 'missed_two', 'miss', 1038800, 0, 'ai', 'pending', 0.4)""",
            (game_id,),
        )
        db.execute(
            """INSERT INTO events
                  (game_id, player, event_type, shot_result, timestamp_ms, review_notes,
                   human_verified, source_type, review_status, confidence)
               VALUES (?, '#40 Dayley', 'shot', 'miss', 1038800, 'Auto-accepted (high confidence)',
                       1, 'ai', 'accepted', 0.9)""",
            (game_id,),
        )
        db.commit()
        report = reject_shots_when_the_ball_is_not_in_play(db, game_id, tag_rows=[
            {"eventtype": "EndQTR", "start": "16:00.7", "quarter": "Q1"},
            {"eventtype": "StartQTR", "start": "17:35.8", "quarter": "Q2"},
            {"eventtype": "2PT", "start": "18:00.0", "team": "Liberty", "result": "Miss"},
        ])
        statuses = db.execute(
            "SELECT event_type, review_status, review_notes FROM events WHERE game_id=? ORDER BY event_type",
            (game_id,),
        ).fetchall()
        assert report["rejected"] == 2
        assert {row["review_status"] for row in statuses} == {"rejected"}
        assert all("not in play" in row["review_notes"] for row in statuses)


def test_a_shot_by_the_team_on_defense_is_rejected(app):
    from manual_tag_teach import reject_shots_when_the_other_team_has_the_ball

    game_id = "teach-defense-no-shot"
    with app.app_context():
        db = get_db()
        db.execute(
            """INSERT INTO events
                  (game_id, player, event_type, shot_result, timestamp_ms, details_json,
                   human_verified, source_type, review_status, confidence)
               VALUES (?, '#40 Dayley', 'missed_two', 'miss', 151600, ?, 0, 'ai', 'pending', 0.4)""",
            (game_id, '{"team": "Liberty"}'),
        )
        db.commit()
        report = reject_shots_when_the_other_team_has_the_ball(db, game_id, tag_rows=[{
            "team": "Liberty",
            "side": "Defense",
            "eventtype": "OB",
            "start": "2:31.4",
        }])
        status = db.execute(
            "SELECT review_status, review_notes FROM events WHERE game_id=?",
            (game_id,),
        ).fetchone()
        assert report["rejected"] == 1
        assert status["review_status"] == "rejected"
        assert "did not have the ball" in status["review_notes"]
    game_id = "teach-shot-twin"
    with app.app_context():
        db = get_db()
        for event_type in ("shot", "made_two"):
            db.execute(
                """INSERT INTO events
                      (game_id, player, event_type, shot_result, timestamp_ms,
                       human_verified, source_type, review_status, confidence)
                   VALUES (?, '5', ?, 'make', 10000, 0, 'ai', 'pending', 0.4)""",
                (game_id, event_type),
            )
        db.commit()
        teach_from_film_tool_rows(db, game_id, [{
            "eventtype": "2PT",
            "result": "Make",
            "player": "40 - Dayley",
            "team": "Liberty",
            "start": "0:10.0",
        }])
        rows = db.execute(
            """SELECT event_type, player, review_status FROM events
                WHERE game_id=? AND source_type='ai' ORDER BY event_type""",
            (game_id,),
        ).fetchall()
        by_type = {row["event_type"]: row for row in rows}
        assert by_type["made_two"]["review_status"] == "corrected"
        assert "Dayley" in by_type["made_two"]["player"]
        assert by_type["shot"]["review_status"] == "pending"


def test_rerun_uses_the_base_films_manual_tags(app):
    from manual_tag_teach import apply_saved_manual_teach

    base = "jrhigh_adrian,_or_TEACH_BASE"
    rerun = base + "__rerun_20260929_010000"
    with app.app_context():
        db = get_db()
        teach_from_film_tool_rows(db, base, [{
            "eventtype": "2PT",
            "result": "Make",
            "player": "21 - Colman",
            "team": "Liberty",
            "start": "1:00.0",
        }])
        db.execute(
            """INSERT INTO events
                  (game_id, player, event_type, shot_result, timestamp_ms,
                   human_verified, source_type, review_status, confidence)
               VALUES (?, '8', 'made_two', 'make', 60000, 0, 'ai', 'pending', 0.4)""",
            (rerun,),
        )
        db.commit()
        report = apply_saved_manual_teach(db, rerun)
        assert report["corrected"] == 1
        row = db.execute(
            "SELECT player, event_type, review_status FROM events WHERE game_id=? AND source_type='ai'",
            (rerun,),
        ).fetchone()
        assert row["event_type"] == "made_two"
        assert row["review_status"] == "corrected"
        assert "Colman" in row["player"]


def test_make_between_tags_is_not_rejected(app):
    game_id = "teach-open-stretch"
    with app.app_context():
        db = get_db()
        db.execute(
            """INSERT INTO events
                  (game_id, player, event_type, shot_result, timestamp_ms,
                   human_verified, source_type, review_status, confidence)
               VALUES (?, '5', 'made_two', 'make', 60000, 0, 'ai', 'pending', 0.4)""",
            (game_id,),
        )
        db.commit()
        report = teach_from_film_tool_rows(db, game_id, [
            {"eventtype": "2PT", "result": "Make", "player": "40 - Dayley", "team": "Liberty", "start": "0:10.0"},
            {"eventtype": "2PT", "result": "Miss", "player": "21 - Colman", "team": "Liberty", "start": "2:00.0"},
        ])
        assert report["rejected"] == 0
        row = db.execute(
            "SELECT review_status, player FROM events WHERE game_id=? AND source_type='ai'",
            (game_id,),
        ).fetchone()
        assert row["review_status"] == "pending"
        assert row["player"] == "5"


def test_unmatched_tag_is_not_inserted_as_a_make(app):
    game_id = "teach-orphan-tag"
    with app.app_context():
        db = get_db()
        db.execute(
            """INSERT INTO events
                  (game_id, player, event_type, shot_result, timestamp_ms,
                   human_verified, source_type, review_status, confidence)
               VALUES (?, '5', 'made_two', 'make', 40000, 0, 'ai', 'pending', 0.4)""",
            (game_id,),
        )
        db.commit()
        report = teach_from_film_tool_rows(db, game_id, [{
            "eventtype": "2PT",
            "result": "Make",
            "player": "40 - Dayley",
            "team": "Liberty",
            "start": "0:10.0",
        }])
        assert report["unmatched_manual"] == 1
        assert report["corrected"] == 0
        rows = db.execute(
            "SELECT event_type, player, review_status, source_type FROM events WHERE game_id=?",
            (game_id,),
        ).fetchall()
        assert len(rows) == 2
        ai = [row for row in rows if row["source_type"] == "ai"][0]
        assert ai["event_type"] == "made_two"
        assert ai["review_status"] == "pending"
        assert ai["player"] == "5"


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


def test_tag_does_not_take_another_players_shot(app):
    from manual_tag_teach import reconcile_makes_with_shots

    game_id = "teach-do-not-steal"
    with app.app_context():
        db = get_db()
        db.execute(
            """INSERT INTO events
                  (game_id, player, event_type, shot_result, timestamp_ms,
                   details_json, source_type, review_status, confidence)
               VALUES (?, '#40 Dayley', 'made_two', 'make', 93000,
                       '{"film_tool_teach": true}', 'ai', 'corrected', 1)""",
            (game_id,),
        )
        db.execute(
            """INSERT INTO events
                  (game_id, player, event_type, shot_result, timestamp_ms,
                   details_json, source_type, review_status, confidence)
               VALUES (?, '#22 Foster', 'shot', 'make', 93000,
                       '{"through_rim": false, "net_moved": true, "generator": "precision"}',
                       'ai', 'pending', 0.5)""",
            (game_id,),
        )
        db.commit()
        report = reconcile_makes_with_shots(db, game_id)
        db.commit()
        assert report["reassigned"] == 0
        assert report["rejected"] == 0
        row = db.execute(
            "SELECT player, review_status FROM events WHERE game_id=? AND event_type='made_two'",
            (game_id,),
        ).fetchone()
        assert row["player"] == "#40 Dayley"
        assert row["review_status"] == "corrected"


def test_a_tagged_make_is_never_rejected_by_the_ai_shot(app):
    from manual_tag_teach import reconcile_makes_with_shots

    game_id = "teach-tag-is-truth"
    with app.app_context():
        db = get_db()
        db.execute(
            """INSERT INTO events
                  (game_id, player, event_type, shot_result, timestamp_ms,
                   details_json, source_type, review_status, human_verified, confidence)
               VALUES (?, '#40 Dayley', 'made_two', 'make', 48200,
                       '{"through_rim": false, "net_moved": false}', 'ai', 'corrected', 1, 1)""",
            (game_id,),
        )
        db.execute(
            """INSERT INTO events
                  (game_id, player, event_type, shot_result, timestamp_ms,
                   details_json, source_type, review_status, confidence)
               VALUES (?, '#40 Dayley', 'shot', 'miss', 48200,
                       '{"through_rim": false, "net_moved": false}', 'ai', 'pending', 0.5)""",
            (game_id,),
        )
        db.commit()
        report = reconcile_makes_with_shots(db, game_id)
        db.commit()
        assert report["rejected"] == 0
        row = db.execute(
            "SELECT review_status FROM events WHERE game_id=? AND event_type='made_two'",
            (game_id,),
        ).fetchone()
        assert row["review_status"] == "corrected"


def test_make_is_rejected_when_its_shot_did_not_go_in(app):
    from manual_tag_teach import reconcile_makes_with_shots

    game_id = "teach-not-a-make"
    with app.app_context():
        db = get_db()
        db.execute(
            """INSERT INTO events
                  (game_id, player, event_type, shot_result, timestamp_ms,
                   details_json, source_type, review_status, confidence)
               VALUES (?, '#40 Dayley', 'made_two', 'make', 48200,
                       '{"through_rim": false, "net_moved": false}', 'ai', 'pending', 1)""",
            (game_id,),
        )
        db.commit()
        report = reconcile_makes_with_shots(db, game_id)
        db.commit()
        assert report["rejected"] == 1
        row = db.execute(
            "SELECT review_status FROM events WHERE game_id=? AND event_type='made_two'",
            (game_id,),
        ).fetchone()
        assert row["review_status"] == "rejected"


def test_an_older_shorter_save_leaves_the_longer_tags_recoverable(tmp_path, monkeypatch):
    import json
    import film_tool_tags

    monkeypatch.setattr(film_tool_tags, "TAGS_ROOT", tmp_path)
    game_id = "jrhigh_adrian,_or_HISTORY"

    def rows(n):
        return [{"eventtype": "2PT", "start": f"{i}:00.0", "quarter": "Q1", "result": "Make"} for i in range(n)]

    film_tool_tags.save_manual_tags(game_id, {"rows": rows(378)})
    assert not (tmp_path / "_history").exists()  # nothing to keep yet
    film_tool_tags.save_manual_tags(game_id, {"rows": rows(246)})  # an older, shorter list arrives
    kept = sorted((tmp_path / "_history").glob("*.json"))
    assert len(kept) == 1
    assert "378rows" in kept[0].name
    assert len(json.loads(kept[0].read_text(encoding="utf-8"))["rows"]) == 378
    # Growing saves within two minutes do not pile up copies.
    film_tool_tags.save_manual_tags(game_id, {"rows": rows(247)})
    film_tool_tags.save_manual_tags(game_id, {"rows": rows(248)})
    assert len(sorted((tmp_path / "_history").glob("*.json"))) == 1


def test_history_keeps_recent_copies_then_one_per_hour(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone
    import film_tool_tags

    monkeypatch.setattr(film_tool_tags, "TAGS_ROOT", tmp_path)
    monkeypatch.setattr(film_tool_tags, "HISTORY_KEEP", 3)
    gid = "jrhigh_adrian,_or_THIN"
    folder = tmp_path / "_history"
    folder.mkdir()
    now = datetime.now(timezone.utc)

    def put(minutes_ago):
        stamp = (now - timedelta(minutes=minutes_ago)).strftime("%Y%m%dT%H%M%S%fZ")
        path = folder / f"{gid}__{stamp}__5rows.json"
        path.write_text("{}", encoding="utf-8")
        return path

    recent = [put(m) for m in (1, 2, 3)]
    # Three copies inside the same old hour, one from a week ago.
    base = 600
    old_same_hour = [put(base + k) for k in (0, 1, 2)]
    week = put(60 * 24 * 7)
    film_tool_tags._prune_history(sorted(folder.glob(f"{gid}__*.json")))
    left = {p.name for p in folder.glob("*.json")}
    assert all(p.name in left for p in recent)
    assert week.name not in left
    assert sum(p.name in left for p in old_same_hour) <= 2  # at most one per clock hour


def test_a_stale_tab_cannot_overwrite_newer_tags(client):
    game_id = "jrhigh_adrian,_or_STALE_TAB"

    def rows(n):
        return [{"eventtype": "2PT", "start": f"{i}:00.0", "quarter": "Q1", "result": "Make"} for i in range(n)]

    first = client.post(f"/api/film/{game_id}/manual-tags", json={"rows": rows(5)})
    assert first.status_code == 200
    base1 = first.get_json()["updatedAt"]
    second = client.post(
        f"/api/film/{game_id}/manual-tags",
        json={"rows": rows(8), "baseUpdatedAt": base1},
    )
    assert second.status_code == 200
    assert "baseUpdatedAt" not in second.get_json()
    # A tab still built on the first version tries to save.
    stale = client.post(
        f"/api/film/{game_id}/manual-tags",
        json={"rows": rows(6), "baseUpdatedAt": base1},
    )
    assert stale.status_code == 409
    assert stale.get_json()["stale"] is True
    # A tab opened before this check sent no version at all.
    old_tab = client.post(f"/api/film/{game_id}/manual-tags", json={"rows": rows(6)})
    assert old_tab.status_code == 409
    kept = client.get(f"/api/film/{game_id}/manual-tags").get_json()
    assert len(kept["rows"]) == 8
    # The Teach AI route is guarded the same way.
    taught = client.post(f"/api/film/{game_id}/teach-manual", json={"rows": rows(6)})
    assert taught.status_code == 409
    assert len(client.get(f"/api/film/{game_id}/manual-tags").get_json()["rows"]) == 8
    # A script that means to replace the copy can say so.
    forced = client.post(
        f"/api/film/{game_id}/manual-tags",
        json={"rows": rows(9), "force": True},
    )
    assert forced.status_code == 200


def test_empty_manual_tags_do_not_replace_saved_rows(client):
    game_id = "jrhigh_adrian,_or_KEEP_TAGS"
    payload = {
        "rows": [{
            "eventtype": "EndQTR",
            "start": "32:15.0",
            "quarter": "Q2",
            "result": "NA",
        }],
    }
    saved = client.post(f"/api/film/{game_id}/manual-tags", json=payload)
    assert saved.status_code == 200
    wiped = client.post(f"/api/film/{game_id}/manual-tags", json={"rows": []})
    assert wiped.status_code == 409
    kept = client.get(f"/api/film/{game_id}/manual-tags").get_json()
    assert kept["rows"][0]["start"] == "32:15.0"
    taught = client.post(f"/api/film/{game_id}/teach-manual", json={"rows": []})
    assert taught.status_code == 409
    kept = client.get(f"/api/film/{game_id}/manual-tags").get_json()
    assert kept["rows"][0]["start"] == "32:15.0"
    cleared = client.post(
        f"/api/film/{game_id}/manual-tags",
        json={"rows": [], "confirmClear": True, "baseUpdatedAt": saved.get_json()["updatedAt"]},
    )
    assert cleared.status_code == 200
    assert cleared.get_json()["rows"] == []


def test_video_tag_pages_list_manual_and_ai(client, db):
    game_id = "tag_pages_game"
    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("tags.mp4", "tags.mp4", "uploads/tags.mp4", 1000, "Adrian", game_id),
    )
    db.execute(
        "INSERT INTO analysis_runs (analysis_key, video_path, status) VALUES (?, ?, ?)",
        (game_id, "uploads/tags.mp4", "completed"),
    )
    db.execute(
        """INSERT INTO events
           (game_id, player, event_type, shot_result, timestamp_ms, source_type, review_status)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (game_id, "0 Sullivan", "made_two", "make", 40700, "ai", "pending"),
    )
    db.commit()
    video_id = db.execute(
        "SELECT id FROM videos WHERE game_id=?",
        (game_id,),
    ).fetchone()["id"]
    posted = client.post(
        f"/api/film/{game_id}/manual-tags",
        json={"rows": [{"eventtype": "EndQTR", "start": "32:15.0", "quarter": "Q2", "player": "Sullivan"}]},
    )
    assert posted.status_code == 200

    manual = client.get(f"/videos/{video_id}/manual-tags")
    assert manual.status_code == 200
    assert b"Manual tags" in manual.data
    assert b"32:15.0" in manual.data
    assert b"Sullivan" in manual.data

    ai = client.get(f"/videos/{video_id}/ai-tags")
    assert ai.status_code == 200
    assert b"AI tags" in ai.data
    assert b"Made two" in ai.data
    assert b"0 Sullivan" in ai.data
    assert b"32:15.0" not in ai.data


def test_unfinished_manual_tags_are_not_complete(client, db):
    game_id = "continue_tags_game"
    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("cont.mp4", "cont.mp4", "uploads/cont.mp4", 1000, "Adrian", game_id),
    )
    db.commit()
    posted = client.post(
        f"/api/film/{game_id}/manual-tags",
        json={"rows": [{"eventtype": "EndQTR", "start": "32:15.0", "quarter": "Q2", "result": "NA"}],
              "lastTaggedTime": "32:15.0"},
    )
    assert posted.status_code == 200
    videos = client.get("/api/videos?light=1").get_json()
    row = next(item for item in videos if item["game_id"] == game_id)
    assert row["manual_tag_count"] == 1
    assert row["manual_complete"] is False
    assert row["manual_last_time"] == "32:15.0"
    finished = client.post(
        f"/api/film/{game_id}/manual-tags",
        json={"rows": [{"eventtype": "EndQTR", "start": "64:00.0", "quarter": "Q4", "result": "NA"}],
              "lastTaggedTime": "64:00.0",
              "baseUpdatedAt": posted.get_json()["updatedAt"]},
    )
    assert finished.status_code == 200
    videos = client.get("/api/videos?light=1").get_json()
    row = next(item for item in videos if item["game_id"] == game_id)
    assert row["manual_complete"] is True


def test_film_continue_flag_for_a_coach_session(client):
    page = client.get("/film/cont.mp4?game_id=continue_tags_game&continue=1")
    assert page.status_code == 200
    assert b"FILM_TOOL_CONTINUE = true" in page.data
    assert b"AUDIENCE_CAN_EDIT = true" in page.data
    assert b"continueTaggingBtn" in page.data


def test_videos_page_offers_tag_lists_and_click_away(client):
    page = client.get("/videos")
    assert page.status_code == 200
    body = page.data
    assert b"Manual tags" in body
    assert b"AI tags" in body
    assert b"Tag this film by hand" in body
    assert b"Accept or reject AI marks" in body
    assert b"Continue tagging" in body
    assert b"row-actions-menu[open]" in body
    assert b"trackOpenActionMenu" in body
