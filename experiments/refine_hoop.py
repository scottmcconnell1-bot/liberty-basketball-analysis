#!/usr/bin/env python3
import cv2
import numpy as np
import json
import os

def detect_hoop_circles(frame, dp=1.2, minDist=50, param1=100, param2=30, minRadius=80, maxRadius=200):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 5)
    circles = cv2.HoughCircles(gray, cv2.HOUGH_GRADIENT, dp, minDist,
                               param1=param1, param2=param2,
                               minRadius=minRadius, maxRadius=maxRadius)
    if circles is not None:
        circles = np.uint16(np.around(circles))
        return circles[0, :]  # return first circle
    else:
        return None

def main():
    video_path = 'uploads/Liberty_Vs_Riverstone_Q1.webm'
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Cannot open video")
        return
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f'Video: {frame_count} frames @ {fps:.2f} fps')
    
    centres = []
    radii = []
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % 10 != 0:  # stride 10
            frame_idx += 1
            continue
        circle = detect_hoop_circles(frame, minRadius=70, maxRadius=180)
        if circle is not None:
            x, y, r = circle
            centres.append([x, y])
            radii.append(r)
            if len(centres) % 20 == 0:
                print(f'Processed {frame_idx} frames, {len(centres)} hoops detected')
        frame_idx += 1
        if frame_idx > 1000:  # limit to first 1000 frames for speed
            break
    cap.release()
    
    if len(centres) == 0:
        print("No hoops detected")
        return
    centres = np.array(centres)
    radii = np.array(radii)
    centre_mean = np.mean(centres, axis=0)
    centre_std = np.std(centres, axis=0)
    radius_mean = np.mean(radii)
    radius_std = np.std(radii)
    print(f'Hoop centre mean: {centre_mean} +/- {centre_std}')
    print(f'Hoop radius mean: {radius_mean:.2f} +/- {radius_std:.2f} px')
    
    # Load existing hoop params for scale
    hoop_path = 'hoop_params.json'
    if os.path.exists(hoop_path):
        with open(hoop_path) as f:
            hoop = json.load(f)
        scale_ft_per_px = hoop['scale_ft_per_px']
    else:
        # Assume known radius 0.75 ft
        radius_mean_ft = 0.75
        scale_ft_per_px = radius_mean_ft / radius_mean if radius_mean > 0 else 0.0054
    
    print(f'Using scale: {scale_ft_per_px} ft/px (from existing or derived)')
    hoop_center_ft = centre_mean * scale_ft_per_px
    hoop_radius_ft = radius_mean * scale_ft_per_px
    print(f'Hoop centre (ft): {hoop_center_ft}')
    print(f'Hoop radius (ft): {hoop_radius_ft}')
    
    # Save new hoop params
    new_hoop = {
        'hoop_center_px': centre_mean.tolist(),
        'hoop_radius_px': float(radius_mean),
        'scale_ft_per_px': float(scale_ft_per_px),
        'scale_in_per_px': float(scale_ft_per_px * 12),
        'num_detections': len(centres)
    }
    with open('hoop_params_refined.json', 'w') as f:
        json.dump(new_hoop, f, indent=2)
    print('Saved refined hoop params to hoop_params_refined.json')

if __name__ == '__main__':
    main()