import sqlite3
conn = sqlite3.connect('film_analysis.db')
cursor = conn.cursor()
cursor.execute("SELECT id, name, category, diagram_json FROM plays ORDER BY id")
rows = cursor.fetchall()
print(f'Total plays: {len(rows)}')
for r in rows:
    print(f'  id={r[0]}, name={r[1]}, category={r[2]}, diagram={r[3][:100] if r[3] else "None"}...')
conn.close()