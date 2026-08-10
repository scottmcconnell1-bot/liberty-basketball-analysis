"""Measure FT line / paint landmarks + find arrow tips on page 32."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from playbook_sheet_align import COURT_H, COURT_W, find_court_bbox

path = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0032.png")
img = cv2.imread(str(path))
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
x0, y0, x1, y1 = find_court_bbox(gray)
crop = gray[y0:y1, x0:x1]
ch, cw = crop.shape[:2]

def to_svg(px, py):
    return px / cw * COURT_W, py / ch * COURT_H

# Horizontal projection: find FT line (dense horizontal ink in upper-middle paint)
ink = (crop < 110).astype(np.uint8)
row_density = ink.mean(axis=1)
# Focus on center columns (paint)
paint = ink[:, int(cw * 0.35) : int(cw * 0.65)]
paint_rows = paint.mean(axis=1)
# Top of court is basket; FT line is a strong horizontal band around 30-40% down
candidates = []
for y in range(int(ch * 0.18), int(ch * 0.55)):
    if paint_rows[y] > 0.12:
        candidates.append((paint_rows[y], y))
candidates.sort(reverse=True)
print("Strong paint horizontal rows (top 8):")
for dens, y in candidates[:8]:
    sx, sy = to_svg(cw / 2, y)
    print(f"  y_px={y} dens={dens:.3f} svg_y={sy:.1f}")

# Lane left/right verticals
col_density = paint.mean(axis=0)
# Absolute x in crop
paint_x0 = int(cw * 0.35)
for x_off in range(0, paint.shape[1]):
    pass
left_lane_candidates = []
right_lane_candidates = []
full_cols = ink.mean(axis=0)
# Lane lines around 36% and 64% of width typically
for x in range(int(cw * 0.28), int(cw * 0.45)):
    if full_cols[x] > 0.08:
        left_lane_candidates.append((full_cols[x], x))
for x in range(int(cw * 0.55), int(cw * 0.72)):
    if full_cols[x] > 0.08:
        right_lane_candidates.append((full_cols[x], x))
left_lane_candidates.sort(reverse=True)
right_lane_candidates.sort(reverse=True)
print("Left lane candidates:")
for dens, x in left_lane_candidates[:5]:
    print(f"  x_px={x} dens={dens:.3f} svg_x={to_svg(x,0)[0]:.1f}")
print("Right lane candidates:")
for dens, x in right_lane_candidates[:5]:
    print(f"  x_px={x} dens={dens:.3f} svg_x={to_svg(x,0)[0]:.1f}")

# Save annotated crop for visual: highlight OCR points and expected elbows
vis = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
# OCR
for name, sx, sy, color in [
    ("1", 254.6, 301.0, (0, 0, 255)),
    ("2", 433.5, 209.2, (0, 128, 255)),
]:
    px, py = int(sx / COURT_W * cw), int(sy / COURT_H * ch)
    cv2.circle(vis, (px, py), 12, color, 2)
    cv2.putText(vis, name, (px + 14, py), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

# Current bad seeds
for name, sx, sy, color in [
    ("3f", 55.0, 168.0, (255, 0, 255)),
    ("4f", 185.0, 168.0, (255, 0, 0)),
    ("5f", 315.0, 168.0, (255, 0, 0)),
    ("2f", 433.5, 125.0, (0, 255, 255)),
    ("blk", 178.0, 48.0, (0, 255, 0)),
]:
    px, py = int(sx / COURT_W * cw), int(sy / COURT_H * ch)
    cv2.drawMarker(vis, (px, py), color, cv2.MARKER_TILTED_CROSS, 16, 2)
    cv2.putText(vis, name, (px + 10, py - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

# Proposed PDF-matching seeds
for name, sx, sy, color in [
    ("3p", 66.5, 209.2, (255, 255, 0)),
    ("4p", 185.0, 175.0, (0, 255, 128)),
    ("5p", 315.0, 175.0, (0, 255, 128)),
    ("pop4", 110.0, 215.0, (128, 255, 255)),
    ("pop5", 390.0, 215.0, (128, 255, 255)),
    ("blkOCR", 178.1, 99.8, (255, 128, 0)),
]:
    px, py = int(sx / COURT_W * cw), int(sy / COURT_H * ch)
    cv2.circle(vis, (px, py), 10, color, 2)
    cv2.putText(vis, name, (px + 10, py + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

out = Path("_tmp_game_page32_overlay.png")
cv2.imwrite(str(out), vis)
print(f"Wrote {out}")

# Also page 36 overlay with OCR + seeds
path36 = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0036.png")
img36 = cv2.imread(str(path36))
gray36 = cv2.cvtColor(img36, cv2.COLOR_BGR2GRAY)
x0, y0, x1, y1 = find_court_bbox(gray36)
crop36 = gray36[y0:y1, x0:x1]
vis36 = cv2.cvtColor(crop36, cv2.COLOR_GRAY2BGR)
ch, cw = crop36.shape[:2]
for name, sx, sy, color in [
    ("1", 101.1, 250.3, (0, 0, 255)),
    ("2", 433.5, 209.2, (0, 128, 255)),
    ("3", 248.9, 292.1, (0, 255, 0)),
    ("4", 298.1, 179.5, (255, 0, 0)),
    ("5seed", 178.0, 100.0, (255, 255, 0)),
    ("1force", 72.0, 250.0, (255, 0, 255)),
    ("5blk48", 178.0, 48.0, (0, 255, 255)),
    ("rblk48", 322.0, 48.0, (0, 255, 255)),
]:
    px, py = int(sx / COURT_W * cw), int(sy / COURT_H * ch)
    cv2.circle(vis36, (px, py), 11, color, 2)
    cv2.putText(vis36, name, (px + 12, py), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
out36 = Path("_tmp_game_page36_overlay.png")
cv2.imwrite(str(out36), vis36)
print(f"Wrote {out36}")
