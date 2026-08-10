"""Locate printed digits + arrow tips via pixel analysis; try ink with gap-only seeds."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from playbook_sheet_align import (
    COURT_H,
    COURT_W,
    detect_sheet_digits,
    discover_outgoing_routes,
    find_court_bbox,
)

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")


def svg_from_crop(px, py, crop_w, crop_h):
    return {
        "x": float(px) / crop_w * COURT_W,
        "y": float(py) / crop_h * COURT_H,
    }


def ink_mask(crop_gray):
    # Dark ink on white
    return (crop_gray < 90).astype(np.uint8) * 255


for page in ["0032", "0033", "0034", "0035", "0036"]:
    path = base / f"page_{page}.png"
    img = cv2.imread(str(path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    court = find_court_bbox(gray)
    x0, y0, x1, y1 = court
    crop = gray[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]
    digits = detect_sheet_digits(gray, court)
    print(f"\n=== {page} court={court} crop={cw}x{ch} ===")
    for k in sorted(digits):
        if k.startswith("o"):
            d = digits[k]
            print(f"  OCR {k}: ({d['x']:.1f},{d['y']:.1f})")

    # Gap-only seeds matching printed sheet (from visual + OCR anchors)
    seeds = {
        "0032": {
            # elbows at FT; wings at OCR o2 height; 3 mirrored left of o2
            "o3": {"x": 500 - 433.5, "y": 209.2},  # mirror 2
            "o4": {"x": 185.0, "y": 175.0},  # left elbow
            "o5": {"x": 315.0, "y": 175.0},  # right elbow
        },
        "0033": {
            "o4": {"x": 95.0, "y": 210.0},  # left wing pop landing
            "o5": {"x": 382.0, "y": 210.0},  # right wing with ball
        },
        "0034": {
            "o5": {"x": 360.0, "y": 200.0},
        },
        "0035": {
            "o3": {"x": 310.0, "y": 165.0},  # right elbow area
            "o4": {"x": 255.0, "y": 300.0},  # top
            "o5": {"x": 178.0, "y": 100.0},  # left paint (OCR-like)
        },
        "0036": {
            "o5": {"x": 178.0, "y": 100.0},
        },
    }
    pos = {k: {"x": float(v["x"]), "y": float(v["y"])} for k, v in digits.items() if k.startswith("o")}
    for oid, pt in seeds.get(page, {}).items():
        if oid not in pos:
            pos[oid] = dict(pt)
    # Never overwrite OCR
    print("  positions used:", {k: (round(v['x'],1), round(v['y'],1)) for k,v in sorted(pos.items())})
    outgoing = discover_outgoing_routes(crop, pos)
    print(f"  ink marks={outgoing.get('marks')}")
    for oid, pts in (outgoing.get("paths") or {}).items():
        s, t = pts[0], pts[-1]
        print(f"  ink {oid}: n={len(pts)} ({s['x']:.1f},{s['y']:.1f}) -> ({t['x']:.1f},{t['y']:.1f})")

    # Also dump dashed-ish dark pixels near expected pass corridors — skip, just save overlay
    mask = ink_mask(crop)
    # Find connected components that might be digits (small blobs)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
    digitish = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 40 or area > 900:
            continue
        if w < 6 or h < 10 or w > 45 or h > 55:
            continue
        aspect = h / max(w, 1)
        if aspect < 1.1 or aspect > 3.5:
            continue
        cx, cy = cents[i]
        svg = svg_from_crop(cx, cy, cw, ch)
        digitish.append((area, svg["x"], svg["y"], w, h))
    digitish.sort(key=lambda t: -t[0])
    print("  digitish blobs (top 12):")
    for a, x, y, w, h in digitish[:12]:
        print(f"    area={a} svg=({x:.1f},{y:.1f}) wh={w}x{h}")
