#!/usr/bin/env python3
"""
Fast detector audit using existing v14 detections.
1. Heatmap from v14 pickle (instant — no inference needed)
2. Top-20 frames from v14 with highest confidences, visualized
"""
import os, pickle, cv2
import numpy as np

OUT_DIR = 'pipeline_output/detector_audit'
os.makedirs(OUT_DIR, exist_ok=True)

# === Part 1: Heatmap from existing v14 data ===
with open('pipeline_output/shot_v14.pkl', 'rb') as f:
    data = pickle.load(f)

bc_x = data['ball_x']
bc_y = data['ball_y']
dist = data['dist']
detected = ~np.isnan(bc_x)
bx_all = bc_x[detected]
by_all = bc_y[detected]
dist_all = dist[detected]

print(f"v14 detections: {len(bx_all)} frames")

# Load corresponding confidence from the ball detections list
# The pickle has ball_x, ball_y per frame but confidence was stored separately
# Let's get it from the shots list
shots = data['shots']
print(f"v14 shots: {len(shots)}")

# Build heatmap (1280x720 canvas for the Q1 webm)
heatmap = np.zeros((720, 1280), dtype=np.float32)
for x, y in zip(bx_all.astype(int), by_all.astype(int)):
    if 0 <= x < 1280 and 0 <= y < 720:
        cv2.circle(heatmap, (x, int(y)), 20, 1, -1)

# Gaussian blur
heatmap_blur = cv2.GaussianBlur(heatmap, (61, 61), 0)
if heatmap_blur.max() > 0:
    heatmap_blur = heatmap_blur / heatmap_blur.max()

# Colorize
heatmap_uint8 = (heatmap_blur * 255).astype(np.uint8)
heatmap_color = cv2.applyColorMap(heatmap_uint8, cv2.COLORMAP_JET)

# Blend with background frame
cap = cv2.VideoCapture('uploads/Liberty_Vs_Riverstone_Q1.webm')
ret, bg = cap.read()
cap.release()

if ret:
    bg_small = cv2.resize(bg, (1280, 720))
    bg_gray = cv2.cvtColor(bg_small, cv2.COLOR_BGR2GRAY)
    bg_rgb = cv2.cvtColor(bg_gray, cv2.COLOR_GRAY2BGR)
    blended = cv2.addWeighted(bg_rgb, 0.4, heatmap_color, 0.6, 0)
else:
    blended = heatmap_color

