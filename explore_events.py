import sqlite3
db_path = 'film_analysis.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# The Adrian rerun key from ACTIVE.md (completed one)
rerun_key = 'jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260928_031027'

print('=== Sample events for Adrian rerun ===')
cursor.execute("""
    SELECT 
        e.event_type,
        e.shot_result,
        e.details_json,
        et.label as event_type_label,
        et.category
    FROM events e
    JOIN event_types et ON e.event_type_id = et.id
    WHERE e.game_id = ?
    LIMIT 10
""", (rerun_key,))
rows = cursor.fetchall()
if rows:
    for i, row in enumerate(rows):
        event_type, shot_result, details_json, event_type_label, category = row
        print('Event {}:'.format(i+1))
        print('  event_type column: {}'.format(event_type))
        print('  shot_result column: {}'.format(shot_result))
        print('  event_types.label: {}'.format(event_type_label))
        print('  event_types.category: {}'.format(category))
        print('  details_json: {}'.format(details_json[:100] + ('...' if len(details_json) > 100 else '')))
        print()
else:
    print('No events found')

# Let's also check what distinct event_type values we have
print('=== Distinct event_type values in events ===')
cursor.execute("""
    SELECT DISTINCT e.event_type, COUNT(*) as count
    FROM events e
    WHERE e.game_id = ?
    GROUP BY e.event_type
    ORDER BY count DESC
""", (rerun_key,))
rows = cursor.fetchall()
if rows:
    for event_type, count in rows:
        print('  {}: {} events'.format(event_type, count))
else:
    print('No event_type values found')

# Check distinct shot_result values
print('=== Distinct shot_result values in events ===')
cursor.execute("""
    SELECT DISTINCT e.shot_result, COUNT(*) as count
    FROM events e
    WHERE e.game_id = ?
    GROUP BY e.shot_result
    ORDER BY count DESC
""", (rerun_key,))
rows = cursor.fetchall()
if rows:
    for shot_result, count in rows:
        print('  {}: {} events'.format(shot_result, count))
else:
    print('No shot_result values found')

conn.close()