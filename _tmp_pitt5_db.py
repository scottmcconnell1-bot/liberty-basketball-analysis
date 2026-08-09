import sqlite3
import json

con = sqlite3.connect("film_analysis.db")
con.row_factory = sqlite3.Row
cur = con.cursor()
cols = [r[1] for r in cur.execute("PRAGMA table_info(plays)")]
print("plays cols", cols)
rows = cur.execute(
    "SELECT id, name, diagram_json, description FROM plays WHERE id=137 OR lower(name) LIKE '%pitt%'"
).fetchall()
for row in rows:
    d = dict(row)
    try:
        dj = json.loads(d.get("diagram_json") or "{}")
    except Exception:
        dj = d.get("diagram_json")
    print("--- play", d["id"], d["name"])
    print("diagram", json.dumps(dj, indent=2)[:2000])

steps = cur.execute(
    "SELECT id, play_id, step_number, label, source_image, "
    "substr(positions_json,1,120) as pos, substr(notes,1,80) as notes "
    "FROM play_steps WHERE play_id=137 ORDER BY step_number"
).fetchall()
print("\n=== steps for 137 ===")
for s in steps:
    print(dict(s))

# nearby pitt plays for page range context
nearby = cur.execute(
    "SELECT id, name, diagram_json FROM plays WHERE id BETWEEN 130 AND 145 ORDER BY id"
).fetchall()
print("\n=== nearby plays ===")
for r in nearby:
    try:
        dj = json.loads(r["diagram_json"] or "{}")
    except Exception:
        dj = {}
    print(
        r["id"],
        r["name"],
        "pages",
        dj.get("start_page"),
        "-",
        dj.get("end_page"),
        "excl",
        dj.get("excluded_pages"),
    )
