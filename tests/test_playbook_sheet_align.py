"""Tests for play-sheet court crop + digit alignment."""

import json
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from playbook_sheet_align import analyze_sheet_image, find_court_bbox, resolve_upload_path


FIXTURE = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0087.png")


@pytest.mark.skipif(not FIXTURE.is_file(), reason="Rub page_0087 fixture not present")
def test_find_court_bbox_skips_header():
    img = cv2.imread(str(FIXTURE))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    x0, y0, x1, y1 = find_court_bbox(gray)
    assert y0 > h * 0.15  # header above court
    assert (x1 - x0) * (y1 - y0) > w * h * 0.2


@pytest.mark.skipif(not FIXTURE.is_file(), reason="Rub page_0087 fixture not present")
def test_analyze_sheet_finds_opening_digits(tmp_path):
    result = analyze_sheet_image(FIXTURE, cache_base=tmp_path)
    assert result["ok"]
    frac = result["court_frac"]
    assert frac["y0"] > 0.15
    pos = result["positions"]
    # Sheet 1 Rub has at least the wing/point digits
    assert "o1" in pos
    assert "o2" in pos
    assert "o3" in pos
    # Point (1) is below the wings (higher y, basket at top)
    assert pos["o1"]["y"] > pos["o2"]["y"]
    assert pos["o1"]["y"] > 250


def test_resolve_upload_path(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads" / "bulk_imports"
    uploads.mkdir(parents=True)
    f = uploads / "a.png"
    f.write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    p = resolve_upload_path("/uploads/bulk_imports/a.png", tmp_path)
    assert p == f.resolve()


def test_sheet_align_api(client, tmp_path, monkeypatch):
    if not FIXTURE.is_file():
        pytest.skip("Rub fixture missing")
    # Point resolve into real uploads; cache into tmp
    r = client.post(
        "/api/playbook/sheet-align",
        data=json.dumps({"image_url": "/uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0087.png"}),
        content_type="application/json",
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data.get("ok")
    assert "court_frac" in data
    assert "o1" in (data.get("positions") or {})


@pytest.mark.skipif(not FIXTURE.is_file(), reason="Rub page_0087 fixture not present")
def test_trace_paths_end_on_destination_digits():
    from playbook_sheet_align import analyze_sheet_image, trace_paths_for_transition

    base = FIXTURE.parent
    a = analyze_sheet_image(base / "page_0089.png")
    b = analyze_sheet_image(base / "page_0090.png")
    paths = trace_paths_for_transition(base / "page_0089.png", a["positions"], b["positions"])
    assert paths
    for pid, poly in paths.items():
        assert len(poly) >= 2
        assert poly[0]["x"] == a["positions"][pid]["x"]
        assert poly[0]["y"] == a["positions"][pid]["y"]
        assert poly[-1]["x"] == b["positions"][pid]["x"]
        assert poly[-1]["y"] == b["positions"][pid]["y"]
