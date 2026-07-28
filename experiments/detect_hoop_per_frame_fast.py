#!/usr/bin/env python3
import cv2
import numpy as np
import sys
import os

def detect_hoop(frame):
    # Resize to width 640 for speed
    height, width = frame.shape[:2]
    if width > 640:
        scale = 640 / width
        new_width = 640
        new_height = int(height * scale)
        resized = cv2.resize(frame, (new_width, new_height))
    else:
        resized = frame
        scale = 1.0
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (9,9), 2)
    circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=30,
                               param1=50, param2=30, minRadius=20, maxRadius=200)
    if circles is not None:
        circles = np.uint16(np.around(circles))
        # choose circle with highest accumulator
        best = circles[0][np.argmax(circles[0][:,2])]
        x, y, r = best
        # scale back to original size
        x = x / scale
        y = y / scale
        r = r / scale
        return float(x), float(y), float(r)
    else:
        return None, None, None

def main(video_path, out_npy, stride=16):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video {video_path}')
    fps = cap.get(5)
    frame_count = int(cap.get(7))
    centers = []
    radii = []
    frame_indices = []
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % stride != 0:
            frame_idx += 1
            continue
        x, y, r = detect_hoop(frame)
        centers.append((x, y) if x is not None else (np.nan, np.nan))
        radii.append(r if r is not None else np.nan)
        frame_indices.append(frame_idx)
        frame_idx += 1
        if frame_idx % (stride*50) == 0:
            print(f'Processed {frame_idx}/{frame_count} frames')
    cap.release()
    centers_arr = np.array(centers)
    radii_arr = np.array(radii)
    frame_indices_arr = np.array(frame_indices)
    data = {
        'frame_indices': frame_indices_arr,
        'centers': centers_arr,
        'radii': radii_arr
    }
    np.save(out_npy, data)
    print(f'Saved hoop data to {out_npy}')
    print(f'Valid detections: {np.sum(~np.isnan(centers_arr[:,0]))}')

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python detect_hoop_per_frame_fast.py <video_path> <out_npy> [stride]')
        sys.exit(1)
    video_path = sys.argv[1]
    out_npy = sys.argv[2]
    stride = int(sys.argv[3]) if len(sys.argv) > 3 else 16
    main(video_path, out_npy, stride)