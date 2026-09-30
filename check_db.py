import sqlite3
db_path = 'film_analysis.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
# Check what game_ids exist in events table
cursor.execute("""
    SELECT DISTINCT game_id FROM events LIMIT 20
""")
game_ids = cursor.fetchall()
print('First 20 distinct game_ids in events:')
for gid in game_ids:
    print(f'  {gid[0]}')
print()
# Check for the specific keys we're interested in
rerun_key = 'jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260928_031027'
base_key = 'jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334'
print(f'Checking for rerun key: {rerun_key}')
cursor.execute("""
    SELECT COUNT(*) FROM events WHERE game_id = ?
""", (rerun_key,))
count = cursor.fetchone()[0]
print(f'  Events with rerun key: {count}')
print(f'Checking for base key: {base_key}')
cursor.execute("""
    SELECT COUNT(*) FROM events WHERE game_id = ?
""", (base_key,))
count = cursor.fetchone()[0]
print(f'  Events with base key: {count}')
print()
# Let's also check analysis_runs table for these keys
print('Checking analysis_runs table:')
cursor.execute("""
    SELECT analysis_key, status, started_at FROM analysis_runs WHERE analysis_key LIKE '%Adrian%' LIMIT 10
""")
runs = cursor.fetchall()
for run in runs:
    print(f'  analysis_key: {run[0][:80]}..., status: {run[1]}, started: {run[2]}')
conn.close()