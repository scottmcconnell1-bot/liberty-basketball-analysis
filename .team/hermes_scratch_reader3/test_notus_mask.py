import cv2
import numpy as np
from pathlib import Path
import sys
sys.path.insert(0, '.')

from scoreboard_clock_720p import _read_notus_digit, _read_score, _load_segment_geometry

ROOT = Path('.')
video_path = ROOT / 'uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4'

cap = cv2.VideoCapture(str(video_path))
fps = cap.get(cv2.CAP_PROP_FPS)

# Notus-specific mask
def _notus_red_mask(crop: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    # Warm colors: red (0-12, 165-180) + orange/yellow (12-30)
    # Lower saturation and value thresholds
    low1 = cv2.inRange(hsv, (0, 30, 30), (30, 255, 255))
    high = cv2.inRange(hsv, (150, 30, 30), (180, 255, 255))
    mask = cv2.bitwise_or(low1, high)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

# Test on all gate timestamps for Game A1
timestamps_ms = [201900, 605700, 1009500, 1413300, 1817100, 2220900, 2624700, 3028500, 3432300, 3836100]

g1_h_tens = [1031, 614, 25, 29]
g1_h_ones = [1057, 613, 26, 30]
g1_a_tens = [1197, 613, 26, 30]
g1_a_ones = [1223, 613, 26, 30]

cells = {
    "home": {"tens": g1_h_tens, "ones": g1_h_ones},
    "away": {"tens": g1_a_tens, "ones": g1_a_ones}
}

expected = {
    201900: (0, 4),
    605700: (2, 11),
    1009500: (4, 11),
    1413300: (5, 14),
    1817100: (10, 15),
    2220900: (13, 19),
    2624700: (15, 25),
    3028500: (21, 30),
    3432300: (29, 38),
    3836100: (29, 40),
}

def _crop(frame, box):
    x, y, w, h = (int(v) for v in box)
    return frame[max(0, y):max(0, y)+h, max(0, x):max(0, x)+w]

def _read_score_notus(frame, cell):
    tens_box = cell.get("tens")
    ones_box = cell.get("ones")
    if not tens_box or not ones_box:
        return None
    tens = _read_notus_digit(_notus_red_mask(_crop(frame, tens_box)))
    ones = _read_notus_digit(_notus_red_mask(_crop(frame, ones_box)))
    if tens == "" and ones == "":
        return None
    if ones == "":
        ones = None
    text = ("?" if tens is None else tens) + ("?" if ones is None else ones)
    from scoreboard_clock import _score_value
    return _score_value([text])

print("Testing _notus_red_mask on Game A1 gate frames:")
for ts in timestamps_ms:
    frame_num = int(round(ts / 1000.0 * fps))
    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ok, frame = cap.read()
    cap.release()
    
    home_score = _read_score_notus(frame, cells["home"])
    away_score = _read_score_notus(frame, cells["away"])
    exp_home, exp_away = expected[ts]
    status = "OK" if (home_score == exp_home and away_score == exp_away) else "FAIL"
    print(f"  {ts/1000:.0f}s: exp=({exp_home},{exp_away}) got=({home_score},{away_score}) {status}")
    
    if status == "FAIL":
        # Debug
        h_tens_mask = _notus_red_mask(_crop(frame, g1_h_tens))
        h_ones_mask = _notus_red_mask(_crop(frame, g1_h_ones))
        a_tens_mask = _notus_red_mask(_crop(frame, g1_a_tens))
        a_ones_mask = _notus_red_mask(_crop(frame, g1_a_ones))
        print(f"    home_tens mask: {(h_tens_mask>0).sum()}, home_ones: {(h_ones_mask>0).sum()}")
        print(f"    away_tens mask: {(a_tens_mask>0).sum()}, away_ones: {(a_ones_mask>0).sum()}")
        geometry = _load_segment_geometry()
        for name, (fx0, fy0, fx1, fy1) in geometry.items():
            for slot_name, mask in [("h_tens", h_tens_mask), ("h_ones", h_ones_mask), ("a_tens", a_tens_mask), ("a_ones", a_ones_mask)]:
                sx0 = int(fx0 * mask.shape[1])
                sx1 = max(int(fx1 * mask.shape[1]), sx0 + 1)
                sy0 = int(fy0 * mask.shape[0])
                sy1 = max(int(fy1 * mask.shape[0]), sy0 + 1)
                cell = mask[sy0:sy1, sx0:sx1]
                if cell.size:
                    frac = float((cell > 0).mean())
                    if frac > 0.01:
                        print(f"      {slot_name}.{name}: frac={frac:.4f}")

cap.release()