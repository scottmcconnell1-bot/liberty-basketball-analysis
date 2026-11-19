import json
import cv2
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent

with open(ROOT / '.team/specs/04_notus_crop_truth.json') as f:
    truth = json.load(f)

with open(ROOT / 'data/roi/notus_segment_geometry.json') as f:
    seg_geo = json.load(f)

with open(ROOT / '.team/reader_run2_FAILED/notus_red_thresholds.json') as f:
    thresholds = json.load(f)

print('Thresholds:', thresholds)
print()
print('Segment geometry (normalized 0-1):')
for seg, coords in seg_geo['segments'].items():
    print(f'  {seg}: {coords}')

crop_dir = ROOT / 'data/roi/notus_crops'
crops = sorted(crop_dir.glob('*.png'))
print(f'Total gate crops: {len(crops)}')
for c in crops:
    print(f'  {c.name}')

# Segment pixels for different crop sizes
print()
print('--- Segment pixels for A1 tens (25x29) ---')
w, h = 25, 29
for seg, (x1, y1, x2, y2) in seg_geo['segments'].items():
    px1, py1 = int(x1 * w), int(y1 * h)
    px2, py2 = int(x2 * w), int(y2 * h)
    print(f'  {seg}: ({px1},{py1}) -> ({px2},{py2}) size={px2-px1}x{py2-py1}')

print()
print('--- Segment pixels for A1 ones (26x30) ---')
w, h = 26, 30
for seg, (x1, y1, x2, y2) in seg_geo['segments'].items():
    px1, py1 = int(x1 * w), int(y1 * h)
    px2, py2 = int(x2 * w), int(y2 * h)
    print(f'  {seg}: ({px1},{py1}) -> ({px2},{py2}) size={px2-px1}x{py2-py1}')

print()
print('--- Segment pixels for A tens (22x28) ---')
w, h = 22, 28
for seg, (x1, y1, x2, y2) in seg_geo['segments'].items():
    px1, py1 = int(x1 * w), int(y1 * h)
    px2, py2 = int(x2 * w), int(y2 * h)
    print(f'  {seg}: ({px1},{py1}) -> ({px2},{py2}) size={px2-px1}x{py2-py1}')

print()
print('--- Segment pixels for A ones (23x29) ---')
w, h = 23, 29
for seg, (x1, y1, x2, y2) in seg_geo['segments'].items():
    px1, py1 = int(x1 * w), int(y1 * h)
    px2, py2 = int(x2 * w), int(y2 * h)
    print(f'  {seg}: ({px1},{py1}) -> ({px2},{py2}) size={px2-px1}x{py2-py1}')