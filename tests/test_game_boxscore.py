"""Official box score: line score, team, individuals."""

from game_boxscore import (
    apply_ai_event,
    decorate_line,
    empty_line,
    even_split_line_score,
    line_from_scorebook_player,
    running_line_score,
    shooting_pct,
    sum_lines,
)


def test_scoreboard_lookup_does_not_invent_a_quarter():
    from scoreboard_clock import legal_clock, quarter_from_scoreboard, scoreboard_at

    assert scoreboard_at([], 90_000) is None
    assert scoreboard_at([{"timestamp_ms": 90_000, "period": 1, "clock": "7:46"}], 90_400)["clock"] == "7:46"
    assert scoreboard_at([{"timestamp_ms": 90_000, "period": 1}], 90_400)["period"] == 1
    assert scoreboard_at([{"timestamp_ms": 90_000, "period": 1}], 20_000) is None
    assert legal_clock("7:46")
    assert legal_clock("12:00")
    assert not legal_clock("7:62")
    assert not legal_clock("7:66")
    assert not legal_clock("3:6")
    assert not legal_clock(None)
    assert quarter_from_scoreboard({"period": 1, "clock": "7:46"}) == 1
    assert quarter_from_scoreboard({"period": 1}) is None
    assert quarter_from_scoreboard({"period": 1, "clock": "7:62"}) is None
    assert quarter_from_scoreboard({"clock": "7:46"}) is None


def test_shooting_pct_and_running_totals():
    assert shooting_pct(0, 0) is None
    assert shooting_pct(1, 2) == 50.0
    rows = running_line_score([(12, 8), (10, 6), (14, 9), (15, 3)])
    assert [r["period"] for r in rows] == ["Q1", "Q2", "Q3", "Q4"]
    assert rows[0]["liberty"] == 12 and rows[0]["liberty_running"] == 12
    assert rows[3]["liberty_running"] == 51
    assert rows[3]["opponent_running"] == 26


def test_scorebook_player_two_three_ft():
    line = decorate_line(line_from_scorebook_player({
        "jersey": "40",
        "name": "Dayley",
        "team": "away",
        "pts": 26,
        "fgm": 11,
        "tpm": 1,
        "ftm": 3,
        "fta": 4,
        "extras": {"fg2": 10, "fg3": 1},
    }))
    assert line["pts"] == 26
    assert line["fgm2"] == 10
    assert line["fgm3"] == 1
    assert line["ftm"] == 3
    assert line["fta"] == 4
    assert line["ft_pct"] == 75.0


def test_apply_ai_event_types():
    line = empty_line()
    assert apply_ai_event(line, "made_three") == 3
    assert apply_ai_event(line, "missed_two") == 0
    assert apply_ai_event(line, "steal") == 0
    assert apply_ai_event(line, "offensive_rebound") == 0
    assert apply_ai_event(line, "turnover") == 0
    out = decorate_line(line)
    assert out["pts"] == 3
    assert out["fgm3"] == 1
    assert out["fga2"] == 1
    assert out["stl"] == 1
    assert out["oreb"] == 1
    assert out["tov"] == 1
    skipped = empty_line()
    assert apply_ai_event(skipped, "shot", "make") == 0
    assert skipped["pts"] == 0


def test_sum_team_lines():
    a = decorate_line(line_from_scorebook_player({"pts": 15, "extras": {"fg2": 6, "fg3": 1}, "ftm": 0, "fta": 0}))
    b = decorate_line(line_from_scorebook_player({"pts": 11, "extras": {"fg2": 4, "fg3": 1}, "ftm": 0, "fta": 0}))
    total = sum_lines([a, b])
    assert total["pts"] == 26
    assert total["fgm2"] == 10
    assert total["fgm3"] == 2


def test_even_split_line_score_sums_to_final():
    rows = even_split_line_score(51, 26)
    assert [r["period"] for r in rows] == ["Q1", "Q2", "Q3", "Q4"]
    assert rows[-1]["liberty_running"] == 51
    assert rows[-1]["opponent_running"] == 26


