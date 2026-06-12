"""
Audit top-20 v14 detections: classify what's at each detection point
by analyzing the actual pixel content in a region around (x,y).
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

# Basket positions (approximate from v14 data)
basket_left_x, basket_left_y = 260.9, 566.5
basket_right_x, basket_right_y = 691.3, 448.6

results = []

for i, s in enumerate(top20, 1):
    frame_num = s['frame']
    bx, by = s['bx'], s['by']
    conf = s['conf']
    
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, frame = cap.read()
    if not ret:
        results.append({'#': i, 'frame': frame_num, 'conf': conf, 'x': bx, 'y': by, 'error': 'frame read failed'})
        continue
    
    h, w = frame.shape[:2]
    
    # Extract ROI around detection point (20x20 region)
    roi_size = 20
    x1 = max(0, int(bx - roi_size))
    y1 = max(0, int(by - roi_size))
    x2 = min(w, int(bx + roi_size))
    y2 = min(h, int(by + roi_size))
    
    if x2 <= x1 or y2 <= y1:
        results.append({'#': i, 'frame': frame_num, 'conf': conf, 'x': bx, 'y': by, 'error': 'invalid ROI'})
        continue
    
    roi = frame[y1:y2, x1:x2]
    
    # Convert to HSV
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mean_hsv = np.mean(hsv.reshape(-1, 3), axis=0)
    std_hsv = np.std(hsv.reshape(-1, 3), axis=0)
    
    # Convert to grayscale for texture analysis
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    mean_gray = np.mean(gray)
    std_gray = np.std(gray)
    
    # Check if detection is near either basket
    dist_left = np.sqrt((bx - basket_left_x)**2 + (by - basket_left_y)**2)
    dist_right = np.sqrt((bx - basket_right_x)**2 + (by - basket_right_y)**2)
    min_basket_dist = min(dist_left, dist_right)
    
    # Location analysis - where in the frame?
    x_pct = bx / w * 100
    y_pct = by / h * 100
    
    # Edge density (rim/backboard = high edges)
    edges = cv2.Canny(gray, 50, 150)
    edge_density = np.sum(edges > 0) / edges.size
    
    # Color checks
    mean_bgr = np.mean(roi.reshape(-1, 3), axis=0)
    
    result = {
        '#': i,
        'frame': frame_num,
        'conf': conf,
        'x': round(bx, 1),
        'y': round(by, 1),
        'x_pct': round(x_pct, 1),
        'y_pct': round(y_pct, 1),
        'mean_H': round(mean_hsv[0], 1),
        'mean_S': round(mean_hsv[1], 1),
        'mean_V': round(mean_hsv[2], 1),
        'std_H': round(std_hsv[0], 1),
        'mean_gray': round(mean_gray, 1),
        'std_gray': round(std_gray, 1),
        'edge_density': round(edge_density, 3),
        'dist_nearest_basket': round(min_basket_dist, 1),
        'mean_R': round(mean_bgr[2], 1),
        'mean_G': round(mean_bgr[1], 1),
        'mean_B': round(mean_bgr[0], 1),
    }
    results.append(result)

cap.release()

# Print results as a table
print(f"{'#':<4} {'Frame':<8} {'Conf':<14} {'X':<8} {'Y':<8} {'X%':<6} {'Y%':<6} {'H':<6} {'S':<6} {'V':<6} {'Gray':<6} {'Edge':<6} {'BkDist':<8}")
for r in results:
    if 'error' in r:
        print(f"{r['#']:<4} {r['frame']:<8} {r['conf']:<14} ERROR: {r['error']}")
    else:
        print(f"{r['#']:<4} {r['frame']:<8} {r['conf']:<14.10f} {r['x']:<8} {r['y']:<8} {r['x_pct']:<6} {r['y_pct']:<6} {r['mean_H']:<6} {r['mean_S']:<6} {r['mean_V']:<6} {r['mean_gray']:<6} {r['edge_density']:<6} {r['dist_nearest_basket']:<8}")

print("\n\n=== CLASSIFICATION GUIDE ===")
print("Orange/brown detection (H~5-20, S>100) + low edge = likely BASKETBALL")
print("Near basket (<100px) + high edge = likely RIM/BACKBOARD")  
print("Center court area + low saturation = likely COURT MARKING")
print("Blue region (H~100-120) + high saturation = likely PLAYER JERSEY")
print("Low saturation + high value + low edge = likely FLOOR REFLECTION")

print("\n\n=== AUTO-CLASSIFICATION ATTEMPT ===")
for r in results:
    if 'error' in r:
        print(f"#{r['Frame']}: ERROR")
        continue
    
    reasons = []
    classification = "Unknown"
    audit_conf = "Low"
    
    h, s, v = r['mean_H'], r['mean_S'], r['mean_V']
    edge = r['edge_density']
    bkdist = r['dist_nearest_basket']
    gray = r['mean_gray']
    
    # Basketball: orange-brown color (H 5-25 in OpenCV), moderate-high saturation, low-moderate edge density
    is_orange = (3 <= h <= 25) and s > 80
    is_brown = (h <= 15) and (40 < s <= 120) and v < 150
    
    # Rim: near basket, high edge density, metallic/gray color
    is_near_basket = bkdist < 120
    is_high_edge = edge > 0.15
    is_gray_metallic = s < 60 and gray > 80
    
    # Court marking: center area, low saturation uniform region
    is_center = 30 < r['x_pct'] < 70 and 30 < r['y_pct'] < 70
    is_low_sat = s < 40
    
    # Player jersey: blue (H~100-120), high saturation
    is_blue = 90 <= h <= 130 and s > 80
    
    # Floor reflection: high value, low saturation, low edge
    is_reflection = v > 180 and s < 50 and edge < 0.1
    
    scores = {
        'Basketball': 0,
        'Rim/backboard': 0,
        'Court marking/logo': 0,
        'Player/jersey': 0,
        'Floor reflection': 0,
    }
    
    if is_orange or is_brown:
        scores['Basketball'] += 2
    if is_orange:
        scores['Basketball'] += 1
    if is_near_basket and is_high_edge:
        scores['Rim/backboard'] += 2
    if is_near_basket and is_gray_metallic:
        scores['Rim/backboard'] += 1
    if is_center and is_low_sat:
        scores['Court marking/logo'] += 2
    if is_blue:
        scores['Player/jersey'] += 3
    if is_reflection:
        scores['Floor reflection'] += 2
    if edge > 0.2 and is_near_basket:
        scores['Rim/backboard'] += 1
    # Basketballs are round and small - check if gray is moderate (not too bright/dark)
    if 60 < gray < 180 and (is_orange or is_brown):
        scores['Basketball'] += 1
    
    # Pick highest score
    best = max(scores, key=scores.get)
    if scores[best] >= 3:
        classification = best
        audit_conf = "Medium"
    elif scores[best] >= 2:
        classification = best
        audit_conf = "Low"
    else:
        classification = "Other"
        audit_conf = "Low"
    
    print(f"#{r['#']} F{r['Frame']}: {classification} ({audit_conf}) - H={h} S={s} V={v} Edge={edge:.3f} BkDist={bkdist:.0f} Gray={gray}")
