"""Unit tests for Fast Scout play diagram digitization (no EasyOCR required)."""

from __future__ import annotations

import numpy as np
import pytest

from playbook_digitize import (
    _classify_text,
    _suppress_offense_near_defense,
    detect_court_frame,
    prefer_from_play_category,
    px_to_svg,
    resolve_image_path,
)


def test_classify_text_offense_and_defense():
    assert _classify_text("3") == ("offense", 3)
    assert _classify_text("x2") == ("defense", 2)
    assert _classify_text("X5") == ("defense", 5)
    assert _classify_text("x") == ("x_only", None)
    assert _classify_text("12") == (None, None)


def test_px_to_svg_y_flip_basket_at_image_top():
    court = (0, 0, 1000, 1000)
    # Image top-center (basket) → high SVG y
    sx, sy = px_to_svg(500, 50, court)
    assert 240 <= sx <= 260
    assert sy > 400
    # Image bottom-center (half court) → low SVG y
    sx2, sy2 = px_to_svg(500, 950, court)
    assert sy2 < 80


def test_suppress_offense_near_defense():
    markers = [
        {"kind": "offense", "id": 2, "conf": 1.0, "fx": 100, "fy": 100, "key": "o2"},
        {"kind": "defense", "id": 2, "conf": 1.0, "fx": 105, "fy": 102, "key": "d2"},
        {"kind": "offense", "id": 1, "conf": 1.0, "fx": 400, "fy": 400, "key": "o1"},
    ]
    kept = _suppress_offense_near_defense(markers)
    keys = {(m["kind"], m["id"]) for m in kept}
    assert ("defense", 2) in keys
    assert ("offense", 1) in keys
    assert ("offense", 2) not in keys


def test_prefer_from_category():
    assert prefer_from_play_category("defense") == "defense"
    assert prefer_from_play_category("offense") == "offense"
    assert prefer_from_play_category("") == "auto"


def test_detect_court_frame_fallback_shape():
    gray = np.full((1584, 1224), 255, dtype=np.uint8)
    # Draw a dark square court frame
    gray[260:1060, 100:1120] = 0
    gray[270:1050, 110:1110] = 255
    box = detect_court_frame(gray)
    x0, y0, x1, y1 = box
    assert x1 - x0 > 500
    assert y1 - y0 > 400
    assert y0 < 400


def test_resolve_image_path_missing(tmp_path):
    assert resolve_image_path("/uploads/nope.png", upload_root=tmp_path) is None
