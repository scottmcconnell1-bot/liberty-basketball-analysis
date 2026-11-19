import cv2
import numpy as np
import json
from pathlib import Path

ROOT = Path(".")

def get_red_mask(crop):
    with open(ROOT / "data" / "roi" / "notus_red_thresholds.json", "r") as f:
        thresh = json.load(f)
    h_min, h_max, s_min, v_min = thresh["h_min"], thresh["h_max"], thresh["s_min"], thresh["v_min"]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    if h_min <= h_max:
        mask = cv2.inRange(hsv, (h_min, s_min, v_min), (h_max, 255, 255))
    else:
        low = cv2.inRange(hsv, (0, s_min, v_min), (h_max, 255, 255))
        high = cv2.inRange(hsv, (h_min, s_min, v_min), (179, 255, 255))
        mask = cv2.bitwise_or(low, high)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

def main():
    with open(ROOT / "data" / "roi" / "notus_scoreboard_rois.json", "r") as f:
        roi_data = json.load(f)
    with open(ROOT / ".team" / "notus_fit_crops" / "eye_read_values.json", "r") as f:
        eye_reads = json.load(f)["entries"]

    game_map = {
        "A1": "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334",
        "A": "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334"
    }

    slot_data = {} 
    for entry in eye_reads:
        if entry["digit"] is None:
            continue
        game_id = game_map[entry["game"]]
        slot = entry["slot"]
        key = (game_id, slot)
        if key not in slot_data:
            slot_data[key] = []
        slot_data[key].append(entry["timestamp_s"])

    print(f"{'Game':<10} | {'Slot':<12} | {'Orig Box':<20} | {'Best Shift':<12} | {'Cov Before':<12} | {'Cov After':<12}")
    print("-" * 85)

    for (game_id, slot), timestamps in slot_data.items():
        team, pos = slot.split("_")
        orig_box = roi_data["games"][game_id]["scores"][team][pos]
        x0, y0, w, h = orig_box
        
        video_rel_path = roi_data["games"][game_id]["video"]
        video_path = ROOT / video_rel_path
        cap = cv2.VideoCapture(str(video_path))
        
        frames = []
        for ts in timestamps:
            cap.set(cv2.CAP_PROP_POS_MSEC, ts * 1000)
            ret, frame = cap.read()
            if ret:
                frames.append(frame)
        cap.release()

        if not frames:
            continue

        best_shift = (0, 0)
        max_median_cov = -1.0
        
        initial_covs = []
        for frame in frames:
            crop = frame[y0:y0+h, x0:x0+w]
            mask = get_red_mask(crop)
            initial_covs.append(np.count_nonzero(mask) / (w * h))
        initial_median = np.median(initial_covs)

        for dx in range(-8, 9):
            for dy in range(-6, 7):
                shift_covs = []
                valid_shift = True
                for frame in frames:
                    nx, ny = x0 + dx, y0 + dy
                    if nx < 0 or ny < 0 or nx + w > frame.shape[1] or ny + h > frame.shape[0]:
                        valid_shift = False
                        break
                    crop = frame[ny:ny+h, nx:nx+w]
                    mask = get_red_mask(crop)
                    shift_covs.append(np.count_nonzero(mask) / (w * h))
                
                if not valid_shift:
                    continue
                
                median_cov = np.median(shift_covs)
                if median_cov > max_median_cov + 1e-6:
                    max_median_cov = median_cov
                    best_shift = (dx, dy)
                elif abs(median_cov - max_median_cov) < 1e-6:
                    if abs(dx) + abs(dy) < abs(best_shift[0]) + abs(best_shift[1]):
                        best_shift = (dx, dy)

        game_short = "A1" if "A1" in game_id else "A"
        print(f"{game_short:<10} | {slot:<12} | {str(orig_box):<20} | {str(best_shift):<12} | {initial_median:<12.4f} | {max_median_cov:<12.4f}")

if __name__ == "__main__":
    main()
