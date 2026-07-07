"""Tests for MaxPreps printable schedule PDF parsing."""

from schedule_import import (
    is_maxpreps_printable_schedule,
    parse_maxpreps_schedule_text,
)

MAXPREPS_SCHEDULE_TEXT = """America's Source for High School Sports
Liberty Charter Basketball Schedule (2025-26)
Date Opponent Result
12/2
7:30p
Marsing (Marsing, ID)
Location: Liberty Charter
(W) 67 - 56
12/4
8:00p
Nyssa (Nyssa, OR)
Game Details: Nyssa Tournament
(L) 70 - 51
1/5
7:30p
@ Idaho City (Idaho City, ID) *
Location: Idaho City High School
(W) 65 - 40
7/6/26, 9:52 PM Printable Liberty Charter High School Basketball Schedule
https://www.maxpreps.com/print/schedule.aspx?schoolid=abc&print=1 1/4
Date Opponent Result
1/30
7:30p
Wilder (Wilder, ID) *
Location: Liberty Charter
(W) 55 - 17
2/21
7:30p
Rimrock (Bruneau, ID) ****  (L) 51 - 38
Schedule Legend
"""

SEASON_INFO = {
    "name": "2025-26",
    "start_date": "2025-11-01",
    "end_date": "2026-03-31",
}


def test_is_maxpreps_printable_schedule():
    assert is_maxpreps_printable_schedule(MAXPREPS_SCHEDULE_TEXT)
    assert not is_maxpreps_printable_schedule("DATE OPPONENT TIMES\n12/01/2025 Riverside 7:00 PM")


def test_parse_maxpreps_schedule_text():
    games = parse_maxpreps_schedule_text(
        MAXPREPS_SCHEDULE_TEXT,
        pdf_team="boys_hs",
        season_info=SEASON_INFO,
    )
    assert len(games) == 5
    assert games[0]["game_date"] == "2025-12-02"
    assert games[0]["game_time"] == "19:30"
    assert games[0]["opponent_name"] == "Marsing"
    assert games[0]["location_type"] == "home"

    idaho_city = next(g for g in games if g["opponent_name"] == "Idaho City")
    assert idaho_city["game_date"] == "2026-01-05"
    assert idaho_city["location_type"] == "away"

    wilder = next(g for g in games if g["opponent_name"] == "Wilder")
    assert wilder["game_date"] == "2026-01-30"

    rimrock = next(g for g in games if g["opponent_name"] == "Rimrock")
    assert rimrock["game_date"] == "2026-02-21"
    assert rimrock["game_time"] == "19:30"

    nyssa = next(g for g in games if g["opponent_name"] == "Nyssa")
    assert nyssa["tournament_name"] == "Nyssa Tournament"


def test_parse_maxpreps_schedule_combined_pdfplumber_layout():
    text = """Date Opponent Result
12/2 Marsing (Marsing, ID) (W) 67 - 56
7:30p Location: Liberty Charter
12/9 @ Melba (Melba, ID) (L) 61 - 49
7:30p Location: Melba High School
7/6/26, 9:52 PM Printable Liberty Charter High School Basketball Schedule
"""
    games = parse_maxpreps_schedule_text(text, pdf_team="boys_hs", season_info=SEASON_INFO)
    assert len(games) == 2
    assert games[0]["opponent_name"] == "Marsing"
    assert games[0]["game_time"] == "19:30"
    assert games[1]["opponent_name"] == "Melba"
    assert games[1]["location_type"] == "away"


def test_parse_schedule_text_uses_maxpreps_parser():
    from blueprints.core import _parse_schedule_text

    games = _parse_schedule_text(
        MAXPREPS_SCHEDULE_TEXT,
        pdf_team="boys_hs",
        season_info=SEASON_INFO,
    )
    assert len(games) == 5
    assert games[0]["opponent_name"] == "Marsing"
    assert all(g["game_date"] != "2026-07-06" for g in games)
