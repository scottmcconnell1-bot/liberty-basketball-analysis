import sqlite3
db_path = 'film_analysis.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# The Adrian rerun key from ACTIVE.md (completed one)
rerun_key = 'jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334__rerun_20260928_031027'
base_key = 'jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334'

print('=== Events analysis for Adrian rerun: {} ==='.format(rerun_key))
cursor.execute("""
    SELECT 
        COUNT(*) as total_events,
        SUM(CASE WHEN e.event_type IN ('made_two','made_three','made_free_throw') THEN 1 ELSE 0 END) as makes,
        SUM(CASE WHEN e.event_type = 'made_two' THEN 1 ELSE 0 END) as makes_2pt,
        SUM(CASE WHEN e.event_type = 'made_three' THEN 1 ELSE 0 END) as makes_3pt,
        SUM(CASE WHEN e.event_type = 'made_free_throw' THEN 1 ELSE 0 END) as makes_ft,
        SUM(CASE e.event_type
                WHEN 'made_two' THEN 2
                WHEN 'made_three' THEN 3
                WHEN 'made_free_throw' THEN 1
                ELSE 0
            END) as points_from_makes
    FROM events e
    WHERE e.game_id = ?
""", (rerun_key,))
stats = cursor.fetchone()
if stats:
    total_events, makes, makes_2pt, makes_3pt, makes_ft, points = stats
    print('Total events: {}'.format(total_events))
    print('Total makes: {} (2pt: {}, 3pt: {}, ft: {})'.format(makes, makes_2pt, makes_3pt, makes_ft))
    print('Total points from makes: {}'.format(points))
    print()

# Also check the breakdown by player/team if available
print('=== Top scorers (by makes) ===')
cursor.execute("""
    SELECT 
        e.player,
        COUNT(*) as makes,
        SUM(CASE e.event_type
            WHEN 'made_two' THEN 2
            WHEN 'made_three' THEN 3
            WHEN 'made_free_throw' THEN 1
            ELSE 0
        END) as points
    FROM events e
    WHERE e.game_id = ? AND e.event_type IN ('made_two','made_three','made_free_throw')
    GROUP BY e.player
    ORDER BY makes DESC
    LIMIT 10
""", (rerun_key,))
scorers = cursor.fetchall()
if scorers:
    for player, makes, points in scorers:
        player_name = player if player is not None else "Unknown"
        print('  {}: {} makes, {} points'.format(player_name, makes, points))
else:
    print('  No scoring events found with player names')
print()

# Check what the ACTIVE.md says the computed score should be
print('=== According to ACTIVE.md (lines 163-164) ===')
print('Results AI card counts 17 makes, 31 points: Liberty 21 (Dayley 15, Colman 4, Peterson 2) and Adrian 10 (Mendoza 4, Alvarez 3, Foster 2, Rodus 1)')
print()
print('=== Checking if our computed score matches ===')
if stats:
    total_events, makes, makes_2pt, makes_3pt, makes_ft, points = stats
    if makes == 17 and points == 31:
        print('MATCH: 17 makes, 31 points')
    else:
        print('MISMATCH: Computed {} makes, {} points vs 17 makes, 31 points'.format(makes, points))
        print('   Difference: {} makes, {} points'.format(makes - 17, points - 31))
        
        # Let's see what the breakdown should be according to ACTIVE.md
        expected_liberty = 21  # points
        expected_adrian = 10   # points
        print('   Expected Liberty: {} points, Adrian: {} points'.format(expected_liberty, expected_adrian))
        
        # Check team breakdown if we have team_id in events
        print()
        print('=== Checking team breakdown (if available) ===')
        cursor.execute("""
            SELECT 
                e.team_id,
                COUNT(*) as makes,
                SUM(CASE e.event_type
                    WHEN 'made_two' THEN 2
                    WHEN 'made_three' THEN 3
                    WHEN 'made_free_throw' THEN 1
                    ELSE 0
                END) as points
            FROM events e
            WHERE e.game_id = ? AND e.event_type IN ('made_two','made_three','made_free_throw')
            GROUP BY e.team_id
        """, (rerun_key,))
        team_stats = cursor.fetchall()
        if team_stats:
            for team_id, makes, points in team_stats:
                print('  Team ID {}: {} makes, {} points'.format(team_id, makes, points))
        else:
            print('  No team_id data in events')
else:
    print('Could not compute score - no events found')

conn.close()