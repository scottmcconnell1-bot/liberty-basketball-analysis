import sqlite3, math, json

conn = sqlite3.connect('film_analysis.db')
conn.row_factory = sqlite3.Row

# Get all shot/make/miss events with their detection positions
shot_events = conn.execute("""
    SELECT e.id as event_id, e.player, e.event_type,
           e.timestamp_ms, e.details_json, e.source_frame
    FROM events e
    WHERE e.game_id = 'riverstone_Liberty_Vs_Riverstone_20260519_103815'
      AND e.event_type IN ('shot', 'make', 'miss')
    ORDER BY e.timestamp_ms
""").fetchall()

print(f"Total shot events: {len(shot_events)}")
print()

results = []
for event in shot_events:
    shot_result = "make" if event["event_type"] == "make" else "miss"
    player_cluster = event["player"]
    details = {}
    if event["details_json"]:
        try:
            details = json.loads(event["details_json"])
        except:
            pass

    peak_frame = details.get("peak_frame")
    source_frame = event["source_frame"]
    frame = peak_frame or source_frame

    court_x = None
    court_y = None

    if frame is not None and player_cluster is not None:
        det = conn.execute("""
            SELECT x_center, y_center
            FROM detections
            WHERE game_id = ? AND object_class = 'person'
              AND player_cluster = CAST(? AS INTEGER)
              AND frame_number BETWEEN ? AND ?
            ORDER BY ABS(frame_number - ?)
            LIMIT 1
        """, ('riverstone_Liberty_Vs_Riverstone_20260519_103815', player_cluster,
              frame - 10, frame + 10, frame)).fetchone()

        if det and det[0] is not None:
            cx = max(0, min(det[0], 1919)) / 1920.0
            cy = max(0, min(det[1], 1079)) / 1080.0
            court_x = cx
            court_y = cy

    results.append({
        'event_id': event['event_id'],
        'type': event['event_type'],
        'result': shot_result,
        'court_x': court_x,
        'court_y': court_y,
        'player': player_cluster,
        'frame': frame,
    })

# Print all
print(f'  {"x":>8} {"y":>8} {"result":>6} {"event":>6} {"player":>7} {"frame":>7}')
print('-' * 55)
for r in results:
    cx = f'{r["court_x"]:.4f}' if r["court_x"] is not None else '    NULL'
    cy = f'{r["court_y"]:.4f}' if r["court_y"] is not None else '    NULL'
    p = str(r["player"]) if r["player"] is not None else 'NULL'
    f = str(r["frame"]) if r["frame"] is not None else 'NULL'
    print(f'  {cx:>8} {cy:>8} {r["result"]:>6} {r["type"]:>6} {p:>7} {f:>7}')

# Filter valid
valid = [r for r in results if r['court_x'] is not None and r['court_y'] is not None
         and r['court_x'] < 0.99 and r['court_y'] < 0.99]
print(f'\nValid shots (non-NULL, non-edge): {len(valid)}')
print(f'NULL positions: {len([r for r in results if r["court_x" ] is None])}')
print(f'Edge positions: {len([r for r in results if r["court_x"] is not None and (r["court_x"] >= 0.99 or r["court_y"] >= 0.99)])}')

if valid:
    xs = [r['court_x'] for r in valid]
    ys = [r['court_y'] for r in valid]
    print(f'\nX range: [{min(xs):.4f}, {max(xs):.4f}], mean={sum(xs)/len(xs):.4f}')
    print(f'Y range: [{min(ys):.4f}, {max(ys):.4f}], mean={sum(ys)/len(ys):.4f}')

    # Distance from various basket positions
    print('\nDistance from candidate basket positions:')
    for bx, by, label in [(0.5, 1.0, 'bottom(0.5,1.0)'), (0.5, 0.0, 'top(0.5,0.0)'),
                          (0.5, 0.1, '(0.5,0.1)'), (0.5, 0.2, '(0.5,0.2)'),
                          (0.5, 0.3, '(0.5,0.3)')]:
        dists = [math.sqrt((r['court_x']-bx)**2 + (r['court_y']-by)**2) for r in valid]
        print(f'  From {label}: min={min(dists):.3f} max={max(dists):.3f} mean={sum(dists)/len(dists):.3f}')

    # Sort by y to understand the layout
    print('\nShots sorted by Y (top to bottom of frame):')
    for r in sorted(valid, key=lambda r: r['court_y']):
        d_top = math.sqrt((r['court_x']-0.5)**2 + r['court_y']**2)
        d_bot = math.sqrt((r['court_x']-0.5)**2 + (r['court_y']-1.0)**2)
        print(f'  ({r["court_x"]:.4f}, {r["court_y"]:.4f})  d_top={d_top:.3f}  d_bot={d_bot:.3f}  {r["result"]}')

    # Makes only
    makes = [r for r in valid if r['result'] == 'make']
    if makes:
        print(f'\nMakes: {len(makes)}')
        mx = sum(r['court_x'] for r in makes) / len(makes)
        my = sum(r['court_y'] for r in makes) / len(makes)
        print(f'Makes centroid: ({mx:.4f}, {my:.4f})')
        for r in sorted(valid, key=lambda r: r['court_y']):
            d = math.sqrt((r['court_x']-mx)**2 + (r['court_y']-my)**2)
            print(f'  ({r["court_x"]:.4f}, {r["court_y"]:.4f})  d_centroid={d:.3f}  {r["result"]}')

conn.close()
