"""
Shot detection v4c: Efficient single-pass.
Court keypoints + ball detection + frame differencing.
"""
import cv2, numpy as np, pickle, time
import pandas as pd
from ultralytics import YOLO

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

print("Loading models...")
court_model = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/court_keypoint_detector.pt')
ball_model = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/ball_detector.pt')

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print("Total frames: %d" % total)

kp_arr = np.full((total, 18, 2), np.nan)
ball_cx = np.full(total, np.nan)
ball_cy = np.full(total, np.nan)
motion_raw = np.zeros(total)

prev_gray = None
fn = 0
start = time.time()

while True:
    ret, frame = cap.read()
    if not ret or fn >= total:
        break

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Court keypoints every 10 frames
    if fn % 10 == 0:
        r = court_model.predict(frame, conf=0.3, verbose=False)[0]
        if r.keypoints is not None and len(r.keypoints) > 0:
            kp_arr[fn] = r.keypoints[0].xy.cpu().numpy()[0]

    # Ball detection every 5 frames
    if fn % 5 == 0:
        r = ball_model.predict(frame, conf=0.15, verbose=False)[0]
        if r.boxes is not None:
            best_conf = 0
            best_box = None
            for box in r.boxes:
                cls = ball_model.names[int(box.cls[0])]
                cf = float(box.conf[0])
                if cls == 'Ball' and cf > best_conf:
                    best_conf = cf
                    best_box = box
            if best_box is not None:
                x1, y1, x2, y2 = best_box.xyxy[0].tolist()
                ball_cx[fn] = (x1+x2)/2
                ball_cy[fn] = (y1+y2)/2

    # Frame differencing (every frame)
    if prev_gray is not None:
        diff = cv2.absdiff(prev_gray, gray)
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        motion_raw[fn] = np.sum(thresh > 0)

    prev_gray = gray
    fn += 1
    if fn % 500 == 0:
        elapsed = time.time() - start
        print("  %d/%d, %.1f fps, %d ball det" % (fn, total, fn/elapsed if elapsed>0 else 0, int(np.sum(~np.isnan(ball_cx)))))

cap.release()
print("Detection: %.1f sec" % (time.time()-start))

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

# ---- Interpolate ball ----
print("Interpolating ball...")
for i in range(1, total):
    if np.isnan(ball_cx[i]) and not np.isnan(ball_cx[i-1]):
        ball_cx[i] = ball_cx[i-1]
        ball_cy[i] = ball_cy[i-1]
for i in range(total-2, -1, -1):
    if np.isnan(ball_cx[i]) and not np.isnan(ball_cx[i+1]):
        ball_cx[i] = ball_cx[i+1]
        ball_cy[i] = ball_cy[i+1]

ball_detected = ~np.isnan(ball_cx)
print("Ball: %d/%d frames (%.1f%%)" % (int(np.sum(ball_detected)), total, np.sum(ball_detected)/total*100))

# ---- Keypoint positions ----
print("\nKeypoint positions:")
for kp in range(18):
    v = ~np.isnan(kp_arr[:, kp, 0])
    if np.sum(v) > 10:
        print("  KP%2d: N=%d x=%.0f±%.0f y=%.0f±%.0f" % (
            kp, int(np.sum(v)),
            np.nanmean(kp_arr[v,kp,0]), np.nanstd(kp_arr[v,kp,0]),
            np.nanmean(kp_arr[v,kp,1]), np.nanstd(kp_arr[v,kp,1])))

# ---- Basket position from keypoints ----
# Use two most stable keypoints near the basket area
# KP6, KP7 are typically at the backboard area
# Compute basket midpoint from multiple baseline keypoints
# Determine which keypoints are at the "ends" of the court
kp_means = []
for kp in range(18):
    v = ~np.isnan(kp_arr[:, kp, 0])
    if np.sum(v) > total * 0.5:
        kp_means.append((kp, np.nanmean(kp_arr[v, kp, 0]), np.nanmean(kp_arr[v, kp, 1])))

