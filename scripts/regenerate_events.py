#!/usr/bin/env python
"""Regenerate events and enhanced analysis for a game with fixed event generator."""
import sqlite3
import cv2
import sys

game_id = 'adrian_20260228_semifinal'
db_path = 'film_analysis.db'

# Update run status
conn = sqlite3.connect(db_path)
conn.execute("UPDATE analysis_runs SET status='running', progress_pct=50, progress_step='Regenerating events (fixed)...' WHERE game_id=?", (game_id,))
conn.commit()
conn.close()

# Step 1: Regenerate events with fixed logic
print('=== Event Generation (fixed) ===', flush=True)
from event_generator import main as generate_events
generate_events(game_id, db_path)

# Step 2: Run enhanced analysis
print('=== Enhanced Analysis ===', flush=True)
cap = cv2.VideoCapture('uploads/Adrian_20260228.mp4', cv2.CAP_FFMPEG)
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
cap.release()
print(f'FPS: {fps}', flush=True)

from film_analysis import run_enhanced_analysis
run_enhanced_analysis(db_path, game_id, fps)

# Update run status
conn = sqlite3.connect(db_path)
conn.execute("UPDATE analysis_runs SET status='completed', progress_pct=100, progress_step='Done', completed_at=CURRENT_TIMESTAMP WHERE game_id=?", (game_id,))
conn.commit()
conn.close()

# Print summary
conn = sqlite3.connect(db_path)
for table in ['events', 'shot_classifications', 'play_recognitions', 'player_minutes', 'player_effect']:
    col = 'game_id' if table == 'events' else None
    if col:
        row = conn.execute(f'SELECT COUNT(*) FROM {table} WHERE game_id=?', (game_id,)).fetchone()
    else:
        row = conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()
    print(f'{table}: {row[0]}', flush=True)
conn.close()

print('=== DONE ===', flush=True)
