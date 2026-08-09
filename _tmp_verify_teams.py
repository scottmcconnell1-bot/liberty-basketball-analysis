import urllib.request
import sqlite3

html = urllib.request.urlopen("http://127.0.0.1:8080/playbook").read().decode("utf-8", "replace")
print("team_select", "playbookTeamSelect" in html)
print("hs_boys", "hs_boys" in html)
print("hs_girls", "High School Girls" in html)
print("copy", "Copy to" in html)
print("pitt", "Pitt 5" in html)
print("rip", ">Rip<" in html or "Rip" in html)

db = sqlite3.connect("film_analysis.db")
db.row_factory = sqlite3.Row
cols = [r[1] for r in db.execute("PRAGMA table_info(plays)")]
print("has team_key", "team_key" in cols)
print("by team", [dict(r) for r in db.execute(
    "SELECT team_key, COUNT(*) c FROM plays GROUP BY team_key"
).fetchall()])
row = db.execute("SELECT id, name, team_key FROM plays WHERE name = ?", ("Rip",)).fetchone()
print("rip", dict(row) if row else None)
