from pathlib import Path
from playbook_sheet_align import (
    analyze_sheet_image,
    discover_outgoing_routes,
    find_court_bbox,
)
import cv2

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
pos120 = analyze_sheet_image(base / "page_0120.png")["positions"]
pos121 = analyze_sheet_image(base / "page_0121.png")["positions"]
merged = dict(pos120)
merged.update(pos121)
img = cv2.imread(str(base / "page_0121.png"), cv2.IMREAD_GRAYSCALE)
x0, y0, x1, y1 = find_court_bbox(img)
crop = img[y0:y1, x0:x1]
out = discover_outgoing_routes(crop, merged)
print("outgoing", out)
