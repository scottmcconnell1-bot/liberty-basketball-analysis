"""Tests for roster import parsers and API."""
import io

import pytest

from roster_import import (
    detect_roster_file_type,
    is_maxpreps_printable_roster,
    parse_maxpreps_roster_text,
    parse_roster_csv,
    parse_roster_excel,
    parse_roster_text,
    parse_roster_upload,
)


def _sample_excel_bytes():
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["POS", "#", "NAME", "GRADE"])
    sheet.append(["PG", 0, "Carter Sullivan", 8])
    sheet.append(["SG", 3, "Jonathan Kariuki", 8])
    sheet.append(["C", 45, "Jasper Musgrave", 8])
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


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

MAXPREPS_HS_ROSTER_TEXT = """Printable Opponent High School Basketball Roster
# Player Grade Position Height Weight
0 Caleb Henrickson G Fr. 5'8" 150
1 Blake Baker G Jr. 5'11" 160
10 Tyden Blacker G So. 6'0" 170
"""


def test_parse_roster_csv_liberty_format():
    players = parse_roster_csv(SAMPLE_CSV)
    assert len(players) == 3
    assert players[0]["name"] == "Carter Sullivan"
    assert players[0]["jersey_number"] == "0"
    assert players[0]["position"] == "PG"
    assert players[0]["grade"] == "8"
    assert players[2]["label"] == "45 - Jasper Musgrave, 8"


def test_parse_roster_csv_jersey_numbers_only():
    players = parse_roster_csv("5\n12\n23\n")
    assert len(players) == 3
    assert players[0]["jersey_number"] == "5"
    assert players[0]["label"] == "5"
    assert players[1]["label"] == "12"
    assert players[2]["label"] == "23"


def test_filter_players_with_jersey_excludes_coaches():
    from roster_import import _filter_players_with_jersey, _normalize_player

    players = _filter_players_with_jersey([
        _normalize_player(jersey_number="12", name="Smith"),
        _normalize_player(name="Head Coach Smith"),
        _normalize_player(jersey_number=None, name="1234 School Rd"),
    ])
    assert len(players) == 1
    assert players[0]["jersey_number"] == "12"


def test_parse_maxpreps_flattened_single_line():
    blob = (
        "Players (11) # Player Grade Position "
        "45 Jasper Musgrave 8 C 3 Jonathan Kariuki 8 PG 0 Carter Sullivan 8 PG "
        "Staff (2) Head Coach Smith"
    )
    players = parse_maxpreps_roster_text(blob)
    assert len(players) == 3
    jerseys = {p["jersey_number"] for p in players}
    assert jerseys == {"45", "3", "0"}


def test_parse_roster_csv_space_separated_jerseys():
    players = parse_roster_csv("5 12 23")
    assert len(players) == 3
    assert [p["jersey_number"] for p in players] == ["5", "12", "23"]


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


def test_parse_maxpreps_hs_roster_position_before_grade():
    players = parse_maxpreps_roster_text(MAXPREPS_HS_ROSTER_TEXT)
    assert len(players) == 3
    assert players[0]["jersey_number"] == "0"
    assert players[0]["name"] == "Caleb Henrickson"
    assert players[0]["position"] == "G"
    assert players[0]["grade"] == "Fr"
    assert players[1]["name"] == "Blake Baker"
    assert players[1]["grade"] == "Jr"


def test_parse_roster_rows_single_column_maxpreps_line():
    players = parse_roster_csv("0 Caleb Henrickson G Fr. 5'8\" 150\n")
    assert len(players) == 1
    assert players[0]["jersey_number"] == "0"
    assert players[0]["name"] == "Caleb Henrickson"
    assert players[0]["position"] == "G"
    assert players[0]["grade"] == "Fr"


def test_detect_roster_file_type():
    assert detect_roster_file_type("roster.csv") == "csv"
    assert detect_roster_file_type("roster.xlsx") == "excel"
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


def test_parse_roster_excel_liberty_format():
    file_obj = io.BytesIO(_sample_excel_bytes())
    players = parse_roster_excel(file_obj)
    assert len(players) == 3
    assert players[0]["name"] == "Carter Sullivan"
    assert players[0]["jersey_number"] == "0"
    assert players[2]["label"] == "45 - Jasper Musgrave, 8"


def test_parse_roster_upload_excel_auto():
    file_obj = io.BytesIO(_sample_excel_bytes())
    file_obj.filename = "2026 Liberty A Roster.xlsx"
    result = parse_roster_upload(file_obj, file_type="auto")
    assert result["detected_type"] == "excel"
    assert result["count"] == 3


def test_api_rosters_import_excel(client):
    data = {
        "file": (io.BytesIO(_sample_excel_bytes()), "roster.xlsx"),
        "file_type": "excel",
    }
    resp = client.post("/api/rosters/import", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["detected_type"] == "excel"
    assert payload["count"] == 3
    assert payload["players"][1]["name"] == "Jonathan Kariuki"


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
