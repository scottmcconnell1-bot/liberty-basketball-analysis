import sqlite3, math

conn = sqlite3.connect('film_analysis.db')
conn.row_factory = sqlite3.Row

# ALL shots for this game
rows = conn.execute("""
    SELECT court_x, court_y, shot_type, shot_result 
    FROM shot_classifications 
    WHERE game_id='riverstone_Liberty_Vs_Riverstone_20260519_103815'
    ORDER BY shot_type, court_y, court_x
""").fetchall()
print(f'Total shots (all): {len(rows)}')
print()
for r in rows:
    cx = f'{r["court_x"]:.4f}' if r["court_x"] is not None else 'NULL'
    cy = f'{r["court_y"]:.4f}' if r["court_y"] is not None else 'NULL'
    print(f'  cx={cx:>8} cy={cy:>8}  {r["shot_type"]:>5}  {r["shot_result"]}')

# Count by type and result
print()
from collections import defaultdict
counts = defaultdict(lambda: {'make': 0, 'miss': 0})
for r in rows:
    counts[r['shot_type']][r['shot_result']] += 1
for t in sorted(counts):
    c = counts[t]
    print(f'  {t}: make={c["make"]}, miss={c["miss"]}, total={c["make"]+c["miss"]}')

# Count NULL positions
nulls = [r for r in rows if r['court_x'] is None or r['court_y'] is None]
edges = [r for r in rows if r['court_x'] is not None and r['court_y'] is not None and (r['court_x'] >= 0.99 or r['court_y'] >= 0.99)]
valid = [r for r in rows if r['court_x'] is not None and r['court_y'] is not None and r['court_x'] < 0.99 and r['court_y'] < 0.99]
print(f'\nNull positions: {len(nulls)}')
print(f'Edge positions: {len(edges)}')
print(f'Valid positions: {len(valid)}')

# Show edge shots
if edges:
    print('\n--- EDGE SHOTS ---')
    for r in edges:
        print(f'  cx={r["court_x"]:.4f} cy={r["court_y"]:.4f}  {r["shot_type"]}  {r["shot_result"]}')

# Show NULL shots
if nulls:
    print('\n--- NULL SHOTS ---')
    for r in nulls:
        print(f'  cx=NULL cy=NULL  {r["shot_type"]}  {r["shot_result"]}')

# Now let's look at the valid shots more carefully
# The court coordinates: x is horizontal (0=left, 1=right), y is vertical (0=top, 1=bottom)
# For a typical basketball camera angle, the basket is at the TOP of the frame (low y)
# The 3pt line arcs around the basket
# Shots near the basket (low y) = 2pt, shots far from basket (high y) = 3pt

print('\n=== VALID SHOTS ANALYSIS ===')
print('Assuming basket is near TOP of frame (y ~ 0.0-0.15)')
print()
for r in sorted(valid, key=lambda r: r['court_y']):
    # Distance from top-center (likely basket area)
    d_top = math.sqrt((r['court_x']-0.5)**2 + (r['court_y']-0.0)**2)
    # Distance from (0.5, 0.1) - slightly below top
    d_01 = math.sqrt((r['court_x']-0.5)**2 + (r['court_y']-0.1)**2)
    print(f'  ({r["court_x"]:.4f}, {r["court_y"]:.4f})  dist_top={d_top:.4f}  dist_(0.5,0.1)={d_01:.4f}  {r["shot_result"]}')

conn.close()
