"""Visualize stroke mask / CCs on page 122 after digit erase."""
from pathlib import Path
import cv2
import numpy as np
from playbook_sheet_align import (
    analyze_sheet_image, find_court_bbox, _stroke_mask, _svg_to_crop, _has_xy, _ink_mask_no_close
)

p = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0122.png")
pos = analyze_sheet_image(p)["positions"]
gray = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2GRAY)
x0,y0,x1,y1 = find_court_bbox(gray)
crop = gray[y0:y1, x0:x1]
ch,cw = crop.shape[:2]
raw = _ink_mask_no_close(crop)
stroke = _stroke_mask(crop)
erased = stroke.copy()
for i in range(1,6):
    pt = pos.get(f"o{i}")
    if _has_xy(pt):
        cx,cy = _svg_to_crop(pt,cw,ch)
        cv2.circle(erased,(cx,cy),16,0,-1)

out = Path("_tmp_recording_frames/rip_review")
cv2.imwrite(str(out/"p122_raw_ink.png"), raw)
cv2.imwrite(str(out/"p122_stroke.png"), stroke)
cv2.imwrite(str(out/"p122_erased.png"), erased)

n, labels, stats, cents = cv2.connectedComponentsWithStats(erased, 8)
vis = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
rng = np.random.default_rng(0)
print(f"CCs={n-1}")
for i in range(1,n):
    x,y,w,h,area = stats[i]
    color = tuple(int(c) for c in rng.integers(40,255,3))
    vis[labels==i] = color
    if area >= 40:
        print(f"  i={i} area={area} wh=({w},{h}) cent=({cents[i][0]:.0f},{cents[i][1]:.0f})")
cv2.imwrite(str(out/"p122_cc_vis.png"), vis)
print("wrote visuals")
