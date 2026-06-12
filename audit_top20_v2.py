"""
Audit top-20 v14 detections using pixel analysis + spatial reasoning.
Classify each detection based on HSV color, edge density, basket proximity, and position.
"""
import cv2
import numpy as np
import pickle

# Load v14 data
with open('/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl', 'rb') as f:
    v14 = pickle.load(f)

shots = v14['shots']
shots.sort(key=lambda s: s['conf'], reverse=True)
top20 = shots[:20]

# Load the 720p video
video_path = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
cap = cv2.VideoCapture(video_path)

# Basket positions (approximate median from v14 data)
basket_left = (260.9, 566.5)
basket_right = (691.3, 448.6)

results = []

for i, s in enumerate(top20, 1):
    frame_num = s['frame']
    bx, by = s['bx'], s['by']
    conf = s['conf']
    
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, frame = cap.read()
    if not ret:
        results.append({'idx': i, 'frame': frame_num, 'conf': conf, 'x': bx, 'y': by, 'error': 'frame read failed'})
        continue
    
    h_frame, w_frame = frame.shape[:2]
    
    # Extract 30x30 ROI around detection
    roi_size = 30
    x1 = max(0, int(bx - roi_size))
    y1 = max(0, int(by - roi_size))
    x2 = min(w_frame, int(bx + roi_size))
    y2 = min(h_frame, int(by + roi_size))
    
    if x2 <= x1 or y2 <= y1:
        results.append({'idx': i, 'frame': frame_num, 'conf': conf, 'x': bx, 'y': by, 'error': 'invalid ROI'})
        continue
    
    roi = frame[y1:y2, x1:x2]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    
    # Statistics
    h_vals = hsv[:,:,0].flatten().astype(float)
    s_vals = hsv[:,:,1].flatten().astype(float)
    v_vals = hsv[:,:,2].flatten().astype(float)
    
    mean_h = np.mean(h_vals)
    mean_s = np.mean(s_vals)
    mean_v = np.mean(v_vals)
    median_h = np.median(h_vals)
    pct_orange = np.sum((h_vals >= 5) & (h_vals <= 25) & (s_vals > 60)) / len(h_vals) * 100
    
    mean_gray = np.mean(gray)
    std_gray = np.std(gray)
    
    # Edge density
    edges = cv2.Canny(gray, 30, 100)
    edge_pct = np.sum(edges > 0) / edges.size
    
    # Position analysis
    x_pct = bx / w_frame * 100
    y_pct = by / h_frame * 100
    
    # Distance to baskets
    d_left = np.sqrt((bx - basket_left[0])**2 + (by - basket_left[1])**2)
    d_right = np.sqrt((bx - basket_right[0])**2 + (by - basket_right[1])**2)
    d_basket = min(d_left, d_right)
    
    # Court zone
    # 720p frame: x=0 is left, x=1280 is right, y=0 is top, y=720 is bottom
    # Left basket at ~x=260, right basket at ~x=690
    # Center court ~x=640
    is_left_side = bx < 480
    is_right_side = bx > 800
    is_center_x = 400 <= bx <= 800
    is_bottom_half = y_pct > 60
    
    results.append({
        'idx': i,
        'frame': frame_num,
        'conf': conf,
        'x': round(bx, 1),
        'y': round(by, 1),
        'x_pct': round(x_pct, 1),
        'y_pct': round(y_pct, 1),
        'mean_h': round(mean_h, 1),
        'median_h': round(median_h, 1),
        'mean_s': round(mean_s, 1),
        'mean_v': round(mean_v, 1),
        'pct_orange': round(pct_orange, 1),
        'edge_pct': round(edge_pct, 3),
        'd_basket': round(d_basket, 1),
        'mean_gray': round(mean_gray, 1),
        'std_gray': round(std_gray, 1),
        'is_left': is_left_side,
        'is_right': is_right_side,
        'is_center_x': is_center_x,
        'is_bottom': is_bottom_half,
    })

cap.release()

# Classification logic
print("=" * 120)
print("TOP-20 v14 DETECTION AUDIT")
print("=" * 120)
print()