def test_official_box_does_not_inflate_scorebook_player(db, monkeypatch):
    from game_boxscore import build_official_box

    analysis_key = "box_keep_book"
    book = {
        "home_team": "Adrian",
        "away_team": "Liberty",
        "final_score_home": 26,
        "final_score_away": 51,
        "players": [
            {
                "team": "away",
                "jersey": "40",
                "name": "Dayley",
                "pts": 26,
                "ftm": 3,
                "fta": 4,
                "extras": {"fg2": 10, "fg3": 1},
            },
            {"team": "home", "jersey": "13", "name": "Mendoza", "pts": 8},
        ],
    }
    monkeypatch.setattr("game_boxscore.load_scorebook", lambda gid: book)
    db.execute(
        """INSERT INTO analysis_runs (game_id, analysis_key, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (None, analysis_key, "uploads/demo.mp4"),
    )
    for i in range(80):
        db.execute(
            """INSERT INTO events
               (game_id, event_type, player, shot_result, timestamp_ms, human_verified, review_status)
               VALUES (?, 'made_two', '40', 'made', ?, 0, 'accepted')""",
            (analysis_key, 1000 + i * 100),
        )
    db.commit()

    box = build_official_box(db, analysis_key)
    dayley = next(p for p in box["players"]["liberty"] if p["name"] == "Dayley")
    assert dayley["pts"] == 26
    assert dayley["fgm2"] == 10
    assert dayley["ast"] == 0
    assert box["final"]["liberty"] == 51
    assert box["final"]["opponent"] == 26
    assert box["line_score"][-1]["liberty_running"] == 51
    assert box["line_score"][-1]["opponent_running"] == 26
    assert box["line_score_source"] == "scorebook_even_split"


def test_ai_box_uses_events_not_the_scorebook_points(db, monkeypatch):
    from game_boxscore import build_official_box

    analysis_key = "box_ai_events"
    book = {
        "home_team": "Adrian",
        "away_team": "Liberty",
        "final_score_home": 26,
        "final_score_away": 51,
        "quarters": [{"period": 1, "home_pts": 10, "away_pts": 16}],
        "players": [
            {"team": "away", "jersey": "40", "name": "Dayley", "pts": 26, "extras": {"fg2": 10, "fg3": 1}},
        ],
    }
    monkeypatch.setattr("game_boxscore.load_scorebook", lambda gid: book)
    db.execute(
        """INSERT INTO analysis_runs (game_id, analysis_key, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (None, analysis_key, "uploads/demo.mp4"),
    )
    db.execute(
        """INSERT INTO events
           (game_id, event_type, player, shot_result, timestamp_ms, human_verified, review_status)
           VALUES (?, 'made_two', '#40 Dayley', 'made', 1000, 0, 'accepted')""",
        (analysis_key,),
    )
    db.commit()

    box = build_official_box(db, analysis_key, event_counts=True)
    dayley = next(p for p in box["players"]["liberty"] if p["name"] == "Dayley")
    assert dayley["pts"] == 2
    assert box["final"]["liberty"] != 51
    assert box["line_score_source"] == "ai_events"


def test_duplicate_jersey_uses_home_light_away_dark(db, monkeypatch):
    import json
    from game_boxscore import build_official_box

    analysis_key = "box_color_11"
    book = {
        "home_team": "Adrian",
        "away_team": "Liberty",
        "final_score_home": 26,
        "final_score_away": 51,
        "players": [
            {"team": "away", "jersey": "11", "name": "Flores", "pts": 2, "extras": {"fg2": 1, "fg3": 0}},
            {"team": "home", "jersey": "11", "name": "Linkhart", "pts": 0, "extras": {"fg2": 0, "fg3": 0}},
        ],
    }
    monkeypatch.setattr("game_boxscore.load_scorebook", lambda gid: book)
    db.execute(
        """INSERT INTO analysis_runs (game_id, analysis_key, video_path, status)
           VALUES (?, ?, ?, 'completed')""",
        (None, analysis_key, "uploads/demo.mp4"),
    )
    db.execute(
        """INSERT INTO events
           (game_id, event_type, player, timestamp_ms, human_verified, review_status, details_json)
           VALUES (?, 'rebound_offensive', '#11', 1000, 0, 'accepted', ?)""",
        (analysis_key, json.dumps({"jersey_number": 11, "team_side": "away"})),
    )
    db.execute(
        """INSERT INTO events
           (game_id, event_type, player, timestamp_ms, human_verified, review_status, details_json)
           VALUES (?, 'rebound_offensive', '#11', 2000, 0, 'accepted', ?)""",
        (analysis_key, json.dumps({"jersey_number": 11, "team_side": "home"})),
    )
    db.execute(
        """INSERT INTO events
           (game_id, event_type, player, timestamp_ms, human_verified, review_status, details_json)
           VALUES (?, 'steal', '#11', 3000, 0, 'accepted', ?)""",
        (analysis_key, json.dumps({"jersey_number": 11, "team_side": "away"})),
    )
    db.commit()

    box = build_official_box(db, analysis_key)
    flores = next(p for p in box["players"]["liberty"] if p["name"] == "Flores")
    linkhart = next(p for p in box["players"]["opponent"] if p["name"] == "Linkhart")
    assert flores["pts"] == 2
    assert flores["oreb"] == 1
    assert flores["stl"] == 1
    assert linkhart["pts"] == 0
    assert linkhart["oreb"] == 1
    assert linkhart["stl"] == 0


def test_scorebook_totals_fill_two_point_line_without_extras():
    """Book fgm/fga are totals; the 2PT split is derived when extras.fg2 is missing."""
    player = {"jersey": "5", "name": "Book Only", "team": "home", "pts": 14, "fgm": 6, "fga": 13, "tpm": 0}
    line = decorate_line(line_from_scorebook_player(player))
    assert line["fgm2"] == 6
    assert line["fga2"] == 13
    assert line["fgm3"] == 0
    assert line["fg_pct"] == round(6 / 13 * 100, 1)


def test_scorebook_totals_subtract_threes_from_two_point_split():
    player = {"jersey": "3", "name": "Shooter", "team": "home", "pts": 17, "fgm": 7, "fga": 16, "tpm": 3, "tpa": 8}
    line = decorate_line(line_from_scorebook_player(player))
    assert (line["fgm2"], line["fga2"]) == (4, 8)
    assert (line["fgm3"], line["fga3"]) == (3, 8)


def test_unknown_home_away_final_matches_line_score(db, monkeypatch):
    """Neither team name says Liberty: Liberty = home everywhere, including team PTS."""
    import game_boxscore

    scorebook = {
        "home_team": "Patriots",
        "away_team": "Adrian",
        "final_score_home": 52,
        "final_score_away": 40,
        "quarters": [
            {"home_pts": 12, "away_pts": 10},
            {"home_pts": 14, "away_pts": 8},
            {"home_pts": 12, "away_pts": 12},
            {"home_pts": 14, "away_pts": 10},
        ],
    }
    monkeypatch.setattr(game_boxscore, "load_scorebook", lambda _gid: scorebook)
    box = game_boxscore.build_official_box(db, "unknown-home-away")
    assert box["line_score"][-1]["liberty_running"] == 52
    assert box["team"]["liberty"]["pts"] == 52
    assert box["team"]["opponent"]["pts"] == 40
    assert box["final"]["liberty"] == 52
