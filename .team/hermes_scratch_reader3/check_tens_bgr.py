import cv2
import numpy as np
from pathlib import Path

ROOT = Path('.')
video_path = ROOT / 'uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4'

cap = cv2.VideoCapture(str(video_path))
fps = cap.get(cv2.CAP_PROP_FPS)

g1_h_tens = [1031, 614, 25, 29]

frame_num = int(round(6 * fps))
cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
ok, frame = cap.read()
cap.release()

x, y, w, h = g1_h_tens
crop = frame[y:y+h, x:x+w]

print(f"Home tens at 6s crop shape: {crop.shape}")
print(f"Full crop BGR stats:")
print(f"  B: {crop[:,:,0].min()}-{crop[:,:,0].max()}, mean={crop[:,:,0].mean():.1f}")
print(f"  G: {crop[:,:,1].min()}-{crop[:,:,1].max()}, mean={crop[:,:,1].mean():.1f}")
print(f"  R: {crop[:,:,2].min()}-{crop[:,:,2].max()}, mean={crop[:,:,2].mean():.1f}")

reddish = (crop[:,:,2] > crop[:,:,1]) & (crop[:,:,2] > crop[:,:,0])
print(f"\nReddish pixels (R>G and R>B): {reddish.sum()} / {crop.size//3} = {reddish.sum()/(crop.size//3)*100:.1f}%")

hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
for v_thresh in [30, 40, 50, 60, 70, 80, 90, 100, 110, 120]:
    bright = hsv[:,:,2] > v_thresh
    bright_reddish = bright & reddish
    print(f"V>{v_thresh} AND reddish: {bright_reddish.sum()} / {crop.size//3} = {bright_reddish.sum()/(crop.size//3)*100:.1f}%")

# Also check a later frame where home_tens is readable
frame_num = int(round(1817 * fps))
cap = cv2.VideoCapture(str(video_path))
cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
ok, frame = cap.read()
cap.release()

crop = frame[y:y+h, x:x+w]
print(f"\nHome tens at 1817s crop shape: {crop.shape}")
print(f"Full crop BGR stats:")
print(f"  B: {crop[:,:,0].min()}-{crop[:,:,0].max()}, mean={crop[:,:,0].mean():.1f}")
print(f"  G: {crop[:,:,1].min()}-{crop[:,:,1].max()}, mean={crop[:,:,1].mean():.1f}")
print(f"  R: {crop[:,:,2].min()}-{crop[:,:,2].max()}, mean={crop[:,:,2].mean():.1f}")

reddish = (crop[:,:,2] > crop[:,:,1]) & (crop[:,:,2] > crop[:,:,0])
print(f"\nReddish pixels (R>G and R>B): {reddish.sum()} / {crop.size//3} = {reddish.sum()/(crop.size//3)*100:.1f}%")

hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
for v_thresh in [30, 40, 50, 60, 70, 80, 90, 100, 110, 120]:
    bright = hsv[:,:,2] > v_thresh
    bright_reddish = bright & reddish
    print(f"V>{v_thresh} AND reddish: {bright_reddish.sum()} / {crop.size//3} = {bright_reddish.sum()/(crop.size//3)*100:.1f}%")