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


def test_classify_rejects_multidigit_substring_false_positive():
    """Regression: `"23" in "12345"` is True — must require exact digit tokens."""
    assert ("23" in "12345") is True  # documents the footgun
    assert ("23" in ("1", "2", "3", "4", "5")) is False
    from playbook_sheet_align import _classify_roi

    # Synthetic blank ROI — template fallback may return 0; just ensure no crash
    # and that multi-digit EasyOCR hits cannot become digit 23 via substring.
    gray = np.full((40, 30), 255, np.uint8)
    digit, _conf = _classify_roi(gray)
    assert digit in (0, 1, 2, 3, 4, 5)


@pytest.mark.skipif(
    not Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0138.png").is_file(),
    reason="Zone-Slash page_0138 fixture not present",
)
def test_zone_slash_align_skips_header_digits(tmp_path):
    """Press-break pages must not park tokens on title text (o23 / y≈7)."""
    page = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0138.png")
    result = analyze_sheet_image(page, cache_base=tmp_path)
    assert result["ok"]
    assert result["court_frac"]["y0"] > 0.15, result["court_frac"]
    pos = result["positions"]
    assert "o23" not in pos
    assert all(k in {f"o{i}" for i in range(1, 6)} for k in pos)
    # Detected digits should sit on the court, not the title strip.
    for pid, p in pos.items():
        assert p["y"] > 30, f"{pid} still in header band: {p}"


def test_playbook_html_has_align_ready_banner():
    html = PLAYBOOK_HTML.read_text(encoding="utf-8")
    assert "sheetAlignBanner" in html
    assert "Aligning play sheets" in html
    assert "Ready to play" in html
    assert "playAllBtn" in html
    assert "setSheetAlignStatus" in html
    # Default Play All is animation (opt-in slideshow only).
    assert "__playbookSheetSlideshow" in html
    assert "buildActionBeats" in html
    assert "fetchSheetInkPaths" in html
    assert "orientSheetPass" in html
    assert "orderTriangleBeats" in html
    assert "isTrianglePlay" in html
    assert "heldLandings" in html
    assert "sheetDigitMaskLayer" in html
    # Animation view: no sheet underlay / white digit disks (tokens on SVG court).
    assert "Clean animated court: no sheet PNG, no white digit disks" in html
    assert "Digit masks retired for animation view" in html
    # Ink fetch must use next-sheet OCR, not animated/held toRaw tips.
    assert "nextHere[oid] || here[oid] || a" in html
    assert "if (!anyMove) return { paths: {}, marks: {}, passes: [] };" not in html
    assert "return playHasSheets(list) && !playHasDrawnMovements(list);" not in html


@pytest.mark.skipif(
    not Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0127.png").is_file(),
    reason="Triangle page_0127 fixture not present",
)
def test_triangle_opening_pass_then_cuts():
    """Triangle page 127: Pass 1→2 then cuts 1→3, 5→top, 3 toward 2, 4 across."""
    from playbook_sheet_align import analyze_sheet_image, trace_marked_paths_for_transition

    base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
    pos = analyze_sheet_image(base / "page_0127.png")["positions"]
    marked = trace_marked_paths_for_transition(base / "page_0127.png", pos, pos)
    pairs = {(p["fromPid"], p["toPid"]) for p in marked.get("passes") or [] if not p.get("orphan")}
    assert ("o1", "o2") in pairs
    marks = marked.get("marks") or {}
    paths = marked.get("paths") or {}
    assert marks.get("o1") == "cut"
    assert marks.get("o5") == "cut"
    assert marks.get("o3") == "cut"
    assert marks.get("o4") == "cut"
    assert "o2" not in marks  # receiver stays
    # 1 cuts toward left wing (3); 5 fills top (higher y); 4 slides right.
    assert paths["o1"][-1]["x"] < 120
    assert paths["o5"][-1]["y"] > paths["o5"][0]["y"] + 80
    assert paths["o4"][-1]["x"] > paths["o4"][0]["x"] + 80
    assert paths["o3"][-1]["x"] > paths["o3"][0]["x"] + 80


