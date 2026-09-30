import sqlite3
db_path = 'film_analysis.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

rerun_key = 'jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260928_031027'

print('=== Events for Adrian rerun, broken down by human_verified and source_type ===')
cursor.execute("""
    SELECT 
        e.human_verified,
        e.source_type,
        COUNT(*) as count,
        SUM(CASE 
            WHEN et.label = 'Made 2PT' THEN 2
            WHEN et.label = 'Made 3PT' THEN 3
            WHEN et.label = 'Made Free Throw' THEN 1
            ELSE 0 
        END) as points
    FROM events e
    JOIN event_types et ON e.event_type_id = et.id
    WHERE e.game_id = ?
    GROUP BY e.human_verified, e.source_type
    ORDER BY e.human_verified DESC, e.source_type
""", (rerun_key,))
rows = cursor.fetchall()
if rows:
    for hv, st, cnt, pts in rows:
        print('  human_verified={}, source_type={}: {} events, {} points'.format(hv, st, cnt, pts))
else:
    print('  No events found')

print()
print('=== Now, let'"'"'s compute the score for human_verified=1 events (assuming these are the accepted ones) ===')
cursor.execute("""
    SELECT 
        COUNT(*) as total_events,
        SUM(CASE 
            WHEN et.label = 'Made 2PT' THEN 2
            WHEN et.label = 'Made 3PT' THEN 3
            WHEN et.label = 'Made Free Throw' THEN 1
            ELSE 0 
        END) as total_points,
        SUM(CASE 
            WHEN et.label = 'Made 2PT' THEN 1
            WHEN et.label = 'Made 3PT' THEN 1
            WHEN et.label = 'Made Free Throw' THEN 1
            ELSE 0 
        END) as total_makes
    FROM events e
    JOIN event_types et ON e.event_type_id = et.id
    WHERE e.game_id = ? AND e.human_verified = 1
""", (rerun_key,))
row = cursor.fetchone()
if row:
    total_events, total_points, total_makes = row
    print('Human verified events:')
    print('  Total events: {}'.format(total_events))
    print('  Total makes: {}'.format(total_makes))
    print('  Total points: {}'.format(total_points))
    print()
    # Breakdown by make type for human_verified=1
    cursor.execute("""
        SELECT 
            et.label,
            COUNT(*) as count
        FROM events e
        JOIN event_types et ON e.event_type_id = et.id
        WHERE e.game_id = ? AND e.human_verified = 1 AND et.label IN ('Made 2PT', 'Made 3PT', 'Made Free Throw')
        GROUP BY et.label
        ORDER BY count DESC
    """, (rerun_key,))
    makes_breakdown = cursor.fetchall()
    if makes_breakdown:
        print('Make breakdown (human_verified=1):')
        for label, count in makes_breakdown:
            points = 2 if label == 'Made 2PT' else (3 if label == 'Made 3PT' else 1)
            print('  {}: {} events => {} points'.format(label, count, count * points))

print()
print('=== Let'"'"'s also check source_type ===')
cursor.execute("""
    SELECT 
        e.source_type,
        COUNT(*) as count
    FROM events e
    WHERE e.game_id = ?
    GROUP BY e.source_type
    ORDER BY count DESC
""", (rerun_key,))
source_types = cursor.fetchall()
if source_types:
    print('Source type distribution:')
    for st, cnt in source_types:
        print('  {}: {} events'.format(st, cnt))

print()
print('=== According to ACTIVE.md, AI card should show ===')
print('17 makes, 31 points: Liberty 21, Adrian 10')
print()
print('=== Difference (human_verified=1 vs expected) ===')
if row:
    total_events, total_points, total_makes = row
    print('Makes difference: {} (computed) - 17 (expected) = {}'.format(total_makes, total_makes - 17))
    print('Points difference: {} (computed) - 31 (expected) = {}'.format(total_points, total_points - 31))

conn.close()