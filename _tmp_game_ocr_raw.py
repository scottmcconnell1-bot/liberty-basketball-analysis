"""Raw OCR + ink dump for 1-Game pages (bypass seed/force comparison)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import cv2

from playbook_sheet_align import (
    analyze_sheet_image,
    detect_sheet_digits,
    discover_outgoing_routes,
    find_court_bbox,
    seed_game_sheet_positions,
    trace_marked_paths_for_transition,
)

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")

for page in ["0032", "0033", "0034", "0035", "0036"]:
    path = base / f"page_{page}.png"
    img = cv2.imread(str(path))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    court = find_court_bbox(gray)
    digits = detect_sheet_digits(gray, court)
    print(f"\n=== {page} raw OCR (svg) ===")
    for k in sorted(digits):
        if k.startswith("o"):
            d = digits[k]
            print(f"  {k}: x={d['x']:.1f} y={d['y']:.1f} conf={d.get('confidence', '?')}")

    # Ink discovery from raw OCR only (no game seed)
    x0, y0, x1, y1 = court
    crop = gray[y0:y1, x0:x1]
    pos_raw = {k: {"x": float(v["x"]), "y": float(v["y"])} for k, v in digits.items() if k.startswith("o")}
    outgoing = discover_outgoing_routes(crop, pos_raw)
    print(f"  ink-from-OCR marks={outgoing.get('marks')}")
    for oid, pts in (outgoing.get("paths") or {}).items():
        print(f"  ink {oid}: n={len(pts)} start={pts[0]} tip={pts[-1]}")

print("\n\n=== CURRENT seeded pipeline ===")
for page in ["0032", "0033", "0034", "0035", "0036"]:
    path = base / f"page_{page}.png"
    with tempfile.TemporaryDirectory() as td:
        res = analyze_sheet_image(path, cache_base=td)
        pos_s = res["positions"]
        marked = trace_marked_paths_for_transition(path, pos_s, pos_s, cache_base=td)
    print(f"\n--- {page} ---")
    for k in sorted(pos_s):
        if k.startswith("o"):
            print(f"  {k}: ({pos_s[k]['x']:.1f}, {pos_s[k]['y']:.1f})")
    print(f"  marks={marked.get('marks')}")
    for oid, pts in (marked.get("paths") or {}).items():
        print(f"  path {oid} [{marked['marks'].get(oid)}] n={len(pts)} tip=({pts[-1]['x']:.1f},{pts[-1]['y']:.1f})")
    for p in marked.get("passes") or []:
        tip = (p.get("points") or [{}])[-1]
        print(f"  pass {p.get('fromPid')}->{p.get('toPid')} tip=({tip.get('x')},{tip.get('y')}) orphan={p.get('orphan')}")
