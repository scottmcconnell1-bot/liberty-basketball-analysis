#!/usr/bin/env python3
"""
Create contact sheet with ground truth boxes overlaid on benchmark frames.
Shows positive (green box = GT ball) and negative (no box) frames.
"""
import os, cv2, numpy as np

FRAMES_DIR = 'benchmark/frames'
LABELS_DIR = 'benchmark/labels'
OUT_DIR = 'benchmark'

def draw_gt_boxes(img, gt_boxes):
    """Draw GT boxes in green."""
    h, w = img.shape[:2]
    out = img.copy()
    for box in gt_boxes:
        cx, cy, bw, bh = box
        x1 = int((cx - bw/2) * w)
        y1 = int((cy - bh/2) * h)
        x2 = int((cx + bw/2) * w)
        y2 = int((cy + bh/2) * h)
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(out, 'GT', (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
    return out

# Load GT labels
gt_labels = {}
for f in os.listdir(LABELS_DIR):
    if not f.endswith('.txt'):
        continue
    fname = f.replace('.txt', '.jpg')
    boxes = []
    with open(os.path.join(LABELS_DIR, f)) as fh:
        for line in fh:
            parts = line.strip().split()
            if len(parts) == 5:
                boxes.append(tuple(float(x) for x in parts[1:]))
    gt_labels[fname] = boxes

# Select 10 positive + 10 negative for contact sheet
positive = sorted([f for f, b in gt_labels.items() if len(b) > 0])
negative = sorted([f for f, b in gt_labels.items() if len(b) == 0])

sample_pos = positive[::max(1, len(positive)//10)][:10]
sample_neg = negative[:10]
sample = sample_pos + sample_neg

# Create contact sheet: 5 cols x 4 rows
cols, rows = 5, 4
thumb_w, thumb_h = 256, 144
sheet = np.zeros((rows * (thumb_h + 30), cols * (thumb_w + 5), 3), dtype=np.uint8)

for idx, fname in enumerate(sample):
    fpath = os.path.join(FRAMES_DIR, fname)
    img = cv2.imread(fpath)
    if img is None:
        continue
    
    gt_boxes = gt_labels.get(fname, [])
    thumb = draw_gt_boxes(img, gt_boxes)
    thumb = cv2.resize(thumb, (thumb_w, thumb_h))
    
    r, c = idx // cols, idx % cols
    y_off = r * (thumb_h + 30)
    x_off = c * (thumb_w + 5)
    
    sheet[y_off:y_off+thumb_h, x_off:x_off+thumb_w] = thumb
    
    label = 'POS' if fname in sample_pos else 'NEG'
    color = (0, 255, 0) if label == 'POS' else (128, 128, 128)
    cv2.putText(sheet, label, (x_off+2, y_off+12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    cv2.putText(sheet, fname[:25], (x_off+2, y_off+thumb_h+15), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (200, 200, 200), 1)

cv2.imwrite(os.path.join(OUT_DIR, 'contact_sheet.jpg'), sheet)
print(f'Contact sheet saved to {OUT_DIR}/contact_sheet.jpg ({len(sample)} frames)')
