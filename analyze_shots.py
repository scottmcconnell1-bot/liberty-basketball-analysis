import sqlite3, math

conn = sqlite3.connect('film_analysis.db')
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT court_x, court_y, shot_type, shot_result 
    FROM shot_classifications 
    WHERE game_id='riverstone_Liberty_Vs_Riverstone_20260519_103815' 
      AND court_x IS NOT NULL AND court_y IS NOT NULL
      AND court_x < 0.99 AND court_y < 0.99
    ORDER BY court_y, court_x
""").fetchall()
print(f'Total valid shots: {len(rows)}')
print()
print(f'  {"court_x":>8} {"court_y":>8} {"type":>5} {"result":>6}')
print('-' * 35)
for r in rows:
    print(f'  {r["court_x"]:8.4f} {r["court_y"]:8.4f} {r["shot_type"]:>5} {r["shot_result"]:>6}')
print()
# Summary stats
xs = [r['court_x'] for r in rows]
ys = [r['court_y'] for r in rows]
print(f'court_x range: [{min(xs):.4f}, {max(xs):.4f}], mean={sum(xs)/len(xs):.4f}')
print(f'court_y range: [{min(ys):.4f}, {max(ys):.4f}], mean={sum(ys)/len(ys):.4f}')
print()

# Distance from various candidate basket positions
for bx, by, label in [(0.5, 1.0, 'bottom_center'), (0.5, 0.0, 'top_center'), (0.5, 0.15, 'near_top')]:
    dists = [math.sqrt((r['court_x']-bx)**2 + (r['court_y']-by)**2) for r in rows]
    print(f'Dist from {label} ({bx},{by}): min={min(dists):.4f}, max={max(dists):.4f}, mean={sum(dists)/len(dists):.4f}')
print()

# Count by result
makes = [r for r in rows if r['shot_result'] == 'make']
misses = [r for r in rows if r['shot_result'] == 'miss']
print(f'Makes: {len(makes)}, Misses: {len(misses)}')
print()

# Show makes separately
print('--- MAKES ---')
for r in makes:
    d_bottom = math.sqrt((r['court_x']-0.5)**2 + (r['court_y']-1.0)**2)
    d_top = math.sqrt((r['court_x']-0.5)**2 + (r['court_y']-0.0)**2)
    print(f'  ({r["court_x"]:.4f}, {r["court_y"]:.4f})  dist_bottom={d_bottom:.4f}  dist_top={d_top:.4f}')
print()
print('--- MISSES ---')
for r in misses:
    d_bottom = math.sqrt((r['court_x']-0.5)**2 + (r['court_y']-1.0)**2)
    d_top = math.sqrt((r['court_x']-0.5)**2 + (r['court_y']-0.0)**2)
    print(f'  ({r["court_x"]:.4f}, {r["court_y"]:.4f})  dist_bottom={d_bottom:.4f}  dist_top={d_top:.4f}')

# Find makes centroid
if makes:
    mx = sum(r['court_x'] for r in makes) / len(makes)
    my = sum(r['court_y'] for r in makes) / len(makes)
    print(f'\nMakes centroid: ({mx:.4f}, {my:.4f})')
    d3 = [math.sqrt((r['court_x']-mx)**2 + (r['court_y']-my)**2) for r in rows]
    print(f'Dist from makes centroid: min={min(d3):.4f}, max={max(d3):.4f}, mean={sum(d3)/len(d3):.4f}')
    print('\nAll shots sorted by distance from makes centroid:')
    indexed = list(zip(rows, d3))
    indexed.sort(key=lambda x: x[1])
    for r, d in indexed:
        print(f'  ({r["court_x"]:.4f}, {r["court_y"]:.4f})  dist={d:.4f}  {r["shot_result"]}')

conn.close()