# Mark basket positions
blx_mean = np.nanmean(data['basket_left'][0])
bly_mean = np.nanmean(data['basket_left'][1])
brx_mean = np.nanmean(data['basket_right'][0])
bry_mean = np.nanmean(data['basket_right'][1])
cv2.circle(blended, (int(blx_mean), int(bly_mean)), 15, (255, 255, 255), 3)
cv2.circle(blended, (int(brx_mean), int(bry_mean)), 15, (255, 255, 255), 3)
cv2.putText(blended, 'L', (int(blx_mean)-5, int(bly_mean)-20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)
cv2.putText(blended, 'R', (int(brx_mean)-5, int(bry_mean)-20), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)

cv2.imwrite(f'{OUT_DIR}/detection_heatmap.jpg', blended)
cv2.imwrite(f'{OUT_DIR}/detection_heatmap_raw.jpg', heatmap_color)
print("Heatmap saved")

# === Part 2: Top-20 from v14 ===
# Sort shots by... we don't have per-frame conf in the ball arrays
# But we DO have the shot list with confidence
shots_sorted = sorted(shots, key=lambda s: s['conf'], reverse=True)

print(f"\n=== TOP 20 SHOTS BY CONFIDENCE (from v14) ===")
cap = cv2.VideoCapture('uploads/Liberty_Vs_Riverstone_Q1.webm')

for rank, s in enumerate(shots_sorted[:20]):
    fn = s['frame']
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if not ret:
        continue
    
    # Draw ball position
    bx_i, by_i = int(s['bx']), int(s['by'])
    cv2.circle(frame, (bx_i, by_i), 15, (0, 255, 0), 3)
    cv2.drawMarker(frame, (bx_i, by_i), (0, 0, 255), cv2.MARKER_CROSS, 25, 2)
    
    # Draw basket
    cv2.circle(frame, (int(blx_mean), int(bly_mean)), 10, (255, 255, 255), 2)
    cv2.circle(frame, (int(brx_mean), int(bry_mean)), 10, (255, 255, 255), 2)
    
    cv2.putText(frame, f"#{rank+1} conf={s['conf']:.6f} {s['type']} {s['result']}", (10, 30),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(frame, f"F{fn} dist={s['dist']:.0f}px", (10, 60),
               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    
    cv2.imwrite(f'{OUT_DIR}/top20_{rank+1:02d}_f{fn:04d}_conf{s["conf"]:.6f}.jpg', frame)
    
    print(f"  #{rank+1}: F{fn:4d} conf={s['conf']:.6f} {s['type']:3s} {s['result']:4s} d={s['dist']:5.1f}px ({bx_i},{by_i})")

cap.release()

# Also create a contact sheet of top 20
print("\nCreating contact sheet...")
cols, rows = 5, 4
thumb_w, thumb_h = 256, 144
sheet = np.zeros((rows * (thumb_h + 25), cols * (thumb_w + 5), 3), dtype=np.uint8)

cap = cv2.VideoCapture('uploads/Liberty_Vs_Riverstone_Q1.webm')
for rank, s in enumerate(shots_sorted[:20]):
    fn = s['frame']
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if not ret:
        continue
    
    thumb = cv2.resize(frame, (thumb_w, thumb_h))
    r, c = rank // cols, rank % cols
    y_off = r * (thumb_h + 25)
    x_off = c * (thumb_w + 5)
    
    # Draw mini marker
    bx_s = int(s['bx'] * thumb_w / 1280)
    by_s = int(s['by'] * thumb_h / 720)
    cv2.drawMarker(thumb, (bx_s, by_s), (0, 255, 0), cv2.MARKER_CROSS, 15, 2)
    
    sheet[y_off:y_off+thumb_h, x_off:x_off+thumb_w] = thumb
    cv2.putText(sheet, f"#{rank+1} c={s['conf']:.4f}", (x_off+2, y_off+12),
               cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

cap.release()
cv2.imwrite(f'{OUT_DIR}/top20_contact_sheet.jpg', sheet)
print("Contact sheet saved")

# === Part 3: Distribution stats ===
print(f"\n=== DISTANCE DISTRIBUTION ===")
d = dist_all[~np.isnan(dist_all)]
print(f"Total: {len(d)}")
print(f"< 50px (near basket): {(d < 50).sum()} ({(d<50).sum()/len(d)*100:.1f}%)")
print(f"50-150px (shooting range): {((d>=50)&(d<150)).sum()} ({((d>=50)&(d<150)).sum()/len(d)*100:.1f}%)")
print(f"150-300px (mid-range): {((d>=150)&(d<300)).sum()} ({((d>=150)&(d<300)).sum()/len(d)*100:.1f}%)")
print(f"> 300px (far): {(d >= 300).sum()} ({(d>=300).sum()/len(d)*100:.1f}%)")

print(f"\nCenter of mass of all detections: ({bx_all.mean():.0f}, {by_all.mean():.0f})")
print(f"Std: ({bx_all.std():.0f}, {by_all.std():.0f})")
print(f"Basket positions: L=({blx_mean:.0f},{bly_mean:.0f}) R=({brx_mean:.0f},{bry_mean:.0f})")

# Are detections concentrated near center or spread across court?
court_center_x, court_center_y = 590, 335  # center of 1280x720
print(f"Court center: ({court_center_x}, {court_center_y})")
print(f"Mean detection dist from court center: {np.mean(np.sqrt((bx_all-court_center_x)**2 + (by_all-court_center_y)**2)):.0f}px")

print(f"\nAll audit files saved to {OUT_DIR}/")
