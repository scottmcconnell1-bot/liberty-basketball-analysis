"""Debug why page 122 outgoing finds nothing; probe seed/walk quality."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from playbook_sheet_align import (
    _crop_to_svg,
    _has_xy,
    _mid_raw_ink_fraction,
    _morph_skeleton,
    _poly_len_svg,
    _stroke_mask,
    _svg_to_crop,
    _walk_skeleton_to_tip,
    analyze_sheet_image,
    classify_polyline_mark,
    find_court_bbox,
)

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
p = base / "page_0122.png"
pos = analyze_sheet_image(p)["positions"]
img = cv2.imread(str(p))
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
x0, y0, x1, y1 = find_court_bbox(gray)
crop = gray[y0:y1, x0:x1]
ch, cw = crop.shape[:2]
stroke_raw = _stroke_mask(crop)
skel = _morph_skeleton(stroke_raw)
if cv2.countNonZero(skel) < 20:
    skel = cv2.dilate(stroke_raw, np.ones((3, 3), np.uint8), 1)
walkable = cv2.bitwise_or(skel, cv2.dilate(skel, np.ones((3, 3), np.uint8), 1))

digit_px = []
for i in range(1, 6):
    oid = f"o{i}"
    pt = pos.get(oid)
    if not _has_xy(pt):
        continue
    cx, cy = _svg_to_crop(pt, cw, ch)
    digit_px.append((oid, cx, cy, 14))
    print(f"{oid} crop=({cx},{cy}) svg=({pt['x']:.1f},{pt['y']:.1f})")

out_dir = Path("_tmp_recording_frames/rip_review")
vis = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
vis[walkable > 0] = (0, 180, 0)
for oid, cx, cy, rad in digit_px:
    cv2.circle(vis, (cx, cy), rad, (0, 0, 255), 2)
    cv2.putText(vis, oid, (cx + 8, cy - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)

for oid, cx, cy, rad in digit_px:
    seeds = []
    yy0, yy1 = max(0, cy - rad - 12), min(ch, cy + rad + 14)
    xx0, xx1 = max(0, cx - rad - 12), min(cw, cx + rad + 14)
    for yy in range(yy0, yy1):
        for xx in range(xx0, xx1):
            d2 = (xx - cx) ** 2 + (yy - cy) ** 2
            if d2 < (rad + 3) ** 2 or d2 > (rad + 14) ** 2:
                continue
            if walkable[yy, xx]:
                seeds.append((xx, yy))
    print(f"\n{oid}: {len(seeds)} seeds")
    others = [(c, y, r) for (oid2, c, y, r) in digit_px if oid2 != oid]
    start_digits = [(cx, cy, rad)] + others
    seen = set()
    candidates = []
    for sx, sy in seeds:
        key = (sx // 5, sy // 5)
        if key in seen:
            continue
        seen.add(key)
        path_px = _walk_skeleton_to_tip(walkable, sx, sy, start_digits)
        if len(path_px) < 4:
            continue
        svg_pts = [_crop_to_svg(x, y, cw, ch) for x, y in path_px]
        svg_pts[0] = {"x": float(pos[oid]["x"]), "y": float(pos[oid]["y"])}
        plen = _poly_len_svg(svg_pts)
        mid = _mid_raw_ink_fraction(crop, svg_pts, svg_pts[0], svg_pts[-1])
        kind = classify_polyline_mark(crop, svg_pts)
        tip = svg_pts[-1]
        candidates.append((plen, mid, kind, tip, path_px))
        print(
            f"  walk n={len(path_px)} len={plen:.1f} mid={mid:.2f} kind={kind} "
            f"tip=({tip['x']:.1f},{tip['y']:.1f})"
        )
    if candidates:
        best = max(candidates, key=lambda t: t[0] if t[1] >= 0.40 and t[2] != "pass" else -1)
        if best[1] >= 0.40 and best[2] != "pass":
            for x, y in best[4]:
                cv2.circle(vis, (x, y), 1, (0, 255, 255), -1)

cv2.imwrite(str(out_dir / "page122_walk_debug.jpg"), vis)
print("wrote", out_dir / "page122_walk_debug.jpg")

# Also try larger annulus / longer walk for o1 and o2
print("\n--- relaxed annulus for o1/o2 ---")
for oid in ("o1", "o2"):
    pt = pos[oid]
    cx, cy = _svg_to_crop(pt, cw, ch)
    for rad_extra in (18, 24, 32):
        seeds = []
        for yy in range(max(0, cy - rad_extra - 16), min(ch, cy + rad_extra + 18)):
            for xx in range(max(0, cx - rad_extra - 16), min(cw, cx + rad_extra + 18)):
                d2 = (xx - cx) ** 2 + (yy - cy) ** 2
                if d2 < (10) ** 2 or d2 > (rad_extra + 16) ** 2:
                    continue
                if walkable[yy, xx]:
                    seeds.append((xx, yy))
        print(f"{oid} rad_extra={rad_extra}: {len(seeds)} seeds")
