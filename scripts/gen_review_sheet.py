#!/usr/bin/env python3
"""Generate review package for new_candidates with confidence >= 0.60."""

import os
import csv
from PIL import Image, ImageDraw, ImageFont

REVIEW_DIR = "new_candidates/review"
CONTACT_SHEET_PATH = os.path.join(REVIEW_DIR, "review_sheet_01.png")
ZOOMED_DIR = os.path.join(REVIEW_DIR, "zoomed_crops")
IMAGES_DIR = "new_candidates/images"
LABELS_DIR = "new_candidates/labels"

os.makedirs(ZOOMED_DIR, exist_ok=True)

# Load manifest
rows = []
with open(os.path.join(REVIEW_DIR, "review_manifest.csv")) as f:
    reader = csv.DictReader(f)
    for row in reader:
        rows.append(row)

rows.sort(key=lambda r: -float(r['confidence']))

COLS = 10
ROWS = 4
THUMB_W, THUMB_H = 200, 150
PAD = 10
LABEL_H = 20

total_w = COLS * (THUMB_W + PAD) + PAD
total_h = ROWS * (THUMB_H + LABEL_H + PAD) + PAD

sheet = Image.new('RGB', (total_w, total_h), color=(30, 30, 30))
draw = ImageDraw.Draw(sheet)

try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
except:
    font = ImageFont.load_default()

zoom_count = 0

for idx, row in enumerate(rows):
    filename = row['filename']
    conf = float(row['confidence'])
    cand_id = filename.replace('.jpg', '')

    img_path = os.path.join(IMAGES_DIR, filename)
    label_path = os.path.join(LABELS_DIR, f"{cand_id}.txt")

    if not os.path.exists(img_path):
        print(f"MISSING: {img_path}")
        continue

    img = Image.open(img_path)
    iw, ih = img.size

    # Parse YOLO box
    box_px = None
    if os.path.exists(label_path):
        with open(label_path) as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 5:
                    _, cx, cy, bw, bh = [float(p) for p in parts]
                    x1 = int((cx - bw/2) * iw)
                    y1 = int((cy - bh/2) * ih)
                    x2 = int((cx + bw/2) * iw)
                    y2 = int((cy + bh/2) * ih)
                    box_px = (x1, y1, x2, y2)
                    break

    # Draw box on full image copy
    box_img = img.copy()
    if box_px:
        d = ImageDraw.Draw(box_img)
        d.rectangle(box_px, outline=(0, 255, 0), width=max(2, iw // 200))

    # Resize to thumbnail and place on sheet
    thumb = box_img.resize((THUMB_W, THUMB_H))
    col = idx % COLS
    row_idx = idx // COLS
    x = PAD + col * (THUMB_W + PAD)
    y = PAD + row_idx * (THUMB_H + LABEL_H + PAD)
    sheet.paste(thumb, (x, y))

    # Label
    label_text = f"{cand_id[:14]} c={conf:.2f}"
    draw.text((x, y + THUMB_H + 2), label_text, fill=(200, 200, 200), font=font)

    # Save zoomed crop around detection
    if box_px:
        x1, y1, x2, y2 = box_px
        margin = int(max(x2-x1, y2-y1) * 0.5)
        cx, cy = (x1+x2)//2, (y1+y2)//2
        crop = img.crop((
            max(0, cx - margin),
            max(0, cy - margin),
            min(iw, cx + margin),
            min(ih, cy + margin)
        ))
        crop.save(os.path.join(ZOOMED_DIR, f"{cand_id}_zoom.jpg"))
        zoom_count += 1

sheet.save(CONTACT_SHEET_PATH)
print(f"Contact sheet: {CONTACT_SHEET_PATH} ({total_w}x{total_h})")
print(f"Zoomed crops: {zoom_count} files in {ZOOMED_DIR}/")
