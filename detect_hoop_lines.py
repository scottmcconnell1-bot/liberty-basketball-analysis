#!/usr/bin/env python3
import cv2
import numpy as np
import pandas as pd
import sys
import os

def detect_hoop_and_lines(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5,5), 0)
    # Hoop detection via HoughCircles
    circles = cv2.HoughCircles(blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=30,
                               param1=50, param2=30, minRadius=20, maxRadius=150)
    hoop_center = None
    hoop_radius = None
    if circles is not None:
        circles = np.uint16(np.around(circles))
        # Choose the circle with highest accumulator? just take first
        x, y, r = circles[0][0]
        hoop_center = (float(x), float(y))
        hoop_radius = float(r)
    # Line detection via HoughLinesP
    edges = cv2.Canny(blur, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, rho=1, theta=np.pi/180, threshold=80,
                            minLineLength=30, maxLineGap=10)
    # Separate vertical and horizontal lines based on angle
    vert_lines = []
    horiz_lines = []
    if lines is not None:
        for line in lines[:,0]:
            x1,y1,x2,y2 = line
            angle = np.abs(np.arctan2(y2-y1, x2-x1)) * 180 / np.pi
            if angle < 20 or angle > 160:  # near horizontal
                horiz_lines.append(((x1,y1),(x2,y2)))
            elif 70 < angle < 110:  # near vertical
                vert_lines.append(((x1,y1),(x2,y2)))
    # Compute average x for leftmost and rightmost vertical lines
    left_x = None
    right_x = None
    if vert_lines:
        # compute average x of each line
        line_xs = []
        for (p1,p2) in vert_lines:
            xs = [p1[0], p2[0]]
            line_xs.append(np.mean(xs))
        # sort
        sorted_idx = np.argsort(line_xs)
        left_x = np.mean([vert_lines[sorted_idx[0]][0][0], vert_lines[sorted_idx[0]][1][0]])
        right_x = np.mean([vert_lines[sorted_idx[-1]][0][0], vert_lines[sorted_idx[-1]][1][0]])
    # Compute average y for lowest and second lowest horizontal lines (baseline lowest y?)
    baseline_y = None
    ft_y = None
    if horiz_lines:
        line_ys = []
        for (p1,p2) in horiz_lines:
            ys = [p1[1], p2[1]]
            line_ys.append(np.mean(ys))
        sorted_idx = np.argsort(line_ys)
        # lowest y (smallest) is top of image? Since camera looks down, baseline likely higher y? We'll just take two extremes.
        baseline_y = np.mean([horiz_lines[sorted_idx[0]][0][1], horiz_lines[sorted_idx[0]][1][1]])
        ft_y = np.mean([horiz_lines[sorted_idx[-1]][0][1], horiz_lines[sorted_idx[-1]][1][1]])
    return hoop_center, hoop_radius, left_x, right_x, baseline_y, ft_y

def main(video_path, out_npy, stride=4):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f'Cannot open video {video_path}')
    fps = cap.get(5)
    frame_count = int(cap.get(7))
    Hs = []
    frame_indices = []
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % stride != 0:
            frame_idx += 1
            continue
        hoop_center, hoop_radius, left_x, right_x, baseline_y, ft_y = detect_hoop_and_lines(frame)
        # Build src and dst points if we have enough
        src_pts = []
        dst_pts = []
        # Hoop center
        if hoop_center:
            src_pts.append([hoop_center[0], hoop_center[1]])
            dst_pts.append([0.0, 0.0])
        # Point on hoop right
        if hoop_center and hoop_radius:
            src_pts.append([hoop_center[0] + hoop_radius, hoop_center[1]])
            dst_pts.append([0.75, 0.0])
        # Left baseline corner
        if left_x is not None and baseline_y is not None:
            src_pts.append([left_x, baseline_y])
            dst_pts.append([-25.0, -5.0])
        # Right baseline corner
        if right_x is not None and baseline_y is not None:
            src_pts.append([right_x, baseline_y])
            dst_pts.append([25.0, -5.0])
        if len(src_pts) >= 4:
            src = np.array(src_pts, dtype=np.float32)
            dst = np.array(dst_pts, dtype=np.float32)
            H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
            if H is not None:
                Hs.append(H)
                frame_indices.append(frame_idx)
            else:
                Hs.append(None)
                frame_indices.append(frame_idx)
        else:
            Hs.append(None)
            frame_indices.append(frame_idx)
        frame_idx += 1
        if frame_idx % (stride*50) == 0:
            print(f'Processed {frame_idx}/{frame_count} frames')
    cap.release()
    # Save as dict
    data = {'frame_indices': frame_indices, 'Hs': Hs}
    np.save(out_npy, data)
    print(f'Saved homography data to {out_npy} ({(len([h for h in Hs if h is not None]))} valid matrices)')

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('Usage: python detect_hoop_lines.py <video_path> <out_npy> [stride]')
        sys.exit(1)
    video_path = sys.argv[1]
    out_npy = sys.argv[2]
    stride = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    main(video_path, out_npy, stride)