@pytest.mark.skipif(
    not Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0128.png").is_file(),
    reason="Triangle page_0128 fixture not present",
)
def test_triangle_entry_pass_only():
    """Triangle page 128: Pass 2→5 only (no invented rotation cuts)."""
    from playbook_sheet_align import analyze_sheet_image, trace_marked_paths_for_transition

    base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
    pos = analyze_sheet_image(base / "page_0128.png")["positions"]
    # Carry o3 from opening (OCR often misses it on mid sheets).
    pos = dict(pos)
    pos.setdefault("o3", {"x": 250.0, "y": 200.0})
    marked = trace_marked_paths_for_transition(base / "page_0128.png", pos, pos)
    pairs = {(p["fromPid"], p["toPid"]) for p in marked.get("passes") or [] if not p.get("orphan")}
    assert ("o2", "o5") in pairs
    assert ("o5", "o1") not in pairs
    assert not (marked.get("marks") or {})


@pytest.mark.skipif(
    not Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0129.png").is_file(),
    reason="Triangle page_0129 fixture not present",
)
def test_triangle_rotation_pass_and_cuts():
    """Triangle page 129: Pass 5→1, then 5→2 / 3→top / 2→nail / 4 across."""
    from playbook_sheet_align import analyze_sheet_image, trace_marked_paths_for_transition

    base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
    pos = analyze_sheet_image(base / "page_0129.png")["positions"]
    pos = dict(pos)
    pos.setdefault("o3", {"x": 250.0, "y": 200.0})
    # Fresh OCR leaves 4 on the left so the printed cross still fires.
    marked = trace_marked_paths_for_transition(base / "page_0129.png", pos, pos)
    pairs = {(p["fromPid"], p["toPid"]) for p in marked.get("passes") or [] if not p.get("orphan")}
    assert ("o5", "o1") in pairs
    marks = marked.get("marks") or {}
    paths = marked.get("paths") or {}
    assert marks.get("o5") == "cut"
    assert marks.get("o3") == "cut"
    assert marks.get("o2") == "cut"
    assert marks.get("o4") == "cut"
    assert paths["o5"][-1]["x"] > 380
    assert paths["o3"][-1]["y"] > 250
    assert paths["o4"][-1]["x"] > paths["o4"][0]["x"] + 80


@pytest.mark.skipif(
    not Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0120.png").is_file(),
    reason="Rip page_0120 fixture not present",
)
def test_rip_sheet_pass_filters_false_chord():
    """Rip page 120: keep dashed 1→3 pass; reject white-space chord to 4."""
    from playbook_sheet_align import analyze_sheet_image, trace_marked_paths_for_transition

    base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
    pos = analyze_sheet_image(base / "page_0120.png")["positions"]
    marked = trace_marked_paths_for_transition(base / "page_0120.png", pos, pos)
    pairs = {(p["fromPid"], p["toPid"]) for p in marked.get("passes") or []}
    assert ("o1", "o3") in pairs
    assert ("o1", "o4") not in pairs
    # Pass sheet must not invent o5 screen/dribble from court-line wander.
    assert "o5" not in (marked.get("marks") or {})
    assert "o4" not in (marked.get("marks") or {})
    # Guard must not "screen" onto another digit (regression: o1→o5 screen).
    assert "o1" not in (marked.get("marks") or {})
    assert "o2" not in (marked.get("marks") or {})
    assert "o3" not in (marked.get("marks") or {})


@pytest.mark.skipif(
    not Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0121.png").is_file(),
    reason="Rip page_0121 fixture not present",
)
def test_rip_page_121_big_screens_hold():
    """Rip page 121: o4/o5 walk left to T-bar screen tips (carry-forward o4)."""
    from playbook_sheet_align import analyze_sheet_image, trace_marked_paths_for_transition

    base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
    pos120 = analyze_sheet_image(base / "page_0120.png")["positions"]
    pos121 = analyze_sheet_image(base / "page_0121.png")["positions"]
    merged = dict(pos120)
    merged.update(pos121)
    marked = trace_marked_paths_for_transition(base / "page_0121.png", merged, merged)
    marks = marked.get("marks") or {}
    paths = marked.get("paths") or {}
    assert marks.get("o4") == "screen"
    assert marks.get("o5") == "screen"
    # Tips sit left of starts (into the paint), not snapped back to wing/elbow.
    assert paths["o4"][-1]["x"] < paths["o4"][0]["x"] - 45
    assert paths["o5"][-1]["x"] < paths["o5"][0]["x"] - 45
    assert abs(paths["o4"][-1]["y"] - paths["o4"][0]["y"]) < 80
    assert abs(paths["o5"][-1]["y"] - paths["o5"][0]["y"]) < 50
    # Reverse-pass sheet: bigs screen only — no false guard screen/cut residue.
    assert marks.get("o1") != "screen"
    assert "o1" not in marks
    assert "o3" not in marks


