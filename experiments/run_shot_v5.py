"""
Shot detection v5: Uses fine-tuned ball detector + court keypoints.
Two-pass approach:
  Pass 1: Detect court keypoints (every 10 frames) + ball (every frame, fine-tuned model)
  Pass 2: Analyze ball trajectories near baskets for shot detection
"""
import cv2, numpy as np, pickle, time, os
import pandas as pd
from ultralytics import YOLO
from scipy.signal import find_peaks

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'
MODELS = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/models'

# Use fine-tuned model if available, otherwise fallback
FINE_TUNED = OUT + '/runs/finetune/weights/best.pt'
if os.path.exists(FINE_TUNED):
    BALL_MODEL = FINE_TUNED
    print("Using fine-tuned model")
else:
    BALL_MODEL = MODELS + '/ball_detector.pt'
    print("Using pretrained model")

COURT_MODEL = MODELS + '/court_keypoint_detector.pt'

print("Loading models...")
ball_m = YOLO(BALL_MODEL)
court_m = YOLO(COURT_MODEL)

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print("Total frames: %d" % total)

# Arrays
ball_cx = np.full(total, np.nan)
ball_cy = np.full(total, np.nan)
ball_conf = np.zeros(total)
kp_arr = np.full((total, 18, 2), np.nan)
motion = np.zeros(total)

prev_gray = None
fn = 0
start = time.time()

while True:
    ret, frame = cap.read()
    if not ret or fn >= total:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Ball detection every frame (fine-tuned model should be more accurate)
    r = ball_m.predict(frame, conf=0.15, verbose=False)[0]
    if r.boxes is not None:
        best_conf = 0
        best_box = None
        for box in r.boxes:
            cls = ball_m.names[int(box.cls[0])]
            cf = float(box.conf[0])
            if cls == 'Ball' and cf > best_conf:
                best_conf = cf
                best_box = box
        if best_box is not None:
            x1, y1, x2, y2 = best_box.xyxy[0].tolist()
            ball_cx[fn] = (x1+x2)/2
            ball_cy[fn] = (y1+y2)/2
            ball_conf[fn] = best_conf

    # Court keypoints every 10 frames
    if fn % 10 == 0:
        r = court_m.predict(frame, conf=0.3, verbose=False)[0]
        if r.keypoints is not None and len(r.keypoints) > 0:
            kp_arr[fn] = r.keypoints[0].xy.cpu().numpy()[0]

    # Frame differencing
    if prev_gray is not None:
        diff = cv2.absdiff(prev_gray, gray)
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        motion[fn] = np.sum(thresh > 0)

    prev_gray = gray
    fn += 1
    if fn % 500 == 0:
        elapsed = time.time() - start
        nb = int(np.sum(~np.isnan(ball_cx)))
        print("  %d/%d, %.1f fps, %d ball det" % (fn, total, fn/elapsed if elapsed>0 else 0, nb))

cap.release()
det_time = time.time() - start
print("Detection: %.1f sec, %d ball detections" % (det_time, int(np.sum(~np.isnan(ball_cx)))))

# ---- Interpolate keypoints ----
print("Interpolating keypoints...")
for kp in range(18):
    last = np.array([np.nan, np.nan])
    for i in range(total):
        if not np.isnan(kp_arr[i, kp, 0]): last = kp_arr[i, kp].copy()
        elif not np.isnan(last[0]): kp_arr[i, kp] = last
    last = np.array([np.nan, np.nan])
    for i in range(total-1, -1, -1):
        if not np.isnan(kp_arr[i, kp, 0]): last = kp_arr[i, kp].copy()
        elif not np.isnan(last[0]): kp_arr[i, kp] = last

# ---- Basket position ----
# Use KP4 (far right, stable) and KP5 (far left, stable) as basket indicators
# Actually, let's use the two most extreme X keypoints
kp_means = []
for kp in range(18):
    v = ~np.isnan(kp_arr[:, kp, 0])
    if np.sum(v) > total * 0.5:
        kp_means.append((kp, np.nanmean(kp_arr[v, kp, 0]), np.nanmean(kp_arr[v, kp, 1])))

kp_means.sort(key=lambda x: x[1])
left_kps = [k[0] for k in kp_means[:4]]
right_kps = [k[0] for k in kp_means[-4:]]

basket_left_x = np.nanmean(np.stack([kp_arr[:, kp, 0] for kp in left_kps], axis=1), axis=1)
basket_left_y = np.nanmean(np.stack([kp_arr[:, kp, 1] for kp in left_kps], axis=1), axis=1)
basket_right_x = np.nanmean(np.stack([kp_arr[:, kp, 0] for kp in right_kps], axis=1), axis=1)
basket_right_y = np.nanmean(np.stack([kp_arr[:, kp, 1] for kp in right_kps], axis=1), axis=1)

# ---- Ball-basket distance ----
dist_left = np.full(total, np.nan)
dist_right = np.full(total, np.nan)
for i in range(total):
    if not np.isnan(ball_cx[i]):
        if not np.isnan(basket_left_x[i]):
            dist_left[i] = np.sqrt((ball_cx[i]-basket_left_x[i])**2 + (ball_cy[i]-basket_left_y[i])**2)
        if not np.isnan(basket_right_x[i]):
            dist_right[i] = np.sqrt((ball_cx[i]-basket_right_x[i])**2 + (ball_cy[i]-basket_right_y[i])**2)

dist_to_basket = np.nanmin(np.stack([dist_left, dist_right], axis=1), axis=1)

