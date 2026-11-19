import cv2
import numpy as np
from pathlib import Path
import sys
sys.path.insert(0, '.')

from scoreboard_clock_720p import _read_notus_digit, _load_segment_geometry

ROOT = Path('.')
video_path = ROOT / 'uploads/LIBERTY_H_v_NOTUS_A_20260809_221334.mp4'

def _notus_red_mask(crop: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    low = cv2.inRange(hsv, (0, 50, 50), (12, 255, 255))
    high = cv2.inRange(hsv, (165, 50, 50), (180, 255, 255))
    mask = cv2.bitwise_or(low, high)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

cap = cv2.VideoCapture(str(video_path))
fps = cap.get(cv2.CAP_PROP_FPS)

timestamps_ms = [187300, 561900, 936500, 1311100, 1685700, 2060300, 2434900, 2809500, 3184100, 3558700]

g2_h_tens = [1032, 615, 22, 28]
g2_h_ones = [1058, 614, 23, 29]
g2_a_tens = [1199, 615, 22, 28]
g2_a_ones = [1225, 614, 23, 29]

cells = {
    "home": {"tens": g2_h_tens, "ones": g2_h_ones},
    "away": {"tens": g2_a_tens, "ones": g2_a_ones}
}

expected = {
    187300: (5, 2),
    561900: (11, 4),
    936500: (13, 8),
    1311100: (16, 9),
    1685700: (16, 11),
    2060300: (16, 15),
    2434900: (19, 15),
    2809500: (23, 17),
    3184100: (25, 21),
    3558700: (36, 21),
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

print("Testing _notus_red_mask (HSV S>50, V>50) on Game A gate frames:")
for ts in timestamps_ms:
    frame_num = int(round(ts / 1000.0 * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ok, frame = cap.read()
    
    home_score = _read_score_notus(frame, cells["home"])
    away_score = _read_score_notus(frame, cells["away"])
    exp_home, exp_away = expected[ts]
    status = "OK" if (home_score == exp_home and away_score == exp_away) else "FAIL"
    print(f"  {ts/1000:.0f}s: exp=({exp_home},{exp_away}) got=({home_score},{away_score}) {status}")
    
    if status == "FAIL":
        h_tens_mask = _notus_red_mask(_crop(frame, g2_h_tens))
        h_ones_mask = _notus_red_mask(_crop(frame, g2_h_ones))
        a_tens_mask = _notus_red_mask(_crop(frame, g2_a_tens))
        a_ones_mask = _notus_red_mask(_crop(frame, g2_a_ones))
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