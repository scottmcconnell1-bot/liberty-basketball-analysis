#!/usr/bin/env python3
"""Visual audit: extract frame thumbnails + backward corridor overlays for each shot event.

For each valid shot event, saves:
  - Thumbnail of the anchor frame
  - Overlay of the backward emergence corridor on the anchor frame
"""
import sys
sys.path.insert(0, '/home/monk-admin/PROJECTS/liberty-basketball-analysis')

import os
import pickle
import cv2
import numpy as np
import pandas as pd

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
PKL_V14 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl'
CSV_IN  = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v34.csv'
OUT_DIR = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/audit'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0
BWD_WIN = 15
MAX_JUMP = 80


def check_color(hsv, x, y):
    h, w = hsv.shape[:2]
    xi, yi = int(x), int(y)
    return 0 <= xi < w and 0 <= yi < h and 2 <= hsv[yi, xi, 0] <= 32 and hsv[yi, xi, 1] >= 10


def extract_template(img_gray, cx, cy, radius=8):
    h, w = img_gray.shape[:2]
    x1, x2 = max(0, int(cx) - radius), min(w, int(cx) + radius)
    y1, y2 = max(0, int(cy) - radius), min(h, int(cy) + radius)
    patch = img_gray[y1:y2, x1:x2].copy()
    if patch.size < 9:
        return None
    hist = cv2.calcHist([patch], [0], None, [32], [0, 256]).flatten()
    hist = hist / (hist.sum() + 1e-8)
    return {'hist': hist, 'patch': patch.copy()}


def match_template(img_gray, x, y, template, radius=8):
    if template is None:
        return True
    h, w = img_gray.shape[:2]
    x1, x2 = max(0, int(x) - radius), min(w, int(x) + radius + 1)
    y1, y2 = max(0, int(y) - radius), min(h, int(y) + radius + 1)
    patch = img_gray[y1:y2, x1:x2]
    if patch.size < 9:
        return False
    hist = cv2.calcHist([patch], [0], None, [32], [0, 256]).flatten()
    hist = hist / (hist.sum() + 1e-8)
    corr = cv2.compareHist(template['hist'].astype(np.float32),
                           hist.astype(np.float32), cv2.HISTCMP_CORREL)
    ref = template.get('patch')
    if ref is not None and ref.size > 0:
        area_ratio = float(patch.size) / float(ref.size)
    else:
        area_ratio = 1.0
    return corr > 0.5 and 0.3 < area_ratio < 3.0


