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
                location_type, opponent_name, status)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (season_id, "Liberty", "boys", "varsity", "2025-12-01", "19:00", "home", "Riverside", "scheduled"),
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
                location_type, opponent_name, status)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (season_id, "Liberty", "boys", "jr_high", "2025-12-10", "18:00", "away", "Lincoln", "completed"),
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


def test_schedule_table_column_widths(client):
    """Verify schedule table has min-width on Level column."""
    resp = client.get("/schedule")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # Check that Level column has min-width
    assert "min-width:80px" in html
    # Check that "Loc" shorthand is used for Location
    assert ">Loc</th>" in html or ">Loc<" in html
