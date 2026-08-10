"""Analyze Rip pages 120-122 OCR + ink paths (with/without outgoing)."""
from __future__ import annotations

import json
from pathlib import Path

import cv2

from playbook_sheet_align import (
    analyze_sheet_image,
    discover_outgoing_routes,
    find_court_bbox,
    trace_marked_paths_for_transition,
)

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")


def summarize_poly(pts):
    if not pts:
        return None
    a, b = pts[0], pts[-1]
    return {
        "n": len(pts),
        "from": (round(a["x"], 1), round(a["y"], 1)),
        "to": (round(b["x"], 1), round(b["y"], 1)),
    }


for pg in (120, 121, 122):
    p = base / f"page_{pg:04d}.png"
    a = analyze_sheet_image(p)
    pos = a.get("positions") or {}
    print(f"\n=== page_{pg} positions ===")
    for k in sorted(pos):
        v = pos[k]
        print(f"  {k}: x={v['x']:.1f} y={v['y']:.1f}")
    dbg = a.get("debug_positions") or {}
    print("  conf:", {k: round(v.get("confidence", 0), 2) for k, v in dbg.items()})

    marked = trace_marked_paths_for_transition(p, pos, pos)
    print("  passes:", [
        {
            "from": x["fromPid"],
            "to": x["toPid"],
            "poly": summarize_poly(x.get("points")),
        }
        for x in (marked.get("passes") or [])
    ])
    print("  mover paths:", {k: summarize_poly(v) for k, v in (marked.get("paths") or {}).items()})
    print("  marks:", marked.get("marks"))

    img = cv2.imread(str(p))
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    x0, y0, x1, y1 = find_court_bbox(gray)
    crop = gray[y0:y1, x0:x1]
    out = discover_outgoing_routes(crop, pos)
    print("  outgoing paths:", {k: summarize_poly(v) for k, v in (out.get("paths") or {}).items()})
    print("  outgoing marks:", out.get("marks"))
