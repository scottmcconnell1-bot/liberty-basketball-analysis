import sqlite3
conn = sqlite3.connect('film_analysis.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print('Tables:', tables)
for t in tables:
    name = t[0]
    if 'play' in name.lower():
        cursor.execute(f'PRAGMA table_info({name})')
        cols = cursor.fetchall()
        print(f'\n{name} columns:', cols)
        cursor.execute(f'SELECT * FROM {name} LIMIT 10')
        rows = cursor.fetchall()
        print(f'{name} sample:', rows)
conn.close()