basketball_count = 0
rim_count = 0
court_count = 0
player_count = 0
reflection_count = 0
other_count = 0

for r in results:
    if 'error' in r:
        print(f"#{r['idx']:>2} F{r['frame']:>5} | ERROR: {r['error']}")
        continue
    
    h = r['mean_h']
    s = r['mean_s']
    v = r['mean_v']
    edge = r['edge_pct']
    d_b = r['d_basket']
    orange_pct = r['pct_orange']
    
    scores = {
        'Basketball': 0,
        'Rim/backboard': 0,
        'Court marking/logo': 0,
        'Player/jersey': 0,
        'Floor reflection': 0,
        'Other': 0,
    }
    
    # Basketball: dominant orange hue (H 5-25), saturation >40, not gray, roundish
    if 5 <= h <= 25 and s > 40:
        scores['Basketball'] += 2
    if orange_pct > 30:
        scores['Basketball'] += 2
    if orange_pct > 15:
        scores['Basketball'] += 1
    # Basketballs are small, dark-ish orange-brown
    if 5 <= h <= 20 and 30 < s < 120 and 60 < v < 160:
        scores['Basketball'] += 1
    
    # Rim/backboard: very close to basket, higher edges
    if d_b < 50:
        scores['Rim/backboard'] += 3
    elif d_b < 100:
        scores['Rim/backboard'] += 2
    elif d_b < 150:
        scores['Rim/backboard'] += 1
    if d_b < 150 and edge > 0.1:
        scores['Rim/backboard'] += 1
    # Rim is metallic/silver - low saturation, moderate-high value
    if d_b < 200 and s < 50 and 60 < v < 180:
        scores['Rim/backboard'] += 1
    
    # Court marking: center area, very low saturation (floor is brown/gray)
    if r['is_center_x'] and s < 35:
        scores['Court marking/logo'] += 2
    if r['is_center_x'] and 20 < h < 40 and s < 40:
        scores['Court marking/logo'] += 1
    
    # Player jersey: blue hue range
    if 95 <= h <= 125 and s > 50:
        scores['Player/jersey'] += 3
    
    # Floor reflection: very bright, very low saturation
    if v > 180 and s < 40:
        scores['Floor reflection'] += 3
    elif v > 160 and s < 30:
        scores['Floor reflection'] += 2
    
    # Resolve ties with position heuristics
    best = max(scores, key=scores.get)
    best_score = scores[best]
    
    # If no strong signal, mark as Other
    if best_score < 2:
        best = "Other"
    
    # Determine audit confidence
    if best_score >= 4:
        audit_conf = "High"
    elif best_score >= 2:
        audit_conf = "Medium"
    else:
        audit_conf = "Low"
    
    # Tally
    if 'Basketball' in best: basketball_count += 1
    elif 'Rim' in best: rim_count += 1
    elif 'Court' in best: court_count += 1
    elif 'Player' in best: player_count += 1
    elif 'reflection' in best: reflection_count += 1
    else: other_count += 1
    
    print(f"#{r['idx']:>2} | F{r['frame']:>5} | conf={r['conf']:.6f} | "
          f"({r['x']:>6.1f},{r['y']:>5.1f}) | "
          f"H={r['mean_h']:>5.1f} S={r['mean_s']:>5.1f} V={r['mean_v']:>5.1f} | "
          f"Orng%={r['pct_orange']:>5.1f} | "
          f"Edge={r['edge_pct']:.3f} | dBask={r['d_basket']:>6.0f} | "
          f"Gray={r['mean_gray']:>5.1f} | "
          f"=> {best} ({audit_conf})")

print()
print("=" * 120)
print("AUDIT SUMMARY")
print("=" * 120)
print(f"  Basketball:      {basketball_count}")
print(f"  Rim/backboard:   {rim_count}")
print(f"  Court marking:   {court_count}")
print(f"  Player/jersey:   {player_count}")
print(f"  Floor reflection:{reflection_count}")
print(f"  Other:           {other_count}")
print(f"  TOTAL:           {len(results)}")
