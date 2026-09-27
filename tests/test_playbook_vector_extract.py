"""Tests for FastDraw vector PDF → structured play extract."""

from pathlib import Path

import pytest

from playbook_vector_extract import (
    _has_dash_pattern,
    classify_pdf,
    extract_page,
    extract_sheet_from_image_url,
    resolve_pdf_page_from_sheet,
)

PDF = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f.pdf")
PAGE32 = "/uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0032.png"
HAS_PDF = PDF.is_file()


@pytest.mark.skipif(not HAS_PDF, reason="Fast Scout PDF fixture not present")
def test_classify_fastdraw_pdf_is_vector():
    info = classify_pdf(PDF)
    assert info["kind"] == "vector"
    assert info["total_image_xrefs"] == 0
    assert info["pages_with_drawings"] > 300
    assert "FastDraw" in (info.get("creator") or "")


@pytest.mark.skipif(not HAS_PDF, reason="Fast Scout PDF fixture not present")
def test_resolve_png_to_pdf_page():
    resolved = resolve_pdf_page_from_sheet(PAGE32)
    assert resolved is not None
    pdf, page = resolved
    assert pdf.name.endswith(".pdf")
    assert page == 32


@pytest.mark.skipif(not HAS_PDF, reason="Fast Scout PDF fixture not present")
def test_detect_court_uses_outline_not_title_panel():
    import fitz
    from playbook_vector_extract import _DEFAULT_COURT_PDF, _detect_court_rect

    doc = fitz.open(PDF)
    try:
        court = _detect_court_rect(doc[31])
    finally:
        doc.close()
    # White title panel is y0≈163; painted baseline is y0≈207.
    assert court[1] > 190, court
    assert abs(court[0] - _DEFAULT_COURT_PDF[0]) < 2
    assert abs(court[1] - _DEFAULT_COURT_PDF[1]) < 2


@pytest.mark.skipif(not HAS_PDF, reason="Fast Scout PDF fixture not present")
def test_extract_1game_page32_digits():
    step = extract_page(PDF, 32)
    assert step["source"] == "vector"
    pos = step["positions"]
    assert set(pos) >= {"o1", "o2", "o3", "o4", "o5"}
    # Digits live on the half-court (SVG 500x470).
    for oid, p in pos.items():
        assert 0 <= p["x"] <= 500, oid
        assert 0 <= p["y"] <= 470, oid
    # 1 is near top of key / FT area on sheet 1 of 1-Game.
    assert pos["o1"]["y"] > 250
    assert "1-Game" in (step.get("title") or "")
    # Painted-court mapping: 4/5 at elbows (FT band), not on the 3pt arc (~y=235).
    assert 155 < pos["o4"]["y"] < 200, pos["o4"]
    assert 155 < pos["o5"]["y"] < 200, pos["o5"]
    assert pos["o4"]["x"] < 220, pos["o4"]
    assert pos["o5"]["x"] > 280, pos["o5"]
    assert pos["o3"]["x"] < 120, pos["o3"]
    assert pos["o2"]["x"] > 380, pos["o2"]
    assert pos["o4"]["y"] < pos["o1"]["y"] - 40
    # Elbows sit inside the 3pt (peak y=235), not on it.
    assert pos["o4"]["y"] < 220
    actions = step["ink"]["actions"]
    assert actions
    assert [a["seq"] for a in actions] == list(range(1, len(actions) + 1))
    kinds = [(a["kind"], a["fromPid"], a["toPid"]) for a in actions]
    assert ("pass", "o1", "o5") in kinds


@pytest.mark.skipif(not HAS_PDF, reason="Fast Scout PDF fixture not present")
def test_extract_rip_page122_has_dribble_or_cut_ink():
    step = extract_page(PDF, 122)
    ink = step["ink"]
    assert ink["paths"] or ink["passes"]
    # At least one attributed path / pass.
    assert len(ink["paths"]) + len(ink["passes"]) >= 1


def test_has_dash_pattern_pass_vs_cut_encoding():
    """This PDF: non-empty dash array = pass; [] = cut (Scott's typical is inverted)."""
    assert _has_dash_pattern("[ 5.25 5.25 ] 0") is True
    assert _has_dash_pattern("[5.25 5.25] 0") is True
    assert _has_dash_pattern("[] 0") is False
    assert _has_dash_pattern("[]") is False
    assert _has_dash_pattern(None) is False
    assert _has_dash_pattern([5.25, 5.25]) is True
    assert _has_dash_pattern([]) is False


@pytest.mark.skipif(not HAS_PDF, reason="Fast Scout PDF fixture not present")
def test_vector_dashed_pass_solid_cut_known_sheets():
    """Dash→pass / solid→cut on Rip, 1-Game, Triangle, Pitt (no tip≠start invents)."""
    rip120 = extract_page(PDF, 120)
    pairs120 = {(p["fromPid"], p["toPid"]) for p in rip120["ink"]["passes"]}
    assert pairs120 == {("o1", "o3")}
    assert rip120["ink"]["marks"].get("o1") == "pass"

    game32 = extract_page(PDF, 32)
    pairs32 = {(p["fromPid"], p["toPid"]) for p in game32["ink"]["passes"]}
    assert pairs32 == {("o1", "o5")}
    assert game32["ink"]["marks"].get("o3") == "cut"
    assert game32["ink"]["marks"].get("o1") == "pass"

    tri = extract_page(PDF, 127)
    pairs_tri = {(p["fromPid"], p["toPid"]) for p in tri["ink"]["passes"]}
    # Only the dashed stroke is a pass; solids toward other digits stay cuts.
    assert pairs_tri == {("o1", "o2")}
    assert ("o5", "o1") not in pairs_tri
    assert ("o1", "o3") not in pairs_tri
    assert ("o3", "o5") not in pairs_tri
    marks_tri = tri["ink"]["marks"]
    assert marks_tri.get("o5") == "cut"
    assert marks_tri.get("o3") == "cut"

    pitt = extract_page(PDF, 173)
    assert pitt["ink"]["passes"] == []
    marks_pitt = pitt["ink"]["marks"]
    assert marks_pitt.get("o4") == "cut"
    assert marks_pitt.get("o5") == "cut"


@pytest.mark.skipif(not HAS_PDF, reason="Fast Scout PDF fixture not present")
def test_rip122_dashed_stroke_attributed_via_raised_start():
    """Rip p122 dashed start was 66.7px > old 60 — still attributed after bump."""
    step = extract_page(PDF, 122)
    ink = step["ink"]
    assert ink["marks"].get("o1") == "dribble"
    assert ink["marks"].get("o2") == "cut"
    # Dashed stroke near o4 (previously dropped) now owns a pass-marked path.
    assert ink["marks"].get("o4") == "pass"
    assert "o4" in ink["paths"]


@pytest.mark.skipif(not HAS_PDF, reason="Fast Scout PDF fixture not present")
def test_extract_from_image_url(tmp_path, monkeypatch):
    # Exercise path resolution against real uploads when present.
    step = extract_sheet_from_image_url(PAGE32, app_root=Path.cwd())
    assert step is not None
    assert step["page"] == 32
    assert len(step["positions"]) >= 5


class TestSheetExtractApi:
    def test_sheet_extract_vector(self, client):
        if not HAS_PDF:
            pytest.skip("Fast Scout PDF fixture not present")
        r = client.post(
            "/api/playbook/sheet-extract",
            json={"image_url": PAGE32},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["source"] == "vector"
        assert "o1" in data["positions"]
        assert "ink" in data
