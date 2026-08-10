from pathlib import Path
import cv2
from playbook_sheet_align import (
    analyze_sheet_image,
    discover_outgoing_routes,
    find_court_bbox,
    trace_marked_paths_for_transition,
)

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
pos120 = analyze_sheet_image(base / "page_0120.png")["positions"]
pos121 = analyze_sheet_image(base / "page_0121.png")["positions"]
# carry forward missing
merged = dict(pos120)
merged.update(pos121)
print("merged 121 anchors", {k: (round(v["x"], 1), round(v["y"], 1)) for k, v in merged.items()})

img = cv2.imread(str(base / "page_0121.png"), cv2.IMREAD_GRAYSCALE)
x0, y0, x1, y1 = find_court_bbox(img)
crop = img[y0:y1, x0:x1]
out = discover_outgoing_routes(crop, merged)
print("outgoing with carry", out.get("marks"))
for pid, poly in (out.get("paths") or {}).items():
    a, b = poly[0], poly[-1]
    print(f"  {pid}: ({a['x']:.1f},{a['y']:.1f})->({b['x']:.1f},{b['y']:.1f})")

# with looser min_len
out2 = discover_outgoing_routes(crop, merged, min_len_svg=20.0)
print("outgoing looser", out2.get("marks"))
for pid, poly in (out2.get("paths") or {}).items():
    a, b = poly[0], poly[-1]
    print(f"  {pid}: ({a['x']:.1f},{a['y']:.1f})->({b['x']:.1f},{b['y']:.1f})")

marked = trace_marked_paths_for_transition(base / "page_0121.png", merged, merged)
print("marked", marked.get("marks"))
for k, v in (marked.get("paths") or {}).items():
    print(f"  {k} {marked['marks'].get(k)}: ({v[0]['x']:.1f},{v[0]['y']:.1f})->({v[-1]['x']:.1f},{v[-1]['y']:.1f})")

# page 122 with carry-forward 4/5
pos122 = analyze_sheet_image(base / "page_0122.png")["positions"]
merged122 = dict(pos120)
merged122.update(pos122)
marked122 = trace_marked_paths_for_transition(base / "page_0122.png", merged122, merged122)
print("\n122 with carry marks", marked122.get("marks"))
print("122 paths", list((marked122.get("paths") or {}).keys()))
print("122 passes", [(p.get("fromPid"), p.get("toPid"), p.get("orphan")) for p in marked122.get("passes") or []])
