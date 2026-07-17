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


def test_api_schedule_import_maxpreps_pdf(client, monkeypatch):
    from tests.test_maxpreps_schedule_import import MAXPREPS_SCHEDULE_TEXT

    class _FakePage:
        def extract_text(self):
            return MAXPREPS_SCHEDULE_TEXT

    class _FakePdf:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @property
        def pages(self):
            return [_FakePage()]

    monkeypatch.setattr("pdfplumber.open", lambda _file: _FakePdf())

    data = {"pdf": (io.BytesIO(b"%PDF-1.4"), "schedule.pdf"), "team": "boys_hs"}
    resp = client.post("/api/schedule/import-pdf", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload.get("parser") == "maxpreps"
    assert payload.get("count", 0) >= 5
    assert payload["games"][0]["opponent_name"] == "Marsing"


def test_schedule_import_health_endpoint(client):
    resp = client.get("/api/schedule/import-health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ready"] is True
    assert data["maxpreps_parser"] is True
    assert data["pdf_backend"] in ("pdfplumber", "PyPDF2")


def test_api_schedule_import_rejects_footer_junk(client, monkeypatch):
    junk_text = "7/6/26, 9:52 PM Printable Liberty Charter High School Basketball Schedule\n"

    class _FakePage:
        def extract_text(self):
            return junk_text

    class _FakePdf:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        @property
        def pages(self):
            return [_FakePage()]

    monkeypatch.setattr("pdfplumber.open", lambda _file: _FakePdf())

    data = {"pdf": (io.BytesIO(b"%PDF-1.4"), "schedule.pdf"), "team": "boys_hs"}
    resp = client.post("/api/schedule/import-pdf", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    payload = resp.get_json()
    assert "not parsed correctly" in payload["error"]
    assert payload.get("health") is not None


def test_schedule_table_column_widths(client):
    """Verify schedule table has correct column headers."""
    resp = client.get("/schedule")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # Check that schedule table uses new 4-column layout (DATE, OPPONENT, TIMES, Actions)
    assert ">DATE<" in html or "DATE" in html
    assert ">OPPONENT<" in html or "OPPONENT" in html
    assert ">TIMES<" in html or "TIMES" in html
