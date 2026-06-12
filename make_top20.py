"""Create top-20 contact sheet: highest-confidence detections with bounding boxes."""
import pickle, os, numpy as np
import cv2
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle

base = '/home/monk-admin/PROJECTS/liberty-basketball-analysis'
pkl_path = os.path.join(base, 'pipeline_output/shot_v14.pkl')
clip_path = os.path.join(base, 'videos/nfhs_4K_gam021ddbf1cf.mp4')

with open(pkl_path, 'rb') as f:
    data = pickle.load(f)

shots = data['shots']  # 26 shot-level detections
print(f"Total shots: {len(shots)}")

# Sort by confidence descending
shots_sorted = sorted(shots, key=lambda s: -s['conf'])
top20 = shots_sorted[:20]

# Extract frames and create contact sheet
cap = cv2.VideoCapture(clip_path)
h, w = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)), int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))

ncols = 5
nrows = 4
fig, axes = plt.subplots(nrows, ncols, figsize=(20, 16))
fig.suptitle('Top 20 Highest-Confidence v14 Detections', fontsize=16, fontweight='bold')

for idx, (ax, shot) in enumerate(zip(axes.flat, top20)):
    frame_num = shot['frame']
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, frame = cap.read()
    if not ret:
        ax.set_title(f'Frame {frame_num}: READ ERROR')
        continue
    
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    ax.imshow(frame_rgb)
    
    # Draw detection point
    bx, by = shot['bx'], shot['by']
    ax.plot(bx, by, 'g+', markersize=15, mew=2)
    circle = plt.Circle((bx, by), 20, fill=False, color='lime', linewidth=2)
    ax.add_patch(circle)
    
    # Label
    title = f"#{idx+1} F{frame_num}\nconf={shot['conf']:.4f}\n({bx:.0f},{by:.0f})"
    ax.set_title(title, fontsize=9)
    ax.axis('off')

# Hide unused axes
for idx in range(len(top20), nrows*ncols):
    axes.flat[idx].axis('off')

cap.release()
out = os.path.join(base, 'pipeline_output/top20_contact_sheet.png')
fig.savefig(out, dpi=150, bbox_inches='tight')
plt.close()
print(f"Contact sheet saved: {out}")

# Also print the top 20 data
print("\nTop 20 detections:")
for i, s in enumerate(top20):
    print(f"  #{i+1}: frame={s['frame']}, conf={s['conf']:.5f}, pos=({s['bx']:.0f},{s['by']:.0f}), dist={s['dist']:.0f}px, type={s['type']}")
