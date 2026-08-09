"""Restore Pitt 5 (137) to real pages 172+173; clear left-block drop hack."""
import json
import sqlite3
from pathlib import Path

from playbook_sheet_align import analyze_sheet_image

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
pos172 = analyze_sheet_image(base / "page_0172.png")["positions"]
pos173 = analyze_sheet_image(base / "page_0173.png")["positions"]

def bake(pos):
    return {k: {"x": round(float(v["x"]), 1), "y": round(float(v["y"]), 1)} for k, v in pos.items()}

opening = bake(pos172)
screen = bake(pos173)
print("opening", opening)
print("screen", screen)

c = sqlite3.connect("film_analysis.db")
c.row_factory = sqlite3.Row
play = c.execute("SELECT * FROM plays WHERE id = 137").fetchone()
dj = json.loads(play["diagram_json"])
# Full PDF Pitt 5 range is 172–173 (formation + action). Keep 172 out of any
# "extra" list — it is the formation sheet, not an add-on beyond the play.
dj["start_page"] = 172
dj["end_page"] = 173
dj.pop("excluded_pages", None)
dj["name"] = dj.get("name") or "Pitt 5"

c.execute(
    "UPDATE plays SET diagram_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 137",
    (json.dumps(dj),),
)
c.execute("DELETE FROM play_steps WHERE play_id = 137")

img172 = "/uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0172.png"
img173 = "/uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0173.png"

steps = [
    (0, "Step 1 (Page 172)", json.dumps(opening), "[]", "", img172),
    (1, "Step 2 (Page 173)", json.dumps(screen), "[]", "", img173),
]
for sn, label, pos, mov, notes, src in steps:
    c.execute(
        """INSERT INTO play_steps
           (play_id, step_number, label, positions_json, movements_json, notes, source_image)
           VALUES (137, ?, ?, ?, ?, ?, ?)""",
        (sn, label, pos, mov, notes, src),
    )
c.commit()

rows = c.execute(
    "SELECT step_number, label, source_image FROM play_steps WHERE play_id=137 ORDER BY step_number"
).fetchall()
print("diagram", dj)
print("steps", [dict(r) for r in rows])
