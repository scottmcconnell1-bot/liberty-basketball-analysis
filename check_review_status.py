import sqlite3
db_path = 'film_analysis.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

rerun_key = 'jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260928_031027'

print('=== Review status distribution for events ===')
cursor.execute("""
    SELECT 
        e.review_status,
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
    GROUP BY e.review_status
    ORDER BY count DESC
""", (rerun_key,))
rows = cursor.fetchall()
if rows:
    for status, cnt, pts in rows:
        print('  review_status={}: {} events, {} points'.format(status, cnt, pts))
else:
    print('  No review_status data')

print()
print('=== Now, let'"'"'s compute the score for events that are not rejected (maybe review_status != \"rejected\") ===')
# We need to know what review_status values indicate acceptance. From ACTIVE.md: teach corrected 67, rejected 154, 79 tags with no AI event.
# The accepted makes likely include the human verified manual tags and the teach-corrected AI events.
# Let's assume that accepted events are those with review_status not equal to 'rejected' and maybe also not 'pending'?
# But let's first see what values exist.

cursor.execute("""
    SELECT DISTINCT e.review_status FROM events e WHERE e.game_id = ?
""", (rerun_key,))
statuses = cursor.fetchall()
print('Distinct review_status values:')
for s in statuses:
    print('  {}'.format(s[0] if s[0] is not None else 'NULL'))

print()
# Let's try: accepted = human_verified=1 OR (review_status is not 'rejected' and maybe something else)
# We'll compute score for events where review_status IS NOT 'rejected'
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
    WHERE e.game_id = ? AND (e.review_status IS NULL OR e.review_status != 'rejected')
""", (rerun_key,))
row = cursor.fetchone()
if row:
    total_events, total_points, total_makes = row
    print('Events where review_status IS NOT \"rejected\":')
    print('  Total events: {}'.format(total_events))
    print('  Total makes: {}'.format(total_makes))
    print('  Total points: {}'.format(total_points))
    print()
    # Breakdown
    cursor.execute("""
        SELECT 
            et.label,
            COUNT(*) as count
        FROM events e
        JOIN event_types et ON e.event_type_id = et.id
        WHERE e.game_id = ? AND (e.review_status IS NULL OR e.review_status != 'rejected') AND et.label IN ('Made 2PT', 'Made 3PT', 'Made Free Throw')
        GROUP BY et.label
        ORDER BY count DESC
    """, (rerun_key,))
    makes_breakdown = cursor.fetchall()
    if makes_breakdown:
        print('Make breakdown:')
        for label, count in makes_breakdown:
            points = 2 if label == 'Made 2PT' else (3 if label == 'Made 3PT' else 1)
            print('  {}: {} events => {} points'.format(label, count, count * points))

print()
print('=== Let'"'"'s also check the teach process: according to ACTIVE.md, teach corrected 67 tags from the 146 base-film tags. ===')
print('Those 67 corrected tags likely became accepted makes. Let'"'"'s see if we can find events that are linked to manual tags.')

# We might need to look at the film_tags table or the teach process. But for now, let'"'"'s see if there is a column that indicates manual origin.
# We have source_type: ai or manual? We saw source_type=ai for all events in the earlier check. Let's double-check.
cursor.execute("""
    SELECT DISTINCT e.source_type FROM events e WHERE e.game_id = ?
""", (rerun_key,))
source_types = cursor.fetchall()
print('Distinct source_type values:')
for st in source_types:
    print('  {}'.format(st[0] if st[0] is not None else 'NULL'))

print()
# If source_type is only 'ai', then the manual tags are not in the events table as source_type=manual? Maybe they are inserted with source_type=manual? Let's check again but maybe we missed because we only looked at ai source_type earlier.
# Let's do a breakdown of source_type and human_verified.
cursor.execute("""
    SELECT 
        e.source_type,
        e.human_verified,
        COUNT(*) as count
    FROM events e
    WHERE e.game_id = ?
    GROUP BY e.source_type, e.human_verified
    ORDER BY e.source_type, e.human_verified
""", (rerun_key,))
rows = cursor.fetchall()
if rows:
    for st, hv, cnt in rows:
        print('  source_type={}, human_verified={}: {} events'.format(st, hv, cnt))

conn.close()