import sqlite3
from pathlib import Path

c = sqlite3.connect("film_analysis.db", timeout=30)
c.execute("PRAGMA busy_timeout=60000")
print("running", c.execute("SELECT COUNT(*) FROM analysis_runs WHERE status='running'").fetchone()[0])
for r in c.execute(
    "SELECT id, analysis_key, status, progress_pct, substr(COALESCE(progress_step,''),1,60) "
    "FROM analysis_runs ORDER BY id DESC LIMIT 8"
):
    print(r)
