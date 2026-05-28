#!/usr/bin/env python3
"""v35: Extract richer trajectory features + visual audit.

For each shot event, computes from the bidirectional track:
  - growth: how much the ball moves away from basket (px/frame forward)
  - width: lateral spread of the corridor (std dev of lateral displacements)
  - turn: direction change consistency (angular variance proxy)
  - angle_var: variance of displacement angles along track
  - decay: how quickly forward tracking loses lock (fraction of successful frames)

Then saves frame thumbnail + corridor overlay per event.
"""
import os, pickle, cv2
import numpy as np
import pandas as pd

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
PKL_V14 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl'
PKL_V8  = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v8.pkl'
CSV_V34 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v34.csv'
CSV_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v35.csv'
OUT_DIR = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/audit_v35'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0

FWD_WIN, BWD_WIN = 20, 15
MAX_JUMP = 80
MIN_PTS = 10


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


def track_bidir(cap, fnum, cx, cy, total):
    """Bidirectional template-locked OF track from anchor."""
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


def compute_track_features(track, bx, by):
    """Compute richer features from a bidirectional track relative to basket (bx, by)."""
    if len(track) < 5:
        return None

    xs = np.array([x for _, x, y in track])
    ys = np.array([y for _, x, y in track])

    # Find anchor index (where distance to basket is minimized)
    dists = np.sqrt((xs - bx)**2 + (ys - by)**2)
    anchor_idx = int(np.argmin(dists))

    # === growth: rate of distance increase in forward direction ===
    if anchor_idx < len(track) - 2:
        fwd_dists = dists[anchor_idx:]
        fwd_frames = np.array([f for f, _, _ in track[anchor_idx:]])
        if len(fwd_dists) >= 3:
            # Linear fit: dist = a*frame + b
            if fwd_frames[-1] > fwd_frames[0]:
                growth = float(np.polyfit(fwd_frames, fwd_dists, 1)[0])
            else:
                growth = 0.0
        else:
            growth = 0.0
    else:
        growth = 0.0

    # === width: lateral spread perpendicular to main trajectory direction ===
    if len(track) >= 3:
        dx = xs[-1] - xs[0]
        dy = ys[-1] - ys[0]
        traj_len = np.sqrt(dx**2 + dy**2)
        if traj_len > 1:
            # Cross-track distance for each point
            cross = np.abs((xs - xs[0]) * dy - (ys - ys[0]) * dx) / traj_len
            width = float(np.std(cross))
        else:
            width = 0.0
    else:
        width = 0.0

    # === turn: how much the heading angle changes ===
    if len(track) >= 4:
        angles = []
        for i in range(2, len(track)):
            dx1 = xs[i-1] - xs[i-2]
            dy1 = ys[i-1] - ys[i-2]
            dx2 = xs[i] - xs[i-1]
            dy2 = ys[i] - ys[i-1]
            a1 = np.arctan2(dy1, dx1)
            a2 = np.arctan2(dy2, dx2)
            da = a2 - a1
            # Normalize to [-pi, pi]
            da = (da + np.pi) % (2 * np.pi) - np.pi
            angles.append(abs(da))
        turn = float(np.mean(angles))
    else:
        turn = 0.0

    # === angle_var: variance of displacement angles across the whole track ===
    if len(track) >= 3:
        displacements = np.diff(np.column_stack([xs, ys]), axis=0)
        angs = np.arctan2(displacements[:, 1], displacements[:, 0])
        # Circular variance
        R = np.sqrt(np.mean(np.cos(angs))**2 + np.mean(np.sin(angs))**2)
        angle_var = float(1 - R)  # 0=all same direction, 1=uniform
    else:
        angle_var = 1.0

    # === decay: fraction of forward frames that lost tracking ===
    max_fwd = min(FWD_WIN, int(track[-1][0]) - int(track[0][0]))
    actual_fwd = len(track) - 1 - anchor_idx
    if max_fwd > 0:
        decay = 1.0 - (actual_fwd / max_fwd)
    else:
        decay = 1.0

    return {
        'growth': round(float(growth), 3),
        'width': round(float(width), 2),
        'turn': round(float(turn), 3),
        'angle_var': round(float(angle_var), 3),
        'decay': round(float(decay), 3),
        'track_len': len(track),
        'anchor_idx': anchor_idx,
    }


