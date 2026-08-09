"""Prototype tighter outgoing discovery for Rip page 122."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from playbook_sheet_align import (
    _crop_to_svg,
    _has_xy,
    _ink_mask_no_close,
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


def discover_outgoing_v2(crop_gray, positions, min_disp_svg=40.0, min_len_svg=45.0):
    ch, cw = crop_gray.shape[:2]
    stroke_raw = _stroke_mask(crop_gray)
    # Erase digit disks so walks cannot loop on glyph ink.
    erased = stroke_raw.copy()
    digit_px = []
    for i in range(1, 6):
        oid = f"o{i}"
        p = (positions or {}).get(oid)
        if not _has_xy(p):
            continue
        cx, cy = _svg_to_crop(p, cw, ch)
        digit_px.append((oid, cx, cy, 18))
        cv2.circle(erased, (cx, cy), 20, 0, -1)

    skel = _morph_skeleton(erased)
    if cv2.countNonZero(skel) < 20:
        skel = cv2.dilate(erased, np.ones((3, 3), np.uint8), 1)
    walkable = cv2.bitwise_or(skel, cv2.dilate(skel, np.ones((3, 3), np.uint8), 1))

    paths = {}
    marks = {}
    for oid, cx, cy, rad in digit_px:
        seeds = []
        # Wider annulus — action strokes often start outside tight digit ring.
        for yy in range(max(0, cy - 36), min(ch, cy + 38)):
            for xx in range(max(0, cx - 36), min(cw, cx + 38)):
                d2 = (xx - cx) ** 2 + (yy - cy) ** 2
                if d2 < 16 ** 2 or d2 > 34 ** 2:
                    continue
                if walkable[yy, xx]:
                    seeds.append((xx, yy))
        if not seeds:
            continue
        others = [(c, y, r) for (oid2, c, y, r) in digit_px if oid2 != oid]
        start_digits = [(cx, cy, rad)] + others
        best = None
        seen = set()
        for sx, sy in seeds:
            key = (sx // 4, sy // 4)
            if key in seen:
                continue
            seen.add(key)
            path_px = _walk_skeleton_to_tip(walkable, sx, sy, start_digits, max_steps=1200)
            if len(path_px) < 6:
                continue
            svg_pts = [_crop_to_svg(x, y, cw, ch) for x, y in path_px]
            svg_pts[0] = {"x": float(positions[oid]["x"]), "y": float(positions[oid]["y"])}
            tip = svg_pts[-1]
            disp = ((tip["x"] - svg_pts[0]["x"]) ** 2 + (tip["y"] - svg_pts[0]["y"]) ** 2) ** 0.5
            plen = _poly_len_svg(svg_pts)
            if disp < min_disp_svg or plen < min_len_svg:
                continue
            # Prefer stroke-mask mid-ink (raw no-close zeroes on closed squiggles)
            mid_raw = _mid_raw_ink_fraction(crop_gray, svg_pts, svg_pts[0], tip)
            # stroke mid
            pts = []
            for pt in svg_pts:
                pts.append(_svg_to_crop(pt, cw, ch))
            sx0, sy0 = pts[0]
            ex0, ey0 = pts[-1]
            r2 = 28 * 28
            mid_pts = [
                (x, y)
                for (x, y) in pts
                if (x - sx0) ** 2 + (y - sy0) ** 2 > r2 and (x - ex0) ** 2 + (y - ey0) ** 2 > r2
            ]
            if len(mid_pts) < 4:
                mid_stroke = 0.0
            else:
                from playbook_sheet_align import _path_ink_fraction
                mid_stroke = _path_ink_fraction(erased, mid_pts, radius=5)
            mid = max(mid_raw, mid_stroke)
            if mid < 0.35:
                continue
            kind = classify_polyline_mark(crop_gray, svg_pts)
            if kind == "pass":
                continue
            # Squiggle → dribble: high path_len / displacement ratio
            if plen / max(disp, 1.0) >= 1.55 and kind == "cut":
                kind = "dribble"
            score = disp + 0.25 * plen + 40 * mid
            if best is None or score > best[0]:
                best = (score, svg_pts, kind, disp, plen, mid)
        if best:
            paths[oid] = best[1]
            marks[oid] = best[2]
            print(
                f"  {oid}: kind={best[2]} disp={best[3]:.1f} len={best[4]:.1f} mid={best[5]:.2f} "
                f"tip=({best[1][-1]['x']:.1f},{best[1][-1]['y']:.1f})"
            )
    return paths, marks


base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
for pg in (120, 121, 122):
    p = base / f"page_{pg:04d}.png"
    pos = analyze_sheet_image(p)["positions"]
    img = cv2.imread(str(p))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    x0, y0, x1, y1 = find_court_bbox(gray)
    crop = gray[y0:y1, x0:x1]
    print(f"\n=== page_{pg} v2 outgoing ===")
    discover_outgoing_v2(crop, pos)
