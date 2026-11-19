import cv2
import numpy as np
from pathlib import Path

ROOT = Path('.')
video_path = ROOT / 'uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4'

cap = cv2.VideoCapture(str(video_path))
fps = cap.get(cv2.CAP_PROP_FPS)

g1_h_ones = [1057, 613, 26, 30]

frame_num = int(round(6 * fps))
cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
ok, frame = cap.read()
cap.release()

x, y, w, h = g1_h_ones
crop = frame[y:y+h, x:x+w]

# Find pixels with V > 120 in HSV
hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
bright = hsv[:,:,2] > 120

# Get BGR values of bright pixels
bgr_bright = crop[bright]
print(f"Bright pixels (V>120) BGR: count={len(bgr_bright)}")
if len(bgr_bright) > 0:
    print(f"  B: {bgr_bright[:,0].min()}-{bgr_bright[:,0].max()}, mean={bgr_bright[:,0].mean():.1f}")
    print(f"  G: {bgr_bright[:,1].min()}-{bgr_bright[:,1].max()}, mean={bgr_bright[:,1].mean():.1f}")
    print(f"  R: {bgr_bright[:,2].min()}-{bgr_bright[:,2].max()}, mean={bgr_bright[:,2].mean():.1f}")

# Also check the overall crop BGR stats
print(f"\nFull crop BGR stats:")
print(f"  B: {crop[:,:,0].min()}-{crop[:,:,0].max()}, mean={crop[:,:,0].mean():.1f}")
print(f"  G: {crop[:,:,1].min()}-{crop[:,:,1].max()}, mean={crop[:,:,1].mean():.1f}")
print(f"  R: {crop[:,:,2].min()}-{crop[:,:,2].max()}, mean={crop[:,:,2].mean():.1f}")

# Check if R > G and R > B (reddish)
reddish = (crop[:,:,2] > crop[:,:,1]) & (crop[:,:,2] > crop[:,:,0])
print(f"\nReddish pixels (R>G and R>B): {reddish.sum()} / {crop.size//3} = {reddish.sum()/(crop.size//3)*100:.1f}%")

# Bright AND reddish
bright_reddish = bright & reddish
print(f"Bright (V>120) AND reddish: {bright_reddish.sum()} / {crop.size//3} = {bright_reddish.sum()/(crop.size//3)*100:.1f}%")

# What about V>50 and reddish?
bright50 = hsv[:,:,2] > 50
bright50_reddish = bright50 & reddish
print(f"Bright (V>50) AND reddish: {bright50_reddish.sum()} / {crop.size//3} = {bright50_reddish.sum()/(crop.size//3)*100:.1f}%")