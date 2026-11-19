import cv2
import json
import os
from pathlib import Path

# Configuration
ROI_FILE = "data/roi/notus_scoreboard_rois.json"
OUTPUT_DIR = ".team/notus_fit_crops/"
# Use keys from ROI file
GAMES = [
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334",
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334"
]
# Mapping game keys to likely video files based on observed filenames
VIDEO_MAP = {
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334": "Q1.mp4",
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334": "Q1.mp4" # Fallback to Q1 if A is missing
}

GATE_TIMES = {
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334": [202, 606, 1010, 1413, 1817, 2221, 2625, 3028, 3432, 3836],
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334": [187, 562, 936, 1311, 1686, 2060, 2435, 2810, 3184, 3559]
}
HOLDOUT_TIMES = {
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334": [246.9, 650.7, 1054.5, 1458.3, 1862.1, 2265.9, 2669.7, 3073.5, 3477.3, 3881.1],
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334": [232.3, 606.8, 981.3, 1356.0, 1730.6, 2105.1, 2479.6, 2854.1, 3229.6, 3603.9]
}

def is_fitting_frame(ts, game_id):
    all_excluded = GATE_TIMES[game_id] + HOLDOUT_TIMES[game_id]
    for ex in all_excluded:
        if abs(ts - ex) < 60:
            return False
    return True

def extract_crops():
    with open(ROI_FILE, 'r') as f:
        rois = json.load(f)
    
    # Find video files for Notus games
    video_dir = Path("videos")
    if not video_dir.exists():
        video_dir = Path("data/videos")
        if not video_dir.exists():
            print(f"Video directory not found.")
            return

    slots = ["home_tens", "home_ones", "away_tens", "away_ones"]
    crops_total = 0
    
    for game_id in GAMES:
        video_path = None
        video_filename = VIDEO_MAP.get(game_id)
        if video_filename:
            for v_dir in [Path("videos"), Path("data/videos")]:
                v_path = v_dir / video_filename
                if v_path.exists():
                    video_path = str(v_path)
                    break
        
        if not video_path:
            print(f"Video for {game_id} not found.")
            continue

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        # Correct ROI extraction based on JSON structure: rois[games][game_id][scores][home/away][tens/ones]
        game_data = rois.get("games", {}).get(game_id, {})
        if not game_data:
            game_data = rois.get("default", {})
        
        scores_roi = game_data.get("scores", {})
        
        found_counts = {slot: 0 for slot in slots}
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        step = total_frames // 100 if total_frames > 100 else 1
        
        for frame_idx in range(0, total_frames, step):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret: break
            
            ts = frame_idx / fps
            if not is_fitting_frame(ts, game_id):
                continue
            
            for slot in slots:
                if found_counts[slot] < 10:
                    try:
                        side, digit = slot.split("_")
                        box = scores_roi[side][digit]
                        x, y, w, h = box
                        crop = frame[y:y+h, x:x+w]
                        if crop.size > 0:
                            filename = f"{game_id}_{slot}_{ts:.2f}s.png"
                            cv2.imwrite(os.path.join(OUTPUT_DIR, filename), crop)
                            found_counts[slot] += 1
                    except (KeyError, ValueError):
                        continue
            
            if all(count >= 10 for count in found_counts.values()):
                break
                
        cap.release()
        crops_total += sum(found_counts.values())

    return crops_total

if __name__ == "__main__":
    total = extract_crops()
    print(f"Total crops saved: {total}")
