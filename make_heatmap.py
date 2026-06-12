import pickle, os, numpy as np
import cv2
from matplotlib import pyplot as plt

base = '/home/monk-admin/PROJECTS/liberty-basketball-analysis'
pkl_path = os.path.join(base, 'pipeline_output/shot_v14.pkl')
clip_path = os.path.join(base, 'videos/nfhs_4K_gam021ddbf1cf.mp4')

with open(pkl_path, 'rb') as f:
    data = pickle.load(f)

bx = data['ball_x']
by = data['ball_y']

cap = cv2.VideoCapture(clip_path)
cap.set(cv2.CAP_PROP_POS_FRAMES, 500)
ret, frame = cap.read()
cap.release()
h, w = frame.shape[:2]
print(f"Frame size: {w}x{h}")

# Heatmap
heatmap = np.zeros((h, w), dtype=np.float32)
for i in range(len(bx)):
    if not np.isnan(bx[i]) and not np.isnan(by[i]):
        px, py = int(bx[i]), int(by[i])
        if 0 <= px < w and 0 <= py < h:
            cv2.circle(heatmap, (px, py), 30, 1.0, -1)

heatmap = cv2.GaussianBlur(heatmap, (91, 91), 25)
if heatmap.max() > 0:
    heatmap = heatmap / heatmap.max()

frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
hm_uint8 = (heatmap * 255).astype(np.uint8)
hm_color = cv2.applyColorMap(hm_uint8, cv2.COLORMAP_JET)
hm_rgb = cv2.cvtColor(hm_color, cv2.COLOR_BGR2RGB)
overlay = (0.6 * frame_rgb + 0.4 * hm_rgb).clip(0, 255).astype(np.uint8)

fig, ax = plt.subplots(1, 1, figsize=(16, 9))
ax.imshow(overlay)
ax.set_title(f'v14 Detection Heatmap (2700 frames, {np.sum(~np.isnan(bx))} detections)')
ax.axis('off')
out = os.path.join(base, 'pipeline_output/detection_heatmap.png')
fig.savefig(out, dpi=150, bbox_inches='tight')
plt.close()
print(f"Heatmap saved: {out}")

# Scatter
fig, ax = plt.subplots(1, 1, figsize=(16, 9))
ax.imshow(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
valid = ~np.isnan(bx)
ax.scatter(bx[valid], by[valid], c='red', s=8, alpha=0.4, label=f'Detections ({valid.sum()})')
ax.set_title('v14 Detections on Frame 500')
ax.set_xlim(0, w)
ax.set_ylim(h, 0)
ax.legend()
out2 = os.path.join(base, 'pipeline_output/detection_scatter.png')
fig.savefig(out2, dpi=150, bbox_inches='tight')
plt.close()
print(f"Scatter saved: {out2}")

# Distributions
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
ax1.hist(by[valid], bins=50, color='red', alpha=0.7)
ax1.set_xlabel('Y pixel'); ax1.set_ylabel('Count')
ax1.set_title('Y-coordinate Distribution')
ax1.axvline(by[valid].mean(), color='black', linestyle='--')
ax1.legend([f'Mean={by[valid].mean():.1f}'])
ax2.hist(bx[valid], bins=50, color='blue', alpha=0.7)
ax2.set_xlabel('X pixel'); ax2.set_ylabel('Count')
ax2.set_title('X-coordinate Distribution')
ax2.axvline(bx[valid].mean(), color='black', linestyle='--')
ax2.legend([f'Mean={bx[valid].mean():.1f}'])
out3 = os.path.join(base, 'pipeline_output/detection_distributions.png')
fig.savefig(out3, dpi=150, bbox_inches='tight')
plt.close()
print(f"Distributions saved: {out3}")

# Heatmap peak
my, mx = np.unravel_index(heatmap.argmax(), heatmap.shape)
print(f"\nDetection stats:")
print(f"  Total frames: {len(bx)}")
print(f"  Valid detections: {valid.sum()}")
print(f"  X range: [{bx[valid].min():.0f}, {bx[valid].max():.0f}], std={bx[valid].std():.1f}")
print(f"  Y range: [{by[valid].min():.0f}, {by[valid].max():.0f}], std={by[valid].std():.1f}")
print(f"  Heatmap peak: ({mx}, {my})")

# Grid analysis
cells = {}
for i in range(len(bx)):
    if not np.isnan(bx[i]) and not np.isnan(by[i]):
        cx = int(bx[i]) // 100 * 100
        cy = int(by[i]) // 100 * 100
        cell = (cx, cy)
        cells[cell] = cells.get(cell, 0) + 1

sorted_cells = sorted(cells.items(), key=lambda x: -x[1])
total = sum(cells.values())
print(f"\nTop 15 100px grid cells:")
for (cx, cy), cnt in sorted_cells[:15]:
    print(f"  ({cx},{cy}): {cnt} ({cnt/total*100:.1f}%)")

# Also check if the "shots" list has higher-confidence entries with frame positions
shots = data.get('shots', [])
print(f"\nShot-level detections: {len(shots)}")
for s in shots[:5]:
    print(f"  {s}")
