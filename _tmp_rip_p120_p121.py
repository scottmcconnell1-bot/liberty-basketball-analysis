from pathlib import Path
from playbook_sheet_align import analyze_sheet_image, discover_outgoing_routes, find_court_bbox, trace_marked_paths_for_transition
import cv2

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
for pg in (120, 121):
    pos = analyze_sheet_image(base / f"page_{pg:04d}.png")["positions"]
    if pg == 121:
        pos = {**analyze_sheet_image(base / "page_0120.png")["positions"], **pos}
    img = cv2.imread(str(base / f"page_{pg:04d}.png"), cv2.IMREAD_GRAYSCALE)
    x0, y0, x1, y1 = find_court_bbox(img)
    crop = img[y0:y1, x0:x1]
    out = discover_outgoing_routes(crop, pos)
    print(f"page {pg} outgoing marks", out.get("marks"))
    for k, v in (out.get("paths") or {}).items():
        print(f"  {k}: tip=({v[-1]['x']:.1f},{v[-1]['y']:.1f}) n={len(v)}")
    m = trace_marked_paths_for_transition(base / f"page_{pg:04d}.png", pos, pos)
    print(f"page {pg} marked", m.get("marks"))
