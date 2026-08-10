from pathlib import Path
import cv2
import numpy as np
from playbook_sheet_align import (
    analyze_sheet_image,
    find_court_bbox,
    _stroke_mask,
    _morph_skeleton,
    _svg_to_crop,
    _crop_to_svg,
    _walk_skeleton_to_tip,
    _poly_len_svg,
    _mid_raw_ink_fraction,
    _path_ink_fraction_stroke,
    classify_polyline_mark,
    _has_xy,
)

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
pos120 = analyze_sheet_image(base / "page_0120.png")["positions"]
pos121 = analyze_sheet_image(base / "page_0121.png")["positions"]
merged = dict(pos120)
merged.update(pos121)
img = cv2.imread(str(base / "page_0121.png"), cv2.IMREAD_GRAYSCALE)
x0, y0, x1, y1 = find_court_bbox(img)
crop = img[y0:y1, x0:x1]
ch, cw = crop.shape[:2]

for erase_r in (8, 10, 12, 14):
    stroke_raw = _stroke_mask(crop)
    erased = stroke_raw.copy()
    digit_px = []
    for i in range(1, 6):
        oid = f"o{i}"
        p = merged.get(oid)
        if not _has_xy(p):
            continue
        cx, cy = _svg_to_crop(p, cw, ch)
        digit_px.append((oid, cx, cy, 16))
        cv2.circle(erased, (cx, cy), erase_r, 0, -1)
    skel = _morph_skeleton(erased)
    walkable = cv2.bitwise_or(skel, cv2.dilate(skel, np.ones((3, 3), np.uint8), 1))
    print(f"\n=== erase_r={erase_r} ===")
    for oid, cx, cy, rad in digit_px:
        if oid not in ("o4", "o5"):
            continue
        seeds = []
        for yy in range(max(0, cy - 40), min(ch, cy + 42)):
            for xx in range(max(0, cx - 40), min(cw, cx + 42)):
                d2 = (xx - cx) ** 2 + (yy - cy) ** 2
                if d2 < 6 ** 2 or d2 > 38 ** 2:
                    continue
                if walkable[yy, xx]:
                    seeds.append((xx, yy))
        others = [(c, y, r) for (oid2, c, y, r) in digit_px if oid2 != oid]
        start_digits = [(cx, cy, rad)] + others
        best = None
        seen = set()
        for sx, sy in seeds:
            key = (sx // 4, sy // 4)
            if key in seen:
                continue
            seen.add(key)
            path_px = _walk_skeleton_to_tip(walkable, sx, sy, start_digits, max_steps=700)
            if len(path_px) < 5:
                continue
            svg_pts = [_crop_to_svg(x, y, cw, ch) for x, y in path_px]
            svg_pts[0] = {"x": float(merged[oid]["x"]), "y": float(merged[oid]["y"])}
            tip = svg_pts[-1]
            disp = ((tip["x"] - svg_pts[0]["x"]) ** 2 + (tip["y"] - svg_pts[0]["y"]) ** 2) ** 0.5
            plen = _poly_len_svg(svg_pts)
            if disp < 25 or plen > 280:
                continue
            mid = max(
                _mid_raw_ink_fraction(crop, svg_pts, svg_pts[0], tip),
                _path_ink_fraction_stroke(crop, svg_pts, svg_pts[0], tip),
            )
            kind = classify_polyline_mark(crop, svg_pts)
            score = disp + (40 if kind == "screen" else 0)
            if best is None or score > best[0]:
                best = (score, disp, plen, mid, kind, tip)
        if best:
            print(f"  {oid}: disp={best[1]:.1f} plen={best[2]:.1f} mid={best[3]:.2f} kind={best[4]} tip=({best[5]['x']:.1f},{best[5]['y']:.1f})")
        else:
            print(f"  {oid}: NONE")