def trace_backward(cap, anchor_f, anchor_x, anchor_y, total):
    """Trace backward from anchor, returning list of (frame, x, y)."""
    cap.set(cv2.CAP_PROP_POS_FRAMES, anchor_f)
    ret, img0 = cap.read()
    if not ret:
        return []
    gray0 = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
    hsv0 = cv2.cvtColor(img0, cv2.COLOR_BGR2HSV)
    if not check_color(hsv0, anchor_x, anchor_y):
        return []
    template = extract_template(gray0, anchor_x, anchor_y, radius=8)
    if template is None:
        return []

    pts = np.array([[[float(anchor_x), float(anchor_y)]]], dtype=np.float32)
    gray_prev = gray0
    backward = []

    for df in range(1, min(BWD_WIN, anchor_f + 1)):
        fi = anchor_f - df
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ret, img = cap.read()
        if not ret:
            break
        gf = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        np2, st, _ = cv2.calcOpticalFlowPyrLK(gray_prev, gf, pts, None,
            winSize=(15, 15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
        if st[0, 0] == 1:
            nx, ny = float(np2[0, 0, 0]), float(np2[0, 0, 1])
            hf = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            if check_color(hf, nx, ny) and match_template(gf, nx, ny, template):
                if abs(nx - float(pts[0, 0, 0])) < MAX_JUMP and abs(ny - float(pts[0, 0, 1])) < MAX_JUMP:
                    backward.append((fi, nx, ny))
                    pts = np2.reshape(1, 1, 2)
                    gray_prev = gf
                    continue
            elif len(backward) > 3:
                break
            break
        else:
            break

    return backward


def draw_overlay(img, backward_pts, anchor_x, anchor_y, label=""):
    """Draw backward corridor overlay on image."""
    vis = img.copy()
    # Draw basket positions
    cv2.circle(vis, (int(BLX), int(BLY)), 8, (0, 0, 255), 2)
    cv2.circle(vis, (int(BRX), int(BRY)), 8, (0, 0, 255), 2)

    # Build point list: backward_pts are (frame, x, y); append anchor
    all_pts = list(backward_pts) + [(0, anchor_x, anchor_y)]

    # Draw corridor line (faded to bright)
    n = len(all_pts)
    for i in range(1, len(all_pts)):
        alpha = int(255 * i / n)
        color = (0, alpha, 255 - alpha)  # green->yellow
        p1 = (int(all_pts[i-1][1]), int(all_pts[i-1][2]))
        p2 = (int(all_pts[i][1]), int(all_pts[i][2]))
        cv2.line(vis, p1, p2, color, 2)

    # Draw points
    for fi, fx, fy in all_pts:
        cv2.circle(vis, (int(fx), int(fy)), 3, (0, 255, 255), -1)

    # Anchor highlight
    cv2.circle(vis, (int(anchor_x), int(anchor_y)), 6, (0, 0, 255), 2)

    if label:
        cv2.putText(vis, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    return vis


def main():
    df = pd.read_csv(CSV_IN)

    # Filter to rows with valid emergence
    mask = df['emergence_n_points'].notna() & (df['emergence_n_points'] > 0)
    df_valid = df[mask].copy()
    print(f"Processing {len(df_valid)} valid shot events...")

    cap = cv2.VideoCapture(VIDEO)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    os.makedirs(OUT_DIR, exist_ok=True)

    # Save index
    rows = []

    for _, row in df_valid.iterrows():
        f = int(row['frame'])
        cx, cy = float(row['anchor_px']), 0  # We'll use the stored origin as anchor

        # Re-read the actual ball position from the video at anchor frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img_anchor = cap.read()
        if not ret:
            print(f"  F{f}: FAIL - couldn't read frame")
            continue

        # Trace backward
        # Use center of frame as fallback anchor if needed
        ax, ay = 640, 360  # default center

        # Try to find ball using color detection
        hsv = cv2.cvtColor(img_anchor, cv2.COLOR_BGR2HSV)
        ball_mask = (hsv[:,:,0] >= 2) & (hsv[:,:,0] <= 32) & (hsv[:,:,1] >= 10)
        contours, _ = cv2.findContours(ball_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Find the largest orange contour near expected ball regions
        best = None
        best_area = 0
        for c in contours:
            area = cv2.contourArea(c)
            if area > 5 and area > best_area:
                M = cv2.moments(c)
                if M['m00'] > 0:
                    bx = M['m10'] / M['m00']
                    by = M['m01'] / M['m00']
                    # Check if within reasonable range of either basket
                    d_l = np.sqrt((bx - BLX)**2 + (by - BLY)**2)
                    d_r = np.sqrt((bx - BRX)**2 + (by - BRY)**2)
                    if d_l < 250 or d_r < 250:
                        best = (bx, by)
                        best_area = area

        if best:
            ax, ay = best
            print(f"  F{f}: ball detected at ({ax:.0f}, {ay:.0f})")
        else:
            print(f"  F{f}: using stored origin as anchor")
            # Use stored anchor position
            if pd.notna(row.get('origin')):
                origin_str = str(row['origin'])
                if ',' in origin_str:
                    parts = origin_str.strip('()').split(',')
                    ax, ay = float(parts[0]), float(parts[1])

        backward = trace_backward(cap, f, ax, ay, total)
        print(f"  F{f}: {len(backward)} backward points")

        # Save thumbnail
        thumb_path = os.path.join(OUT_DIR, f'F{f:04d}_thumb.jpg')
        cv2.imwrite(thumb_path, img_anchor)

        # Save overlay
        make_miss = row.get('make_miss', '?')
        sector = row.get('origin_sector', '?')
        dist = row.get('origin_distance_ft', '?')
        lat = row.get('origin_lateral_ft', '?')
        stab = row.get('corridor_stability', '?')
        label = f"F{f} {make_miss} {sector} dist={dist}ft lat={lat}ft stab={stab}"
        vis = draw_overlay(img_anchor, backward, ax, ay, label)
        overlay_path = os.path.join(OUT_DIR, f'F{f:04d}_corridor.jpg')
        cv2.imwrite(overlay_path, vis)

        rows.append({
            'frame': f,
            'make_miss': make_miss,
            'sector': sector,
            'dist_ft': dist,
            'lat_ft': lat,
            'stab': stab,
            'n_back': len(backward),
            'thumb': thumb_path,
            'overlay': overlay_path,
        })

    cap.release()

    # Save audit index
    audit_df = pd.DataFrame(rows)
    audit_path = os.path.join(OUT_DIR, 'audit_index.csv')
    audit_df.to_csv(audit_path, index=False)
    print(f"\nSaved audit index to {audit_path}")
    print(f"Total: {len(audit_df)} events with overlays")


if __name__ == '__main__':
    main()
