#!/usr/bin/env python
"""Run full pipeline: event generation + enhanced analysis."""
import sqlite3, time

game_id = 'adrian_20260228_semifinal'
db_path = 'film_analysis.db'
fps = 25.0

# Step 1: Event generation
print('=== Step 1: Event Generation ===', flush=True)
from event_generator import main as generate_events
t0 = time.time()
result = generate_events(game_id, db_path)
print(f'Event generation: {time.time()-t0:.1f}s, result={result}', flush=True)

# Step 2: Enhanced analysis
print('=== Step 2: Enhanced Analysis ===', flush=True)
from film_analysis import run_enhanced_analysis
t0 = time.time()
result = run_enhanced_analysis(db_path, game_id, fps, video_width=1920, video_height=1080)
print(f'Enhanced analysis: {time.time()-t0:.1f}s', flush=True)

# Summary
conn = sqlite3.connect(db_path)
print('', flush=True)
for table in ['events', 'shot_classifications', 'play_recognitions', 'player_minutes', 'player_effect']:
    row = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE game_id=?', (game_id,)).fetchone()
    print(f'{table}: {row[0]}', flush=True)

rows = conn.execute('SELECT event_type, COUNT(*) as cnt FROM events WHERE game_id=? GROUP BY event_type ORDER BY cnt DESC', (game_id,)).fetchall()
print('', flush=True)
print('Event breakdown:', flush=True)
for r in rows:
    print(f'  {r[0]}: {r[1]}', flush=True)

conn.close()
print('', flush=True)
print('=== DONE ===', flush=True)
