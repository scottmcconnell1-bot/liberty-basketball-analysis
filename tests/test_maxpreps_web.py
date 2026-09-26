"""Tests for MaxPreps HTTP ranking/schedule parsers."""

from maxpreps_web import (
    basketball_season_slug,
    parse_liberty_ranking,
    parse_schedule_results,
    ranking_url,
)
from datetime import date


RANKINGS_MD = """
| # | Team | Ovr. | Rating | Str. |
| --- | --- | --- | --- | --- |
| 16 | Valley | 17-7-0 | -3.33 | -9.2 |
| 17 | Liberty Charter | 14-11-0 | -4.07 | -6.7 |
| 18 | Victory Charter | 15-9-0 | -5.41 | -10.8 |
"""

GIRLS_RANKINGS_MD = """
| 12 | Liberty Charter | 18-9-0 | 1.72 | -7.4 |
"""

SCHEDULE_MD = """
| Date/Time | Opponent | Result | Watch | Game Info |
| --- | --- | --- | --- | --- |
| 12/2 7:30pm | vs Marsing | W 67-56 | Watch Replay | Box Score |
| 12/4 8:00pm | vs Nyssa | L 70-51 | | Box Score |
| 1/5 7:30pm | @ Idaho City* | W 65-40 | Watch Replay | Box Score |
| 2/4 7:30pm | vs GSAA* | W 69-56 | | Box Score |
"""


def test_parse_liberty_ranking_from_table():
    assert parse_liberty_ranking(RANKINGS_MD) == 17
    assert parse_liberty_ranking(GIRLS_RANKINGS_MD) == 12
    assert parse_liberty_ranking("no teams here") is None


def test_parse_schedule_results_scores_and_conference():
    games = parse_schedule_results(SCHEDULE_MD, season_start_year=2025)
    assert len(games) == 4
    marsing = games[0]
    assert marsing["game_date"] == "2025-12-02"
    assert marsing["opponent_name"] == "Marsing"
    assert marsing["result"] == "win"
    assert marsing["liberty_score"] == 67
    assert marsing["opponent_score"] == 56
    assert marsing["is_conference"] is False

    nyssa = games[1]
    assert nyssa["result"] == "loss"
    assert nyssa["liberty_score"] == 51
    assert nyssa["opponent_score"] == 70

    idaho = games[2]
    assert idaho["game_date"] == "2026-01-05"
    assert idaho["location_type"] == "away"
    assert idaho["is_conference"] is True
    assert idaho["liberty_score"] == 65

    gsaa = games[3]
    assert gsaa["opponent_name"] == "GSAA"
    assert gsaa["is_conference"] is True


def test_parse_schedule_aria_labels():
    html = '''
    <a aria-label="W 67-56 vs Marsing, 12/2"></a>
    <a aria-label="L 70-51 vs Nyssa, 12/4"></a>
    <p>On 1/5, the Liberty Charter varsity basketball team won their away conference game against Idaho City</p>
    <a aria-label="W 65-40 at Idaho City, 1/5"></a>
    '''
    games = parse_schedule_results(html, season_start_year=2025)
    assert [g["game_date"] for g in games] == ["2025-12-02", "2025-12-04", "2026-01-05"]
    assert games[0]["liberty_score"] == 67
    assert games[1]["liberty_score"] == 51
    assert games[1]["opponent_score"] == 70
    assert games[2]["location_type"] == "away"
    assert games[2]["is_conference"] is True


def test_playoff_conference_tournament_is_not_regular_conference():
    html = '''
    <p>On 2/26, the Compass Charter varsity basketball team won their away conference tournament game against Liberty Charter</p>
    <a aria-label="L 53-22 vs Compass Charter, 2/26"></a>
    '''
    games = parse_schedule_results(html, season_start_year=2025)
    assert games[0]["is_conference"] is False


def test_season_slug_and_ranking_url():
    assert basketball_season_slug(date(2026, 9, 15)) == "25-26"
    assert basketball_season_slug(date(2026, 11, 15)) == "26-27"
    url = ranking_url("Idaho", "boys", "25-26")
    assert "25-26" in url
    assert "statedivisionid=" in url


def _schedule_db():
    import sqlite3

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(
        """CREATE TABLE scheduled_games (
               id INTEGER PRIMARY KEY, season_id INTEGER, gender TEXT, level TEXT,
               game_date TEXT, opponent_name TEXT);
           INSERT INTO scheduled_games VALUES (1, 3, 'girls', 'varsity', '2026-01-09', 'Nampa Christian');
           INSERT INTO scheduled_games VALUES (2, 3, 'boys', 'varsity', '2026-01-09', 'Nampa Christian');
           INSERT INTO scheduled_games VALUES (3, 3, 'boys', 'jv', '2026-01-10', 'Adrian');
           INSERT INTO scheduled_games VALUES (4, 3, 'boys', 'jv', '2026-01-10', 'Vale');"""
    )
    return db


def _capture():
    saved = []

    def save_fn(db, game_id, liberty, opponent, is_conference=False):
        saved.append((game_id, liberty, opponent))

    return saved, save_fn


def test_apply_results_doubleheader_uses_gender_and_level():
    from maxpreps_web import apply_results_to_season

    saved, save_fn = _capture()
    parsed = [{"game_date": "2026-01-09", "opponent_name": "Nampa Christian", "liberty_score": 61, "opponent_score": 48}]
    matched, unmatched = apply_results_to_season(
        _schedule_db(), 3, parsed, save_fn, gender="boys", level="varsity"
    )
    assert (matched, unmatched) == (1, [])
    assert saved == [(2, 61, 48)]


def test_apply_results_same_date_resolved_by_opponent_or_reported():
    from maxpreps_web import apply_results_to_season

    saved, save_fn = _capture()
    parsed = [
        {"game_date": "2026-01-10", "opponent_name": "Vale", "liberty_score": 40, "opponent_score": 30},
        {"game_date": "2026-01-09", "opponent_name": "Nampa Christian", "liberty_score": 50, "opponent_score": 45},
    ]
    matched, unmatched = apply_results_to_season(_schedule_db(), 3, parsed, save_fn)
    # Vale picks game 4 by name; the 01-09 boys/girls tie cannot be split without gender.
    assert saved == [(4, 40, 30)]
    assert matched == 1
    assert len(unmatched) == 1 and "ambiguous" in unmatched[0]


def test_scrape_ranking_tries_browser_when_page_has_no_liberty_row(monkeypatch):
    import maxpreps_web

    monkeypatch.setattr(maxpreps_web, "fetch_url", lambda url: "<html><table></table></html>")
    monkeypatch.setattr(maxpreps_web, "_playwright_ranking_fallback", lambda url: 4)
    result = maxpreps_web.scrape_ranking("Idaho", "boys")
    assert result["ranking"] == 4
    assert result["error"] is None


def test_failed_ranking_scrape_keeps_cached_value(client, db, monkeypatch):
    import blueprints.core as core_mod

    db.execute(
        """INSERT INTO maxpreps_rankings (team_key, state, ranking, ranking_url)
           VALUES ('varsity_boys', 'Idaho', 3, 'https://example/boys')"""
    )
    db.commit()
    monkeypatch.setattr(
        core_mod, "_scrape_maxpreps_ranking",
        lambda state, gender: (None, f"https://example/{gender}", "403 Forbidden"),
    )
    resp = client.post("/api/teams/rankings", data={"state": "Idaho"})
    assert resp.status_code == 200
    row = db.execute(
        "SELECT ranking FROM maxpreps_rankings WHERE team_key='varsity_boys' AND state='Idaho'"
    ).fetchone()
    assert row["ranking"] == 3
