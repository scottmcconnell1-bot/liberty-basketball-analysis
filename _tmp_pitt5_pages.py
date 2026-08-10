"""Inspect pages around Pitt 5 and what Cycle Spots owns."""
import json
import sqlite3
from pathlib import Path

from playbook_sheet_align import analyze_sheet_image, trace_marked_paths_for_transition

con = sqlite3.connect("film_analysis.db")
con.row_factory = sqlite3.Row
# Cycle Spots and any plays with pages near 172
rows = con.execute(
    "SELECT id, name, diagram_json FROM plays ORDER BY id"
).fetchall()
for r in rows:
    try:
        dj = json.loads(r["diagram_json"] or "{}")
    except Exception:
        continue
    sp, ep = dj.get("start_page"), dj.get("end_page")
    if sp is None:
        continue
    if 165 <= int(sp) <= 185 or (ep is not None and 165 <= int(ep) <= 185):
        print(r["id"], r["name"], sp, ep, dj.get("excluded_pages"), dj.get("option_names"))

# Also check git history / backups for play 137 original diagram
print("\n=== page OCR positions 170-178 ===")
base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
for pg in range(170, 179):
    p = base / f"page_{pg:04d}.png"
    if not p.is_file():
        print(pg, "MISSING")
        continue
    align = analyze_sheet_image(p)
    pos = align.get("positions") or {}
    brief = {k: (round(v["x"], 1), round(v["y"], 1)) for k, v in pos.items()}
    marked = trace_marked_paths_for_transition(p, pos, pos)
    marks = marked.get("marks") or {}
    paths = marked.get("paths") or {}
    tips = {}
    for oid, poly in paths.items():
        if poly and len(poly) >= 2:
            tips[oid] = (round(poly[-1]["x"], 1), round(poly[-1]["y"], 1), len(poly))
    passes = [
        (p.get("fromPid"), p.get("toPid"), p.get("orphan"))
        for p in (marked.get("passes") or [])
    ]
    print(f"PAGE {pg} pos={brief}")
    print(f"       marks={marks} tips={tips} passes={passes}")
