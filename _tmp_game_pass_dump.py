"""Dump 1-Game pass polylines vs digit centers."""
from pathlib import Path

from playbook_sheet_align import (
    _CACHE_VERSION,
    analyze_sheet_image,
    trace_marked_paths_for_transition,
)

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
for pg in ["0032", "0034", "0036"]:
    p = base / f"page_{pg}.png"
    pos = analyze_sheet_image(p)["positions"]
    m = trace_marked_paths_for_transition(p, pos, pos)
    print("===", pg, "cache", _CACHE_VERSION)
    print(
        "pos",
        {
            k: (round(v["x"], 1), round(v["y"], 1))
            for k, v in pos.items()
            if str(k).startswith("o")
        },
    )
    for pass_ in m.get("passes") or []:
        pts = pass_.get("points") or []
        print(
            f"  pass {pass_.get('fromPid')}->{pass_.get('toPid')} "
            f"orphan={pass_.get('orphan')} n={len(pts)}"
        )
        if pts:
            print(
                f"    start=({pts[0]['x']:.1f},{pts[0]['y']:.1f}) "
                f"end=({pts[-1]['x']:.1f},{pts[-1]['y']:.1f})"
            )
            to_pid = pass_.get("toPid")
            recv = pos.get(to_pid) if to_pid else None
            if recv and pts:
                tip = pts[-1]
                gap = ((tip["x"] - recv["x"]) ** 2 + (tip["y"] - recv["y"]) ** 2) ** 0.5
                print(f"    tip_vs_ocr_{to_pid}={gap:.1f}px")
            if len(pts) > 2:
                xs = [t["x"] for t in pts]
                print(f"    xRange=({min(xs):.1f}-{max(xs):.1f})")
    for oid, kind in (m.get("marks") or {}).items():
        poly = (m.get("paths") or {}).get(oid) or []
        tip = poly[-1] if poly else None
        tip_s = None if not tip else (round(tip["x"], 1), round(tip["y"], 1))
        print(f"  {oid} {kind} n={len(poly)} tip={tip_s}")
