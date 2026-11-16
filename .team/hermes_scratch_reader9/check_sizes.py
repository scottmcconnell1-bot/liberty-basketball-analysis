import json
import cv2
import numpy as np
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scoreboard_clock_720p import _notus_red_mask

with open(ROOT / 'data/roi/notus_segment_geometry.json') as f:
    seg_geo = json.load(f)

with open(ROOT / '.team/notus_fit_crops/eye_read_values.json') as f:
    eye_data = json.load(f)

# Check crop sizes per game/slot
sizes = {}
for entry in eye_data['entries']:
    crop_path = ROOT / entry['crop_path']
    img = cv2.imread(str(crop_path))
    if img is not None:
        h, w = img.shape[:2]
        key = f"{entry['game']}_{entry['slot']}"
        if key not in sizes:
            sizes[key] = []
        sizes[key].append((w, h))

for key, vals in sizes.items():
    ws = [v[0] for v in vals]
    hs = [v[1] for v in vals]
    print(f"  {key}: w={min(ws)}-{max(ws)} (mode={max(set(ws), key=ws.count)}), h={min(hs)}-{max(hs)} (mode={max(set(hs), key=hs.count)})")