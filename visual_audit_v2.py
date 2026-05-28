#!/usr/bin/env python3
"""visual_audit_v2.py — Use v14 tracked ball positions + re-track from correct anchors.

For each valid shot event, seeds the bidirectional OF track from the v14
ball position (not color detection) and draws the corridor overlay.
"""
import os, pickle, cv2
import numpy as np
import pandas as pd

VIDEO  = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
PKL_V14 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl'
PKL_V8  = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v8.pkl'
CSV_V34 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v34.csv'
OUT_DIR = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/audit_v35b'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0

FWD_WIN, BWD_WIN = 20, 15
MAX_JUMP = 80
MAKE_R = 55


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


def track_bidir_from(cap, fnum, cx, cy, total):
    """Bidirectional OF track seeded from known ball position."""
    cap.set(cv2.CAP_PROP_POS_FRAMES, fnum)
    ret, img0 = cap.read()
    if not ret:
        return []
    gray0 = cv2.cvtColor(img0, cv2.COLOR_BGR2GRAY)
    hsv0 = cv2.cvtColor(img0, cv2.COLOR_BGR2HSV)
    if not check_color(hsv0, cx, cy):
        return []
    template = extract_template(gray0, cx, cy, radius=8)
    if template is None:
        return []

    # Backward
    pts = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
    gray_prev = gray0
    backward = []
    for f in range(fnum - 1, max(fnum - BWD_WIN, 0), -1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret: break
        gf = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        np2, st, _ = cv2.calcOpticalFlowPyrLK(gray_prev, gf, pts, None,
            winSize=(15,15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
        if st[0, 0] == 1:
            nx, ny = float(np2[0, 0, 0]), float(np2[0, 0, 1])
            hf = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            if check_color(hf, nx, ny) and match_template(gf, nx, ny, template):
                if abs(nx - float(pts[0, 0, 0])) < MAX_JUMP and abs(ny - float(pts[0, 0, 1])) < MAX_JUMP:
                    backward.append((f, nx, ny))
                    pts = np2.reshape(1, 1, 2)
                    gray_prev = gf
                    continue
        gray_prev = gf

    # Forward
    pts = np.array([[[float(cx), float(cy)]]], dtype=np.float32)
    gray_prev = gray0
    forward = []
    for f in range(fnum + 1, min(fnum + FWD_WIN, total)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret: break
        gf = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        np2, st, _ = cv2.calcOpticalFlowPyrLK(gray_prev, gf, pts, None,
            winSize=(15,15), maxLevel=2,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 10, 0.03))
        if st[0, 0] == 1:
            nx, ny = float(np2[0, 0, 0]), float(np2[0, 0, 1])
            hf = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            if check_color(hf, nx, ny) and match_template(gf, nx, ny, template):
                if abs(nx - float(pts[0, 0, 0])) < MAX_JUMP and abs(ny - float(pts[0, 0, 1])) < MAX_JUMP:
                    forward.append((f, nx, ny))
                    pts = np2.reshape(1, 1, 2)
                    gray_prev = gf
                    continue
        gray_prev = gf

    return backward[::-1] + [(fnum, float(cx), float(cy))] + forward


def draw_corridor_on_frame(img, track, make_miss, sector, dist_ft, lat_ft, stab, frame_num):
    """Draw clean corridor overlay on frame."""
    vis = img.copy()
    h, w = vis.shape[:2]

    # Basket marks
    cv2.circle(vis, (int(BLX), int(BLY)), 12, (0, 0, 255), 2)
    cv2.circle(vis, (int(BRX), int(BRY)), 12, (0, 0, 255), 2)
    cv2.putText(vis, 'L', (int(BLX)-4, int(BLY)-16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,255), 1)
    cv2.putText(vis, 'R', (int(BRX)-4, int(BRY)-16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0,0,255), 1)

    if not track or len(track) < 2:
        cv2.putText(vis, f'F{frame_num} NO TRACK', (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        return vis

    xs = np.array([x for _, x, y in track])
    ys = np.array([y for _, x, y in track])
    n = len(track)

    # Find anchor (closest to either basket)
    dl = np.sqrt((xs - BLX)**2 + (ys - BLY)**2)
    dr = np.sqrt((xs - BRX)**2 + (ys - BRY)**2)
    anchor_idx = int(np.argmin(np.minimum(dl, dr)))

    # Draw track segments with gradient
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
        p1 = (int(xs[i-1]), int(ys[i-1]))
        p2 = (int(xs[i]), int(ys[i]))
        cv2.line(vis, p1, p2, color, 3)

    # Draw all track points
    for fx, fy in zip(xs, ys):
        cv2.circle(vis, (int(fx), int(fy)), 4, (0, 255, 255), -1)

    # Highlight anchor
    ax_a, ay_a = int(xs[anchor_idx]), int(ys[anchor_idx])
    cv2.circle(vis, (ax_a, ay_a), 10, (0, 0, 255), 3)

    # Label
    label = f'F{frame_num} {make_miss} {sector} d={dist_ft}ft lat={lat_ft}ft stab={stab}'
    cv2.rectangle(vis, (5, 5), (len(label)*9 + 15, 35), (0, 0, 0), -1)
    cv2.putText(vis, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

    # Track stats
    track_info = f'track={n}f back={anchor_idx} fwd={n-anchor_idx-1}'
    cv2.putText(vis, track_info, (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

    return vis


def main():
    # Load data
    df34 = pd.read_csv(CSV_V34)

    with open(PKL_V14, 'rb') as f:
        v14 = pickle.load(f)
    ball_x, ball_y = v14['ball_x'], v14['ball_y']
    total = len(ball_x)

    with open(PKL_V8, 'rb') as f:
        v8 = pickle.load(f)

    # Filter to valid events
    mask = df34['emergence_n_points'].notna() & (df34['emergence_n_points'] > 0)
    df_valid = df34[mask].copy()
    print(f"Valid events: {len(df_valid)}")

    cap = cv2.VideoCapture(VIDEO)
    os.makedirs(OUT_DIR, exist_ok=True)

    for _, row in df_valid.iterrows():
        f = int(row['frame'])

        # Use v14 tracked ball position
        if f >= total or np.isnan(ball_x[f]):
            print(f"  F{f}: no v14 position, skipping")
            continue

        cx, cy = float(ball_x[f]), float(ball_y[f])
        print(f"  F{f}: v14 ball at ({cx:.0f}, {cy:.0f})")

        # Track bidirectionally from correct seed
        track = track_bidir_from(cap, f, cx, cy, total)
        print(f"    track_len={len(track)}")

        # Read anchor frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret:
            continue

        # Draw overlay
        make_miss = row.get('make_miss', '?')
        sector = row.get('origin_sector', '?')
        dist_ft = row.get('origin_distance_ft', '?')
        lat_ft = row.get('origin_lateral_ft', '?')
        stab = row.get('corridor_stability', '?')

        vis = draw_corridor_on_frame(img, track, make_miss, sector, dist_ft, lat_ft, stab, f)
        path = os.path.join(OUT_DIR, f'F{f:04d}_corridor.jpg')
        cv2.imwrite(path, vis)
        print(f"    saved {path}")

        # Also save a zoomed thumbnail around the track
        if track and len(track) >= 2:
            xs = [x for _, x, y in track]
            ys = [y for _, x, y in track]
            margin = 80
            x1clip = max(0, int(min(xs)) - margin)
            y1clip = max(0, int(min(ys)) - margin)
            x2clip = min(img.shape[1], int(max(xs)) + margin)
            y2clip = min(img.shape[0], int(max(ys)) + margin)
            if x2clip > x1clip and y2clip > y1clip:
                thumb = img[y1clip:y2clip, x1clip:x2clip]
                thumb_vis = vis[y1clip:y2clip, x1clip:x2clip]
                thumb_path = os.path.join(OUT_DIR, f'F{f:04d}_thumb.jpg')
                cv2.imwrite(thumb_path, thumb)
                thumb_overlay_path = os.path.join(OUT_DIR, f'F{f:04d}_thumb_overlay.jpg')
                cv2.imwrite(thumb_overlay_path, thumb_vis)

    cap.release()
    print(f"\nDone. Output in {OUT_DIR}/")


if __name__ == '__main__':
    main()
