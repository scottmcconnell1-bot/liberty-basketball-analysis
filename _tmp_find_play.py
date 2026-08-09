import sqlite3, json
c = sqlite3.connect(r"C:\Users\scott\Documents\liberty-basketball-analysis\data\analysis.db")
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("tables:", tables)
for t in tables:
    if "play" in t.lower() or "sheet" in t.lower() or "step" in t.lower():
        cols = [x[1] for x in c.execute(f"PRAGMA table_info({t})").fetchall()]
        print(f"\n{t}: {cols}")
        try:
            n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  count={n}")
        except Exception as e:
            print("  count err", e)