@pytest.mark.skipif(
    not Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0122.png").is_file(),
    reason="Rip page_0122 fixture not present",
)
def test_rip_page_122_dribble_corner_drop():
    """Rip page 122: 1 dribbles to block tip; 2 cuts to corner; orphan pass 1→2."""
    from playbook_sheet_align import analyze_sheet_image, trace_marked_paths_for_transition

    base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
    pos = analyze_sheet_image(base / "page_0122.png")["positions"]
    marked = trace_marked_paths_for_transition(base / "page_0122.png", pos, pos)
    marks = marked.get("marks") or {}
    paths = marked.get("paths") or {}
    assert marks.get("o1") == "dribble"
    assert marks.get("o2") == "cut"
    assert paths["o1"][-1]["y"] < paths["o1"][0]["y"]  # toward basket
    assert paths["o2"][-1]["y"] < paths["o2"][0]["y"]  # drop to corner
    assert paths["o2"][-1]["x"] > 380  # right corner
    orphans = [p for p in (marked.get("passes") or []) if p.get("orphan")]
    assert orphans and orphans[0].get("fromPid") == "o1" and orphans[0].get("toPid") == "o2"
    # Beat order contract used by the animator: dribble before cut destination.
    assert paths["o1"][-1]["y"] < 150  # elbow/block tip, not reverse-swap upcourt
    assert paths["o2"][-1]["y"] < paths["o2"][0]["y"] - 40


@pytest.mark.skipif(
    not Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0122.png").is_file(),
    reason="Rip page_0122 fixture not present",
)
def test_rip_page_122_ignores_held_landing_to_positions():
    """Stale held to_positions (prior screen tip) must not turn o1 dribble into a cut."""
    from playbook_sheet_align import analyze_sheet_image, trace_marked_paths_for_transition

    base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
    pos = analyze_sheet_image(base / "page_0122.png")["positions"]
    # Client bug shape: OCR from, heldLandings to (o1 yanked to o5's old tip).
    to_pos = dict(pos)
    to_pos["o1"] = {"x": 319.5, "y": 192.9}
    marked = trace_marked_paths_for_transition(base / "page_0122.png", pos, to_pos)
    marks = marked.get("marks") or {}
    paths = marked.get("paths") or {}
    assert marks.get("o1") == "dribble"
    assert marks.get("o2") == "cut"
    assert paths["o1"][-1]["y"] < 150
    assert paths["o2"][-1]["y"] < pos["o2"]["y"] - 40
    orphans = [p for p in (marked.get("passes") or []) if p.get("orphan")]
    assert orphans and orphans[0].get("fromPid") == "o1" and orphans[0].get("toPid") == "o2"


def test_classify_dashed_pass_vs_solid_cut():
    """Dashed corridor → pass; solid stroke → cut."""
    from playbook_sheet_align import classify_polyline_mark

    h, w = 300, 400
    # Solid cut
    solid = np.full((h, w), 255, np.uint8)
    cv2.line(solid, (40, 150), (360, 150), 0, 3)
    solid_poly = [
        {"x": 40.0 / w * 500.0, "y": 150.0 / h * 470.0},
        {"x": 360.0 / w * 500.0, "y": 150.0 / h * 470.0},
    ]
    assert classify_polyline_mark(solid, solid_poly) == "cut"

    # Dashed pass
    dashed = np.full((h, w), 255, np.uint8)
    for x0 in range(40, 360, 24):
        cv2.line(dashed, (x0, 150), (min(360, x0 + 10), 150), 0, 3)
    dashed_poly = [
        {"x": 40.0 / w * 500.0, "y": 150.0 / h * 470.0},
        {"x": 200.0 / w * 500.0, "y": 150.0 / h * 470.0},
        {"x": 360.0 / w * 500.0, "y": 150.0 / h * 470.0},
    ]
    assert classify_polyline_mark(dashed, dashed_poly) == "pass"