# ---- Motion spike ----
kernel = np.ones(30) / 30
motion_bg = np.convolve(motion, kernel, mode='same')
motion_spike = motion - motion_bg

# ---- SHOT DETECTION ----
print("\n=== SHOT DETECTION ===")

# Method 1: Closest ball-basket approaches with color verification
print("\nMethod 1: Ball-basket proximity")
cap = cv2.VideoCapture(VIDEO)

# Find local minima in distance
inv_dist = -dist_to_basket.copy()
inv_dist[np.isnan(inv_dist)] = 0
peak_indices, _ = find_peaks(inv_dist, distance=15, height=-200)

# Filter: must have orange color AND be within 120px
color_verified = []
for pi in peak_indices:
    if dist_to_basket[pi] > 120:
        continue

    cap.set(cv2.CAP_PROP_POS_FRAMES, pi)
    ret, frame = cap.read()
    if not ret:
        continue

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    bx, by = int(ball_cx[pi]), int(ball_cy[pi])
    if 0 <= bx < 1280 and 0 <= by < 720:
        pixel_hsv = hsv[by, bx]
        if pixel_hsv[0] < 30 and pixel_hsv[1] > 15:
            color_verified.append(pi)

print("Color-verified close approaches: %d" % len(color_verified))
for pi in color_verified:
    print("  F%4d: dist=%.0fpx conf=%.3f" % (pi, dist_to_basket[pi], ball_conf[pi]))

# Method 2: Gap-based (ball disappears near basket)
print("\nMethod 2: Gap-based shots")
ball_detected = ~np.isnan(ball_cx)
gap_shots = []

for fn in range(20, total):
    if ball_detected[fn]:
        continue

    last_fn = None
    for prev in range(fn-1, max(0, fn-40), -1):
        if ball_detected[prev]:
            last_fn = prev
            break
    if last_fn is None:
        continue

    gap = fn - last_fn
    if gap < 3 or gap > 35:
        continue

    if not np.isnan(dist_to_basket[last_fn]) and dist_to_basket[last_fn] < 150:
        # Verify color at departure
        cap.set(cv2.CAP_PROP_POS_FRAMES, last_fn)
        ret, frame = cap.read()
        if ret:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            bx, by = int(ball_cx[last_fn]), int(ball_cy[last_fn])
            if 0 <= bx < 1280 and 0 <= by < 720:
                pixel_hsv = hsv[by, bx]
                if pixel_hsv[0] < 30 and pixel_hsv[1] > 15:
                    gap_shots.append(last_fn)

print("Gap-based shots: %d" % len(gap_shots))
for gs in gap_shots:
    print("  F%4d: dist=%.0fpx gap follows" % (gs, dist_to_basket[gs]))

cap.release()

# ---- Combine and deduplicate ----
print("\n=== COMBINED SHOT CANDIDATES ===")
all_candidates = sorted(set(color_verified + gap_shots))

# Deduplicate within 30 frames
deduped = []
i = 0
while i < len(all_candidates):
    j = i + 1
    while j < len(all_candidates) and all_candidates[j] - all_candidates[j-1] < 30:
        j += 1
    group = all_candidates[i:j]
    # Pick frame with minimum distance to basket
    best = min(group, key=lambda f: dist_to_basket[f] if not np.isnan(dist_to_basket[f]) else 9999)
    deduped.append(best)
    i = j

print("Final shot candidates: %d" % len(deduped))
for fn in deduped:
    d = dist_to_basket[fn]
    ms = motion_spike[fn]
    bc = ball_conf[fn]
    bx = ball_cx[fn]
    by = ball_cy[fn]
    wb = 'left' if dist_left[fn] < dist_right[fn] else 'right' if not np.isnan(dist_to_basket[fn]) else '?'
    print("  F%4d: dist=%.0fpx conf=%.3f motion=%.0f basket=%s cursor=(%.0f,%.0f)" % (
        fn, d if not np.isnan(d) else -1, bc, ms, wb, bx if not np.isnan(bx) else -1, by if not np.isnan(by) else -1))

# Save
results = {
    'candidates': deduped,
    'ball_cx': ball_cx, 'ball_cy': ball_cy, 'ball_conf': ball_conf,
    'dist_to_basket': dist_to_basket, 'dist_left': dist_left, 'dist_right': dist_right,
    'motion_spike': motion_spike,
    'basket_left': (basket_left_x, basket_left_y),
    'basket_right': (basket_right_x, basket_right_y),
    'kp_arr': kp_arr,
}
with open(OUT + '/shot_v5.pkl', 'wb') as f:
    pickle.dump(results, f)

pd.DataFrame([{
    'frame': fn,
    'ball_basket_dist': round(float(dist_to_basket[fn]), 1) if not np.isnan(dist_to_basket[fn]) else None,
    'ball_conf': round(float(ball_conf[fn]), 3),
    'motion_spike': round(float(motion_spike[fn]), 1),
    'which_basket': 'left' if dist_left[fn] < dist_right[fn] else 'right' if not np.isnan(dist_to_basket[fn]) else '?',
    'ball_x': round(float(ball_cx[fn]), 1) if not np.isnan(ball_cx[fn]) else None,
    'ball_y': round(float(ball_cy[fn]), 1) if not np.isnan(ball_cy[fn]) else None,
} for fn in deduped]).to_csv(OUT + '/shot_candidates_v5.csv', index=False)

print("\nDONE. Saved shot_v5.pkl and shot_candidates_v5.csv")
