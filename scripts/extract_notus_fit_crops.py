import cv2
import json
import os
from pathlib import Path

# Configuration
ROI_FILE = "data/roi/notus_scoreboard_rois.json"
OUTPUT_DIR = ".team/notus_fit_crops/"
GAMES = [
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334",
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334"
]

GATE_TIMES = {
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334": [202, 606, 1010, 1413, 1817, 2221, 2625, 3028, 3432, 3836],
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334": [187, 562, 936, 1311, 1686, 2060, 2435, 2810, 3184, 3559]
}
HOLDOUT_TIMES = {
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334": [246.9, 650.7, 1054.5, 1458.3, 1862.1, 2265.9, 2669.7, 3073.5, 3477.3, 3881.1],
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334": [232.3, 606.8, 981.3, 1356.0, 1730.6, 2105.1, 2479.6, 2854.1, 3229.6, 3603.9]
}

def get_nearest_allowed_time(ts, game_id):
    all_excluded = GATE_TIMES[game_id] + HOLDOUT_TIMES[game_id]
    while True:
        min_dist = min([abs(ts - ex) for ex in all_excluded])
        if min_dist >= 60:
            return ts, min_dist
        
        # Find which excluded time is causing the violation
        violator = min(all_excluded, key=lambda ex: abs(ts - ex))
        # Move ts away from violator to exactly 60s
        if ts > violator:
            ts = violator + 60
        else:
            ts = violator - 60
        
        # Clamp to 0 (cannot be negative)
        ts = max(0, ts)

def extract_crops():
    with open(ROI_FILE, 'r') as f:
        rois = json.load(f)
    
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    slots = ["home_tens", "home_ones", "away_tens", "away_ones"]
    crops_total = 0
    
    for game_id in GAMES:
        game_data = rois.get("games", {}).get(game_id)
        if not game_data:
            print(f"Error: No data for {game_id} in ROI file.")
            exit(1)
            
        video_rel_path = game_data.get("video")
        if not video_rel_path:
            print(f"Error: No video path for {game_id} in ROI file.")
            exit(1)
            
        video_path = Path(video_rel_path)
        if not video_path.exists():
            print(f"Error: Video file {video_path} not found.")
            exit(1)

        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps
        
        scores_roi = game_data.get("scores", {})
        
        # Choose 10 timestamps spread evenly across duration
        chosen_ts = []
        for i in range(10):
            ts = (duration / 10) * i + (duration / 20)
            allowed_ts, dist = get_nearest_allowed_time(ts, game_id)
            # Clamp to duration
            allowed_ts = min(allowed_ts, duration - 0.1)
            chosen_ts.append(allowed_ts)
            print(f"Game {game_id}: ts={allowed_ts:.2f}s, dist_to_excluded={dist:.2f}s")

        for ts in chosen_ts:
            frame_idx = int(ts * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue
            
            # Save slot crops
            for slot in slots:
                try:
                    side, digit = slot.split("_")
                    box = scores_roi[side][digit]
                    x, y, w, h = box
                    crop = frame[y:y+h, x:x+w]
                    if crop.size > 0:
                        filename = f"{game_id}_{slot}_{ts:.2f}s.png"
                        cv2.imwrite(os.path.join(OUTPUT_DIR, filename), crop)
                        crops_total += 1
                except (KeyError, ValueError):
                    continue
            
            # Save cell crops (home and away)
            for side in ["home", "away"]:
                try:
                    box = scores_roi[side]["cell"]
                    x, y, w, h = box
                    crop = frame[y:y+h, x:x+w]
                    if crop.size > 0:
                        filename = f"{game_id}_{side}_cell_{ts:.2f}s.png"
                        cv2.imwrite(os.path.join(OUTPUT_DIR, filename), crop)
                        crops_total += 1
                except (KeyError, ValueError):
                    continue
                    
        cap.release()

    return crops_total

if __name__ == "__main__":
    total = extract_crops()
    print(f"Total crops saved: {total}")
