import json
import cv2
import numpy as np
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scoreboard_clock_720p import _read_score, game_rois, load_rois, _notus_red_mask

ROI_FILE = ROOT / "data" / "roi" / "notus_scoreboard_rois.json"
TRUTH_FILE = ROOT / ".team" / "specs" / "04_notus_crop_truth.json"

with open(TRUTH_FILE) as f:
    truth = json.load(f)

rois = load_rois(ROI_FILE)

def analyze_frame(game_id, crop_name, sample, config):
    """Read frame and analyze each digit"""
    cap = cv2.VideoCapture(str(ROOT / config["video"]))
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(sample["timestamp_ms"] / 1000.0 * config["fps"])))
    ok, frame = cap.read()
    cap.release()
    
    if not ok or frame is None:
        print(f"  Failed to read frame")
        return
    
    print(f"  Frame shape: {frame.shape}")
    cells = config.get("scores") or {}
    
    for side in ['home', 'away']:
        cell = cells.get(side) or {}
        tens_box = cell.get('tens')
        ones_box = cell.get('ones')
        
        for pos, box in [('tens', tens_box), ('ones', ones_box)]:
            if not box:
                continue
            x, y, w, h = box
            digit_crop = frame[y:y+h, x:x+w]
            
            # Get expected
            exp_home, exp_away = truth[game_id][crop_name]
            exp_digit = exp_home if side == 'home' else exp_away
            
            # Analyze with mask
            mask = _notus_red_mask(digit_crop)
            red_pct = 100 * np.count_nonzero(mask) / mask.size
            
            # Load segment geometry
            with open(ROOT / 'data/roi/notus_segment_geometry.json') as f:
                seg_geo = json.load(f)
            
            segments_px = {}
            for seg, (sx1, sy1, sx2, sy2) in seg_geo['segments'].items():
                px1, py1 = int(sx1 * w), int(sy1 * h)
                px2, py2 = int(sx2 * w), int(sy2 * h)
                segments_px[seg] = (px1, py1, px2, py2)
            
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
            
            # Read using actual function
            got = _read_score(frame, cell)
            
            status = "OK" if got == exp_digit else "FAIL" if got is not None else "None"
            print(f"    {side}_{pos} (exp={exp_digit}, got={got}): red={red_pct:.1f}% on={on_str} {status}")
            
            if got != exp_digit:
                print(f"      Crop: {w}x{h}")
                for seg in 'abcdefg':
                    px1, py1, px2, py2 = segments_px[seg]
                    if px1 >= px2 or py1 >= py2:
                        continue
                    seg_mask = mask[py1:py2, px1:px2]
                    seg_total = seg_mask.size
                    seg_red = np.count_nonzero(seg_mask)
                    occupancy = seg_red / seg_total if seg_total > 0 else 0
                    marker = " *" if occupancy >= 0.12 else ""
                    print(f"      {seg}: {occupancy:.3f} ({seg_red}/{seg_total}) {marker} @({px1},{py1})-({px2},{py2})")

# Test the failing cases
failures = [
    ('jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334', 'notus_A1_01_606s'),
    ('jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334', 'notus_A1_05_2221s'),
    ('jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334', 'notus_A1_09_3836s'),
    ('jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334', 'notus_A_00_187s'),
    ('jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334', 'notus_A_02_936s'),
    ('jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334', 'notus_A_05_2060s'),
    ('jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334', 'notus_A_07_2810s'),
    ('jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334', 'notus_A_08_3184s'),
    ('jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334', 'notus_A_09_3559s'),
]

for game_id, crop_name in failures:
    config = game_rois(rois, game_id)
    sample = None
    for s in config.get("samples", []):
        if Path(str(s.get("crop"))).stem == crop_name:
            sample = s
            break
    if not sample:
        print(f"{crop_name}: no sample found")
        continue
    
    print(f"\n{crop_name} (game={game_id}):")
    analyze_frame(game_id, crop_name, sample, config)