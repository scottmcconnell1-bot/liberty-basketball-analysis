"""Tests for roster import parsers and API."""
import io

import pytest

from roster_import import (
    detect_roster_file_type,
    is_maxpreps_printable_roster,
    parse_maxpreps_roster_text,
    parse_roster_csv,
    parse_roster_text,
    parse_roster_upload,
)


SAMPLE_CSV = """POS,#,NAME,GRADE
PG,0,Carter Sullivan,8
SG,3,Jonathan Kariuki,8
C,45,Jasper Musgrave,8
"""

MAXPREPS_ROSTER_TEXT = """7/5/26, 9:41 PM Printable Liberty Charter High School Basketball Roster
Liberty Charter Basketball Roster (2025-26)
Players (11)
# Player Grade Position Height Weight
45 Jasper Musgrave 8 C 6'2" 180
3 Jonathan Kariuki 8 PG 5'10" 150
0 Carter Sullivan 8 PG 5'8" 140
Staff (2)
Head Coach Smith
"""


def test_parse_roster_csv_liberty_format():
    players = parse_roster_csv(SAMPLE_CSV)
    assert len(players) == 3
    assert players[0]["name"] == "Carter Sullivan"
    assert players[0]["jersey_number"] == "0"
    assert players[0]["position"] == "PG"
    assert players[0]["grade"] == "8"
    assert players[2]["label"] == "45 - Jasper Musgrave, 8"


def test_is_maxpreps_printable_roster():
    assert is_maxpreps_printable_roster(MAXPREPS_ROSTER_TEXT)
    assert not is_maxpreps_printable_roster(SAMPLE_CSV)


def test_parse_maxpreps_roster_text():
    players = parse_maxpreps_roster_text(MAXPREPS_ROSTER_TEXT)
    assert len(players) == 3
    assert players[0]["name"] == "Jasper Musgrave"
    assert players[0]["jersey_number"] == "45"
    assert players[0]["position"] == "C"
    assert players[1]["name"] == "Jonathan Kariuki"


def test_detect_roster_file_type():
    assert detect_roster_file_type("roster.csv") == "csv"
    assert detect_roster_file_type("roster.pdf", MAXPREPS_ROSTER_TEXT) == "maxpreps_pdf"
    assert detect_roster_file_type("roster.pdf", "Team Roster\n0 Carter Sullivan 8 PG") == "pdf"


def test_parse_roster_text_auto_csv():
    players, detected = parse_roster_text(SAMPLE_CSV, file_type="auto", filename="roster.csv")
    assert detected == "csv"
    assert len(players) == 3


def test_parse_roster_text_auto_maxpreps():
    players, detected = parse_roster_text(
        MAXPREPS_ROSTER_TEXT,
        file_type="auto",
        filename="roster.pdf",
    )
    assert detected == "maxpreps_pdf"
    assert len(players) == 3


def test_parse_roster_upload_csv():
    file_obj = io.BytesIO(SAMPLE_CSV.encode("utf-8"))
    file_obj.filename = "2026 Liberty A Roster.csv"
    result = parse_roster_upload(file_obj, file_type="csv")
    assert result["detected_type"] == "csv"
    assert result["count"] == 3


def test_parse_roster_upload_invalid_type():
    file_obj = io.BytesIO(SAMPLE_CSV.encode("utf-8"))
    file_obj.filename = "roster.csv"
    with pytest.raises(ValueError, match="Invalid file_type"):
        parse_roster_upload(file_obj, file_type="bad")


def test_api_rosters_import_no_file(client):
    resp = client.post("/api/rosters/import")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_api_rosters_import_csv(client):
    data = {
        "file": (io.BytesIO(SAMPLE_CSV.encode("utf-8")), "roster.csv"),
        "file_type": "csv",
    }
    resp = client.post("/api/rosters/import", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["count"] == 3
    assert payload["detected_type"] == "csv"
    assert payload["players"][0]["name"] == "Carter Sullivan"


def test_api_rosters_import_auto_detect_csv(client):
    data = {
        "file": (io.BytesIO(SAMPLE_CSV.encode("utf-8")), "roster.csv"),
        "file_type": "auto",
    }
    resp = client.post("/api/rosters/import", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["detected_type"] == "csv"
    assert payload["count"] == 3


def test_api_rosters_import_empty_csv(client):
    data = {
        "file": (io.BytesIO(b"POS,#,NAME,GRADE\n"), "empty.csv"),
        "file_type": "csv",
    }
    resp = client.post("/api/rosters/import", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "No players found" in resp.get_json()["error"]
