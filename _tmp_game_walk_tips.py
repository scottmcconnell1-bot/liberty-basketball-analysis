"""Estimate ink arrow tips per 1-Game page by walking from seeded starts."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from playbook_sheet_align import (
    COURT_H,
    COURT_W,
    classify_polyline_mark,
    detect_sheet_digits,
    find_court_bbox,
    _crop_to_svg,
    _morph_skeleton,
    _stroke_mask,
    _svg_to_crop,
    _walk_skeleton_to_tip,
)

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")

# PDF-matching starts (OCR preferred when present)
PAGE_STARTS = {
    "0032": {
        "o1": (254.6, 301.0),
        "o2": (433.5, 209.2),
        "o3": (66.5, 209.2),
        "o4": (191.0, 188.0),
        "o5": (308.0, 188.0),
    },
    "0033": {
        "o1": (254.6, 301.0),
        "o2": (433.5, 209.2),
        "o3": (178.1, 99.8),
        "o4": (110.0, 215.0),
        "o5": (390.0, 215.0),
    },
    "0034": {
        "o1": (101.1, 250.3),
        "o2": (433.5, 209.2),
        "o3": (178.1, 99.8),
        "o4": (224.1, 297.8),
        "o5": (390.0, 215.0),
    },
    "0035": {
        "o1": (101.1, 250.3),
        "o2": (433.5, 209.2),
        "o3": (308.0, 165.0),
        "o4": (254.6, 301.0),
        "o5": (178.0, 100.0),
    },
    "0036": {
        "o1": (101.1, 250.3),
        "o2": (433.5, 209.2),
        "o3": (248.9, 292.1),
        "o4": (298.1, 179.5),
        "o5": (178.0, 100.0),
    },
}


def walk_all(page: str):
    path = base / f"page_{page}.png"
    img = cv2.imread(str(path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    court = find_court_bbox(gray)
    x0, y0, x1, y1 = court
    crop = gray[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]
    ocr = detect_sheet_digits(gray, court)
    starts = dict(PAGE_STARTS[page])
    for k, v in ocr.items():
        if k.startswith("o"):
            starts[k] = (float(v["x"]), float(v["y"]))

    stroke = _stroke_mask(crop)
    erased = stroke.copy()
    digit_px = []
    for oid, (sx, sy) in starts.items():
        cx, cy = _svg_to_crop({"x": sx, "y": sy}, cw, ch)
        digit_px.append((oid, cx, cy, 16))
        erase_r = 10 if oid in ("o4", "o5") else 14
        cv2.circle(erased, (cx, cy), erase_r, 0, -1)
    skel = _morph_skeleton(erased)
    walkable = cv2.bitwise_or(skel, cv2.dilate(skel, np.ones((3, 3), np.uint8), 1))

    print(f"\n=== {page} starts={ {k:(round(v[0],1),round(v[1],1)) for k,v in sorted(starts.items())} } ===")
    for oid, cx, cy, rad in digit_px:
        seeds = []
        for yy in range(max(0, cy - 40), min(ch, cy + 42)):
            for xx in range(max(0, cx - 40), min(cw, cx + 42)):
                d2 = (xx - cx) ** 2 + (yy - cy) ** 2
                if d2 < 10 ** 2 or d2 > 38 ** 2:
                    continue
                if walkable[yy, xx]:
                    seeds.append((xx, yy))
        if not seeds:
            print(f"  {oid}: no seeds")
            continue
        best = None
        others = [(c, y, r) for (oid2, c, y, r) in digit_px if oid2 != oid]
        for sx, sy in seeds[::3]:
            path_px = _walk_skeleton_to_tip(walkable, sx, sy, [(cx, cy, rad)] + others, max_steps=800)
            if len(path_px) < 6:
                continue
            tip = _crop_to_svg(*path_px[-1], cw, ch)
            start = {"x": starts[oid][0], "y": starts[oid][1]}
            disp = ((tip["x"] - start["x"]) ** 2 + (tip["y"] - start["y"]) ** 2) ** 0.5
            if disp < 25 or disp > 280:
                continue
            svg_pts = [_crop_to_svg(x, y, cw, ch) for x, y in path_px]
            svg_pts[0] = start
            kind = classify_polyline_mark(crop, svg_pts)
            score = disp
            if best is None or score > best[0]:
                best = (score, kind, tip, len(svg_pts))
        if best:
            print(f"  {oid}: {best[1]} tip=({best[2]['x']:.1f},{best[2]['y']:.1f}) n={best[3]} disp={best[0]:.1f}")
        else:
            print(f"  {oid}: no walk")


for p in ["0032", "0033", "0034", "0035", "0036"]:
    walk_all(p)
