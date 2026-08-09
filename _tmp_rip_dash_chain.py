"""Refined dash-chain pass + solid dribble/cut on Rip page 122."""
from pathlib import Path
import cv2
import numpy as np
from playbook_sheet_align import (
    analyze_sheet_image, find_court_bbox, _ink_mask_no_close,
    _svg_to_crop, _crop_to_svg, trace_ink_polyline, classify_polyline_mark,
    _poly_len_svg, _mid_raw_ink_fraction, _dashiness_along_path, _polyline_px,
)

p = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0122.png")
pos = analyze_sheet_image(p)["positions"]
gray = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2GRAY)
x0,y0,x1,y1 = find_court_bbox(gray)
crop = gray[y0:y1, x0:x1]
ch,cw = crop.shape[:2]
raw = _ink_mask_no_close(crop)

n, labels, stats, cents = cv2.connectedComponentsWithStats(raw, 8)
# Typical dash dash: area ~90-100, w~16, h~8-9
frags = []
for i in range(1, n):
    x,y,w,h,area = stats[i]
    if 70 <= area <= 130 and 12 <= w <= 22 and 6 <= h <= 12:
        frags.append((cents[i][0], cents[i][1]))
print(f"tight dash frags: {len(frags)}")
# Build chain by nearest-neighbor starting from rightmost
if not frags:
    raise SystemExit("no frags")
pts = list(frags)
start = max(pts, key=lambda t: t[0] - 0.4 * t[1])  # toward corner (high x, low y)
chain = [start]
pts.remove(start)
while pts:
    last = chain[-1]
    nxt = min(pts, key=lambda t: (t[0]-last[0])**2 + (t[1]-last[1])**2)
    dist = ((nxt[0]-last[0])**2 + (nxt[1]-last[1])**2)**0.5
    if dist > 55:
        break
    chain.append(nxt)
    pts.remove(nxt)
print(f"chain len={len(chain)}")
for c in chain:
    s = _crop_to_svg(c[0], c[1], cw, ch)
    print(f"  ({c[0]:.0f},{c[1]:.0f}) svg=({s['x']:.1f},{s['y']:.1f})")

# Pass from elbow-end (leftmost/lowest in chain toward paint) to corner-end
corner = chain[0]
elbow = chain[-1]
# Ensure elbow is the one closer to o1
o1 = pos["o1"]; o2 = pos["o2"]
d_o1_a = ((elbow[0]-_svg_to_crop(o1,cw,ch)[0])**2 + (elbow[1]-_svg_to_crop(o1,cw,ch)[1])**2)**0.5
d_o1_b = ((corner[0]-_svg_to_crop(o1,cw,ch)[0])**2 + (corner[1]-_svg_to_crop(o1,cw,ch)[1])**2)**0.5
if d_o1_b < d_o1_a:
    elbow, corner = corner, elbow

se = _crop_to_svg(elbow[0], elbow[1], cw, ch)
sc = _crop_to_svg(corner[0], corner[1], cw, ch)
print(f"elbow svg=({se['x']:.1f},{se['y']:.1f}) corner svg=({sc['x']:.1f},{sc['y']:.1f})")

# Extend pass endpoints slightly along chain direction for arrow tip
pas = trace_ink_polyline(crop, se, sc, digit_positions=pos)
print("pass classify", classify_polyline_mark(crop, pas), "mid", round(_mid_raw_ink_fraction(crop, pas, se, sc),2),
      "dash", round(_dashiness_along_path(raw, _polyline_px(pas,cw,ch)),2))

# Dribble: o1 -> elbow; require solid (low dash)
drib = trace_ink_polyline(crop, o1, se, digit_positions=pos)
print("dribble classify", classify_polyline_mark(crop, drib), "len", round(_poly_len_svg(drib),1),
      "mid", round(_mid_raw_ink_fraction(crop, drib, o1, se),2),
      "dash", round(_dashiness_along_path(raw, _polyline_px(drib,cw,ch)),2),
      "disp", round(((drib[-1]['x']-o1['x'])**2+(drib[-1]['y']-o1['y'])**2)**0.5,1))

# Cut: o2 -> corner
cut = trace_ink_polyline(crop, o2, sc, digit_positions=pos)
print("cut classify", classify_polyline_mark(crop, cut), "len", round(_poly_len_svg(cut),1),
      "mid", round(_mid_raw_ink_fraction(crop, cut, o2, sc),2),
      "dash", round(_dashiness_along_path(raw, _polyline_px(cut,cw,ch)),2),
      "disp", round(((cut[-1]['x']-o2['x'])**2+(cut[-1]['y']-o2['y'])**2)**0.5,1))

# Ratio path_len/disp for squiggle
def ratio(poly, a):
    plen = _poly_len_svg(poly)
    disp = ((poly[-1]['x']-a['x'])**2+(poly[-1]['y']-a['y'])**2)**0.5
    return plen/max(disp,1), plen, disp
print("dribble ratio", ratio(drib, o1))
print("cut ratio", ratio(cut, o2))
