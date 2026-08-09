"""Raw discovery on 173 without Pitt5 override; inspect continuous ink from o4."""
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

from playbook_sheet_align import (
    analyze_sheet_image,
    discover_big_screen_routes,
    discover_outgoing_routes,
    find_court_bbox,
    trace_ink_polyline,
    classify_polyline_mark,
    apply_pitt5_sequence_routes,
)

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
p173 = base / "page_0173.png"
pos = analyze_sheet_image(p173)["positions"]

img = cv2.imread(str(p173), cv2.IMREAD_GRAYSCALE)
bbox = find_court_bbox(img)
x0, y0, x1, y1 = bbox
crop = img[y0:y1, x0:x1]

# Bypass apply_pitt5 by calling discovery pieces directly
paths = {}
marks = {}
out = discover_outgoing_routes(crop, pos)
print("outgoing paths", list((out.get("paths") or {}).keys()))
print("outgoing marks", out.get("marks"))
for k, v in (out.get("paths") or {}).items():
    print(f"  {k}: ({v[0]['x']:.1f},{v[0]['y']:.1f})->({v[-1]['x']:.1f},{v[-1]['y']:.1f}) mark={out.get('marks',{}).get(k)}")

big = discover_big_screen_routes(crop, pos)
print("\nbig screen", big.get("marks"))
for k, v in (big.get("paths") or {}).items():
    print(f"  {k}: ({v[0]['x']:.1f},{v[0]['y']:.1f})->({v[-1]['x']:.1f},{v[-1]['y']:.1f})")

# Trace o4 full ink walk to various destinations / skeleton tip
o4 = pos["o4"]
o5 = pos["o5"]
left_block = {"x": 176.0, "y": 98.0}
right_block = dict(o4)
basket = {"x": 250.0, "y": 55.0}
screen_spot = {"x": float(o5["x"]) + 18, "y": max(160.0, float(o5["y"]) - 35)}

for name, dest in [
    ("to_o5", o5),
    ("to_left_block", left_block),
    ("to_basket", basket),
    ("to_screen_spot", screen_spot),
]:
    poly = trace_ink_polyline(crop, o4, dest, digit_positions=pos)
    if len(poly) < 2:
        print(name, "no poly")
        continue
    kind = classify_polyline_mark(crop, poly)
    print(
        f"trace {name}: n={len(poly)} end=({poly[-1]['x']:.1f},{poly[-1]['y']:.1f}) class={kind}"
    )

# Visualize raw ink mask
from playbook_sheet_align import _stroke_mask
stroke = _stroke_mask(crop)
vis = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
vis[stroke > 0] = (0, 0, 255)
h, w = crop.shape[:2]

def to_px(pt):
    return int(pt["x"] / 500.0 * w), int(pt["y"] / 470.0 * h)

for oid, ptd in pos.items():
    cv2.circle(vis, to_px(ptd), 10, (0, 255, 0), 2)
    cv2.putText(vis, oid, (to_px(ptd)[0] + 8, to_px(ptd)[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

# Draw natural o4->left and o4->o5 traces
for col, dest in [((255, 255, 0), left_block), ((255, 0, 255), o5), ((0, 255, 255), basket)]:
    poly = trace_ink_polyline(crop, o4, dest, digit_positions=pos)
    pts = [to_px(pt) for pt in poly]
    for a, b in zip(pts, pts[1:]):
        cv2.line(vis, a, b, col, 2)

outp = Path("_tmp_pitt5_vis")
outp.mkdir(exist_ok=True)
cv2.imwrite(str(outp / "page173_raw_ink.png"), vis)
print("wrote raw ink vis")

# Read title bands with absolute path check
for pg in range(168, 177):
    p = base / f"page_{pg:04d}.png"
    imgc = cv2.imread(str(p))
    if imgc is None:
        continue
    h, w = imgc.shape[:2]
    band = imgc[0 : int(h * 0.12), :]
    dest = outp / f"title_{pg:04d}.jpg"
    cv2.imwrite(str(dest), band, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    print("title", dest, dest.exists(), dest.stat().st_size)
