from pathlib import Path
import cv2
from playbook_sheet_align import (
    analyze_sheet_image,
    trace_marked_paths_for_transition,
    discover_outgoing_routes,
    discover_dash_pass_chains,
    find_court_bbox,
    trace_ink_polyline,
    _mid_raw_ink_fraction,
    _path_ink_fraction_stroke,
    _poly_len_svg,
    classify_polyline_mark,
)

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
for page in ["page_0121.png", "page_0122.png"]:
    pos = analyze_sheet_image(base / page)["positions"]
    print("===", page, "OCR")
    for k in sorted(pos):
        print(f"  {k}: ({pos[k]['x']:.1f}, {pos[k]['y']:.1f})")
    img = cv2.imread(str(base / page), cv2.IMREAD_GRAYSCALE)
    x0, y0, x1, y1 = find_court_bbox(img)
    crop = img[y0:y1, x0:x1]
    out = discover_outgoing_routes(crop, pos)
    print("outgoing marks", out.get("marks"))
    for pid, poly in (out.get("paths") or {}).items():
        a, b = poly[0], poly[-1]
        print(f"  {pid}: ({a['x']:.1f},{a['y']:.1f})->({b['x']:.1f},{b['y']:.1f}) n={len(poly)}")
    chains = discover_dash_pass_chains(crop)
    print("dash chains", len(chains))
    for c in chains:
        print(f"  ({c[0]['x']:.1f},{c[0]['y']:.1f})->({c[-1]['x']:.1f},{c[-1]['y']:.1f}) n={len(c)}")
    marked = trace_marked_paths_for_transition(base / page, pos, pos)
    print("marked marks", marked.get("marks"))
    for k, v in (marked.get("paths") or {}).items():
        print(f"  path {k}: ({v[0]['x']:.1f},{v[0]['y']:.1f})->({v[-1]['x']:.1f},{v[-1]['y']:.1f})")
    print("passes", [(p.get("fromPid"), p.get("toPid"), p.get("orphan")) for p in marked.get("passes") or []])

# Probe o2 -> corner tip on page 122
page = base / "page_0122.png"
pos = analyze_sheet_image(page)["positions"]
img = cv2.imread(str(page), cv2.IMREAD_GRAYSCALE)
x0, y0, x1, y1 = find_court_bbox(img)
crop = img[y0:y1, x0:x1]
chains = discover_dash_pass_chains(crop)
end = chains[0][-1]
start = chains[0][0]
print("\n=== o2 to corner probe ===")
print("pass start/end", start, end)
a = pos["o2"]
route = trace_ink_polyline(crop, a, end, digit_positions=pos)
print("route n", len(route))
if len(route) >= 2:
    plen = _poly_len_svg(route)
    disp = ((end["x"] - a["x"]) ** 2 + (end["y"] - a["y"]) ** 2) ** 0.5
    mid = max(
        _mid_raw_ink_fraction(crop, route, a, end),
        _path_ink_fraction_stroke(crop, route, a, end),
    )
    kind = classify_polyline_mark(crop, route)
    print(f"plen={plen:.1f} disp={disp:.1f} mid={mid:.3f} kind={kind}")
    print("endpts", route[0], route[-1])

# Also probe o1 to start and o1 continuing past start toward block
print("\n=== o1 dribble probe ===")
a1 = pos["o1"]
route1 = trace_ink_polyline(crop, a1, start, digit_positions=pos)
if len(route1) >= 2:
    plen = _poly_len_svg(route1)
    disp = ((start["x"] - a1["x"]) ** 2 + (start["y"] - a1["y"]) ** 2) ** 0.5
    mid = max(
        _mid_raw_ink_fraction(crop, route1, a1, start),
        _path_ink_fraction_stroke(crop, route1, a1, start),
    )
    kind = classify_polyline_mark(crop, route1)
    print(f"to dash start: plen={plen:.1f} disp={disp:.1f} mid={mid:.3f} kind={kind} ratio={plen/max(disp,1):.2f}")

# Try extend toward lower-right block-ish target
blockish = {"x": 310.0, "y": 70.0}
route_b = trace_ink_polyline(crop, a1, blockish, digit_positions=pos)
if len(route_b) >= 2:
    print("to blockish tip", route_b[-1], "n", len(route_b), "kind", classify_polyline_mark(crop, route_b))
