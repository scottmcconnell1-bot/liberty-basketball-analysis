"""Verify JrHigh import landed Active, no analysis queued."""
import json
import sqlite3
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
c = sqlite3.connect(str(ROOT / "film_analysis.db"))
c.row_factory = sqlite3.Row
print("archived col", "archived" in [r[1] for r in c.execute("PRAGMA table_info(videos)")])
print("archive counts", list(c.execute("select coalesce(archived,0), count(*) from videos group by 1")))
print("jrhigh rows:")
for r in c.execute(
    "select id, opponent, archived, game_id, stored_filename from videos where id>=64 order by id"
):
    print(dict(r))
n = c.execute(
    "select count(*) from analysis_runs where analysis_key like 'jrhigh%' or ifnull(base_analysis_key,'') like 'jrhigh%'"
).fetchone()[0]
print("analysis_runs jrhigh=", n)

sb = ROOT / "uploads" / "stat_books" / "jrhigh"
print("stat_books files", len(list(sb.glob('*'))) if sb.exists() else 'missing', sb)

for url in [
    "http://127.0.0.1:8080/api/videos?light=1",
    "http://127.0.0.1:8080/api/videos/archive-counts",
]:
    with urllib.request.urlopen(url, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    if isinstance(data, list):
        jr = [v for v in data if str(v.get("game_id") or "").startswith("jrhigh_")]
        print("API active total", len(data), "jrhigh", len(jr))
        for v in sorted(jr, key=lambda x: x.get("id", 0)):
            print(
                " ",
                v.get("id"),
                v.get("display_game"),
                "archived=",
                v.get("archived"),
                "status=",
                v.get("analysis_status"),
            )
    else:
        print("counts", data)
