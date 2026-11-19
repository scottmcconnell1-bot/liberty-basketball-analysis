import json
import cv2
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent

with open(ROOT / 'data/roi/notus_segment_geometry.json') as f:
    seg_geo = json.load(f)

with open(ROOT / '.team/reader_run2_FAILED/notus_red_thresholds.json') as f:
    thresholds = json.load(f)

with open(ROOT / 'data/roi/notus_scoreboard_rois.json') as f:
    roi = json.load(f)

with open(ROOT / '.team/specs/04_notus_crop_truth.json') as f:
    truth = json.load(f)

h_min = thresholds['h_min']
h_max = thresholds['h_max']
s_min = thresholds['s_min']
v_min = thresholds['v_min']

print(f"Thresholds: h in [{h_min}..{h_max}] (wrap), s>={s_min}, v>={v_min}")

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

def analyze_digit_crop(digit_crop, label):
    """Analyze a single digit crop and return (digit, on_segments_str)"""
    if digit_crop is None or digit_crop.size == 0:
        print(f"  {label}: empty crop")
        return None, ""
    
    h, w = digit_crop.shape[:2]
    mask = notus_red_mask(digit_crop)
    total_pixels = w * h
    red_pixels = np.count_nonzero(mask)
    
    # Get segment regions in pixel coordinates
    segments_px = {}
    for seg, (x1, y1, x2, y2) in seg_geo['segments'].items():
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)
        segments_px[seg] = (px1, py1, px2, py2)
    
    # Check each segment
    on_segs = []
    for seg in 'abcdefg':
        px1, py1, px2, py2 = segments_px[seg]
        if px1 >= px2 or py1 >= py2:
            continue
        seg_mask = mask[py1:py2, px1:px2]
        seg_total = seg_mask.size
        seg_red = np.count_nonzero(seg_mask)
        occupancy = seg_red / seg_total if seg_total > 0 else 0
        if occupancy >= 0.12:
            on_segs.append(seg)
    
    on_str = ''.join(sorted(on_segs))
    digit = None
    for d, pattern in SEVEN_SEGMENT.items():
        if ''.join(sorted(pattern)) == on_str:
            digit = d
            break
    
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
        game_str = 'A1'
    else:
        game_key = 'jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334'
        game_str = 'A'
    
    parts = name.split('_')
    idx = parts[2]
    time_str = parts[3].replace('s', '')
    
    truth_game_key = f"jrhigh_notus_LIBERTY_H_v_NOTUS_{game_str}_20260809_221334"
    truth_crop_key = f"notus_{game_str}_{idx}_{time_str}s"
    
    if truth_game_key not in truth or truth_crop_key not in truth[truth_game_key]:
        print(f"  No truth for {truth_crop_key}")
        continue
    
    exp_home, exp_away = truth[truth_game_key][truth_crop_key]
    
    # Load full crop
    full_crop = cv2.imread(str(crop_path))
    if full_crop is None:
        print(f"  Failed to load {crop_path}")
        continue
    
    game_roi = roi['games'][game_key]
    
    for side, exp_digit in [('home', exp_home), ('away', exp_away)]:
        for pos in ['tens', 'ones']:
            box = game_roi['scores'][side][pos]
            x, y, w, h = box
            digit_crop = full_crop[y:y+h, x:x+w]
            
            digit, on_str = analyze_digit_crop(digit_crop, f"{side}_{pos}")
            
            status = "✓" if digit == exp_digit else "✗" if digit is not None else "None"
            print(f"  {side}_{pos} (exp={exp_digit}): got={digit} on={on_str} {status}")
            
            if digit != exp_digit:
                # Detailed segment analysis
                h_c, w_c = digit_crop.shape[:2]
                mask = notus_red_mask(digit_crop)
                print(f"    Crop: {w_c}x{h_c}, red={np.count_nonzero(mask)}/{w_c*h_c} ({100*np.count_nonzero(mask)/(w_c*h_c):.1f}%)")
                for seg in 'abcdefg':
                    x1, y1, x2, y2 = seg_geo['segments'][seg]
                    px1, py1 = int(x1 * w_c), int(y1 * h_c)
                    px2, py2 = int(x2 * w_c), int(y2 * h_c)
                    if px1 >= px2 or py1 >= py2:
                        continue
                    seg_mask = mask[py1:py2, px1:px2]
                    seg_total = seg_mask.size
                    seg_red = np.count_nonzero(seg_mask)
                    occupancy = seg_red / seg_total if seg_total > 0 else 0
                    marker = " *" if occupancy >= 0.12 else ""
                    print(f"    {seg}: {occupancy:.3f} ({seg_red}/{seg_total}) {marker}")