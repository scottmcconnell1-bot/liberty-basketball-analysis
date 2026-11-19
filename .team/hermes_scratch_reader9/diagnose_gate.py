import json
import cv2
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent

with open(ROOT / 'data/roi/notus_segment_geometry.json') as f:
    seg_geo = json.load(f)

with open(ROOT / '.team/reader_run2_FAILED/notus_red_thresholds.json') as f:
    thresholds = json.load(f)

# Load ROI to know crop boxes
with open(ROOT / 'data/roi/notus_scoreboard_rois.json') as f:
    roi = json.load(f)

# Truth
with open(ROOT / '.team/specs/04_notus_crop_truth.json') as f:
    truth = json.load(f)

h_min = thresholds['h_min']
h_max = thresholds['h_max']
s_min = thresholds['s_min']
v_min = thresholds['v_min']

print(f"Thresholds: h in [{h_min}..{h_max}] (wrap), s>={s_min}, v>={v_min}")

# SEVEN_SEGMENT mapping from scoreboard_clock_720p.py
SEVEN_SEGMENT = {
    0: "abcef", 1: "bc", 2: "abged", 3: "abgcd", 4: "fgbc",
    5: "afgcd", 6: "afgecd", 7: "abc", 8: "abcdefg", 9: "abfgcd"
}

def notus_red_mask(crop):
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    if h_min <= h_max:
        mask = cv2.inRange(hsv, (h_min, s_min, v_min), (h_max, 255, 255))
    else:
        low = cv2.inRange(hsv, (0, s_min, v_min), (h_max, 255, 255))
        high = cv2.inRange(hsv, (h_min, s_min, v_min), (179, 255, 255))
        mask = cv2.bitwise_or(low, high)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

def analyze_crop(crop_path, game_id, slot_name):
    """Analyze a single crop and print segment occupancy"""
    crop = cv2.imread(str(crop_path))
    if crop is None:
        print(f"  Failed to load {crop_path}")
        return
    
    h, w = crop.shape[:2]
    print(f"  Crop size: {w}x{h}")
    
    mask = notus_red_mask(crop)
    total_pixels = w * h
    red_pixels = np.count_nonzero(mask)
    print(f"  Red pixels: {red_pixels}/{total_pixels} ({100*red_pixels/total_pixels:.1f}%)")
    
    # Get segment regions in pixel coordinates
    segments_px = {}
    for seg, (x1, y1, x2, y2) in seg_geo['segments'].items():
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)
        segments_px[seg] = (px1, py1, px2, py2)
    
    # Check each segment
    for seg in 'abcdefg':
        px1, py1, px2, py2 = segments_px[seg]
        if px1 >= px2 or py1 >= py2:
            continue
        seg_mask = mask[py1:py2, px1:px2]
        seg_total = seg_mask.size
        seg_red = np.count_nonzero(seg_mask)
        occupancy = seg_red / seg_total if seg_total > 0 else 0
        print(f"    {seg}: {seg_red}/{seg_total} = {occupancy:.3f} ({px2-px1}x{py2-py1} @ {px1},{py1})")
    
    # Try to read digit
    on_segs = []
    for seg in 'abcdefg':
        px1, py1, px2, py2 = segments_px[seg]
        if px1 >= px2 or py1 >= py2:
            continue
        seg_mask = mask[py1:py2, px1:px2]
        seg_total = seg_mask.size
        seg_red = np.count_nonzero(seg_mask)
        occupancy = seg_red / seg_total if seg_total > 0 else 0
        if occupancy >= 0.12:  # _SEGMENT_ON threshold
            on_segs.append(seg)
    
    on_str = ''.join(sorted(on_segs))
    digit = None
    for d, pattern in SEVEN_SEGMENT.items():
        if ''.join(sorted(pattern)) == on_str:
            digit = d
            break
    
    print(f"  ON segments: {on_str} -> digit: {digit}")
    return digit, on_str

# Process all gate crops
crop_dir = ROOT / 'data/roi/notus_crops'
crops = sorted(crop_dir.glob('*.png'))

print("=" * 60)
print("GATE CROP ANALYSIS")
print("=" * 60)

for crop_path in crops:
    name = crop_path.stem
    print(f"\n{crop_path.name}:")
    
    # Parse game and timestamp
    if 'A1' in name:
        game_key = 'jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334'
    else:
        game_key = 'jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334'
    
    # Determine slot from crop name
    # The crops are full scoreboard crops, not individual digit crops
    # We need to extract each digit region
    
    crop = cv2.imread(str(crop_path))
    if crop is None:
        continue
    
    game_roi = roi['games'][game_key]
    
    # Extract each digit region
    for side in ['home', 'away']:
        for pos in ['tens', 'ones']:
            box = game_roi['scores'][side][pos]
            x, y, w, h = box
            digit_crop = crop[y:y+h, x:x+w]
            
            # Get expected digit from truth
            truth_key = f"notus_{'A1' if 'A1' in name else 'A'}_{name.split('_')[2]}_{name.split('_')[3].replace('s','')}"
            # Actually let's parse properly
            # notus_A1_00_202s -> game A1, index 00, time 202s
            parts = name.split('_')
            game_str = parts[1]  # A1 or A
            idx = parts[2]       # 00-09
            time_str = parts[3].replace('s', '')  # 202
            
            truth_game_key = f"jrhigh_notus_LIBERTY_H_v_NOTUS_{game_str}_20260809_221334"
            truth_crop_key = f"notus_{game_str}_{idx}_{time_str}s"
            
            if truth_game_key in truth and truth_crop_key in truth[truth_game_key]:
                exp_home, exp_away = truth[truth_game_key][truth_crop_key]
                exp_digit = exp_home if side == 'home' else exp_away
            else:
                exp_digit = None
            
            # Only analyze if we have expected digit
            if exp_digit is not None:
                print(f"  {side}_{pos} (exp={exp_digit}): box={box}")
                digit, on_str = analyze_crop(digit_crop, game_key, f"{side}_{pos}")
                if digit != exp_digit:
                    print(f"    *** MISMATCH: got {digit}, expected {exp_digit} ***")