kp_means.sort(key=lambda x: x[1])  # sort by X
print("\nKPs sorted by X:")
for kp, cx, cy in kp_means:
    print("  KP%2d: (%.0f, %.0f)" % (kp, cx, cy))

# Use the two groups of keypoints at each end as baskets
left_kps = [k[0] for k in kp_means[:4]]
right_kps = [k[0] for k in kp_means[-4:]]
print("\nLeft basket KPs:", left_kps)
print("Right basket KPs:", right_kps)

# Compute basket position as mean of basket keypoints per frame
basket_left_x = np.nanmean(np.stack([kp_arr[:, kp, 0] for kp in left_kps], axis=1), axis=1)
basket_left_y = np.nanmean(np.stack([kp_arr[:, kp, 1] for kp in left_kps], axis=1), axis=1)
basket_right_x = np.nanmean(np.stack([kp_arr[:, kp, 0] for kp in right_kps], axis=1), axis=1)
basket_right_y = np.nanmean(np.stack([kp_arr[:, kp, 1] for kp in right_kps], axis=1), axis=1)

# ---- Ball-to-basket distance ----
dist_left = np.full(total, np.nan)
dist_right = np.full(total, np.nan)
for i in range(total):
    if not np.isnan(ball_cx[i]):
        if not np.isnan(basket_left_x[i]):
            dist_left[i] = np.sqrt((ball_cx[i]-basket_left_x[i])**2 + (ball_cy[i]-basket_left_y[i])**2)
        if not np.isnan(basket_right_x[i]):
            dist_right[i] = np.sqrt((ball_cx[i]-basket_right_x[i])**2 + (ball_cy[i]-basket_right_y[i])**2)

dist_to_basket = np.nanmin(np.stack([dist_left, dist_right], axis=1), axis=1)

print("\nBall-basket distance (when ball detected):")
v = ~np.isnan(dist_to_basket)
if np.sum(v) > 0:
    for pct in [10, 25, 50, 75, 90]:
        print("  %dth pctl: %.0fpx" % (pct, np.nanpercentile(dist_to_basket, pct)))

# ---- Motion normalization ----
print("\nMotion analysis...")
# Rolling average to account for camera window = 30
kernel = np.ones(30) / 30
motion_bg = np.convolve(motion_raw, kernel, mode='same')
motion_spike = motion_raw - motion_bg

# ---- Shot detection ----
print("\n=== SHOT CANDIDATES ===")

# Find local minima in ball-basket distance (ball closest to basket)
# These are the "closest approach" = potential shot release or ball-at-rim
from scipy.signal import find_peaks

# Invert distance to find minima as peaks
inv_dist = -dist_to_basket
inv_dist[np.isnan(inv_dist)] = 0

# Find peaks in inverted distance = closest approaches
peak_indices, peak_props = find_peaks(inv_dist, distance=20, height=-200)

print("Closest ball-basket approaches: %d" % len(peak_indices))
for pi in peak_indices[:20]:
    which = "left" if dist_left[pi] < dist_right[pi] else "right"
    print("  F%d: dist=%.0fpx (%s basket) motion_spike=%.0f" % (
        pi, dist_to_basket[pi], which, motion_spike[pi]))

# Filter: only close approaches (< 150px from basket)
close_approaches = [pi for pi in peak_indices if dist_to_basket[pi] < 150]
print("\nClose approaches (<150px): %d" % len(close_approaches))
for pi in close_approaches:
    which = "left" if dist_left[pi] < dist_right[pi] else "right"
    print("  F%d: dist=%.0fpx (%s)" % (pi, dist_to_basket[pi], which))

