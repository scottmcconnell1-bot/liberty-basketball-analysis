"""Schedule-integrated game result recording tests."""


def _create_season(client):
    response = client.post(
        "/api/seasons",
        json={
            "name": "2025-26 Test",
            "start_date": "2025-11-01",
            "end_date": "2026-03-31",
        },
    )
    assert response.status_code == 201
    return response.get_json()["id"]


def test_schedule_record_game_saves_score_and_marks_complete(client, app):
    season_id = _create_season(client)
    scheduled = client.post(
        "/api/scheduled_games",
        json={
            "season_id": season_id,
            "game_date": "2025-12-10",
            "opponent_name": "Record Test Opponent",
            "location_type": "home",
        },
    ).get_json()

    response = client.post(
        f"/schedule/games/{scheduled['id']}/record",
        data={
            "liberty_score": "62",
            "opponent_score": "55",
            "is_conference": "1",
            "filter_season_id": season_id,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Game result saved." in response.data
    assert b"Record Test Opponent" in response.data
    assert b"62-55" in response.data

    with app.app_context():
        from helpers import get_db

        db = get_db()
        scheduled_row = db.execute(
            "SELECT status FROM scheduled_games WHERE id = ?",
            (scheduled["id"],),
        ).fetchone()
        game_row = db.execute(
            """SELECT home_score, away_score, result, is_conference
               FROM games WHERE scheduled_game_id = ?""",
            (scheduled["id"],),
        ).fetchone()

    assert scheduled_row["status"] == "completed"
    assert game_row["home_score"] == 62
    assert game_row["away_score"] == 55
    assert game_row["result"] == "win"
    assert game_row["is_conference"] == 1


def test_schedule_record_game_away_scores_map_correctly(client, app):
    season_id = _create_season(client)
    scheduled = client.post(
        "/api/scheduled_games",
        json={
            "season_id": season_id,
            "game_date": "2025-12-11",
            "opponent_name": "Away Opponent",
            "location_type": "away",
        },
    ).get_json()

    client.post(
        f"/schedule/games/{scheduled['id']}/record",
        data={
            "liberty_score": "48",
            "opponent_score": "52",
            "filter_season_id": season_id,
        },
        follow_redirects=True,
    )

    with app.app_context():
        from helpers import get_db

        db = get_db()
        game_row = db.execute(
            "SELECT home_score, away_score, result FROM games WHERE scheduled_game_id = ?",
            (scheduled["id"],),
        ).fetchone()

    assert game_row["home_score"] == 52
    assert game_row["away_score"] == 48
    assert game_row["result"] == "loss"


def test_schedule_shows_film_and_stats_links(client, app):
    season_id = _create_season(client)
    scheduled = client.post(
        "/api/scheduled_games",
        json={
            "season_id": season_id,
            "game_date": "2025-12-12",
            "opponent_name": "Linked Opponent",
            "location_type": "home",
        },
    ).get_json()

    client.post(
        f"/schedule/games/{scheduled['id']}/record",
        data={
            "liberty_score": "70",
            "opponent_score": "60",
            "filter_season_id": season_id,
        },
        follow_redirects=True,
    )

    with app.app_context():
        from helpers import get_db

        db = get_db()
        game_id = db.execute(
            "SELECT id FROM games WHERE scheduled_game_id = ?",
            (scheduled["id"],),
        ).fetchone()["id"]
        db.execute(
            """INSERT INTO videos
               (original_filename, stored_filename, file_path, relational_game_id)
               VALUES (?, ?, ?, ?)""",
            ("game.mp4", "linked-game.mp4", "/tmp/linked-game.mp4", game_id),
        )
        video_id = db.execute(
            "SELECT id FROM videos WHERE stored_filename = 'linked-game.mp4'"
        ).fetchone()["id"]
        db.execute(
            """INSERT INTO analysis_runs
               (game_id, analysis_key, video_path, status, source_video_id)
               VALUES (?, ?, ?, 'completed', ?)""",
            (game_id, "linked-analysis-key", "/tmp/linked-game.mp4", video_id),
        )
        db.commit()

    page = client.get(f"/schedule?season_id={season_id}")
    html = page.data.decode("utf-8")
    assert page.status_code == 200
    assert "Linked Opponent" in html
    assert "/analysis/linked-analysis-key" in html
    assert "/film/linked-game.mp4" in html
    assert "game_id=linked-analysis-key" in html


def test_games_page_redirects_to_schedule(client):
    response = client.get("/games")
    assert response.status_code == 302
    assert "/schedule" in response.headers["Location"]
