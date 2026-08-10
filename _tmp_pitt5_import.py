import json
import sqlite3
from pathlib import Path

# Bulk import session metadata
base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
for name in ["session.json", "plays.json", "manifest.json", "import.json", "result.json"]:
    p = base / name
    if p.exists():
        print("FOUND", p, "size", p.stat().st_size)

# Search recursively for pitt
for p in base.rglob("*.json"):
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue
    if "Pitt" in text or "pitt" in text or "172" in text:
        print("json hit", p)

# Also look in data/
for p in Path("data").rglob("*pitt*"):
    print("data hit", p)
for p in Path("data").rglob("*bulk*"):
    if p.is_file() and p.suffix in {".json", ".jsonl", ".db"}:
        print("bulk-ish", p)

# Check play_steps history - any backup tables?
con = sqlite3.connect("film_analysis.db")
cur = con.cursor()
tabs = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
)]
print("tables", [t for t in tabs if "play" in t.lower() or "step" in t.lower() or "import" in t.lower()])

# Look for other steps that reference page_0172 or Pitt
rows = cur.execute(
    "SELECT play_id, step_number, label, source_image FROM play_steps "
    "WHERE source_image LIKE '%0172%' OR source_image LIKE '%0173%' OR label LIKE '%Pitt%'"
).fetchall()
print("steps with 172/173", rows)

# Cycle Spots steps
cs = cur.execute(
    "SELECT id, name, diagram_json FROM plays WHERE name LIKE '%Cycle%'"
).fetchall()
print("cycle", cs)
for r in cs:
    steps = cur.execute(
        "SELECT step_number, label, source_image FROM play_steps WHERE play_id=? ORDER BY step_number",
        (r[0],),
    ).fetchall()
    print(" cycle steps", steps)

# Pitt 1 steps for comparison
for pid in (136, 137):
    steps = cur.execute(
        "SELECT step_number, label, source_image FROM play_steps WHERE play_id=? ORDER BY step_number",
        (pid,),
    ).fetchall()
    print("play", pid, steps)
