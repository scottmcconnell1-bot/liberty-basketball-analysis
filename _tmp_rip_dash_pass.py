"""Find global dashed corridors and solid routes to their endpoints on page 122."""
from pathlib import Path
import cv2
import numpy as np
from playbook_sheet_align import (
    analyze_sheet_image, find_court_bbox, _ink_mask_no_close, _stroke_mask,
    _svg_to_crop, _crop_to_svg, _has_xy, _morph_skeleton, trace_ink_polyline,
    classify_polyline_mark, _poly_len_svg, _dashiness_along_path, _polyline_px,
)

p = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0122.png")
pos = analyze_sheet_image(p)["positions"]
gray = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2GRAY)
x0,y0,x1,y1 = find_court_bbox(gray)
crop = gray[y0:y1, x0:x1]
ch,cw = crop.shape[:2]
raw = _ink_mask_no_close(crop)

# Cluster small dash-like CCs into a pass corridor
n, labels, stats, cents = cv2.connectedComponentsWithStats(raw, 8)
dash_cents = []
for i in range(1, n):
    x,y,w,h,area = stats[i]
    if 40 <= area <= 350 and 6 <= max(w,h) <= 55:
        # elongated-ish
        if max(w,h) / max(1, min(w,h)) >= 1.2 or area < 120:
            dash_cents.append((cents[i][0], cents[i][1], area, w, h))

print(f"dash-like fragments: {len(dash_cents)}")
# Sort roughly by x descending (corner is high x, low y for basket-top)
dash_cents.sort(key=lambda t: -(t[0]) + 0.3 * t[1])
for t in dash_cents[:20]:
    svg = _crop_to_svg(t[0], t[1], cw, ch)
    print(f"  ({t[0]:.0f},{t[1]:.0f}) area={t[2]} wh=({t[3]},{t[4]}) svg=({svg['x']:.1f},{svg['y']:.1f})")

# Fit a line through dash centers in the right half of court
right = [t for t in dash_cents if t[0] > cw * 0.45 and t[1] < ch * 0.45]
print(f"right-upper dash frags: {len(right)}")
if len(right) >= 3:
    pts = np.array([[t[0], t[1]] for t in right], dtype=np.float32)
    # endpoints = extreme points
    dmat = ((pts[:,None,:]-pts[None,:,:])**2).sum(-1)
    i,j = np.unravel_index(np.argmax(dmat), dmat.shape)
    a = pts[i]; b = pts[j]
    # order so a is closer to paint (lower x roughly toward center)
    if a[0] > b[0]:
        a,b = b,a
    print(f"pass corridor ends crop: {a} -> {b}")
    sa = _crop_to_svg(float(a[0]), float(a[1]), cw, ch)
    sb = _crop_to_svg(float(b[0]), float(b[1]), cw, ch)
    print(f"pass corridor svg: ({sa['x']:.1f},{sa['y']:.1f}) -> ({sb['x']:.1f},{sb['y']:.1f})")

    # Trace from o1 to pass-start (dribble), o2 to pass-end (cut)
    o1 = pos["o1"]; o2 = pos["o2"]
    drib = trace_ink_polyline(crop, o1, sa, digit_positions=pos)
    cut = trace_ink_polyline(crop, o2, sb, digit_positions=pos)
    print("dribble", classify_polyline_mark(crop, drib), "len", round(_poly_len_svg(drib),1),
          "end", (round(drib[-1]['x'],1), round(drib[-1]['y'],1)))
    print("cut", classify_polyline_mark(crop, cut), "len", round(_poly_len_svg(cut),1),
          "end", (round(cut[-1]['x'],1), round(cut[-1]['y'],1)))
    # dashiness of dribble path
    print("drib dashiness", _dashiness_along_path(raw, _polyline_px(drib, cw, ch)))
    print("cut dashiness", _dashiness_along_path(raw, _polyline_px(cut, cw, ch)))

    # Also try pass between sa and sb
    pas = trace_ink_polyline(crop, sa, sb, digit_positions=pos)
    print("pass", classify_polyline_mark(crop, pas), "len", round(_poly_len_svg(pas),1))
