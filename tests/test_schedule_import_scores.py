"""Schedule PDF import should persist MaxPreps scores into games records."""


def _create_season(client):
    return client.post(
        "/api/seasons",
        json={
            "name": "2025-26 Import Test",
            "start_date": "2025-11-01",
            "end_date": "2026-03-31",
        },
    ).get_json()["id"]


def test_schedule_import_confirm_creates_game_records_with_scores(client, app):
    season = {
        "name": "2025-26",
        "start_date": "2025-11-01",
        "end_date": "2026-03-31",
    }
    games = [
        {
            "game_date": "2025-12-02",
            "opponent_name": "Marsing",
            "game_time": "19:30",
            "location_type": "home",
            "gender": "boys",
            "level": "varsity",
            "status": "completed",
            "liberty_score": 67,
            "opponent_score": 56,
            "result": "win",
            "is_conference": False,
        },
        {
            "game_date": "2025-12-04",
            "opponent_name": "Nyssa",
            "game_time": "20:00",
            "location_type": "home",
            "gender": "boys",
            "level": "varsity",
            "status": "completed",
            "liberty_score": 51,
            "opponent_score": 70,
            "result": "loss",
            "is_conference": False,
        },
    ]

    response = client.post(
        "/api/schedule/import-pdf/confirm",
        json={"games": games, "team": "boys_hs", "season": season},
    )
    assert response.status_code == 200
    assert response.get_json()["imported"] == 2

    with app.app_context():
        from helpers import get_db

        db = get_db()
        season_id = db.execute(
            "SELECT id FROM seasons WHERE name = ?",
            (season["name"],),
        ).fetchone()["id"]
        scheduled = db.execute(
            """SELECT sg.opponent_name, sg.status, g.home_score, g.away_score, g.result
               FROM scheduled_games sg
               LEFT JOIN games g ON g.scheduled_game_id = sg.id
               ORDER BY sg.game_date"""
        ).fetchall()

    assert len(scheduled) == 2
    assert scheduled[0]["opponent_name"] == "Marsing"
    assert scheduled[0]["status"] == "completed"
    assert scheduled[0]["home_score"] == 67
    assert scheduled[0]["away_score"] == 56
    assert scheduled[0]["result"] == "win"
    assert scheduled[1]["result"] == "loss"

    dashboard = client.get(f"/api/teams/schedule?varsity_boys={season_id}")
    boys = next(t for t in dashboard.get_json()["teams"] if t["key"] == "varsity_boys")
    assert boys["wins"] == 1
    assert boys["losses"] == 1
