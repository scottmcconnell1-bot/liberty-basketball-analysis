import json
import cv2
import numpy as np
from pathlib import Path
import sys
sys.path.insert(0, '.')

from scoreboard_clock import _red_mask, _SEGMENT_ON, _SEVEN_SEGMENT, _score_value

ROOT = Path('.')

with open(ROOT / 'data/roi/notus_scoreboard_rois.json') as f:
    rois = json.load(f)

with open(ROOT / 'data/roi/notus_segment_geometry.json') as f:
    seg_data = json.load(f)

geometry = {name: tuple(rect) for name, rect in seg_data['segments'].items()}

# Crops are 1120x640, ROI coords are for 1280x720
# Scale factors
SCALE_X = 1120 / 1280  # 0.875
SCALE_Y = 640 / 720    # 0.888...

def scale_box(box):
    x, y, w, h = box
    return [int(x * SCALE_X), int(y * SCALE_Y), int(w * SCALE_X), int(h * SCALE_Y)]

def _crop(frame, box):
    x, y, w, h = (int(v) for v in box)
    return frame[max(0, y):max(0, y)+h, max(0, x):max(0, x)+w]

def _read_notus_digit(mask):
    height, width = mask.shape[:2]
    lit = ''
    for name, (fx0, fy0, fx1, fy1) in geometry.items():
        sx0 = int(fx0 * width)
        sx1 = max(int(fx1 * width), sx0 + 1)
        sy0 = int(fy0 * height)
        sy1 = max(int(fy1 * height), sy0 + 1)
        cell = mask[sy0:sy1, sx0:sx1]
        if cell.size and float((cell > 0).mean()) >= _SEGMENT_ON:
            lit += name
    if not lit:
        return ''
    return _SEVEN_SEGMENT.get(lit)

with open(ROOT / '.team/specs/04_notus_crop_truth.json') as f:
    truth = json.load(f)

game1_crops = truth['jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334']
game2_crops = truth['jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334']

game1_roi = rois['games']['jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334']
game2_roi = rois['games']['jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334']

# Scale boxes for crop images
g1_h_tens = scale_box(game1_roi['scores']['home']['tens'])
g1_h_ones = scale_box(game1_roi['scores']['home']['ones'])
g1_a_tens = scale_box(game1_roi['scores']['away']['tens'])
g1_a_ones = scale_box(game1_roi['scores']['away']['ones'])

g2_h_tens = scale_box(game2_roi['scores']['home']['tens'])
g2_h_ones = scale_box(game2_roi['scores']['home']['ones'])
g2_a_tens = scale_box(game2_roi['scores']['away']['tens'])
g2_a_ones = scale_box(game2_roi['scores']['away']['ones'])

print(f"Game A1 scaled boxes:")
print(f"  home tens: {g1_h_tens}")
print(f"  home ones: {g1_h_ones}")
print(f"  away tens: {g1_a_tens}")
print(f"  away ones: {g1_a_ones}")

print(f"\nGame A scaled boxes:")
print(f"  home tens: {g2_h_tens}")
print(f"  home ones: {g2_h_ones}")
print(f"  away tens: {g2_a_tens}")
print(f"  away ones: {g2_a_ones}")

crops_dir = ROOT / 'data/roi/notus_crops'

for game_name, crops_dict, h_tens, h_ones, a_tens, a_ones in [
    ('A1', game1_crops, g1_h_tens, g1_h_ones, g1_a_tens, g1_a_ones),
    ('A', game2_crops, g2_h_tens, g2_h_ones, g2_a_tens, g2_a_ones)
]:
    print(f'\n=== Game {game_name} ===')
    for crop_name, (exp_home, exp_away) in crops_dict.items():
        crop_path = crops_dir / f'{crop_name}.png'
        if not crop_path.exists():
            print(f'  {crop_name}: MISSING')
            continue
        
        frame = cv2.imread(str(crop_path))
        if frame is None:
            print(f'  {crop_name}: FAILED TO LOAD')
            continue
        
        h_tens_mask = _red_mask(_crop(frame, h_tens))
        h_ones_mask = _red_mask(_crop(frame, h_ones))
        a_tens_mask = _red_mask(_crop(frame, a_tens))
        a_ones_mask = _red_mask(_crop(frame, a_ones))
        
        h_tens_digit = _read_notus_digit(h_tens_mask)
        h_ones_digit = _read_notus_digit(h_ones_mask)
        a_tens_digit = _read_notus_digit(a_tens_mask)
        a_ones_digit = _read_notus_digit(a_ones_mask)
        
        def build_score(tens, ones):
            if tens == '' and ones == '':
                return None
            if ones == '':
                ones = None
            text = ('?' if tens is None else tens) + ('?' if ones is None else ones)
            return _score_value([text])
        
        got_home = build_score(h_tens_digit, h_ones_digit)
        got_away = build_score(a_tens_digit, a_ones_digit)
        
        status = 'OK' if (got_home == exp_home and got_away == exp_away) else 'FAIL'
        print(f'  {crop_name}: exp=({exp_home},{exp_away}) got=({got_home},{got_away}) {status}')
        
        if got_home != exp_home:
            print(f'    HOME TENS mask pixels: {(h_tens_mask > 0).sum()}')
            print(f'    HOME ONES mask pixels: {(h_ones_mask > 0).sum()}')
            for name, (fx0, fy0, fx1, fy1) in geometry.items():
                for slot_name, mask in [('tens', h_tens_mask), ('ones', h_ones_mask)]:
                    sx0 = int(fx0 * mask.shape[1])
                    sx1 = max(int(fx1 * mask.shape[1]), sx0 + 1)
                    sy0 = int(fy0 * mask.shape[0])
                    sy1 = max(int(fy1 * mask.shape[0]), sy0 + 1)
                    cell = mask[sy0:sy1, sx0:sx1]
                    if cell.size:
                        frac = float((cell > 0).mean())
                        if frac > 0.01:
                            print(f'      {slot_name}.{name}: frac={frac:.4f}')
        
        if got_away != exp_away:
            print(f'    AWAY TENS mask pixels: {(a_tens_mask > 0).sum()}')
            print(f'    AWAY ONES mask pixels: {(a_ones_mask > 0).sum()}')
            for name, (fx0, fy0, fx1, fy1) in geometry.items():
                for slot_name, mask in [('tens', a_tens_mask), ('ones', a_ones_mask)]:
                    sx0 = int(fx0 * mask.shape[1])
                    sx1 = max(int(fx1 * mask.shape[1]), sx0 + 1)
                    sy0 = int(fy0 * mask.shape[0])
                    sy1 = max(int(fy1 * mask.shape[0]), sy0 + 1)
                    cell = mask[sy0:sy1, sx0:sx1]
                    if cell.size:
                        frac = float((cell > 0).mean())
                        if frac > 0.01:
                            print(f'      {slot_name}.{name}: frac={frac:.4f}')