# ---- Also: ball disappearance near basket = shot in flight ----
print("\n=== GAP-BASED SHOTS ===")
gap_shots = []
for fn in range(20, total):
    if ball_detected[fn]: continue  # ball visible

    # Find last ball detection
    last_fn = None
    for prev in range(fn-1, max(0, fn-40), -1):
        if ball_detected[prev]:
            last_fn = prev
            break
    if last_fn is None: continue

    gap = fn - last_fn
    if gap < 3 or gap > 35: continue

    # Check: was ball near basket at last detection?
    if not np.isnan(dist_to_basket[last_fn]) and dist_to_basket[last_fn] < 150:
        gap_shots.append({
            'frame': last_fn,
            'gap_size': gap,
            'dist_at_departure': dist_to_basket[last_fn],
            'which_basket': 'left' if dist_left[last_fn] < dist_right[last_fn] else 'right'
        })

print("Gap-based shots: %d" % len(gap_shots))
for gs in gap_shots:
    print("  F%d: gap=%d dist=%.0fpx (%s)" % (
        gs['frame'], gs['gap_size'], gs['dist_at_departure'], gs['which_basket']))

# ---- Combine all ----
print("\n=== ALL SHOT CANDIDATES ===")
all_candidates = set()
for pi in close_approaches:
    all_candidates.add(pi)
for gs in gap_shots:
    all_candidates.add(gs['frame'])

# Add motion spike peaks as additional candidates
motion_peaks, _ = find_peaks(motion_spike, distance=30, height=np.percentile(motion_spike, 97))
for mp in motion_peaks:
    # Only add if ball was nearby in preceding frames
    for bf in range(max(0, mp-15), mp):
        if not np.isnan(dist_to_basket[bf]) and dist_to_basket[bf] < 250:
            all_candidates.add(mp)
            break

# Deduplicate
all_candidates = sorted(all_candidates)
deduped = []
i = 0
while i < len(all_candidates):
    j = i + 1
    while j < len(all_candidates) and all_candidates[j] - all_candidates[j-1] < 30:
        j += 1
    group = all_candidates[i:j]
    # Pick frame with minimum ball-basket distance
    best = min(group, key=lambda f: dist_to_basket[f] if not np.isnan(dist_to_basket[f]) else 9999)
    deduped.append(best)
    i = j

print("Final shot candidates: %d" % len(deduped))
for fn in deduped:
    d = dist_to_basket[fn]
    ms = motion_spike[fn]
    bx = ball_cx[fn] if not np.isnan(ball_cx[fn]) else 'N/A'
    by = ball_cy[fn] if not np.isnan(ball_cy[fn]) else 'N/A'
    wb = 'left' if dist_left[fn] < dist_right[fn] else 'right' if not np.isnan(dist_to_basket[fn]) else '?'
    print("  F%d: dist=%s basket=%s motion=%.0f cursor=(%s,%s)" % (
        fn, "%.0fpx"%d if not np.isnan(d) else 'N/A', wb, ms, bx, by))

# Save
results = {
    'candidates': deduped,
    'close_approaches': close_approaches,
    'gap_shots': gap_shots,
    'ball_cx': ball_cx, 'ball_cy': ball_cy,
    'dist_to_basket': dist_to_basket,
    'motion_spike': motion_spike,
    'basket_left': (basket_left_x, basket_left_y),
    'basket_right': (basket_right_x, basket_right_y),
    'kp_arr': kp_arr,
}
with open(OUT + '/shot_v4.pkl', 'wb') as f:
    pickle.dump(results, f)

pd.DataFrame([{
    'frame': fn,
    'ball_basket_dist': round(float(dist_to_basket[fn]), 1) if not np.isnan(dist_to_basket[fn]) else None,
    'motion_spike': round(float(motion_spike[fn]), 1),
    'which': 'left' if dist_left[fn] < dist_right[fn] else 'right' if not np.isnan(dist_to_basket[fn]) else '?',
    'ball_x': round(float(ball_cx[fn]), 1) if not np.isnan(ball_cx[fn]) else None,
    'ball_y': round(float(ball_cy[fn]), 1) if not np.isnan(ball_cy[fn]) else None,
} for fn in deduped]).to_csv(OUT + '/shot_candidates_v4.csv', index=False)

print("\nDONE")