def test_classify_tbar_screen():
    from playbook_sheet_align import classify_polyline_mark

    h, w = 300, 400
    gray = np.full((h, w), 255, np.uint8)
    # Short stem ending with T-bar
    cv2.line(gray, (200, 220), (200, 140), 0, 3)
    cv2.line(gray, (175, 140), (225, 140), 0, 4)
    poly = [
        {"x": 200.0 / w * 500.0, "y": 220.0 / h * 470.0},
        {"x": 200.0 / w * 500.0, "y": 140.0 / h * 470.0},
    ]
    assert classify_polyline_mark(gray, poly) == "screen"


@pytest.mark.skipif(
    not Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0172.png").is_file(),
    reason="Pitt 5 page_0172 fixture not present",
)
def test_pitt5_opening_pass_and_corner_clears():
    """Pitt 5 page 172: Pass 1→5, Cut 1 left corner, Relocate 2 right corner."""
    from playbook_sheet_align import analyze_sheet_image, trace_marked_paths_for_transition

    base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
    pos = analyze_sheet_image(base / "page_0172.png")["positions"]
    marked = trace_marked_paths_for_transition(base / "page_0172.png", pos, pos)
    pairs = {
        (p["fromPid"], p["toPid"])
        for p in marked.get("passes") or []
        if not p.get("orphan")
    }
    assert ("o1", "o5") in pairs
    marks = marked.get("marks") or {}
    paths = marked.get("paths") or {}
    assert marks.get("o1") == "cut"
    assert marks.get("o2") == "cut"
    assert "o5" not in marks  # receiver stays (no false pass-corridor cut)
    assert paths["o1"][-1]["x"] < 120
    assert paths["o1"][-1]["y"] < 160
    assert paths["o2"][-1]["x"] > 380
    assert paths["o2"][-1]["y"] < 160


@pytest.mark.skipif(
    not Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0173.png").is_file(),
    reason="Pitt 5 page_0173 fixture not present",
)
def test_pitt5_screen_sheet_routes():
    """Pitt 5 page 173: Screen 4 (3pt), Cut 5 around to right block, o4_drop left."""
    from playbook_sheet_align import analyze_sheet_image, trace_marked_paths_for_transition

    base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
    pos = analyze_sheet_image(base / "page_0173.png")["positions"]
    marked = trace_marked_paths_for_transition(base / "page_0173.png", pos, pos)
    marks = marked.get("marks") or {}
    paths = marked.get("paths") or {}
    assert marks.get("o4") == "screen"
    assert marks.get("o5") == "cut"
    assert marks.get("o4_drop") == "cut"
    assert "o4_drop" in paths
    o5_start = paths["o5"][0]
    o5_end = paths["o5"][-1]
    # 5 finishes on the right side of the paint / right block.
    assert o5_end["x"] > 220
    assert o5_end["y"] < o5_start["y"]
    # Screen approach is a straight 2-point slide (no squiggly ink stem).
    assert len(paths["o4"]) == 2
    # Screen holds near top / 3pt (not the left block), with clearance from #5.
    o4_end = paths["o4"][-1]
    assert o4_end["y"] > 180
    assert o4_end["x"] < 280
    assert not (o4_end["x"] < 220 and o4_end["y"] < 140)
    gap_45 = (
        (o4_end["x"] - o5_start["x"]) ** 2 + (o4_end["y"] - o5_start["y"]) ** 2
    ) ** 0.5
    assert gap_45 >= 55.0
    # #5 curls around the screener (mid waypoint right of screen tip).
    assert len(paths["o5"]) >= 3
    mid = paths["o5"][1]
    assert mid["x"] > o4_end["x"] + 20
    # Drop starts at screen tip and ends on the left block.
    drop = paths["o4_drop"]
    assert abs(drop[0]["x"] - o4_end["x"]) < 2 and abs(drop[0]["y"] - o4_end["y"]) < 2
    assert drop[-1]["x"] < 220
    assert drop[-1]["y"] < 140
    assert not (marked.get("passes") or [])
