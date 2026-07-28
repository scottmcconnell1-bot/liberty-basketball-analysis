#!/usr/bin/env python3
"""
Explore colour thresholds on sample frames to see what the ball looks like.
We'll sample a few regions and print HSV stats.
"""

import cv2
import numpy as np
import os

FRAME_DIR = "sample_frames"

def explore_frame(fname):
    path = os.path.join(FRAME_DIR, fname)
    img = cv2.imread(path)
    if img is None:
        return
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    print(f"\n{fname}:")
    print(f"  H: min={h.min()}, max={h.max()}, mean={h.mean():.1f}")
    print(f"  S: min={s.min()}, max={s.max()}, mean={s.mean():.1f}")
    print(f"  V: min={v.min()}, max={v.max()}, mean={v.mean():.1f}")
    # Show some percentiles
    for p in [10, 25, 50, 75, 90]:
        hp = np.percentile(h, p)
        sp = np.percentile(s, p)
        vp = np.percentile(v, p)
        print(f"  {p}th: H={hp:.1f}, S={sp:.1f}, V={vp:.1f}")
    # Count pixels in various ranges
    # Orange-ish: H 0-20, S > 50, V > 50
    mask1 = cv2.inRange(hsv, np.array([0,50,50]), np.array([20,255,255]))
    cnt1 = cv2.countNonZero(mask1)
    # Brown-ish: H 0-20, S 30-100, V 30-100
    mask2 = cv2.inRange(hsv, np.array([0,30,30]), np.array([20,100,100]))
    cnt2 = cv2.countNonZero(mask2)
    # Dark: V < 80
    mask3 = cv2.inRange(hsv, np.array([0,0,0]), np.array([180,255,80]))
    cnt3 = cv2.countNonZero(mask3)
    # Very dark: V < 50
    mask4 = cv2.inRange(hsv, np.array([0,0,0]), np.array([180,255,50]))
    cnt4 = cv2.countNonZero(mask4)
    print(f"  Orange-ish (H0-20,S>50,V>50): {cnt1}")
    print(f"  Brown-ish (H0-20,S30-100,V30-100): {cnt2}")
    print(f"  Dark (V<80): {cnt3}")
    print(f"  Very dark (V<50): {cnt4}")

def main():
    files = sorted([f for f in os.listdir(FRAME_DIR) if f.endswith('.jpg')])[:5]
    for f in files:
        explore_frame(f)

if __name__ == "__main__":
    main()