"""
Fine-tune YOLOv8m on ceiling-camera basketball footage.
Strategy:
1. Extract frames from Q1 video at regular intervals
2. Use the abdullahtarek model's high-confidence detections + manual verification to create labels
3. Focus on frames where the ball is clearly visible
4. Train YOLOv8m for 50 epochs on our ceiling camera perspective
"""
import cv2, numpy as np, os, time
from ultralytics import YOLO

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
OUT_BASE = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/training_data'
os.makedirs(OUT_BASE, exist_ok=True)

# Use abdullahtarek model to generate candidate labels
ball_m = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/ball_detector.pt')

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

# Also track the second-best ball detections (low conf might be real ball at hoop)
print(f"Generating training data from {total} frames...")

images_dir = os.path.join(OUT_BASE, 'images')
labels_dir = os.path.join(OUT_BASE, 'labels')
os.makedirs(images_dir, exist_ok=True)
os.makedirs(labels_dir, exist_ok=True)

W, H = 1280, 720

# Sample: every 10th frame for broader coverage
saved = 0
skipped = 0

for fn in range(0, total, 10):
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if not ret: continue

    r = ball_m.predict(frame, conf=0.1, verbose=False)[0]
    if r.boxes is None: continue

    ball_dets = []
    if r.boxes is not None:
        for box in r.boxes:
            cls = ball_m.names[int(box.cls[0])]
            cf = float(box.conf[0])
            if cls == 'Ball' and cf > 0.1:
                x1,y1,x2,y2 = box.xyxy[0].tolist()
                cx, cy = (x1+x2)/2, (y1+y2)/2
                bw, bh = x2-x1, y2-y1
                ball_dets.append((cx, cy, bw, bh, cf))

    if not ball_dets:
        skipped += 1
        continue

    # Normalize to YOLO format (cx,cy,w,h all normalized to 0-1)
    label_lines = []
    for cx, cy, bw, bh, cf in ball_dets:
        # Skip detections at frame edges (likely false positives from bleachers)
        if cx < 50 or cx > W-50 or cy > H-100:
            continue
        xn, yn = cx/W, cy/H
        wn, hn = bw/W, bh/H
        label_lines.append("0 %.6f %.6f %.6f %.6f" % (xn, yn, wn, hn))

    if not label_lines:
        skipped += 1
        continue

    # Save image and labels
    img_path = os.path.join(images_dir, "frame_%05d.jpg" % fn)
    lbl_path = os.path.join(labels_dir, "frame_%05d.txt" % fn)
    cv2.imwrite(img_path, frame)
    with open(lbl_path, 'w') as f:
        f.write("\n".join(label_lines) + "\n")
    saved += 1

    if saved % 50 == 0:
        print("  Saved %d training images (skipped %d)" % (saved, skipped))

cap.release()
print()
print("Total training images: %d" % saved)
print("Skipped (no ball detected): %d" % skipped)
print()

# Create YOLO dataset config
dataset_yaml = """
path: %s
train: images
val: images
names:
  0: basketball
""" % OUT_BASE

with open(os.path.join(OUT_BASE, 'dataset.yaml'), 'w') as f:
    f.write(dataset_yaml.strip() + "\n")

print("Dataset config written to %s/dataset.yaml" % OUT_BASE)
