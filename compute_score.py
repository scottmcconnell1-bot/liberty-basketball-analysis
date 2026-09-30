import sqlite3
db_path = 'film_analysis.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# The Adrian rerun key from ACTIVE.md (completed one)
rerun_key = 'jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260928_031027'
base_key = 'jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334'

print('=== Computing AI card score from events table for Adrian rerun ===')
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
    WHERE e.game_id = ?
""", (rerun_key,))
row = cursor.fetchone()
if row:
    total_events, total_points, total_makes = row
    print('Total events: {}'.format(total_events))
    print('Total makes: {}'.format(total_makes))
    print('Total points: {}'.format(total_points))
    print()
    # Breakdown by make type
    cursor.execute("""
        SELECT 
            et.label,
            COUNT(*) as count
        FROM events e
        JOIN event_types et ON e.event_type_id = et.id
        WHERE e.game_id = ? AND et.label IN ('Made 2PT', 'Made 3PT', 'Made Free Throw')
        GROUP BY et.label
        ORDER BY count DESC
    """, (rerun_key,))
    makes_breakdown = cursor.fetchall()
    if makes_breakdown:
        print('Make breakdown:')
        for label, count in makes_breakdown:
            points = 2 if label == 'Made 2PT' else (3 if label == 'Made 3PT' else 1)
            print('  {}: {} events => {} points'.format(label, count, count * points))
    else:
        print('No make events found')
else:
    print('No events found for rerun key')

print()
print('=== According to ACTIVE.md, AI card should show ===')
print('17 makes, 31 points: Liberty 21, Adrian 10')
print()
print('=== Difference ===')
if row:
    total_events, total_points, total_makes = row
    print('Makes difference: {} (computed) - 17 (expected) = {}'.format(total_makes, total_makes - 17))
    print('Points difference: {} (computed) - 31 (expected) = {}'.format(total_points, total_points - 31))

# Now let's also check the base key for comparison
print()
print('=== Events table for base key ===')
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
    WHERE e.game_id = ?
""", (base_key,))
row = cursor.fetchone()
if row:
    total_events, total_points, total_makes = row
    print('Total events: {}'.format(total_events))
    print('Total makes: {}'.format(total_makes))
    print('Total points: {}'.format(total_points))
    # Breakdown
    cursor.execute("""
        SELECT 
            et.label,
            COUNT(*) as count
        FROM events e
        JOIN event_types et ON e.event_type_id = et.id
        WHERE e.game_id = ? AND et.label IN ('Made 2PT', 'Made 3PT', 'Made Free Throw')
        GROUP BY et.label
        ORDER BY count DESC
    """, (base_key,))
    makes_breakdown = cursor.fetchall()
    if makes_breakdown:
        print('Make breakdown:')
        for label, count in makes_breakdown:
            points = 2 if label == 'Made 2PT' else (3 if label == 'Made 3PT' else 1)
            print('  {}: {} events => {} points'.format(label, count, count * points))

conn.close()