"""Tests for play-sheet court crop + digit alignment."""

import json
from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from playbook_sheet_align import (
    analyze_sheet_image,
    find_court_bbox,
    resolve_upload_path,
    trace_ink_polyline,
    _morph_skeleton,
    _path_ink_fraction,
    _stroke_mask,
)


FIXTURE = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0087.png")
PLAYBOOK_HTML = Path("templates/playbook.html")


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


def _poly_len(poly):
    total = 0.0
    for i in range(1, len(poly)):
        total += (
            (poly[i]["x"] - poly[i - 1]["x"]) ** 2
            + (poly[i]["y"] - poly[i - 1]["y"]) ** 2
        ) ** 0.5
    return total


def test_trace_ink_polyline_hugs_curved_stroke():
    """Synthetic curved ink — path must follow the stroke, not chord white space."""
    h, w = 400, 500
    gray = np.full((h, w), 255, np.uint8)
    pts = []
    for i in range(80):
        t = i / 79.0
        x = int(50 + t * 400)
        y = int(200 + 80 * np.sin(t * np.pi))
        pts.append((x, y))
    for i in range(1, len(pts)):
        cv2.line(gray, pts[i - 1], pts[i], 0, 3)

    start_svg = {"x": 50.0 / w * 500.0, "y": 200.0 / h * 470.0}
    end_svg = {"x": 450.0 / w * 500.0, "y": 200.0 / h * 470.0}
    poly = trace_ink_polyline(gray, start_svg, end_svg)
    assert len(poly) >= 8
    assert poly[0]["x"] == pytest.approx(start_svg["x"])
    assert poly[0]["y"] == pytest.approx(start_svg["y"])
    assert poly[-1]["x"] == pytest.approx(end_svg["x"])
    assert poly[-1]["y"] == pytest.approx(end_svg["y"])

    straight = (
        (end_svg["x"] - start_svg["x"]) ** 2 + (end_svg["y"] - start_svg["y"]) ** 2
    ) ** 0.5
    ratio = _poly_len(poly) / max(straight, 1.0)
    assert ratio >= 1.08, f"expected curved detour, got ratio={ratio:.3f}"

    path_px = [
        (int(round(p["x"] / 500.0 * w)), int(round(p["y"] / 470.0 * h))) for p in poly
    ]
    skel = _morph_skeleton(_stroke_mask(gray))
    ink = _path_ink_fraction(skel, path_px, radius=5)
    assert ink >= 0.7, f"expected ink hug >=0.7, got {ink:.3f}"


def test_trace_ink_rejects_endpoint_only_on_digit_blobs():
    """Two isolated blobs alone must not score as a high-ink curved stroke."""
    h, w = 300, 400
    gray = np.full((h, w), 255, np.uint8)
    cv2.circle(gray, (60, 150), 8, 0, -1)
    cv2.circle(gray, (340, 150), 8, 0, -1)
    start_svg = {"x": 60.0 / w * 500.0, "y": 150.0 / h * 470.0}
    end_svg = {"x": 340.0 / w * 500.0, "y": 150.0 / h * 470.0}
    poly = trace_ink_polyline(gray, start_svg, end_svg)
    straight = (
        (end_svg["x"] - start_svg["x"]) ** 2 + (end_svg["y"] - start_svg["y"]) ** 2
    ) ** 0.5
    # Without a real connecting stroke, keep near-chord (no fake long ink detour).
    assert _poly_len(poly) / max(straight, 1.0) < 1.35


def test_playbook_html_does_not_invent_synthetic_passes():
    html = PLAYBOOK_HTML.read_text(encoding="utf-8")
    assert "Do NOT invent synthetic passes" in html
    assert "inferPassReceiver" not in html
    assert "Classic wing: o1 → o2" not in html
    assert "function buildActionBeats" in html
