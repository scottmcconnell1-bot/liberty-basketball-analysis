"""CC-based outgoing: assign elongated stroke components to nearest digit tip."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from playbook_sheet_align import (
    _crop_to_svg,
    _has_xy,
    _morph_skeleton,
    _poly_len_svg,
    _stroke_mask,
    _svg_to_crop,
    analyze_sheet_image,
    classify_polyline_mark,
    find_court_bbox,
)


def _skeleton_endpoints(skel):
    ys, xs = np.where(skel > 0)
    ends = []
    for x, y in zip(xs.tolist(), ys.tolist()):
        patch = skel[max(0, y - 1) : y + 2, max(0, x - 1) : x + 2]
        if int(patch.sum() // 255) <= 2:  # self + <=1 neighbor
            ends.append((x, y))
    return ends


def _order_skel_path(skel, start):
    """Greedy walk from start along skeleton; return pixel list."""
    ch, cw = skel.shape[:2]
    sx, sy = start
    if skel[sy, sx] == 0:
        # snap
        best = None
        for yy in range(max(0, sy - 3), min(ch, sy + 4)):
            for xx in range(max(0, sx - 3), min(cw, sx + 4)):
                if skel[yy, xx]:
                    d = (xx - sx) ** 2 + (yy - sy) ** 2
                    if best is None or d < best[0]:
                        best = (d, xx, yy)
        if not best:
            return []
        sx, sy = best[1], best[2]
    visited = np.zeros_like(skel, dtype=np.uint8)
    path = [(sx, sy)]
    visited[sy, sx] = 1
    x, y = sx, sy
    nbrs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    for _ in range(2500):
        opts = []
        for dx, dy in nbrs:
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= cw or ny >= ch:
                continue
            if visited[ny, nx] or skel[ny, nx] == 0:
                continue
            opts.append((nx, ny))
        if not opts:
            break
        # Prefer continuing straight when branching
        if len(path) >= 2:
            px, py = path[-2]
            vx, vy = x - px, y - py

            def score(p):
                return (p[0] - x) * vx + (p[1] - y) * vy

            opts.sort(key=score, reverse=True)
        x, y = opts[0]
        visited[y, x] = 1
        path.append((x, y))
    return path


def discover_cc(crop_gray, positions):
    ch, cw = crop_gray.shape[:2]
    stroke = _stroke_mask(crop_gray)
    erased = stroke.copy()
    digits = []
    for i in range(1, 6):
        oid = f"o{i}"
        p = (positions or {}).get(oid)
        if not _has_xy(p):
            continue
        cx, cy = _svg_to_crop(p, cw, ch)
        digits.append((oid, cx, cy))
        cv2.circle(erased, (cx, cy), 16, 0, -1)

    # Also erase tiny speckles; keep elongated strokes
    n, labels, stats, _ = cv2.connectedComponentsWithStats(erased, 8)
    keep = np.zeros_like(erased)
    components = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 60 or area > 18000:
            continue
        long_side = max(w, h)
        short_side = max(1, min(w, h))
        if long_side < 28:
            continue
        if long_side / short_side < 1.3 and area < 400:
            continue
        # reject huge near-full-width bands
        if w > cw * 0.65 and h < 40:
            continue
        mask = (labels == i).astype(np.uint8) * 255
        keep = cv2.bitwise_or(keep, mask)
        components.append((i, area, w, h, mask))

    skel = _morph_skeleton(keep)
    results = {}
    for i, area, w, h, mask in components:
        sk = cv2.bitwise_and(skel, mask)
        ends = _skeleton_endpoints(sk)
        if len(ends) < 1:
            ys, xs = np.where(sk > 0)
            if len(xs) < 5:
                continue
            # fallback: bbox extremes
            ends = [(int(xs.min()), int(ys[xs.argmin()])), (int(xs.max()), int(ys[xs.argmax()]))]
        # Pick endpoint nearest any digit as start; other end as tip
        best_assign = None
        for ex, ey in ends:
            for oid, dx, dy in digits:
                dist = ((ex - dx) ** 2 + (ey - dy) ** 2) ** 0.5
                if dist > 55:
                    continue
                # Walk from this end
                path_px = _order_skel_path(sk, (ex, ey))
                if len(path_px) < 8:
                    continue
                tip = path_px[-1]
                tip_dist = ((tip[0] - dx) ** 2 + (tip[1] - dy) ** 2) ** 0.5
                start_dist = dist
                if tip_dist < 35:
                    continue
                svg = [_crop_to_svg(x, y, cw, ch) for x, y in path_px]
                svg[0] = {"x": float(positions[oid]["x"]), "y": float(positions[oid]["y"])}
                plen = _poly_len_svg(svg)
                disp = (
                    (svg[-1]["x"] - svg[0]["x"]) ** 2 + (svg[-1]["y"] - svg[0]["y"]) ** 2
                ) ** 0.5
                if disp < 35 or plen < 40:
                    continue
                kind = classify_polyline_mark(crop_gray, svg)
                if kind == "pass":
                    continue
                if plen / max(disp, 1) >= 1.55 and kind == "cut":
                    kind = "dribble"
                # Score: prefer close attachment + longer real displacement
                score = tip_dist + disp - 1.5 * start_dist
                if best_assign is None or score > best_assign[0]:
                    best_assign = (score, oid, svg, kind, disp, plen, start_dist)
        if best_assign:
            oid = best_assign[1]
            # keep best per digit
            prev = results.get(oid)
            if prev is None or best_assign[0] > prev[0]:
                results[oid] = best_assign

    out_paths, out_marks = {}, {}
    for oid, (_sc, _oid, svg, kind, disp, plen, sd) in results.items():
        out_paths[oid] = svg
        out_marks[oid] = kind
        tip = svg[-1]
        print(
            f"  {oid}: {kind} disp={disp:.1f} len={plen:.1f} attach={sd:.1f} "
            f"tip=({tip['x']:.1f},{tip['y']:.1f})"
        )
    return out_paths, out_marks


base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
for pg in (120, 121, 122):
    p = base / f"page_{pg:04d}.png"
    pos = analyze_sheet_image(p)["positions"]
    gray = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2GRAY)
    x0, y0, x1, y1 = find_court_bbox(gray)
    crop = gray[y0:y1, x0:x1]
    print(f"\n=== page_{pg} CC outgoing ===")
    discover_cc(crop, pos)
