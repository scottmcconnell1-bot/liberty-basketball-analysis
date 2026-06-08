#!/usr/bin/env python3
"""
Visualize hoop detection on a few sample frames to see if it looks correct.
"""

import cv2
import numpy as np
import os

HOOP_PATH = "hoop_Q1.npy"
FRAME_DIR = "sample_frames"
OUT_DIR = "hoop_vis"
os.makedirs(OUT_DIR, exist_ok=True)

def load_hoop():
    data = np.load(HOOP_PATH, allow_pickle=True).item()
    return data['frame_indices'], data['centers'], data['radii']

def get_hoop(frame_idx, f_ind, cents, rads):
    idx = np.argmin(np.abs(f_ind - frame_idx))
    return cents[idx], rads[idx], f_ind[idx]

def main():
    f_ind, cents, rads = load_hoop()
    print(f"Hoop data: {len(f_ind)} frames")
    print("First 10 radii:", rads[:10])
    print("Last 10 radii:", rads[-10:])
    
    files = sorted([f for f in os.listdir(FRAME_DIR) if f.endswith('.jpg')])
    for fname in files[:5]:  # first 5 frames
        frame_idx = int(fname.split('_')[1].split('.')[0])
        path = os.path.join(FRAME_DIR, fname)
        img = cv2.imread(path)
        if img is None:
            continue
        hoop_center, hoop_radius_px, hoop_frame_idx = get_hoop(frame_idx, f_ind, cents, rads)
        vis = img.copy()
        # Draw center
        cv2.circle(vis, (int(hoop_center[0]), int(hoop_center[1])), 5, (0,0,255), -1)
        # Draw radius circle
        cv2.circle(vis, (int(hoop_center[0]), int(hoop_center[1])), int(hoop_radius_px), (255,0,0), 2)
        # Add text
        cv2.putText(vis, f"Frame {frame_idx} (hoop frame {hoop_frame_idx}) radius={hoop_radius_px:.1f}px", 
                    (10,30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
        out_path = os.path.join(OUT_DIR, f"{fname.split('.')[0]}_hoop.jpg")
        cv2.imwrite(out_path, vis)
        print(f"Saved {out_path}")

if __name__ == "__main__":
    main()