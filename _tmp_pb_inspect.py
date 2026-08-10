import sqlite3

db = sqlite3.connect("film_analysis.db")
db.row_factory = sqlite3.Row
print("play tables", [r[0] for r in db.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%play%'"
).fetchall()])
print("pb cols", [r[1] for r in db.execute("PRAGMA table_info(playbooks)").fetchall()])
print("play cols", [r[1] for r in db.execute("PRAGMA table_info(plays)").fetchall()])
print("playbooks", [dict(r) for r in db.execute("SELECT * FROM playbooks LIMIT 20").fetchall()])
print("plays", db.execute("SELECT COUNT(*) c FROM plays").fetchone()["c"])
print("by pb", [dict(r) for r in db.execute(
    "SELECT playbook_id, COUNT(*) c FROM plays GROUP BY playbook_id"
).fetchall()])
print("sample", [dict(r) for r in db.execute(
    "SELECT id, name, playbook_id FROM plays ORDER BY id DESC LIMIT 15"
).fetchall()])
