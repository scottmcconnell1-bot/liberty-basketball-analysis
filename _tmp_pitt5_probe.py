"""Probe Pitt 5 page 173 screen / left-block geometry."""
from pathlib import Path

import cv2

from playbook_sheet_align import (
    analyze_sheet_image,
    find_court_bbox,
    trace_ink_polyline,
    trace_marked_paths_for_transition,
    _mid_raw_ink_fraction,
)

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
pos = analyze_sheet_image(base / "page_0173.png")["positions"]
print("positions:")
for k, v in sorted(pos.items()):
    print(f"  {k}: ({v['x']:.1f}, {v['y']:.1f})")
marked = trace_marked_paths_for_transition(base / "page_0173.png", pos, pos)
print("marks", marked.get("marks"))
for k, v in (marked.get("paths") or {}).items():
    print(
        f"  {k}: ({v[0]['x']:.1f},{v[0]['y']:.1f})"
        f"->({v[-1]['x']:.1f},{v[-1]['y']:.1f})"
    )

img = cv2.imread(str(base / "page_0173.png"), cv2.IMREAD_GRAYSCALE)
x0, y0, x1, y1 = find_court_bbox(img)
crop = img[y0:y1, x0:x1]
o4 = pos["o4"]
o5 = pos["o5"]
ink = trace_ink_polyline(crop, o4, o5, digit_positions=pos)
print("ink o4->o5 n", len(ink))
if len(ink) >= 2:
    frac = _mid_raw_ink_fraction(crop, ink, o4, o5)
    tip = ink[min(len(ink) - 1, max(2, int(len(ink) * 0.85)))]
    print("frac", frac, "85% tip", tip)
else:
    tip = {"x": float(o5["x"]) + 18, "y": max(160.0, float(o5["y"]) - 35)}
    print("fallback tip", tip)

left_block = {"x": 176.0, "y": 98.0}
# Mirror of right-block o4 start onto left side
left_block_sym = {"x": 500.0 - float(o4["x"]), "y": float(o4["y"])}
print("left_block fixed", left_block, "sym", left_block_sym)

for name, dest in [("fixed", left_block), ("sym", left_block_sym)]:
    ink_lb = trace_ink_polyline(crop, tip, dest, digit_positions=pos)
    if len(ink_lb) < 2:
        print(name, "no poly")
        continue
    frac = _mid_raw_ink_fraction(crop, ink_lb, tip, dest)
    print(
        f"screen->left ({name}): n={len(ink_lb)} end=({ink_lb[-1]['x']:.1f},{ink_lb[-1]['y']:.1f}) frac={frac:.2f}"
    )

# Also try full o4 continuous ink tip (may continue past screen)
ink_full = trace_ink_polyline(crop, o4, left_block, digit_positions=pos)
if len(ink_full) >= 2:
    print(
        f"o4->left_block full: n={len(ink_full)} end=({ink_full[-1]['x']:.1f},{ink_full[-1]['y']:.1f})"
    )
