import sqlite3

db = sqlite3.connect("film_analysis.db")
db.row_factory = sqlite3.Row
print([dict(r) for r in db.execute(
    "SELECT program, COUNT(*) c FROM plays GROUP BY program"
).fetchall()])
row = db.execute(
    "SELECT sql FROM sqlite_master WHERE name='plays'"
).fetchone()
print(row[0] if row else None)
