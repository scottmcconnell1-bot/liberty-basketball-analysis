from small_fixes_v6_copy import fall_through_check, decide_shot

# Test 1: straight drop inside rim -> pass
hoop_x, hoop_y, hoop_w = 100.0, 100.0, 50.0
scale_y = 1.0
cross_frame = 10
ball = [(9, 100.0, 90.0), (10, 100.0, 100.0), (11, 100.0, 110.0), (12, 100.0, 120.0), (13, 100.0, 130.0)]
result = fall_through_check(ball, cross_frame, hoop_x, hoop_y, hoop_w, scale_y)
print(f'Test 1 (straight drop): {result}')

# Test 2: outside rim
ball2 = [(9, 100.0, 90.0), (10, 125.0, 100.0), (11, 125.0, 110.0), (12, 125.0, 120.0), (13, 125.0, 130.0)]
result2 = fall_through_check(ball2, cross_frame, hoop_x, hoop_y, hoop_w, scale_y)
print(f'Test 2 (outside rim): {result2}')

# Test 3: went up
ball3 = [(9, 100.0, 90.0), (10, 100.0, 100.0), (11, 100.0, 120.0), (12, 100.0, 114.0), (13, 100.0, 130.0)]
result3 = fall_through_check(ball3, cross_frame, hoop_x, hoop_y, hoop_w, scale_y)
print(f'Test 3 (went up): {result3}')

# Test 4: short fall (only 2 points)
ball4 = [(9, 100.0, 90.0), (10, 100.0, 100.0), (11, 100.0, 110.0), (12, 100.0, 120.0)]
result4 = fall_through_check(ball4, cross_frame, hoop_x, hoop_y, hoop_w, scale_y)
print(f'Test 4 (short fall): {result4}')

# Test 5: no ball crossing
ball5 = [(10, 100.0, 100.0), (11, 100.0, 110.0), (12, 100.0, 120.0), (13, 100.0, 130.0)]
result5 = fall_through_check(ball5, cross_frame, hoop_x, hoop_y, hoop_w, scale_y)
print(f'Test 5 (no ball crossing): {result5}')

# Test 6: decide_shot with switch off vs on (make track)
hoop = [100.0, 100.0, 50.0, 40.0]
ball6 = [(0, 100.0, 50.0), (1, 100.0, 70.0), (2, 100.0, 90.0), (3, 100.0, 100.0), (4, 100.0, 110.0), (5, 100.0, 120.0), (6, 100.0, 130.0), (7, 100.0, 140.0), (8, 100.0, 150.0), (9, 100.0, 160.0), (10, 100.0, 170.0)]
track = {'t': 1000, 'result': 'make', 'hoop': hoop, 'ball': ball6, 'bodd': []}
pred_off, _ = decide_shot(track, switch_fall_through=False)
pred_on, _ = decide_shot(track, switch_fall_through=True)
print(f'Test 6 (make track): off={pred_off}, on={pred_on}')

# Test 7: decide_shot with switch on never turns miss into make
ball7 = [(0, 100.0, 50.0), (1, 100.0, 60.0), (2, 100.0, 70.0)]
track7 = {'t': 1000, 'result': 'miss', 'hoop': hoop, 'ball': ball7, 'bodd': []}
pred7_off, _ = decide_shot(track7, switch_fall_through=False)
pred7_on, _ = decide_shot(track7, switch_fall_through=True)
print(f'Test 7 (miss track): off={pred7_off}, on={pred7_on}')