def draw_overlay(img, track):
    """Draw full bidirectional track overlay."""
    vis = img.copy()
    h, w = vis.shape[:2]

    # Draw baskets
    cv2.circle(vis, (int(BLX), int(BLY)), 10, (0, 0, 255), 2)
    cv2.circle(vis, (int(BRX), int(BRY)), 10, (0, 0, 255), 2)

    if not track:
        return vis

    xs = [x for _, x, y in track]
    ys = [y for _, x, y in track]
    n = len(track)

    # Draw track line with gradient
    dists = np.sqrt((np.array(xs) - BLX)**2 + (np.array(ys) - BLY)**2)
    dists_r = np.sqrt((np.array(xs) - BRX)**2 + (np.array(ys) - BRY)**2)
    anchor_idx = int(np.argmin(np.minimum(dists, dists_r)))

    for i in range(1, n):
        # Color: blue->green for backward, green->red for forward
        if i <= anchor_idx:
            t = i / max(anchor_idx, 1)
            color = (255 * (1 - t), 255 * t, 0)
        else:
            t = (i - anchor_idx) / max(n - anchor_idx, 1)
            color = (0, 255 * (1 - t), 255 * t)
        p1 = (int(xs[i-1]), int(ys[i-1]))
        p2 = (int(xs[i]), int(ys[i]))
        cv2.line(vis, p1, p2, color, 2)

    # Draw points
    for fx, fy in zip(xs, ys):
        cv2.circle(vis, (int(fx), int(fy)), 3, (0, 255, 255), -1)

    # Highlight anchor (closest to basket)
    ax, ay = xs[anchor_idx], ys[anchor_idx]
    cv2.circle(vis, (int(ax), int(ay)), 8, (0, 0, 255), 2)

    return vis


def main():
    print("Loading v34 features...")
    df34 = pd.read_csv(CSV_V34)

    # Load v14 tracks for ball positions
    with open(PKL_V14, 'rb') as f:
        v14 = pickle.load(f)
    ball_x, ball_y = v14['ball_x'], v14['ball_y']
    total = len(ball_x)

    with open(PKL_V8, 'rb') as f:
        v8 = pickle.load(f)
    bl_x_arr, bl_y_arr = v8['basket_left']
    br_x_arr, br_y_arr = v8['basket_right']

    # Filter to rows with valid emergence data
    mask = df34['emergence_n_points'].notna() & (df34['emergence_n_points'] > 0)
    df_valid = df34[mask].copy()
    print(f"Valid events: {len(df_valid)}")

    cap = cv2.VideoCapture(VIDEO)
    os.makedirs(OUT_DIR, exist_ok=True)

    results = []

    for _, row in df_valid.iterrows():
        f = int(row['frame'])

        # Get ball position from v14 track
        if f < total and not np.isnan(ball_x[f]):
            cx, cy = float(ball_x[f]), float(ball_y[f])
        else:
            print(f"  F{f}: no v14 ball position, skipping")
            continue

        # Which basket is closest?
        d_l = np.sqrt((cx - BLX)**2 + (cy - BLY)**2)
        d_r = np.sqrt((cx - BRX)**2 + (cy - BRY)**2)
        bx, by = (BLX, BLY) if d_l < d_r else (BRX, BRY)

        # Bidirectional track
        track = track_bidir(cap, f, cx, cy, total)
        if len(track) < MIN_PTS:
            print(f"  F{f}: short track ({len(track)} pts)")
            continue

        feats = compute_track_features(track, bx, by)
        if feats is None:
            print(f"  F{f}: feature computation failed")
            continue

        # Scale to feet
        fi = int(f)
        if fi < len(bl_x_arr) and not np.isnan(bl_x_arr[fi]):
            bsep = np.sqrt((bl_x_arr[fi] - br_x_arr[fi])**2 + (bl_y_arr[fi] - br_y_arr[fi])**2)
            scale = bsep / 47.0 if bsep > 200 else 17.7
        else:
            scale = 17.7

        # Get anchor image
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret:
            continue

        # Save overlay
        vis = draw_overlay(img, track)
        overlay_path = os.path.join(OUT_DIR, f'F{f:04d}_corridor.jpg')
        cv2.imwrite(overlay_path, vis)

        # Save thumbnail (crop around track)
        xs = [x for _, x, y in track]
        ys = [y for _, x, y in track]
        margin = 60
        cx2 = int(np.mean(xs))
        cy2 = int(np.mean(ys))
        x1 = max(0, int(min(xs)) - margin)
        y1 = max(0, int(min(ys)) - margin)
        x2 = min(img.shape[1], int(max(xs)) + margin)
        y2 = min(img.shape[0], int(max(ys)) + margin)
        thumb = img[y1:y2, x1:x2]
        thumb_path = os.path.join(OUT_DIR, f'F{f:04d}_thumb.jpg')
        cv2.imwrite(thumb_path, thumb)

        # Merge with v34 features
        result = dict(row)
        result.update(feats)
        result['scale'] = round(scale, 1)
        result['overlay_path'] = overlay_path
        result['thumb_path'] = thumb_path
        results.append(result)

        print(f"  F{f}: track={feats['track_len']} growth={feats['growth']} "
              f"width={feats['width']} turn={feats['turn']} "
              f"angle_var={feats['angle_var']} decay={feats['decay']}")

    cap.release()

    if results:
        df_out = pd.DataFrame(results)
        df_out.to_csv(CSV_OUT, index=False)
        print(f"\nSaved {len(results)} enriched features to {CSV_OUT}")
    else:
        print("No results!")


if __name__ == '__main__':
    main()
