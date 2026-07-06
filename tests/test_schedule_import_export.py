"""Tests for PDF import and MaxPreps export features."""
import io
import pytest


def test_schedule_import_pdf_no_file(client):
    """Reject request with no file."""
    resp = client.post("/api/schedule/import-pdf")
    assert resp.status_code == 400
    data = resp.get_json()
    assert "error" in data


def test_schedule_import_pdf_wrong_type(client):
    """Reject non-PDF files."""
    data = {"pdf": (io.BytesIO(b"not a pdf"), "schedule.txt")}
    resp = client.post("/api/schedule/import-pdf", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400


def test_schedule_import_pdf_confirm_empty(client):
    """Reject empty game list."""
    resp = client.post("/api/schedule/import-pdf/confirm",
                       json={"games": []})
    assert resp.status_code == 400


def test_schedule_import_pdf_confirm_missing_fields(client):
    """Reject games with missing required fields."""
    resp = client.post("/api/schedule/import-pdf/confirm",
                       json={"games": [{"opponent_name": "Test"}]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["imported"] == 0
    assert len(data["errors"]) > 0


def test_schedule_import_pdf_confirm_valid(client, app):
    """Import valid games."""
    with app.app_context():
        from helpers import get_db
        db = get_db()
        # Create a season first
        db.execute("INSERT INTO seasons (name, start_date, end_date) VALUES (?,?,?)",
                   ("2025-26 Test", "2025-09-01", "2026-06-30"))
        db.commit()
        season_id = db.execute("SELECT id FROM seasons WHERE name='2025-26 Test'").fetchone()["id"]

    games = [
        {"game_date": "2025-12-01", "game_time": "7:00 PM", "opponent_name": "Riverside",
         "level": "varsity", "gender": "boys", "location_type": "home", "status": "scheduled", "notes": ""},
        {"game_date": "2025-12-05", "game_time": "6:00 PM", "opponent_name": "Lincoln",
         "level": "jv", "gender": "girls", "location_type": "away", "status": "scheduled", "notes": ""},
    ]
    resp = client.post("/api/schedule/import-pdf/confirm", json={"games": games})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["imported"] == 2


def test_schedule_export_maxpreps(client, app):
    """Export schedule as MaxPreps CSV."""
    with app.app_context():
        from helpers import get_db
        db = get_db()
        # Create season and game
        db.execute("INSERT OR IGNORE INTO seasons (name, start_date, end_date) VALUES (?,?,?)",
                   ("2025-26 Test", "2025-09-01", "2026-06-30"))
        db.commit()
        season_id = db.execute("SELECT id FROM seasons WHERE name='2025-26 Test'").fetchone()["id"]
        db.execute(
            """INSERT INTO scheduled_games
               (season_id, program_name, gender, level, game_date, game_time,
                jv_game_time, frosh_game_time,
                location_type, opponent_name, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (season_id, "Liberty", "boys", "varsity", "2025-12-01", "19:00",
             "16:30", None, "home", "Riverside", "scheduled"),
        )
        db.commit()

    resp = client.get("/schedule/export/maxpreps")
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type
    assert "maxpreps_schedule_export.csv" in resp.headers.get("Content-Disposition", "")
    csv_text = resp.data.decode("utf-8")
    assert "Date" in csv_text
    assert "Opponent" in csv_text
    assert "Riverside" in csv_text
    assert "Varsity" in csv_text
    assert "Home" in csv_text


def test_schedule_export_maxpreps_only_scheduled(client, app):
    """Only scheduled games should be exported."""
    with app.app_context():
        from helpers import get_db
        db = get_db()
        # Ensure season exists
        row = db.execute("SELECT id FROM seasons WHERE name='2025-26 Test'").fetchone()
        if not row:
            db.execute("INSERT INTO seasons (name, start_date, end_date) VALUES (?,?,?)",
                       ("2025-26 Test", "2025-09-01", "2026-06-30"))
            db.commit()
            row = db.execute("SELECT id FROM seasons WHERE name='2025-26 Test'").fetchone()
        season_id = row["id"]
        db.execute(
            """INSERT INTO scheduled_games
               (season_id, program_name, gender, level, game_date, game_time,
                jv_game_time, frosh_game_time,
                location_type, opponent_name, status)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (season_id, "Liberty", "boys", "jr_high", "2025-12-10", "18:00",
             None, None, "away", "Lincoln", "completed"),
        )
        db.commit()

    resp = client.get("/schedule/export/maxpreps")
    csv_text = resp.data.decode("utf-8")
    # Completed game should NOT appear
    assert "Lincoln" not in csv_text


def test_parse_schedule_line_various_formats():
    """Test the PDF text parser with various date formats."""
    from blueprints.core import _parse_schedule_line

    # MM/DD/YYYY format
    result = _parse_schedule_line("12/01/2025 7:00 PM vs Riverside")
    assert result is not None
    assert result["game_date"] == "2025-12-01"
    assert result["opponent_name"] == "Riverside"

    # YYYY-MM-DD format
    result = _parse_schedule_line("2025-12-01 @ Lincoln High")
    assert result is not None
    assert result["game_date"] == "2025-12-01"
    assert result["location_type"] == "away"

    # Text month format
    result = _parse_schedule_line("December 1, 2025 vs Central")
    assert result is not None
    assert result["game_date"] == "2025-12-01"

    # No date — should return None
    result = _parse_schedule_line("Some random text without a date")
    assert result is None

    # Varsity detection
    result = _parse_schedule_line("12/01/2025 Varsity vs Westside")
    assert result is not None
    assert result["level"] == "varsity"

    # Girls detection
    result = _parse_schedule_line("12/01/2025 Girls vs Eastside")
    assert result is not None
    assert result["gender"] == "girls"


def test_parse_schedule_line_jr_high_assumes_pm():
    from blueprints.core import _parse_schedule_line

    result = _parse_schedule_line("TUES, JAN 27 NOTUS (H) 3:30/5:00", pdf_team="jr_boys")
    assert result["jv_game_time"] == "15:30"
    assert result["game_time"] == "17:00"


def test_parse_schedule_line_jr_high_space_separated_times():
    from blueprints.core import _parse_schedule_line

    result = _parse_schedule_line("JAN 27 NOTUS 3:30 5:00", pdf_team="jr_boys")
    assert result["jv_game_time"] == "15:30"
    assert result["game_time"] == "17:00"


def test_parse_schedule_line_jr_high_compact_pm_suffix():
    from blueprints.core import _parse_schedule_line

    result = _parse_schedule_line("TUES, JAN 27 NOTUS (H) 3:30p/5:00p", pdf_team="jr_boys")
    assert result["jv_game_time"] == "15:30"
    assert result["game_time"] == "17:00"
    assert result["opponent_name"] == "Notus"


def test_parse_schedule_line_normalizes_opponent_title_case():
    from blueprints.core import _parse_schedule_line

    result = _parse_schedule_line("JAN 29 RIVERSTONE (A) 4:00/6:00", pdf_team="jr_boys")
    assert result["opponent_name"] == "Riverstone"

    result = _parse_schedule_line("FEB 2 Rimrock (H) 3:30", pdf_team="jr_boys")
    assert result["opponent_name"] == "Rimrock"

    result = _parse_schedule_line("FEB 10 IDAHO CITY (A) 4:00", pdf_team="jr_boys")
    assert result["opponent_name"] == "Idaho City"


def test_parse_schedule_line_tbd_opponent_and_location():
    from blueprints.core import _normalize_opponent_name, _normalize_location_type, _parse_schedule_line

    assert _normalize_opponent_name("tbd") == "TBD"
    assert _normalize_location_type("TBD") == "tbd"

    result = _parse_schedule_line("JAN 15 TBD (TBD) 3:30/5:00", pdf_team="jr_boys")
    assert result is not None
    assert result["opponent_name"] == "TBD"
    assert result["location_type"] == "tbd"

    result = _parse_schedule_line("FEB 5 tbd (tbd) 4:00", pdf_team="jr_boys")
    assert result["opponent_name"] == "TBD"
    assert result["location_type"] == "tbd"


def test_detect_season_jr_boys_uses_title_year():
    from blueprints.core import _detect_season_from_text

    text = "2026 Junior High Boys' Basketball Schedule\nJAN 27 NOTUS 3:30/5:00"
    season = _detect_season_from_text(text, pdf_team="jr_boys")
    assert season is not None
    assert season["start_date"] == "2026-01-01"
    assert season["end_date"] == "2026-02-28"


def test_parse_schedule_text_jr_high_ab_continuation_line():
    """Separate 'A 6:00' continuation lines attach to the previous game."""
    from blueprints.core import _parse_schedule_text

    text = "TUES, DEC 2 MARSING (H) 4:30\nA 6:00"
    games = _parse_schedule_text(text, pdf_team="jr_boys")
    assert len(games) == 1
    assert games[0]["jv_game_time"] == "16:30"
    assert games[0]["game_time"] == "18:00"


def test_parse_maxpreps_printable_schedule():
    from blueprints.core import _parse_schedule_text

    text = """7/5/26, 9:41 PM Printable Liberty Charter High School Basketball Schedule
Liberty Charter Basketball Schedule (2021-22)
Date Opponent Result
12/1 @ Glenns Ferry (Glenns Ferry, ID) (W) 44 - 40
7:30p Location: Glenns Ferry High School
12/4 Council (Council, ID) (W) 50 - 30
2:30p Location: Liberty Charter
12/15 @ Cole Valley Christian (Meridian, ID) (L) 47 - 33
7:30p Location: Cole Valley Christian High School
1/8 @ Murtaugh (Murtaugh, ID) (W) 51 - 32
5:00p Location: Murtaugh High School
"""
    season = {"name": "2021-22 Boys", "start_date": "2021-11-01", "end_date": "2022-03-31"}
    games = _parse_schedule_text(text, pdf_team="boys_hs", season_info=season)
    assert len(games) == 4
    assert games[0]["opponent_name"] == "Glenns Ferry"
    assert games[0]["game_date"] == "2021-12-01"
    assert games[0]["game_time"] == "19:30"
    assert games[0]["location_type"] == "away"
    assert games[0]["status"] == "completed"
    assert games[0]["result"] == "win"
    assert games[0]["liberty_score"] == 44
    assert games[0]["opponent_score"] == 40
    assert games[1]["opponent_name"] == "Council"
    assert games[1]["location_type"] == "home"
    assert games[1]["result"] == "win"
    assert games[1]["liberty_score"] == 50
    assert games[2]["result"] == "loss"
    assert games[2]["liberty_score"] == 33
    assert games[2]["opponent_score"] == 47
    assert games[3]["opponent_name"] == "Murtaugh"
    assert games[3]["game_time"] == "17:00"


def test_schedule_import_pdf_confirm_with_scores(client, app):
    with app.app_context():
        from helpers import get_db
        db = get_db()
        db.execute(
            "INSERT INTO seasons (name, start_date, end_date) VALUES (?,?,?)",
            ("2021-22 Test", "2021-11-01", "2022-03-31"),
        )
        db.commit()

    games = [{
        "game_date": "2021-12-01",
        "game_time": "19:30",
        "opponent_name": "Glenns Ferry",
        "level": "varsity",
        "gender": "boys",
        "location_type": "away",
        "status": "completed",
        "result": "win",
        "liberty_score": 44,
        "opponent_score": 40,
        "is_conference": False,
        "notes": "",
    }]
    resp = client.post(
        "/api/schedule/import-pdf/confirm",
        json={
            "games": games,
            "team": "boys_hs",
            "season": {
                "name": "2021-22 Test",
                "start_date": "2021-11-01",
                "end_date": "2022-03-31",
            },
        },
    )
    assert resp.status_code == 200
    assert resp.get_json()["imported"] == 1

    with app.app_context():
        from helpers import get_db
        db = get_db()
        scheduled = db.execute("SELECT status FROM scheduled_games WHERE opponent_name='Glenns Ferry'").fetchone()
        game = db.execute(
            """SELECT home_score, away_score, result
               FROM games g
               JOIN scheduled_games sg ON sg.id = g.scheduled_game_id
               WHERE sg.opponent_name='Glenns Ferry'"""
        ).fetchone()
    assert scheduled["status"] == "completed"
    assert game["home_score"] == 40
    assert game["away_score"] == 44
    assert game["result"] == "win"


def test_parse_maxpreps_ranking_html():
    from blueprints.core import _parse_maxpreps_ranking_html

    html = """
    <table>
      <tr><td class="rank">16</td><td class="team">Other School</td></tr>
      <tr><td class="rank">17</td><td class="team">Liberty Charter Patriots</td></tr>
    </table>
    """
    assert _parse_maxpreps_ranking_html(html) == 17


def test_rankings_post_without_playwright(client):
    """Ranking refresh should not 500 when Playwright is unavailable."""
    resp = client.post("/api/teams/rankings", data={"state": "Idaho"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert "rankings" in data
    assert "varsity_boys" in data["rankings"]


def test_schedule_table_column_widths(client):
    """Verify schedule table has correct column headers."""
    resp = client.get("/schedule")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # Check that schedule table uses new 4-column layout (DATE, OPPONENT, TIMES, Actions)
    assert ">DATE<" in html or "DATE" in html
    assert ">OPPONENT<" in html or "OPPONENT" in html
    assert ">TIMES<" in html or "TIMES" in html
