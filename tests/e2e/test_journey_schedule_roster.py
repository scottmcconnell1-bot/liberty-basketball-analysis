"""End-to-end journeys: seasons, schedule, games & sources, dashboard records, rosters,
team photos, playbook bulk import and season rollover/archive.

Every journey drives the real HTTP routes (Flask test client, temp DB + temp uploads from
tests/conftest.py) and asserts exact rows / records, not just status codes.

Tests marked ``xfail(strict=True, reason="BUG: ...")`` assert the CORRECT behaviour for a
defect that exists in the app today; they flip to XPASS (and fail the run) once fixed.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.e2e import data as td

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
JSON = "application/json"


# ── helpers ──────────────────────────────────────────────────────────────────

def _j(client, method, path, payload, expect=(200, 201)):
    r = getattr(client, method)(path, data=json.dumps(payload), content_type=JSON)
    assert r.status_code in expect, f"{method.upper()} {path} -> {r.status_code}: {r.data[:300]!r}"
    return r.get_json()


def _form(client, path, data, expect=(302, 303)):
    r = client.post(path, data=data, follow_redirects=False)
    assert r.status_code in expect, f"POST {path} -> {r.status_code}: {r.data[:300]!r}"
    return r


def _q(app, sql, params=()):
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _season_form(client, app, name, start, end):
    _form(client, "/schedule/seasons/save", {"name": name, "start_date": start, "end_date": end,
                                             "season_type": "regular"})
    return _q(app, "SELECT id FROM seasons WHERE name=?", (name,))[0]["id"]


def _game_form(client, app, season_id, *, team, level, gender, game_date, opponent,
               location="home", time_="19:00", status="scheduled", game_id=""):
    _form(client, "/schedule/games/save", {
        "game_id": game_id, "season_id": season_id, "program_name": "Liberty", "team": team,
        "gender": gender, "level": level, "game_date": game_date, "game_time": time_,
        "location_type": location, "opponent_name": opponent, "status": status, "notes": "",
    })
    if game_id:
        return int(game_id)
    return _q(app, "SELECT id FROM scheduled_games WHERE opponent_name=? AND game_date=? ORDER BY id DESC",
              (opponent, game_date))[0]["id"]


def _record(client, sg_id, liberty, opp, conf=False):
    data = {"liberty_score": str(liberty), "opponent_score": str(opp)}
    if conf:
        data["is_conference"] = "1"
    _form(client, f"/schedule/games/{sg_id}/record", data)


def _teams(client, query=""):
    r = client.get("/api/teams/schedule" + query)
    assert r.status_code == 200, r.data[:300]
    return {t["key"]: t for t in r.get_json()["teams"]}


def _record_of(team):
    return (team["wins"], team["losses"], team["conf_wins"], team["conf_losses"])


# A MaxPreps "printable schedule" as the PDF text layer pdfplumber extracts. Dec + Jan games
# straddle the calendar year; MaxPreps prints the winner's score first, so "(L) 61 - 48"
# means Liberty scored 48. "*" marks a conference opponent.
MAXPREPS_ROWS = [
    "Liberty Charter Basketball Schedule (2025-26)",
    "Date Opponent Result",
    "12/2 Marsing (Marsing, ID) (W) 67 - 56",
    "7:30p Location: Liberty Charter",
    "12/9 @ Vale * (L) 61 - 48",
    "7:00p",
    "12/16 Nampa Christian *",
    "1/6 @ Idaho City",
    "1/13 Rimrock * (W) 55 - 40",
    "1/20 @ Salmon River",
    "6:00p",
]
MAXPREPS_EXPECTED = [  # (date, opponent, location, liberty, opp, result, conference)
    ("2025-12-02", "Marsing", "home", 67, 56, "win", False),
    ("2025-12-09", "Vale", "away", 48, 61, "loss", True),
    ("2025-12-16", "Nampa Christian", "home", None, None, None, True),
    ("2026-01-06", "Idaho City", "away", None, None, None, False),
    ("2026-01-13", "Rimrock", "home", 55, 40, "win", True),
    ("2026-01-20", "Salmon River", "away", None, None, None, False),
]


def _upload_schedule_pdf(client, team="boys_hs", rows=MAXPREPS_ROWS):
    r = client.post("/api/schedule/import-pdf",
                    data={"pdf": (io.BytesIO(td.pdf_bytes([rows])), "schedule.pdf"), "team": team},
                    content_type="multipart/form-data")
    assert r.status_code == 200, r.data[:400]
    return r.get_json()


def _confirm_import(client, parsed, team="boys_hs", games=None):
    games = games if games is not None else parsed["games"]
    payload = {"games": games, "team": team, "season": parsed["season"],
               "raw_dates": [g.get("raw_date", "") for g in games],
               "original_dates": [g.get("game_date", "") for g in games]}
    return _j(client, "post", "/api/schedule/import-pdf/confirm", payload, expect=(200,))


# ── Journey 1: season → schedule (form + API) → scores → dashboard + schedule page ──

def test_journey_season_schedule_scores_dashboard(client, app):
    season = _season_form(client, app, "2025-26 Liberty", "2025-11-01", "2026-03-31")
    # Varsity boys: two December games and one after New Year (season spans the year boundary).
    vb1 = _game_form(client, app, season, team="boys_hs", level="varsity", gender="boys",
                     game_date="2025-12-12", opponent="Marsing")
    vb2 = _game_form(client, app, season, team="boys_hs", level="varsity", gender="boys",
                     game_date="2025-12-19", opponent="Vale", location="away")
    vb3 = _game_form(client, app, season, team="boys_hs", level="varsity", gender="boys",
                     game_date="2026-01-09", opponent="Rimrock")
    # Same dates/opponents for the girls and JV must not bleed into the boys' record.
    vg1 = _game_form(client, app, season, team="girls_hs", level="varsity", gender="girls",
                     game_date="2025-12-12", opponent="Marsing", location="away")
    vg2 = _game_form(client, app, season, team="girls_hs", level="varsity", gender="girls",
                     game_date="2026-01-09", opponent="Rimrock")
    jvb = _game_form(client, app, season, team="boys_hs", level="jv", gender="boys",
                     game_date="2025-12-12", opponent="Marsing", time_="17:30")
    future = _game_form(client, app, season, team="girls_hs", level="varsity", gender="girls",
                        game_date="2026-02-20", opponent="Nampa Christian")

    _record(client, vb1, 55, 40, conf=True)
    _record(client, vb2, 48, 61, conf=True)   # away loss
    _record(client, vb3, 70, 65)
    _record(client, vg1, 44, 30, conf=True)   # away win
    _record(client, vg2, 30, 35)
    _record(client, jvb, 40, 20)

    teams = _teams(client)
    assert teams["varsity_boys"]["season_id"] == season
    assert _record_of(teams["varsity_boys"]) == (2, 1, 1, 1)
    assert _record_of(teams["varsity_girls"]) == (1, 1, 1, 0)
    assert _record_of(teams["jv_boys"]) == (1, 0, 0, 0)
    assert _record_of(teams["jv_girls"]) == (0, 0, 0, 0)
    assert teams["varsity_boys"]["last_game"]["opponent_name"] == "Rimrock"
    assert teams["varsity_boys"]["last_game"]["result"] == "win"

    # Away scores are stored home/away but read back from Liberty's side.
    away = _j(client, "get", f"/api/scheduled_games?season_id={season}&gender=boys&level=varsity", None)
    by_opp = {g["opponent_name"]: g for g in away}
    assert (by_opp["Vale"]["liberty_score"], by_opp["Vale"]["opponent_score"]) == (48, 61)
    assert (by_opp["Vale"]["home_score"], by_opp["Vale"]["away_score"]) == (61, 48)
    assert [g["status"] for g in away] == ["completed"] * 3
    girls = _j(client, "get", f"/api/scheduled_games?season_id={season}&gender=girls", None)
    assert [(g["opponent_name"], g["liberty_score"], g["opponent_score"]) for g in girls] == [
        ("Marsing", 44, 30), ("Rimrock", 30, 35), ("Nampa Christian", None, None)]

    html = client.get(f"/schedule?season_id={season}").get_data(as_text=True)
    assert "48-61" in html and "44-30" in html and "70-65" in html

    # Edit a game in place (form) and correct a score: still one row, one games record.
    _game_form(client, app, season, team="boys_hs", level="varsity", gender="boys",
               game_date="2026-01-10", opponent="Rimrock Raiders", game_id=str(vb3))
    _record(client, vb3, 60, 65)
    rows = _q(app, "SELECT * FROM scheduled_games WHERE season_id=? AND team='boys_hs' AND level='varsity'", (season,))
    assert len(rows) == 3
    assert _q(app, "SELECT game_date, opponent_name FROM scheduled_games WHERE id=?", (vb3,)) == [
        {"game_date": "2026-01-10", "opponent_name": "Rimrock Raiders"}]
    assert _q(app, "SELECT home_score, away_score, result FROM games WHERE scheduled_game_id=?", (vb3,)) == [
        {"home_score": 60, "away_score": 65, "result": "loss"}]
    assert _record_of(_teams(client)["varsity_boys"]) == (1, 2, 1, 1)

    # API edit of an unscored game.
    _j(client, "put", f"/api/scheduled_games/{future}", {"game_time": "18:00", "notes": "senior night"})
    assert _q(app, "SELECT game_time, notes, team FROM scheduled_games WHERE id=?", (future,)) == [
        {"game_time": "18:00", "notes": "senior night", "team": "girls_hs"}]

    # MaxPreps CSV export lists only still-scheduled games, with team/level/gender labels.
    r = client.get("/schedule/export/maxpreps")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    rows = list(csv.reader(io.StringIO(r.get_data(as_text=True))))
    assert rows[0][:4] == ["Date", "JV Time", "Frosh Time", "Varsity Time"]
    assert rows[1:] == [["2026-02-20", "", "", "18:00", "Nampa Christian", "Home", "Girls HS", "Varsity",
                         "Girls", "", "No", "2025-26 Liberty"]]

    # Validation paths return 400 and write nothing.
    before = len(_q(app, "SELECT id FROM scheduled_games"))
    assert client.post("/schedule/games/save", data={"season_id": season, "game_date": "",
                                                     "opponent_name": "X"}).status_code == 400
    assert client.post(f"/schedule/games/{vb1}/record", data={"liberty_score": "abc",
                                                             "opponent_score": "4"}).status_code == 400
    assert _j(client, "post", "/api/scheduled_games", {"season_id": season}, expect=(400,))["error"]
    assert client.post("/schedule/seasons/save", data={"name": "2025-26 Liberty", "start_date": "2025-11-01",
                                                       "end_date": "2026-03-31"}).status_code == 409
    assert len(_q(app, "SELECT id FROM scheduled_games")) == before


@pytest.mark.xfail(strict=True, reason="BUG: POST /api/scheduled_games never sets `team`, so girls/jr-high games "
                                       "default to team='boys_hs' and count on the Varsity Boys card")
def test_api_created_girls_game_counts_for_girls_card(client, app):
    season = _j(client, "post", "/api/seasons", {"name": "2025-26", "start_date": "2025-11-01",
                                                 "end_date": "2026-03-31"})["id"]
    g = _j(client, "post", "/api/scheduled_games", {"season_id": season, "game_date": "2025-12-05",
                                                    "opponent_name": "Vale", "gender": "girls",
                                                    "level": "varsity"})
    _record(client, g["id"], 50, 40)
    teams = _teams(client)
    assert _record_of(teams["varsity_girls"])[:2] == (1, 0)
    assert _record_of(teams["varsity_boys"])[:2] == (0, 0)


@pytest.mark.xfail(strict=True, reason="BUG: dashboard record/recent join every games row of a scheduled game, "
                                       "so a second linked games row (film/API) double-counts it")
def test_dashboard_counts_each_scheduled_game_once(client, app):
    season = _season_form(client, app, "2025-26", "2025-11-01", "2026-03-31")
    sg = _game_form(client, app, season, team="boys_hs", level="varsity", gender="boys",
                    game_date="2025-12-05", opponent="Vale")
    _record(client, sg, 60, 50)
    # A film/source record for the same scheduled game (the schedule page itself shows the latest row).
    _j(client, "post", "/api/games", {"scheduled_game_id": sg, "source_type": "manual",
                                      "source_key": "film-vale", "home_score": 60, "away_score": 50,
                                      "result": "win"})
    vb = _teams(client)["varsity_boys"]
    assert (vb["wins"], vb["losses"]) == (1, 0)
    assert [g["opponent_name"] for g in vb["recent"]] == ["Vale"]


@pytest.mark.xfail(strict=True, reason="BUG: dashboard upcoming/recent compare game_date to SQLite date('now') "
                                       "(UTC) instead of the local calendar day")
def test_dashboard_upcoming_uses_local_calendar_day(client, app):
    # Pick a zone whose calendar day differs from UTC right now, so the result is deterministic.
    utc_hour = datetime.now(timezone.utc).hour
    old_tz = os.environ.get("TZ")
    os.environ["TZ"] = "Etc/GMT+12" if utc_hour < 12 else "Etc/GMT-12"
    time.tzset()
    try:
        today = date.today()
        assert today != datetime.now(timezone.utc).date()
        season = _j(client, "post", "/api/seasons", {"name": "Now", "start_date": (today - timedelta(days=30)).isoformat(),
                                                     "end_date": (today + timedelta(days=30)).isoformat()})["id"]
        _game_form(client, app, season, team="boys_hs", level="varsity", gender="boys",
                   game_date=today.isoformat(), opponent="Tonight Opp")
        _game_form(client, app, season, team="boys_hs", level="varsity", gender="boys",
                   game_date=(today - timedelta(days=1)).isoformat(), opponent="Yesterday Opp")
        vb = _teams(client)["varsity_boys"]
        assert [g["opponent_name"] for g in vb["upcoming"]] == ["Tonight Opp"]
        assert [g["opponent_name"] for g in vb["recent"]] == ["Yesterday Opp"]
    finally:
        if old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old_tz
        time.tzset()


# ── Journey 2: MaxPreps schedule PDF import → scores → dashboard; re-import ────────

def test_journey_maxpreps_pdf_import_across_new_year(client, app):
    parsed = _upload_schedule_pdf(client)
    assert parsed["parser"] == "maxpreps" and parsed["count"] == 6
    assert parsed["season"] == {"name": "Liberty Charter Basketball Schedule (2025-26)",
                                "start_date": "2025-11-01", "end_date": "2026-03-31"}
    got = [(g["game_date"], g["opponent_name"], g["location_type"], g["liberty_score"], g["opponent_score"],
            g["result"], g["is_conference"]) for g in parsed["games"]]
    assert got == MAXPREPS_EXPECTED
    assert parsed["games"][0]["game_time"] == "19:30"
    assert {(g["team"], g["level"], g["gender"]) for g in parsed["games"]} == {("boys_hs", "varsity", "boys")}

    res = _confirm_import(client, parsed)
    assert res["imported"] == 6 and "errors" not in res
    seasons = _q(app, "SELECT id, name, start_date, end_date FROM seasons")
    assert len(seasons) == 1
    sid = seasons[0]["id"]
    sched = _j(client, "get", f"/api/scheduled_games?season_id={sid}", None)
    assert [(g["game_date"], g["opponent_name"], g["location_type"], g["liberty_score"], g["opponent_score"],
             g["result"], (bool(g["is_conference"]) if g["game_record_id"] else g["is_conference"]))
            for g in sched] == [
        (d, o, loc, ls, os_, res_, (conf if ls is not None else None))
        for d, o, loc, ls, os_, res_, conf in MAXPREPS_EXPECTED]
    assert [g["status"] for g in sched] == ["completed", "completed", "scheduled", "scheduled", "completed", "scheduled"]
    assert _record_of(_teams(client)["varsity_boys"]) == (2, 1, 1, 1)

    # Record a result for a game that was still scheduled: updates the dashboard exactly.
    idaho_city = next(g for g in sched if g["opponent_name"] == "Idaho City")
    _record(client, idaho_city["id"], 52, 50)
    assert _q(app, "SELECT home_score, away_score, result FROM games WHERE scheduled_game_id=?",
              (idaho_city["id"],)) == [{"home_score": 50, "away_score": 52, "result": "win"}]
    assert _record_of(_teams(client)["varsity_boys"]) == (3, 1, 1, 1)


JR_GIRLS_ROWS = [
    "TUES, DEC 2 MARSING (H) 4:30/6:00",
    "THURS, DEC 4 VALE (A) 4:30/6:00",
    "MON, DEC 8 RIMROCK (H) 5:00/6:15",
    "WED, DEC 10 NAMPA CHRISTIAN (A) 4:30/6:00",
    "FRI, DEC 12 IDAHO CITY (H) 4:00/5:15",
]
# Jr High rows: first time is the B team (jv_game_time), second the A team (game_time).
# The parser stores bare times as-is ("4:30" -> "04:30"), as tests/test_schedule_import_export.py pins.
JR_GIRLS_EXPECTED = [
    ("2025-12-02", "MARSING", "home", "04:30", "06:00"),
    ("2025-12-04", "VALE", "away", "04:30", "06:00"),
    ("2025-12-08", "RIMROCK", "home", "05:00", "06:15"),
    ("2025-12-10", "NAMPA CHRISTIAN", "away", "04:30", "06:00"),
    ("2025-12-12", "IDAHO CITY", "home", "04:00", "05:15"),
]


def _jr_rows(parsed):
    return [(g["game_date"], g["opponent_name"], g["location_type"], g["jv_game_time"], g["game_time"])
            for g in parsed["games"]]


def test_legacy_pdf_jr_high_ab_times(client, app):
    rows = ["LIBERTY CHARTER JR HIGH GIRLS 2025-26 SCHEDULE", "DATE OPPONENT TIMES"] + JR_GIRLS_ROWS
    parsed = _upload_schedule_pdf(client, team="jr_girls", rows=rows)
    assert parsed["parser"] == "legacy"
    assert parsed["season"]["start_date"] == "2025-11-01" and parsed["season"]["end_date"] == "2025-12-31"
    assert _jr_rows(parsed) == JR_GIRLS_EXPECTED
    assert {(g["level"], g["gender"], g["team"]) for g in parsed["games"]} == {("jr_high", "girls", "jr_girls")}
    assert _confirm_import(client, parsed, team="jr_girls")["imported"] == 5
    stored = _q(app, "SELECT team, level, gender, COUNT(*) AS n FROM scheduled_games GROUP BY 1,2,3")
    assert stored == [{"team": "jr_girls", "level": "jr_high", "gender": "girls", "n": 5}]
    sg = _q(app, "SELECT id FROM scheduled_games WHERE opponent_name='VALE'")[0]["id"]
    _record(client, sg, 22, 30)
    assert _record_of(_teams(client)["jr_high_girls"])[:2] == (0, 1)
    assert _record_of(_teams(client)["varsity_girls"])[:2] == (0, 0)


@pytest.mark.xfail(strict=True, reason="BUG: legacy PDF parser (no 'DATE OPPONENT TIMES' header) treats "
                                       "'TUES, DEC 4 ...' rows as continuations and merges the schedule into one game")
def test_legacy_pdf_rows_without_column_header(client, app):
    rows = ["Liberty Jr High Girls Schedule 2025-26"] + JR_GIRLS_ROWS
    parsed = _upload_schedule_pdf(client, team="jr_girls", rows=rows)
    assert _jr_rows(parsed) == JR_GIRLS_EXPECTED


@pytest.mark.xfail(strict=True, reason="BUG: /api/schedule/import-pdf/confirm always INSERTs; re-importing the "
                                       "same schedule duplicates every game and double-counts records")
def test_reimport_same_schedule_does_not_duplicate(client, app):
    parsed = _upload_schedule_pdf(client)
    _confirm_import(client, parsed)
    _confirm_import(client, _upload_schedule_pdf(client))
    assert len(_q(app, "SELECT id FROM scheduled_games")) == 6
    assert len(_q(app, "SELECT id FROM games")) == 3
    assert _record_of(_teams(client)["varsity_boys"]) == (2, 1, 1, 1)


@pytest.mark.xfail(strict=True, reason="BUG: import confirm stores the modal's pdf team for every row and ignores "
                                       "the per-row Program (team) the review table lets the coach change")
def test_import_confirm_honours_per_row_team(client, app):
    parsed = _upload_schedule_pdf(client)
    games = [dict(g) for g in parsed["games"]]
    games[0].update(team="girls_hs", gender="girls")  # coach flips one row to the girls' game
    _confirm_import(client, parsed, games=games)
    row = _q(app, "SELECT team, gender FROM scheduled_games WHERE opponent_name='Marsing'")[0]
    assert row == {"team": "girls_hs", "gender": "girls"}
    teams = _teams(client)
    assert (teams["varsity_girls"]["wins"], teams["varsity_boys"]["wins"]) == (1, 1)


# ── Journey 3: rosters (film-roster import), roster parsing, players, team photos ──

ROSTER_V1 = (
    "POS,#,NAME,GRADE\n"
    "PG,00,D'Angelo O'Neil,12\n"
    'SG,3,"Ironwood, Blake",11\n'
    ",,,\n"
    "C,45,Emery Tallpine-Reyes,10\n"
    "F,21,Jordan Redcliff,9\n"
)
ROSTER_V2 = (  # next upload: C moved up a grade, #21 left, #2 joined
    "POS,#,NAME,GRADE\n"
    "PG,00,D'Angelo O'Neil,12\n"
    'SG,3,"Ironwood, Blake",11\n'
    "C,45,Emery Tallpine-Reyes,11\n"
    "G,2,Avery Northwind,9\n"
)


def _import_roster(client, csv_text, *, season_id, level="varsity", gender="boys", side="our",
                   opponent=None, replace=True):
    data = {"file": (io.BytesIO(csv_text.encode()), "roster.csv"), "file_type": "auto",
            "season_id": str(season_id), "level": level, "gender": gender, "side": side,
            "replace": "true" if replace else "false"}
    if opponent:
        data["opponent"] = opponent
    r = client.post("/api/film-rosters/import", data=data, content_type="multipart/form-data")
    assert r.status_code == 200, r.data[:300]
    return r.get_json()


def _roster(client, season_id, level="varsity", gender="boys", side="our", opponent=None):
    q = f"/api/film-rosters?season_id={season_id}&level={level}&gender={gender}&side={side}"
    if opponent:
        q += f"&opponent={opponent}"
    return [(p["jersey_number"], p["name"], p["position"], p["grade"])
            for p in _j(client, "get", q, None)["players"]]


def test_journey_roster_import_reimport_and_slots(client, app):
    season = _j(client, "post", "/api/seasons", {"name": "2025-26", "start_date": "2025-11-01",
                                                 "end_date": "2026-03-31"})["id"]
    res = _import_roster(client, ROSTER_V1, season_id=season)
    assert res["detected_type"] == "csv" and res["count"] == 4
    assert _roster(client, season) == [
        ("00", "D'Angelo O'Neil", "PG", "12"),
        ("3", "Ironwood, Blake", "SG", "11"),
        ("45", "Emery Tallpine-Reyes", "C", "10"),
        ("21", "Jordan Redcliff", "F", "9"),
    ]
    # Replace-mode re-import updates the slot instead of appending.
    assert _import_roster(client, ROSTER_V2, season_id=season)["count"] == 4
    assert _roster(client, season) == [
        ("00", "D'Angelo O'Neil", "PG", "12"),
        ("3", "Ironwood, Blake", "SG", "11"),
        ("45", "Emery Tallpine-Reyes", "C", "11"),
        ("2", "Avery Northwind", "G", "9"),
    ]
    # Other level/gender/opponent slots are independent.
    _import_roster(client, "POS,#,NAME,GRADE\nG,10,Harper Goldleaf,10\nF,24,Logan Whitecap,9\n",
                   season_id=season, gender="girls")
    _import_roster(client, "POS,#,NAME,GRADE\nG,5,Casey Riverbend,9\n", season_id=season, level="jv")
    _import_roster(client, "POS,#,NAME,GRADE\nC,44,Opp Echo,12\n", season_id=season, side="opp", opponent="Vale")
    assert [p[1] for p in _roster(client, season, gender="girls")] == ["Harper Goldleaf", "Logan Whitecap"]
    assert [p[1] for p in _roster(client, season, level="jv")] == ["Casey Riverbend"]
    assert _roster(client, season, side="opp", opponent="Vale") == [("44", "Opp Echo", "C", "12")]
    assert len(_roster(client, season)) == 4
    counts = _q(app, "SELECT level, gender, side, COUNT(*) AS n FROM film_roster_players GROUP BY 1,2,3 ORDER BY 1,2,3")
    assert counts == [
        {"level": "jv", "gender": "boys", "side": "our", "n": 1},
        {"level": "varsity", "gender": "boys", "side": "opp__vale", "n": 1},
        {"level": "varsity", "gender": "boys", "side": "our", "n": 4},
        {"level": "varsity", "gender": "girls", "side": "our", "n": 2},
    ]
    # Merge mode adds new players without removing existing ones.
    _import_roster(client, "POS,#,NAME,GRADE\nF,33,Morgan Bluehaven,10\n", season_id=season, replace=False)
    assert [p[0] for p in _roster(client, season)] == ["00", "3", "45", "2", "33"]
    # Bad slot values are rejected without writing.
    r = client.post("/api/film-rosters/import", data={"file": (io.BytesIO(ROSTER_V1.encode()), "r.csv"),
                                                      "season_id": str(season), "level": "jr_high",
                                                      "gender": "boys", "side": "our"},
                    content_type="multipart/form-data")
    assert r.status_code == 400 and "Invalid level" in r.get_json()["error"]
    # Delete the opponent slot.
    r = client.delete(f"/api/film-rosters?season_id={season}&level=varsity&gender=boys&side=opp&opponent=Vale")
    assert r.get_json() == {"deleted": 1}
    assert _roster(client, season, side="opp", opponent="Vale") == []


@pytest.mark.xfail(strict=True, reason="BUG: merge-mode roster re-import keys players by label (incl. grade), so a "
                                       "corrected grade adds a duplicate #45 instead of updating the player")
def test_roster_merge_reimport_updates_existing_player(client, app):
    season = _j(client, "post", "/api/seasons", {"name": "S", "start_date": "2025-11-01", "end_date": "2026-03-31"})["id"]
    _import_roster(client, "POS,#,NAME,GRADE\nC,45,Emery Tallpine-Reyes,10\n", season_id=season)
    _import_roster(client, "POS,#,NAME,GRADE\nC,45,Emery Tallpine-Reyes,11\n", season_id=season, replace=False)
    assert _roster(client, season) == [("45", "Emery Tallpine-Reyes", "C", "11")]


@pytest.mark.parametrize("csv_text, expected", [
    pytest.param("Name,#,Pos,Grade\nAvery Northwind,1,PG,8\n",
                 {"name": "Avery Northwind", "jersey_number": "1", "position": "PG", "grade": "8"},
                 marks=pytest.mark.xfail(strict=True, reason="BUG: roster CSV ignores its header; name-first "
                                                             "columns import the position as the player name"),
                 id="name-first-columns"),
    pytest.param("#,Name,Pos,Grade\n3,Blake Ironwood,SG,8\n",
                 {"name": "Blake Ironwood", "jersey_number": "3", "position": "SG", "grade": "8"},
                 marks=pytest.mark.xfail(strict=True, reason="BUG: roster CSV '#,Name,Pos,Grade' drops the grade"),
                 id="jersey-name-pos-grade"),
    pytest.param("POS,#,NAME,GRADE\nF,,Casey Riverbend,7\n",
                 {"name": "Casey Riverbend", "jersey_number": None, "position": "F", "grade": "7"},
                 marks=pytest.mark.xfail(strict=True, reason="BUG: roster CSV drops blank cells before mapping "
                                                             "columns, so a missing jersey turns the grade into #7"),
                 id="blank-jersey-cell"),
    pytest.param("POS,#,NAME,GRADE\nPG,0,Carter Sullivan,8\n\n,,,\nC,45,\"O'Neil, Jasper\",8\n",
                 {"name": "Carter Sullivan", "jersey_number": "0", "position": "PG", "grade": "8"},
                 id="standard-with-blank-rows"),
])
def test_roster_csv_columns_are_mapped_by_header(client, csv_text, expected):
    r = client.post("/api/rosters/import", data={"file": (io.BytesIO(csv_text.encode()), "roster.csv"),
                                                 "file_type": "auto"}, content_type="multipart/form-data")
    assert r.status_code == 200, r.data[:300]
    first = r.get_json()["players"][0]
    assert {k: first[k] for k in expected} == expected


def test_team_photos_upload_list_delete(client, app):
    uploads = Path(app.config["UPLOAD_FOLDER"]) / "team_photos"
    ids = {}
    for key in ("varsity_girls", "jv_boys"):
        r = client.post("/api/teams/photos/upload", data={"file": (io.BytesIO(td.png_bytes()), f"{key}.png"),
                                                          "team_key": key, "caption": f"{key} 2025-26"},
                        content_type="multipart/form-data")
        assert r.status_code == 201
        body = r.get_json()
        assert body["team_key"] == key and body["original_name"] == f"{key}.png"
        assert (uploads / body["filename"]).read_bytes() == td.png_bytes()
        ids[key] = (body["id"], body["filename"])
    listing = _j(client, "get", "/api/teams/photos", None)
    assert sorted(listing) == ["jv_boys", "varsity_girls"]
    assert [p["caption"] for p in listing["varsity_girls"]] == ["varsity_girls 2025-26"]
    assert client.get(f"/uploads/team_photos/{ids['jv_boys'][1]}").data == td.png_bytes()
    assert client.post("/api/teams/photos/upload", data={"file": (io.BytesIO(b"x"), "evil.svg"), "team_key": "x"},
                       content_type="multipart/form-data").status_code == 400
    assert _j(client, "delete", f"/api/teams/photos/{ids['jv_boys'][0]}", None) == {"ok": True}
    assert not (uploads / ids["jv_boys"][1]).exists()
    assert sorted(_j(client, "get", "/api/teams/photos", None)) == ["varsity_girls"]
    assert client.delete(f"/api/teams/photos/{ids['jv_boys'][0]}").status_code == 404


@pytest.mark.xfail(strict=True, reason="BUG: team photo upload builds the path from an unsanitised team_key "
                                       "(path traversal out of uploads/team_photos)")
def test_team_photo_team_key_cannot_escape_folder(client, app):
    upload_root = Path(app.config["UPLOAD_FOLDER"])
    r = client.post("/api/teams/photos/upload", data={"file": (io.BytesIO(td.png_bytes()), "p.png"),
                                                      "team_key": "../escaped"},
                    content_type="multipart/form-data")
    escaped = [p.name for p in upload_root.iterdir() if p.is_file()]
    assert escaped == [], f"file written outside team_photos: {escaped}"
    if r.status_code == 201:
        assert "/" not in r.get_json()["filename"] and ".." not in r.get_json()["filename"]


@pytest.mark.xfail(strict=True, reason="BUG: team photo filenames are team_key + whole-second timestamp; two "
                                       "uploads in the same second overwrite one file shared by both rows")
def test_two_team_photos_in_same_second_keep_both_files(client, app, monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1_790_000_000.25)
    names = []
    for color in ((200, 0, 0), (0, 0, 200)):
        r = client.post("/api/teams/photos/upload", data={"file": (io.BytesIO(td.png_bytes(color=color)), "t.png"),
                                                          "team_key": "varsity_boys"},
                        content_type="multipart/form-data")
        assert r.status_code == 201
        names.append(r.get_json()["filename"])
    assert names[0] != names[1]


def test_players_api_create_list_delete(client, app):
    season = _j(client, "post", "/api/seasons", {"name": "S", "start_date": "2025-11-01", "end_date": "2026-03-31"})["id"]
    for name, num, pos in (("Avery Northwind", 1, "PG"), ("Blake Ironwood", 3, "SG"), ("Emery Tallpine", 11, "C")):
        _j(client, "post", "/api/players", {"name": name, "jersey_number": num, "position": pos, "grade": 8,
                                            "gender": "girls", "level": "varsity", "season_id": season})
    _j(client, "post", "/api/players", {"name": "Other Season", "jersey_number": 2})
    listed = _j(client, "get", f"/api/players?season_id={season}", None)
    assert [(p["jersey_number"], p["name"], p["gender"], p["level"]) for p in listed] == [
        (1, "Avery Northwind", "girls", "varsity"), (3, "Blake Ironwood", "girls", "varsity"),
        (11, "Emery Tallpine", "girls", "varsity")]
    assert len(_j(client, "get", "/api/players", None)) == 4
    assert _j(client, "post", "/api/players", {"name": "  "}, expect=(400,))["error"] == "name required"
    _j(client, "delete", f"/api/players/{listed[1]['id']}", None)
    assert [p["name"] for p in _j(client, "get", f"/api/players?season_id={season}", None)] == [
        "Avery Northwind", "Emery Tallpine"]


# ── Journey 4: games, sources, NFHS matches ─────────────────────────────────────

def test_journey_games_sources_nfhs(client, app):
    season = _season_form(client, app, "2025-26", "2025-11-01", "2026-03-31")
    sg1 = _game_form(client, app, season, team="boys_hs", level="varsity", gender="boys",
                     game_date="2025-12-05", opponent="Vale")
    sg2 = _game_form(client, app, season, team="boys_hs", level="varsity", gender="boys",
                     game_date="2025-12-12", opponent="Marsing")
    _record(client, sg1, 60, 50, conf=True)
    g1 = _q(app, "SELECT id FROM games WHERE scheduled_game_id=?", (sg1,))[0]["id"]

    _form(client, "/nfhs-matches/add", {"scheduled_game_id": sg1, "nfhs_game_id": "gam-1",
                                        "nfhs_url": "https://www.nfhsnetwork.com/events/x/gam-1", "confidence": "0.9"})
    m2 = _j(client, "post", "/api/nfhs_matches", {"scheduled_game_id": sg1, "nfhs_game_id": "gam-2",
                                                  "nfhs_url": "https://www.nfhsnetwork.com/events/x/gam-2"})["id"]
    matches = _j(client, "get", "/api/nfhs_matches", None)
    assert sorted((m["nfhs_game_id"], m["match_status"], m["opponent_name"]) for m in matches) == [
        ("gam-1", "candidate", "Vale"), ("gam-2", "candidate", "Vale")]
    m1 = next(m["id"] for m in matches if m["nfhs_game_id"] == "gam-1")

    _form(client, f"/nfhs-matches/{m1}/confirm", {})
    assert _j(client, "post", f"/api/nfhs_matches/{m1}/confirm", {})["game_id"] == g1  # idempotent
    _form(client, f"/nfhs-matches/{m2}/reject", {})
    assert {m["nfhs_game_id"]: m["match_status"] for m in _j(client, "get", "/api/nfhs_matches", None)} == {
        "gam-1": "confirmed", "gam-2": "rejected"}
    # The confirmed stream attaches to the existing scored game: no new games row, scores intact.
    assert _q(app, "SELECT id, source_type, nfhs_game_id, home_score, away_score, result, is_conference "
                   "FROM games WHERE scheduled_game_id=?", (sg1,)) == [
        {"id": g1, "source_type": "nfhs", "nfhs_game_id": "gam-1", "home_score": 60, "away_score": 50,
         "result": "win", "is_conference": 1}]
    assert [(s["game_id"], s["source_type"]) for s in _j(client, "get", "/api/sources", None)] == [(g1, "nfhs_vod")]

    # NFHS confirm on an unscored game creates a games row with no result (record unchanged).
    m3 = _j(client, "post", "/api/nfhs_matches", {"scheduled_game_id": sg2, "nfhs_game_id": "gam-3",
                                                  "nfhs_url": "https://www.nfhsnetwork.com/events/x/gam-3"})["id"]
    g2 = _j(client, "post", f"/api/nfhs_matches/{m3}/confirm", {})["game_id"]
    assert _record_of(_teams(client)["varsity_boys"]) == (1, 0, 1, 0)

    # Edit that games row through the Games form: scores land on the right scheduled game.
    _form(client, "/games/save", {"game_id": str(g2), "scheduled_game_id": str(sg2), "source_type": "nfhs",
                                  "source_key": "gam-3", "home_score": "40", "away_score": "45", "result": "loss"})
    marsing = next(g for g in _j(client, "get", f"/api/scheduled_games?season_id={season}", None)
                   if g["id"] == sg2)
    assert (marsing["liberty_score"], marsing["opponent_score"], marsing["result"]) == (40, 45, "loss")
    assert _record_of(_teams(client)["varsity_boys"]) == (1, 1, 1, 0)

    # Link / unlink an extra source; delete a game (and its sources) through the form route.
    _form(client, "/games/sources/save", {"game_id": str(g1), "source_type": "local_file",
                                          "source_path": "uploads/vale.mp4"})
    srcs = _j(client, "get", f"/api/sources?game_id={g1}", None)
    assert sorted(s["source_type"] for s in srcs) == ["local_file", "nfhs_vod"]
    _form(client, f"/games/sources/{next(s['id'] for s in srcs if s['source_type'] == 'local_file')}/delete", {})
    assert [s["source_type"] for s in _j(client, "get", f"/api/sources?game_id={g1}", None)] == ["nfhs_vod"]
    assert client.post("/games/save", data={"source_type": "", "source_key": ""}).status_code == 400

    _form(client, f"/games/{g2}/delete", {})
    assert _q(app, "SELECT id FROM games WHERE id=?", (g2,)) == []
    assert _q(app, "SELECT id FROM sources WHERE game_id=?", (g2,)) == []
    assert _record_of(_teams(client)["varsity_boys"]) == (1, 0, 1, 0)
    assert client.get("/nfhs-matches").status_code == 200


@pytest.mark.xfail(strict=True, reason="BUG: DELETE /api/games/<id> leaves its sources rows, so with "
                                       "foreign_keys=ON deleting any game that has film sources raises (500)")
def test_api_delete_game_with_sources(client, app):
    g = _j(client, "post", "/api/games", {"source_type": "manual", "source_key": "film-1"})
    _j(client, "post", "/api/sources", {"game_id": g["id"], "source_type": "local_file", "source_path": "a.mp4"})
    r = client.delete(f"/api/games/{g['id']}")
    assert r.status_code == 200
    assert _q(app, "SELECT id FROM games") == []


@pytest.mark.xfail(strict=True, reason="BUG: deleting a scheduled game that has a recorded score (games row) "
                                       "hits the games.scheduled_game_id FK and 500s")
def test_delete_scored_scheduled_game(client, app):
    season = _season_form(client, app, "2025-26", "2025-11-01", "2026-03-31")
    sg = _game_form(client, app, season, team="boys_hs", level="varsity", gender="boys",
                    game_date="2025-12-05", opponent="Vale")
    _record(client, sg, 60, 50)
    r = client.post(f"/schedule/games/{sg}/delete", data={}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert _q(app, "SELECT id FROM scheduled_games WHERE id=?", (sg,)) == []
    assert _record_of(_teams(client)["varsity_boys"])[:2] == (0, 0)


# ── Journey 5: season rollover / archive ───────────────────────────────────────

def _two_seasons(client, app):
    old = _season_form(client, app, "2024-25 Varsity", "2024-11-01", "2025-03-31")
    new = _season_form(client, app, "2025-26 Varsity", "2025-11-01", "2026-03-31")
    o1 = _game_form(client, app, old, team="boys_hs", level="varsity", gender="boys",
                    game_date="2024-12-06", opponent="Vale")
    o2 = _game_form(client, app, old, team="boys_hs", level="varsity", gender="boys",
                    game_date="2025-01-10", opponent="Marsing", location="away")
    n1 = _game_form(client, app, new, team="boys_hs", level="varsity", gender="boys",
                    game_date="2025-12-05", opponent="Vale")
    _record(client, o1, 58, 44, conf=True)
    _record(client, o2, 61, 59)
    _record(client, n1, 40, 52, conf=True)
    return old, new


def test_journey_season_rollover_keeps_records_separate(client, app):
    old, new = _two_seasons(client, app)
    vb = _teams(client)["varsity_boys"]
    assert [s["id"] for s in vb["seasons"]] == [new, old]
    assert vb["season_id"] == new and vb["season_name"] == "2025-26 Varsity"
    assert _record_of(vb) == (0, 1, 0, 1)
    assert _record_of(_teams(client, f"?varsity_boys={old}")["varsity_boys"]) == (2, 0, 1, 0)
    # A season id that the team has no games in falls back to the default.
    assert _teams(client, "?varsity_boys=9999")["varsity_boys"]["season_id"] == new
    # Editing the new season's dates leaves the old season's games attached and scored.
    _j(client, "put", f"/api/seasons/{new}", {"start_date": "2025-10-15"})
    old_games = _j(client, "get", f"/api/scheduled_games?season_id={old}", None)
    assert [(g["opponent_name"], g["liberty_score"], g["opponent_score"], g["season_name"]) for g in old_games] == [
        ("Vale", 58, 44, "2024-25 Varsity"), ("Marsing", 61, 59, "2024-25 Varsity")]
    assert [g["opponent_name"] for g in _j(client, "get", f"/api/scheduled_games?season_id={new}", None)] == ["Vale"]
    # An empty season can be deleted; the others are untouched.
    extra = _season_form(client, app, "Summer 2026", "2026-06-01", "2026-08-31")
    _form(client, f"/schedule/seasons/{extra}/delete", {})
    assert sorted(s["name"] for s in _j(client, "get", "/api/seasons", None)) == ["2024-25 Varsity", "2025-26 Varsity"]


@pytest.mark.xfail(strict=True, reason="BUG: deleting a season whose games have recorded scores 500s "
                                       "(games.scheduled_game_id FK) instead of deleting or refusing cleanly")
def test_delete_season_with_scored_games(client, app):
    old, new = _two_seasons(client, app)
    r = client.post(f"/schedule/seasons/{old}/delete", data={}, follow_redirects=False)
    assert r.status_code in (302, 303, 409)
    assert _record_of(_teams(client, f"?varsity_boys={new}")["varsity_boys"]) == (0, 1, 0, 1)


@pytest.mark.xfail(strict=True, reason="BUG: scripts/archive_season.py selects games by a non-existent "
                                       "games.season_id, so archives omit every game result (and its events/stats)")
def test_archive_season_includes_game_results(client, app, tmp_path):
    old, _new = _two_seasons(client, app)
    env = dict(os.environ, LIBERTY_DATA_ROOT=str(tmp_path / "data"))
    env.pop("LIBERTY_ARCHIVE_DIR", None)
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "archive_season.py"), "--db", app.config["DATABASE"],
                        "--season-id", str(old)], env=env, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    archives = list((tmp_path / "data" / "archives" / "seasons").glob("*.db"))
    assert len(archives) == 1
    conn = sqlite3.connect(archives[0])
    try:
        assert conn.execute("SELECT COUNT(*) FROM scheduled_games").fetchone()[0] == 2
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "games" in tables
        scores = sorted(conn.execute("SELECT home_score, away_score, result FROM games").fetchall())
    finally:
        conn.close()
    assert scores == [(58, 44, "win"), (59, 61, "win")]


# ── MaxPreps rankings (network stubbed) + playbook bulk import ──────────────────

def test_rankings_refresh_keeps_last_good_value(client, app, monkeypatch):
    import maxpreps_web

    pages = {"boys": "<table><tr><td>3</td><td>Liberty Charter</td></tr></table>", "girls": None}

    def fake_fetch(url, timeout=30):
        page = pages["girls" if "/girls/" in url else "boys"]
        if page is None:
            raise RuntimeError("HTTP 503")
        return page

    monkeypatch.setattr(maxpreps_web, "fetch_url", fake_fetch)
    monkeypatch.setattr(maxpreps_web, "_playwright_ranking_fallback", lambda url: None)
    body = client.post("/api/teams/rankings", data={"state": "Idaho"}).get_json()
    assert body["rankings"]["varsity_boys"]["ranking"] == 3
    assert "varsity_girls" not in body["rankings"] and body["errors"]["varsity_girls"] == "HTTP 503"
    pages["boys"] = None
    body = client.post("/api/teams/rankings", data={"state": "Idaho"}).get_json()
    assert body["rankings"]["varsity_boys"]["ranking"] == 3
    assert client.get("/api/teams/rankings?state=Idaho").get_json()["rankings"]["varsity_boys"]["ranking"] == 3


def _scout_pdf(plays, seed=0):
    """Fast-Scout style playbook PDF: header line + section + play name per page."""
    import pymupdf

    doc = pymupdf.open()
    for n, (section, name) in enumerate(plays):
        page = doc.new_page()
        page.insert_text((72, 72), f"25-26 - Liberty Charter Patriots - {section} - Plays")
        page.insert_text((72, 96), section)
        page.insert_text((72, 120), name)
        page.draw_circle((200 + 40 * seed, 400 + 20 * n), 30, color=(0, 0, 0), width=2)
    out = doc.tobytes()
    doc.close()
    return out


def _bulk_parse(client, pdf):
    r = client.post("/api/playbook/bulk/parse", data={"file": (io.BytesIO(pdf), "book.pdf")},
                    content_type="multipart/form-data")
    assert r.status_code == 200, r.data[:300]
    return r.get_json()


def _bulk_save(client, parsed, extra=()):
    plays = [{"play_name": p["play_name"], "section": p["section"], "subsection": p.get("subsection", ""),
              "category_id": p.get("category_id"), "playbook_id": "", "pages": p["pages"]}
             for p in parsed["plays"]] + list(extra)
    return _j(client, "post", "/api/playbook/bulk/save", {"plays": plays, "playbook_id": ""})


def test_playbook_bulk_import_parse_and_save(client, app):
    pytest.importorskip("pymupdf")
    parsed = _bulk_parse(client, _scout_pdf([("BLOB", "Box 1"), ("BLOB", "Box 1"), ("BLOB", "Cross")]))
    assert parsed["total_pages"] == 3 and parsed["total_plays"] == 2
    assert [(p["play_name"], p["section"], p["page_count"]) for p in parsed["plays"]] == [
        ("Box 1", "BLOB", 2), ("Cross", "BLOB", 1)]
    saved = _bulk_save(client, parsed, extra=[{"play_name": "", "section": "BLOB", "pages": []}])
    assert saved["saved_count"] == 2 and saved["errors"] == ["Play 3: missing name"]
    rows = _q(app, "SELECT p.name, COUNT(s.id) AS steps FROM plays p JOIN play_steps s ON s.play_id = p.id "
                   "WHERE p.id IN (?, ?) GROUP BY p.id ORDER BY p.id", [s["id"] for s in saved["saved"]])
    assert rows == [{"name": "Box 1", "steps": 2}, {"name": "Cross", "steps": 1}]


@pytest.mark.xfail(strict=True, reason="BUG: bulk import renders pages to fixed uploads/bulk_imports/page_NNNN.png, "
                                       "so the next import overwrites the step images of plays already saved")
def test_playbook_bulk_import_does_not_overwrite_saved_play_images(client, app):
    pytest.importorskip("pymupdf")
    first = _bulk_parse(client, _scout_pdf([("BLOB", "Box 1")], seed=0))
    play_id = _bulk_save(client, first)["saved"][0]["id"]
    image_url = _q(app, "SELECT source_image FROM play_steps WHERE play_id=?", (play_id,))[0]["source_image"]
    before = client.get(image_url).data
    _bulk_parse(client, _scout_pdf([("Defense", "Shell Drill")], seed=3))  # a different playbook
    assert client.get(image_url).data == before
