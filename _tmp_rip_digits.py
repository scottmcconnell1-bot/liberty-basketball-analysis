"""Probe digit candidates and action-ink CCs on Rip pages."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from playbook_sheet_align import (
    _crop_to_svg,
    _digit_blob_candidates,
    _ink_mask_no_close,
    _read_digit_patch,
    _stroke_mask,
    _svg_to_crop,
    analyze_sheet_image,
    detect_sheet_digits,
    find_court_bbox,
)

# _read_digit_patch may be private under different name
from playbook_sheet_align import detect_sheet_digits as _ds

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")

# Import digit read helper
import playbook_sheet_align as psa

for pg in (121, 122):
    p = base / f"page_{pg:04d}.png"
    img = cv2.imread(str(p))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    court = find_court_bbox(gray)
    x0, y0, x1, y1 = court
    crop = gray[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]
    print(f"\n===== page_{pg} =====")
    print("detect:", detect_sheet_digits(gray, court))
    cands = _digit_blob_candidates(crop)
    print(f"{len(cands)} blob candidates:")
    for cx, cy, w, h, area in cands:
        # Read digit using same path as detect
        # Peek into detect logic: crop patch around blob
        pad = 4
        x_a = max(0, int(cx - w / 2) - pad)
        y_a = max(0, int(cy - h / 2) - pad)
        x_b = min(cw, int(cx + w / 2) + pad)
        y_b = min(ch, int(cy + h / 2) + pad)
        patch = crop[y_a:y_b, x_a:x_b]
        digit, conf = psa._classify_digit_patch(patch) if hasattr(psa, "_classify_digit_patch") else (0, 0)
        if not hasattr(psa, "_classify_digit_patch"):
            # fall back to internal
            digit, conf = psa._ocr_digit_from_patch(patch) if hasattr(psa, "_ocr_digit_from_patch") else (0, 0)
        svg = _crop_to_svg(cx, cy, cw, ch)
        print(f"  blob ({cx:.0f},{cy:.0f}) wh=({w:.0f},{h:.0f}) area={area:.0f} svg=({svg['x']:.1f},{svg['y']:.1f}) digit={digit} conf={conf:.2f}")

    stroke = _stroke_mask(crop)
    # erase long-ish components near court by size; list CCs
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(stroke, 8)
    print(f"stroke CCs: {n-1}")
    actionish = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 80 or area > 25000:
            continue
        if max(w, h) < 25:
            continue
        # skip very wide/short (court remnants)
        if w > cw * 0.55 and h < 30:
            continue
        if h > ch * 0.55 and w < 30:
            continue
        cx, cy = centroids[i]
        # distance to nearest known digit
        actionish.append((area, w, h, cx, cy, i))
    actionish.sort(reverse=True)
    print(f"actionish CCs: {len(actionish)}")
    for area, w, h, cx, cy, i in actionish[:12]:
        svg = _crop_to_svg(cx, cy, cw, ch)
        print(f"  cc area={area} wh=({w},{h}) center=({cx:.0f},{cy:.0f}) svg=({svg['x']:.1f},{svg['y']:.1f})")
