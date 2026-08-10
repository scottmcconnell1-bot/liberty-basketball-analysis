"""Verify 1-Game passes are straight 2-pt after v12 fix."""
from pathlib import Path

from playbook_sheet_align import analyze_sheet_image, trace_marked_paths_for_transition

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
for pg in ["0032", "0034", "0036"]:
    p = base / f"page_{pg}.png"
    pos = analyze_sheet_image(p)["positions"]
    m = trace_marked_paths_for_transition(p, pos, pos)
    print("===", pg)
    for pass_ in m.get("passes") or []:
        if pass_.get("orphan"):
            continue
        pts = pass_.get("points") or []
        print(
            f"  {pass_.get('fromPid')}->{pass_.get('toPid')} n={len(pts)} "
            f"end=({pts[-1]['x']:.1f},{pts[-1]['y']:.1f})" if pts else f"  empty"
        )
    for oid, kind in (m.get("marks") or {}).items():
        if kind != "screen":
            continue
        tip = (m.get("paths") or {}).get(oid, [])[-1]
        print(f"  screen {oid} tip=({tip['x']:.1f},{tip['y']:.1f})")
