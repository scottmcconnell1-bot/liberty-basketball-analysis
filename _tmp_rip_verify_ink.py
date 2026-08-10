from pathlib import Path
from playbook_sheet_align import analyze_sheet_image, trace_marked_paths_for_transition

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")

# page 122 alone
pos = analyze_sheet_image(base / "page_0122.png")["positions"]
m = trace_marked_paths_for_transition(base / "page_0122.png", pos, pos)
print("=== page 122 ===")
print("marks", m.get("marks"))
for k, v in (m.get("paths") or {}).items():
    print(f"  {k}: ({v[0]['x']:.1f},{v[0]['y']:.1f})->({v[-1]['x']:.1f},{v[-1]['y']:.1f})")
print("passes", [(p.get("fromPid"), p.get("toPid"), p.get("orphan")) for p in m.get("passes") or []])

# page 121 with carry o4
pos120 = analyze_sheet_image(base / "page_0120.png")["positions"]
pos121 = analyze_sheet_image(base / "page_0121.png")["positions"]
merged = dict(pos120)
merged.update(pos121)
m121 = trace_marked_paths_for_transition(base / "page_0121.png", merged, merged)
print("\n=== page 121 + carry ===")
print("marks", m121.get("marks"))
for k, v in (m121.get("paths") or {}).items():
    print(f"  {k}: ({v[0]['x']:.1f},{v[0]['y']:.1f})->({v[-1]['x']:.1f},{v[-1]['y']:.1f})")
print("passes", [(p.get("fromPid"), p.get("toPid"), p.get("orphan")) for p in m121.get("passes") or []])

# page 120 regression
pos120 = analyze_sheet_image(base / "page_0120.png")["positions"]
m120 = trace_marked_paths_for_transition(base / "page_0120.png", pos120, pos120)
pairs = {(p["fromPid"], p["toPid"]) for p in m120.get("passes") or []}
print("\n=== page 120 ===")
print("pairs", pairs)
print("marks", m120.get("marks"))
assert ("o1", "o3") in pairs
assert ("o1", "o4") not in pairs
print("OK regression")
