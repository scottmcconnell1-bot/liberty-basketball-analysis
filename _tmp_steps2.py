import sqlite3
c = sqlite3.connect("film_analysis.db")
c.row_factory = sqlite3.Row
for pid in (109, 127):
    print("play", dict(c.execute("SELECT id,name FROM plays WHERE id=?", (pid,)).fetchone()))
    for s in c.execute(
        "SELECT step_number,label,substr(source_image,1,80) AS src FROM play_steps WHERE play_id=? ORDER BY step_number",
        (pid,),
    ):
        print(" ", dict(s))
