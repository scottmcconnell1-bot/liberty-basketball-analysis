import cv2
import numpy as np
import json
from pathlib import Path

ROOT = Path(".")
from scoreboard_clock import _SEVEN_SEGMENT

def get_on_segments(digit):
    if digit is None: return []
    # _SEVEN_SEGMENT maps a pattern string to a digit string ("abcfg" -> "9")
    # build the ON segments of a digit as the letters common to EVERY pattern that maps to that digit
    digit_str = str(digit)
    patterns = [p for p, d in _SEVEN_SEGMENT.items() if d == digit_str]
    if not patterns: return []
    
    common = set(patterns[0])
    for p in patterns[1:]:
        common &= set(p)
    return sorted(list(common))

def main():
    # Load eye-read values
    with open(".team/notus_fit_crops/eye_read_values.json", "r") as f:
        eye_read = json.load(f)

    # Load segment geometry
    with open("data/roi/notus_segment_geometry.json", "r") as f:
        geom = json.load(f)
    
    segments_norm = geom["segments"]
    
    # Load ROI boxes
    with open("data/roi/notus_scoreboard_rois.json", "r") as f:
        rois = json.load(f)

    all_lit_pixels = []
    
    # Process crops for thresholds
    for entry in eye_read["entries"]:
        digit = entry["digit"]
        if digit is None: continue
        
        slot = entry["slot"]
        crop_path = Path(entry["crop_path"])
        game_id = "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334" if entry["game"] == "A1" else "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334"
        
        # Get box for the slot in this game (using the 'scores' structure as per NEXT_TASK.md)
        # Slot is e.g. 'home_tens' -> rois['games'][game_id]['scores']['home']['tens']
        side, part = slot.split('_')
        box = rois["games"][game_id]["scores"][side][part]
        
        img = cv2.imread(str(crop_path))
        if img is None: continue
        
        h, w, _ = img.shape
        # The crops in .team/notus_fit_crops/ are the slot box crops.
        # The norm segments are relative to a 100x120 box.
        
        # Union ON-segment regions
        on_segs = get_on_segments(digit)
        mask_on = np.zeros((h, w), dtype=np.uint8)
        for seg in on_segs:
            s_box = segments_norm[seg] # [x_min, y_min, x_max, y_max] in normalized 100x120
            # Map to crop pixels: x is 0-100, y is 0-120
            # The images are small. The normalized coords are 0.0 to 1.0.
            x0 = int(s_box[0] * w)
            y0 = int(s_box[1] * h)
            x1 = int(s_box[2] * w)
            y1 = int(s_box[3] * h)
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(w, x1), min(h, y1)
            mask_on[y0:y1, x0:x1] = 1

        
        print(f"Crop {crop_path}: h={h}, w={w}, mask_on_sum={np.sum(mask_on)}")


            
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        on_pixels = hsv[mask_on == 1]
        
        if len(on_pixels) == 0: continue
        
        # lit pixels = V >= per-crop median V inside ON-segment regions
        median_v = np.median(on_pixels[:, 2])
        lit_pixels = on_pixels[on_pixels[:, 2] >= median_v]
        all_lit_pixels.append(lit_pixels)

    pooled_lit = np.vstack(all_lit_pixels)
    
    # Hue central 98% with wrap-around
    hues = pooled_lit[:, 0].astype(float)
    # map hues > 165 to hue-180
    hues_shifted = np.where(hues > 165, hues - 180, hues)
    h_min_s = np.percentile(hues_shifted, 1)
    h_max_s = np.percentile(hues_shifted, 99)
    
    # Map back to 0-179
    # If h_min_s is e.g. -5, it becomes 175. If h_max_s is 10, it stays 10.
    h_min = int(h_min_s) if h_min_s >= 0 else int(h_min_s + 180)
    h_max = int(h_max_s) if h_max_s <= 165 else int(h_max_s - 180)
    # Wait, the wrap-around rule in NEXT_TASK: "map hues > 165 to hue-180... compute 1st and 99th... map back"
    # Example: red is 0-10 and 170-179. 
    # Shifted: 0-10 and -10 to -1. Range is -10 to 10.
    # 1st perc: -9, 99th perc: 9.
    # h_min = -9 -> 171, h_max = 9 -> 9.
    # This is the wrap-around case where h_min > h_max.
    
    s_min = int(np.percentile(pooled_lit[:, 1], 10))
    v_min = int(np.percentile(pooled_lit[:, 2], 10))
    
    thresholds = {"h_min": h_min, "h_max": h_max, "s_min": s_min, "v_min": v_min}
    with open("data/roi/notus_red_thresholds.json", "w") as f:
        json.dump(thresholds, f)
    
    print(f"FROZEN_THRESHOLDS: {thresholds}")

    # REPORT-ONLY off-segment share per game
    # Need to re-process everything
    game_off_shares = {} # game_id -> [shares]
    
    for entry in eye_read["entries"]:
        digit = entry["digit"]
        slot = entry["slot"]
        crop_path = Path(entry["crop_path"])
        game_short = entry["game"]
        game_id = "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334" if game_short == "A1" else "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334"
        
        img = cv2.imread(str(crop_path))
        if img is None: continue
        h, w, _ = img.shape
        
        # OFF-segment regions: segments NOT lit for eye-read digit, and blank tens slots
        if digit is None:
            # Blank tens slot: whole box is OFF
            mask_off = np.ones((h, w), dtype=np.uint8)
        else:
            on_segs = get_on_segments(digit)
            mask_off = np.zeros((h, w), dtype=np.uint8)
            for seg, s_box in segments_norm.items():
                if seg not in on_segs:
                    x0 = int(s_box[0] * w)
                    y0 = int(s_box[1] * h)
                    x1 = int(s_box[2] * w)
                    y1 = int(s_box[3] * h)
                    mask_off[y0:y1, x0:x1] = 1
        
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        off_pixels = hsv[mask_off == 1]
        if len(off_pixels) == 0: continue
        
        # Check frozen mask
        # handle wrap-around h_min > h_max
        h_vals = off_pixels[:, 0]
        s_vals = off_pixels[:, 1]
        v_vals = off_pixels[:, 2]
        
        if h_min <= h_max:
            h_mask = (h_vals >= h_min) & (h_vals <= h_max)
        else:
            h_mask = (h_vals >= h_min) | (h_vals <= h_max)
            
        mask = h_mask & (s_vals >= s_min) & (v_vals >= v_min)
        share = np.mean(mask)
        
        if game_short not in game_off_shares: game_off_shares[game_short] = []
        game_off_shares[game_short].append(share)

    for game, shares in game_off_shares.items():
        print(f"REPORT-ONLY: Game {game} off-segment share: {np.mean(shares):.4%}")

if __name__ == "__main__":
    main()
