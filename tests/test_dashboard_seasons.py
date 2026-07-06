"""Dashboard season filtering tests."""


def test_teams_schedule_filters_by_season(client, app):
    with app.app_context():
        from helpers import get_db
        db = get_db()
        db.execute(
            "INSERT INTO seasons (name, start_date, end_date, season_type) VALUES (?,?,?,?)",
            ("2021-22 Boys", "2021-11-01", "2022-03-31", "regular"),
        )
        db.execute(
            "INSERT INTO seasons (name, start_date, end_date, season_type) VALUES (?,?,?,?)",
            ("Summer 2026", "2026-06-01", "2026-08-31", "summer"),
        )
        db.commit()
        winter_id = db.execute("SELECT id FROM seasons WHERE name='2021-22 Boys'").fetchone()["id"]
        summer_id = db.execute("SELECT id FROM seasons WHERE name='Summer 2026'").fetchone()["id"]
        db.execute(
            """INSERT INTO scheduled_games
               (season_id, program_name, team, gender, level, game_date, opponent_name, status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (winter_id, "Liberty", "boys_hs", "boys", "varsity", "2022-01-15", "Winter Opponent", "completed"),
        )
        db.execute(
            """INSERT INTO scheduled_games
               (season_id, program_name, team, gender, level, game_date, opponent_name, status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (summer_id, "Liberty", "boys_hs", "boys", "varsity", "2026-07-15", "Summer Tourney", "scheduled"),
        )
        db.execute(
            """INSERT INTO scheduled_games
               (season_id, program_name, team, gender, level, game_date, opponent_name, status)
               VALUES (?,?,?,?,?,?,?,?)""",
            (winter_id, "Liberty", "jr_boys", "boys", "jr_high", "2022-02-01", "Jr High Only", "scheduled"),
        )
        sg_winter = db.execute(
            "SELECT id FROM scheduled_games WHERE opponent_name='Winter Opponent'"
        ).fetchone()["id"]
        db.execute(
            """INSERT INTO games
               (scheduled_game_id, source_type, source_key, home_score, away_score, result)
               VALUES (?,?,?,?,?,?)""",
            (sg_winter, "manual", "winter-game", 50, 40, "win"),
        )
        db.commit()

    blank_resp = client.get("/api/teams/schedule?varsity_boys=")
    boys_blank = next(t for t in blank_resp.get_json()["teams"] if t["key"] == "varsity_boys")
    assert boys_blank["season_id"] is None
    assert boys_blank["wins"] == 1

    winter_resp = client.get(f"/api/teams/schedule?varsity_boys={winter_id}")
    boys_winter = next(t for t in winter_resp.get_json()["teams"] if t["key"] == "varsity_boys")
    assert boys_winter["wins"] == 1
    assert boys_winter["season_id"] == winter_id
    assert {s["id"] for s in boys_winter["seasons"]} == {winter_id, summer_id}
    assert all(s["id"] != winter_id or s["name"] == "2021-22 Boys" for s in boys_winter["seasons"])

    jr_high = next(t for t in winter_resp.get_json()["teams"] if t["key"] == "jr_high_boys")
    assert winter_id in {s["id"] for s in jr_high["seasons"]}
    assert summer_id not in {s["id"] for s in jr_high["seasons"]}

    summer_resp = client.get(f"/api/teams/schedule?varsity_boys={summer_id}")
    boys_summer = next(t for t in summer_resp.get_json()["teams"] if t["key"] == "varsity_boys")
    assert boys_summer["wins"] == 0
    assert len(boys_summer["upcoming"]) == 1
    assert boys_summer["upcoming"][0]["opponent_name"] == "Summer Tourney"

    payload_resp = client.get("/api/teams/schedule")
    assert payload_resp.status_code == 200
    payload = payload_resp.get_json()
    assert "teams" in payload
    boys_default = next(t for t in payload["teams"] if t["key"] == "varsity_boys")
    assert "seasons" in boys_default
    assert summer_id in {s["id"] for s in boys_default["seasons"]}


def test_dashboard_index_renders_season_select(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "team-season-select" in html
    assert "onTeamSeasonChange" in html
