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
    cv2.circle(erased, (cx, cy), 18, 0, -1)
skel = _morph_skeleton(erased)
walkable = cv2.bitwise_or(skel, cv2.dilate(skel, np.ones((3, 3), np.uint8), 1))
print("skel nonzero", cv2.countNonZero(skel))

for oid, cx, cy, rad in digit_px:
    if oid not in ("o4", "o5"):
        continue
    seeds = []
    for yy in range(max(0, cy - 34), min(ch, cy + 36)):
        for xx in range(max(0, cx - 34), min(cw, cx + 36)):
            d2 = (xx - cx) ** 2 + (yy - cy) ** 2
            if d2 < 14 ** 2 or d2 > 32 ** 2:
                continue
            if walkable[yy, xx]:
                seeds.append((xx, yy))
    print(f"\n{oid} at crop ({cx},{cy}) svg=({merged[oid]['x']:.1f},{merged[oid]['y']:.1f}) seeds={len(seeds)}")
    others = [(c, y, r) for (oid2, c, y, r) in digit_px if oid2 != oid]
    start_digits = [(cx, cy, rad)] + others
    seen = set()
    cands = []
    for sx, sy in seeds[:80]:
        key = (sx // 5, sy // 5)
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
        mid = max(
            _mid_raw_ink_fraction(crop, svg_pts, svg_pts[0], tip),
            _path_ink_fraction_stroke(crop, svg_pts, svg_pts[0], tip),
        )
        kind = classify_polyline_mark(crop, svg_pts)
        reason = []
        if disp < 30 or plen < 30:
            reason.append("short")
        if plen > 260 or disp > 220:
            reason.append("long")
        if plen / max(disp, 1.0) > 2.6:
            reason.append("loop")
        if mid < 0.35:
            reason.append(f"mid={mid:.2f}")
        if kind == "pass":
            reason.append("pass")
        cands.append((disp, plen, mid, kind, tip, ",".join(reason) or "OK"))
    cands.sort(key=lambda t: -t[0])
    for c in cands[:8]:
        print(f"  disp={c[0]:.1f} plen={c[1]:.1f} mid={c[2]:.2f} kind={c[3]} tip=({c[4]['x']:.1f},{c[4]['y']:.1f}) {c[5]}")
