from pathlib import Path
import cv2
from playbook_sheet_align import (
    analyze_sheet_image,
    discover_outgoing_routes,
    find_court_bbox,
    _stroke_mask,
    _has_tbar_near_end,
    _polyline_px,
)

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
pos = {**analyze_sheet_image(base / "page_0120.png")["positions"], **analyze_sheet_image(base / "page_0121.png")["positions"]}
img = cv2.imread(str(base / "page_0121.png"), cv2.IMREAD_GRAYSCALE)
x0, y0, x1, y1 = find_court_bbox(img)
crop = img[y0:y1, x0:x1]
ch, cw = crop.shape[:2]
stroke = _stroke_mask(crop)
out = discover_outgoing_routes(crop, pos)
poly = out["paths"]["o5"]
path_px = _polyline_px(poly, cw, ch)
print("full tip tbar", _has_tbar_near_end(stroke, path_px))
# Check tbar at various prefixes
for frac in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
    n = max(5, int(len(path_px) * frac))
    sub = path_px[:n]
    print(f"frac={frac:.1f} n={n} tbar={_has_tbar_near_end(stroke, sub)} end={sub[-1]}")
