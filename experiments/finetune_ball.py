"""
Fine-tune abdullahtarek ball detector on our footage.
Use high-confidence YOLO detections that pass color filter as training data.
"""
import cv2, numpy as np, os, shutil, random
from ultralytics import YOLO

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
MODELS = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/models'
OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/ball_finetune'

os.makedirs(OUT + '/images/train', exist_ok=True)
os.makedirs(OUT + '/images/val', exist_ok=True)
os.makedirs(OUT + '/labels/train', exist_ok=True)
os.makedirs(OUT + '/labels/val', exist_ok=True)

# Load v9f raw detections
import pandas as pd
raw = pd.read_csv('/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/v9f_balls_raw.csv')
print("Raw detections: %d" % len(raw))

# Filter: high confidence AND basketball color
cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

training_data = []

for _, r in raw.iterrows():
    if r.conf < 0.5:
        continue

    fn = int(r.frame)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if not ret:
        continue

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Check color at ball center
    cx, cy = int((r.x1+r.x2)/2), int((r.y1+r.y2)/2)
    if 5 <= cx < 1275 and 5 <= cy < 715:
        # Sample region around center
        roi = hsv[cy-3:cy+4, cx-3:cx+4].reshape(-1, 3)
        # Check if majority of pixels are basketball-colored
        orange_mask = (roi[:, 0] >= 3) & (roi[:, 0] <= 28) & (roi[:, 1] > 25)
        orange_frac = np.sum(orange_mask) / len(roi)

        if orange_frac > 0.5:
            # This is likely a real ball
            training_data.append({
                'frame': fn,
                'x1': r.x1, 'y1': r.y1, 'x2': r.x2, 'y2': r.y2,
                'conf': r.conf, 'orange_frac': orange_frac
            })

cap.release()

print("Color-filtered training candidates: %d" % len(training_data))

# Also add some hard negatives (YOLO detected "ball" but it's NOT orange)
# These teach the model what NOT to detect
negatives = []
cap = cv2.VideoCapture(VIDEO)

for _, r in raw.iterrows():
    if r.conf < 0.3 or r.conf >= 0.5:
        continue  # Only medium confidence (ambiguous)

    fn = int(r.frame)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if not ret:
        continue

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    cx, cy = int((r.x1+r.x2)/2), int((r.y1+r.y2)/2)

    if 5 <= cx < 1275 and 5 <= cy < 715:
        roi = hsv[cy-3:cy+4, cx-3:cx+4].reshape(-1, 3)
        orange_mask = (roi[:, 0] >= 3) & (roi[:, 0] <= 28) & (roi[:, 1] > 25)
        orange_frac = np.sum(orange_mask) / len(roi)

        if orange_frac < 0.2:  # NOT a basketball color
            negatives.append({
                'frame': fn,
                'x1': r.x1, 'y1': r.y1, 'x2': r.x2, 'y2': r.y2,
                'conf': r.conf, 'orange_frac': orange_frac
            })

cap.release()

print("Hard negatives: %d" % len(negatives))

# Sample training data — spread across the game
# Take every Nth to get ~100-200 training images
if len(training_data) > 200:
    step = len(training_data) // 200
    training_data = training_data[::step]

if len(negatives) > 100:
    step = len(negatives) // 100
    negatives = negatives[::step]

print("Selected for training: %d positives, %d negatives" % (len(training_data), len(negatives)))

# Split 80/20 train/val
random.seed(42)
random.shuffle(training_data)
split = int(len(training_data) * 0.8)
train_pos = training_data[:split]
val_pos = training_data[split:]

random.shuffle(negatives)
split_n = int(len(negatives) * 0.8)
train_neg = negatives[:split_n]
val_neg = negatives[split_n:]

# Write YOLO format annotations
cap = cv2.VideoCapture(VIDEO)

def write_annotations(data_list, img_dir, label_dir, cap):
    written = 0
    for item in data_list:
        fn = item['frame']

        # Skip if already written
        img_path = '%s/frame_%04d.jpg' % (img_dir, fn)
        lbl_path = '%s/frame_%04d.txt' % (label_dir, fn)

        if os.path.exists(img_path):
            # Just append label (but should be same frame)
            continue

        cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
        ret, frame = cap.read()
        if not ret:
            continue

        h, w = frame.shape[:2]

        # Save image
        cv2.imwrite(img_path, frame)

        # Write YOLO format label
        # Class 0 = Ball (the only class we're adding)
        x_center = ((item['x1'] + item['x2']) / 2) / w
        y_center = ((item['y1'] + item['y2']) / 2) / h
        box_w = (item['x2'] - item['x1']) / w
        box_h = (item['y2'] - item['y1']) / h

        with open(lbl_path, 'w') as f:
            f.write('0 %.6f %.6f %.6f %.6f\n' % (x_center, y_center, box_w, box_h))

        written += 1

    return written

print("Writing training images...")
n_train = write_annotations(train_pos, OUT+'/images/train', OUT+'/labels/train', cap)
n_val = write_annotations(val_pos, OUT+'/images/val', OUT+'/labels/val', cap)

# Also write negative examples (frames with false detections but no ball label)
# Actually, negatives should have NO ball object — just empty label files
for item in train_neg:
    fn = item['frame']
    img_path = '%s/frame_%04d.jpg' % (OUT+'/images/train', fn)
    lbl_path = '%s/frame_%04d.txt' % (OUT+'/labels/train', fn)

    if not os.path.exists(img_path):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
        ret, frame = cap.read()
        if ret:
            cv2.imwrite(img_path, frame)
            open(lbl_path, 'w').close()  # Empty label = no ball

for item in val_neg:
    fn = item['frame']
    img_path = '%s/frame_%04d.jpg' % (OUT+'/images/val', fn)
    lbl_path = '%s/frame_%04d.txt' % (OUT+'/labels/val', fn)

    if not os.path.exists(img_path):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
        ret, frame = cap.read()
        if ret:
            cv2.imwrite(img_path, frame)
            open(lbl_path, 'w').close()

cap.release()

print("Training images: %d" % n_train)
print("Validation images: %d" % n_val)

# Count actual files
train_imgs = len(os.listdir(OUT+'/images/train'))
val_imgs = len(os.listdir(OUT+'/images/val'))
print("Total train images: %d" % train_imgs)
print("Total val images: %d" % val_imgs)

# Create data.yaml for YOLO
yaml = """path: %s
train: images/train
val: images/val

names:
  0: Ball
""" % OUT

with open(OUT + '/data.yaml', 'w') as f:
    f.write(yaml)
print("Created data.yaml")

# Fine-tune YOLO
print("\nStarting fine-tuning...")
model = YOLO(MODELS + '/ball_detector.pt')

results = model.train(
    data=OUT + '/data.yaml',
    epochs=20,
    imgsz=640,
    batch=4,
    device='cpu',
    patience=5,
    save=True,
    project=OUT + '/runs',
    name='finetune',
    pretrained=True,
    optimizer='AdamW',
    lr0=0.0001,
    augment=True,
    mosaic=0.5,
    flipud=0.0,  # Don't flip vertically — ball is always upright
    fliplr=0.5,
    scale=0.2,
    shear=5,
    degrees=5,
)

print("\nFine-tuning complete!")
print("Best weights:", results.save_dir + '/weights/best.pt')
