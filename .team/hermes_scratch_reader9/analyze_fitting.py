import json
import cv2
import numpy as np
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scoreboard_clock_720p import _notus_red_mask

# Load segment geometry
with open(ROOT / 'data/roi/notus_segment_geometry.json') as f:
    seg_geo = json.load(f)

# Load eye-read values
with open(ROOT / '.team/notus_fit_crops/eye_read_values.json') as f:
    eye_data = json.load(f)

# Analyze per-game statistics on fitting frames
game_stats = {'A1': {'crops': 0, 'red_pct': [], 'segments': {}}, 'A': {'crops': 0, 'red_pct': [], 'segments': {}}}

for entry in eye_data['entries']:
    game = entry['game']
    crop_path = ROOT / entry['crop_path']
    digit = entry['digit']
    score = entry['score']
    slot = entry['slot']
    
    img = cv2.imread(str(crop_path))
    if img is None:
        continue
    
    mask = _notus_red_mask(img)
    red_pct = 100 * np.count_nonzero(mask) / mask.size
    game_stats[game]['red_pct'].append(red_pct)
    game_stats[game]['crops'] += 1
    
    h, w = img.shape[:2]
    for seg in 'abcdefg':
        x1, y1, x2, y2 = seg_geo['segments'][seg]
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)
        if px1 >= px2 or py1 >= py2:
            continue
        seg_mask = mask[py1:py2, px1:px2]
        seg_total = seg_mask.size
        seg_red = np.count_nonzero(seg_mask)
        occupancy = seg_red / seg_total if seg_total > 0 else 0
        key = f"{slot}_{seg}"
        if key not in game_stats[game]['segments']:
            game_stats[game]['segments'][key] = []
        game_stats[game]['segments'][key].append(occupancy)

print("=== FITTING FRAMES PER-GAME STATS ===")
for game in ['A1', 'A']:
    s = game_stats[game]
    print(f"\nGame {game}: {s['crops']} crops")
    print(f"  Red %: min={min(s['red_pct']):.1f}, max={max(s['red_pct']):.1f}, mean={np.mean(s['red_pct']):.1f}, median={np.median(s['red_pct']):.1f}")
    
    # Per-slot-segment average occupancy
    for slot in ['home_tens', 'home_ones', 'away_tens', 'away_ones']:
        print(f"  {slot}:")
        for seg in 'abcdefg':
            key = f"{slot}_{seg}"
            if key in s['segments'] and s['segments'][key]:
                vals = s['segments'][key]
                print(f"    {seg}: mean={np.mean(vals):.3f}, median={np.median(vals):.3f}, min={min(vals):.3f}, max={max(vals):.3f}")

# Also check crop sizes per game
print("\n=== CROP SIZES ===")
for entry in eye_data['entries']:
    crop_path = ROOT / entry['crop_path']
    img = cv2.imread(str(crop_path))
    if img:
        h, w = img.shape[:2]
        print(f"  {entry['game']} {entry['slot']}: {w}x{h} (score={entry['score']}, digit={entry['digit']})")