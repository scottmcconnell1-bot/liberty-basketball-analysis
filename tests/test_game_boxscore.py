"""Official box score: line score, team, individuals."""

from game_boxscore import (
    apply_ai_event,
    decorate_line,
    empty_line,
    line_from_scorebook_player,
    running_line_score,
    shooting_pct,
    sum_lines,
)


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
