#!/usr/bin/env python3
"""visual_audit_v3.py — Use v14 tracked positions directly as the corridor.

Instead of re-running OF (which wanders), use the v14 ball_x/ball_y arrays
to plot the actual tracked trajectory through each anchor frame.
"""
import os, pickle, cv2
import numpy as np
import pandas as pd

VIDEO   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
PKL_V14 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl'
CSV_V34 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v34.csv'
OUT_DIR = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/audit_v35c'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0

FWD_WIN, BWD_WIN = 20, 15


def draw_track(img, track_x, track_y, anchor_idx, label="", color_fwd=(0,0,255), color_bwd=(255,0,0)):
    """Draw tracked positions on image. track_x, track_y are arrays of pixel positions."""
    vis = img.copy()
    h, w = vis.shape[:2]

    # Basket marks
    cv2.circle(vis, (int(BLX), int(BLY)), 12, (0, 0, 255), 2)
    cv2.circle(vis, (int(BRX), int(BRY)), 12, (0, 0, 255), 2)

    n = len(track_x)
    if n < 2:
        return vis

    # Draw track segments
    for i in range(1, n):
        progress = i / (n - 1)
        if i <= anchor_idx:
            # Backward: blue -> green
            t = i / max(anchor_idx, 1)
            color = (int(255 * (1-t)), int(255 * t), 0)
        else:
            # Forward: green -> red
            t = (i - anchor_idx) / max(n - anchor_idx, 1)
            color = (0, int(255 * (1-t)), int(255 * t))
        p1 = (int(track_x[i-1]), int(track_y[i-1]))
        p2 = (int(track_x[i]), int(track_y[i]))
        cv2.line(vis, p1, p2, color, 3)

    # Draw points
    for fx, fy in zip(track_x, track_y):
        cv2.circle(vis, (int(fx), int(fy)), 4, (0, 255, 255), -1)

    # Highlight anchor
    ax_a, ay_a = int(track_x[anchor_idx]), int(track_y[anchor_idx])
    cv2.circle(vis, (ax_a, ay_a), 10, (0, 0, 255), 3)

    # Label
    if label:
        cv2.rectangle(vis, (5, 5), (len(label)*9 + 15, 35), (0, 0, 0), -1)
        cv2.putText(vis, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

    info = f'track={n}f back={anchor_idx} fwd={n-anchor_idx-1}'
    cv2.putText(vis, info, (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    return vis


def main():
    df34 = pd.read_csv(CSV_V34)

    with open(PKL_V14, 'rb') as f:
        v14 = pickle.load(f)
    ball_x, ball_y = v14['ball_x'], v14['ball_y']
    total = len(ball_x)

    # Filter to valid events
    mask = df34['emergence_n_points'].notna() & (df34['emergence_n_points'] > 0)
    df_valid = df34[mask].copy()
    print(f"Valid events: {len(df_valid)}")

    cap = cv2.VideoCapture(VIDEO)
    os.makedirs(OUT_DIR, exist_ok=True)

    for _, row in df_valid.iterrows():
        f = int(row['frame'])

        if f >= total or np.isnan(ball_x[f]):
            print(f"  F{f}: no v14 position")
            continue

        # Extract v14 track window around anchor
        f_start = max(0, f - BWD_WIN)
        f_end = min(total, f + FWD_WIN + 1)

        # Get valid (non-NaN) positions in this window
        win_x = ball_x[f_start:f_end].copy()
        win_y = ball_y[f_start:f_end].copy()

        valid = ~np.isnan(win_x) & ~np.isnan(win_y)
        if np.sum(valid) < 5:
            print(f"  F{f}: too few valid track points ({np.sum(valid)})")
            continue

        track_x = win_x[valid]
        track_y = win_y[valid]

        # Anchor is at index (f - f_start), but only count valid points before it
        anchor_valid_idx = int(np.sum(valid[:f - f_start]))

        # Clamp
        anchor_valid_idx = max(0, min(anchor_valid_idx, len(track_x) - 1))

        print(f"  F{f}: v14 track {len(track_x)} pts, anchor_idx={anchor_valid_idx}")
        print(f"    ball at ({track_x[anchor_valid_idx]:.0f}, {track_y[anchor_valid_idx]:.0f})")

        # Read frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret:
            continue

        # Draw
        make_miss = row.get('make_miss', '?')
        sector = row.get('origin_sector', '?')
        dist_ft = row.get('origin_distance_ft', '?')
        lat_ft = row.get('origin_lateral_ft', '?')
        stab = row.get('corridor_stability', '?')
        label = f'F{f} {make_miss} {sector} d={dist_ft} lat={lat_ft} stab={stab}'

        vis = draw_track(img, track_x, track_y, anchor_valid_idx, label)

        path = os.path.join(OUT_DIR, f'F{f:04d}_corridor.jpg')
        cv2.imwrite(path, vis)

        # Zoomed thumbnail around track
        margin = 80
        x1c = max(0, int(np.min(track_x)) - margin)
        y1c = max(0, int(np.min(track_y)) - margin)
        x2c = min(img.shape[1], int(np.max(track_x)) + margin)
        y2c = min(img.shape[0], int(np.max(track_y)) + margin)
        if x2c > x1c and y2c > y1c:
            zoom = vis[y1c:y2c, x1c:x2c]
            zoom_path = os.path.join(OUT_DIR, f'F{f:04d}_zoom.jpg')
            cv2.imwrite(zoom_path, zoom)

        print(f"    saved")

    cap.release()
    print(f"\nDone. Output in {OUT_DIR}/")


if __name__ == '__main__':
    main()
