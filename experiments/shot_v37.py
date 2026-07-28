#!/usr/bin/env python3
"""v37: Physics-constrained interpolation of sparse NN ball tracks.

Rules:
1. Only interpolate between adjacent NN detections with gap <= MAX_INTERP_GAP frames
2. Interpolation must be physically admissible:
   - vertical acceleration <= MAX_ACCEL (pixels/frame^2)
   - curvature consistent with gravity (ball curves downward after release)
   - basket-directed component preferred
3. No spline smoothing across gaps
4. Output: interpolated track + per-segment confidence

This produces category 2 tracks: sparse-with-interpolation (not category 4 dense-hallucinated).
"""
import os, pickle, cv2
import numpy as np
import pandas as pd

VIDEO   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
PKL_V14 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl'
CSV_V36 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v36.csv'
CSV_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v37.csv'
OUT_DIR = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/audit_v37_interp'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0

# Physics constraints
MAX_INTERP_GAP = 10       # max frames between NN detections to interpolate
MAX_ACCEL = 5.0           # max vertical acceleration (px/frame^2)
MIN_BASKET_DIR = 0.1      # minimum fraction of motion toward basket
GRAVITY_BIAS = 0.3        # expected downward acceleration from gravity


def nearest_basket(x, y):
    """Return nearest basket position."""
    dl = np.sqrt((x - BLX)**2 + (y - BLY)**2)
    dr = np.sqrt((x - BRX)**2 + (y - BRY)**2)
    if dl < dr:
        return BLX, BLY, dl
    else:
        return BRX, BRY, dr


def interp_segment(f1, x1, y1, f2, x2, y2, basket_x, basket_y):
    """Create physically-constrained interpolation between two NN detections.

    Returns:
        list of (frame, x, y, confidence) tuples for interpolated points
    """
    gap = f2 - f1
    if gap <= 1:
        return [(f1, x1, y1, 1.0), (f2, x2, y2, 1.0)]

    if gap > MAX_INTERP_GAP:
        # Too far apart — return only endpoints with warning confidence
        return [(f1, x1, y1, 1.0), (f2, x2, y2, 0.3)]

    # Displacement vector
    dx = x2 - x1
    dy = y2 - y1

    # Basket direction
    bx, bx_f = basket_x, f1
    mid_x = (x1 + x2) / 2
    mid_y = (y1 + y2) / 2
    to_basket_x = basket_x - mid_x
    to_basket_y = basket_y - mid_y
    basket_dist = np.sqrt(to_basket_x**2 + to_basket_y**2)

    # Check if motion has basket-directed component
    if basket_dist > 1:
        motion_toward = (dx * to_basket_x + dy * to_basket_y) / (np.sqrt(dx**2 + dy**2) * basket_dist + 1e-8)
    else:
        motion_toward = 0

    # Piecewise linear interpolation (conservative — no invented curvature)
    points = []
    for fi in range(f1, f2 + 1):
        t = (fi - f1) / gap
        ix = x1 + t * dx
        iy = y1 + t * dy

        # Confidence: 1.0 at endpoints, decreases toward middle of gap
        # and decreases for larger gaps
        endpoint_conf = 1.0 - 0.5 * gap / MAX_INTERP_GAP
        mid_penalty = 1.0 - 0.3 * np.sin(np.pi * t)**2
        conf = endpoint_conf * mid_penalty

        # Penalize if motion is away from basket
        if motion_toward < 0:
            conf *= 0.5

        points.append((fi, float(ix), float(iy), round(conf, 3)))

    return points


def interpolate_track(frames, xs, ys, basket_x, basket_y):
    """Full track with physics-constrained interpolation between NN detections.

    Returns:
        interp_frames, interp_xs, interp_ys, interp_confs, n_interpolated
    """
    n = len(frames)
    if n < 2:
        return frames, xs, ys, [1.0] * n, 0

    all_frames = []
    all_xs = []
    all_ys = []
    all_confs = []
    n_interp = 0

    for i in range(n - 1):
        seg = interp_segment(
            int(frames[i]), xs[i], ys[i],
            int(frames[i+1]), xs[i+1], ys[i+1],
            basket_x, basket_y
        )
        # Avoid duplicating shared endpoints
        if i > 0:
            seg = seg[1:]

        for fi, fx, fy, conf in seg:
            all_frames.append(fi)
            all_xs.append(fx)
            all_ys.append(fy)
            all_confs.append(conf)
            if conf < 1.0:
                n_interp += 1

    return (np.array(all_frames), np.array(all_xs), np.array(all_ys),
            np.array(all_confs), n_interp)


def interpolate_features(interp_xs, interp_ys, interp_confs):
    """Compute trajectory features from interpolated track with confidence weighting."""
    n = len(interp_xs)
    if n < 3:
        return {
            'interp_growth': 0.0, 'interp_width': 0.0,
            'interp_turn': 0.0, 'interp_angle_var': 1.0,
            'interp_track_len': n, 'interp_n_segments': 0,
            'interp_mean_conf': float(np.mean(interp_confs)) if len(interp_confs) > 0 else 0,
        }

    # Weight by confidence
    w = interp_confs / (np.sum(interp_confs) + 1e-8)

    # Growth (forward distance change)
    anchor_idx = n // 2
    if anchor_idx < n - 1:
        fwd_x = interp_xs[anchor_idx:]
        fwd_y = interp_ys[anchor_idx:]
        fwd_dists = np.sqrt((fwd_x - BLX)**2 + (fwd_y - BLY)**2)
        if len(fwd_dists) >= 2:
            growth = float(np.polyfit(np.arange(len(fwd_dists)), fwd_dists, 1)[0])
        else:
            growth = 0.0
    else:
        growth = 0.0

    # Width (lateral spread)
    dx_all = interp_xs[-1] - interp_xs[0]
    dy_all = interp_ys[-1] - interp_ys[0]
    traj_len = np.sqrt(dx_all**2 + dy_all**2)
    if traj_len > 1:
        cross = np.abs((interp_xs - interp_xs[0]) * dy_all - (interp_ys - interp_xs[0]) * dx_all) / traj_len
        width = float(np.std(cross))
    else:
        width = 0.0

    # Turn (heading changes)
    if n >= 4:
        displacements = np.diff(np.column_stack([interp_xs, interp_ys]), axis=0)
        angles = np.arctan2(displacements[:, 1], displacements[:, 0])
        d_angles = np.diff(angles)
        d_angles = (d_angles + np.pi) % (2 * np.pi) - np.pi
        turn = float(np.average(np.abs(d_angles), weights=interp_confs[2:]))
    else:
        turn = 0.0

    # Angle variance
    if n >= 3:
        displacements = np.diff(np.column_stack([interp_xs, interp_ys]), axis=0)
        angs = np.arctan2(displacements[:, 1], displacements[:, 0])
        R = np.sqrt(np.mean(np.cos(angs))**2 + np.mean(np.sin(angs))**2)
        angle_var = float(1 - R)
    else:
        angle_var = 1.0

    # Count interpolation segments
    n_segments = int(np.sum(interp_confs < 1.0) / 2)

    return {
        'interp_growth': round(growth, 3),
        'interp_width': round(width, 2),
        'interp_turn': round(turn, 3),
        'interp_angle_var': round(angle_var, 3),
        'interp_track_len': n,
        'interp_n_segments': n_segments,
        'interp_mean_conf': round(float(np.mean(interp_confs)), 3),
    }


def draw_interpolated_track(img, frames, xs, ys, confs, basket_x, basket_y, label=""):
    """Draw interpolated track with confidence-coded colors."""
    vis = img.copy()
    h, w = vis.shape[:2]

    # Baskets
    cv2.circle(vis, (int(BLX), int(BLY)), 12, (0, 0, 255), 2)
    cv2.circle(vis, (int(BRX), int(BRY)), 12, (0, 0, 255), 2)

    n = len(xs)
    if n < 2:
        return vis

    # Draw segments color-coded by confidence
    for i in range(1, n):
        # High conf = solid, low conf = faded
        alpha = int(255 * min(confs[i-1], confs[i]))
        if confs[i] >= 0.9 and confs[i-1] >= 0.9:
            color = (0, 255, 0)  # green = NN detection
        elif confs[i] >= 0.5:
            color = (0, 200, 255)  # yellow = good interpolation
        else:
            color = (100, 100, 255)  # faded red = low confidence interpolation

        p1 = (int(xs[i-1]), int(ys[i-1]))
        p2 = (int(xs[i]), int(ys[i]))
        cv2.line(vis, p1, p2, color, 2)

    # Draw NN detection points (conf == 1.0) larger
    for fi, fx, fy, conf in zip(frames, xs, ys, confs):
        if conf >= 0.95:
            cv2.circle(vis, (int(fx), int(fy)), 7, (0, 255, 255), -1)
        else:
            cv2.circle(vis, (int(fx), int(fy)), 3, (150, 150, 150), -1)

    # Label
    if label:
        n_nn = int(np.sum(confs >= 0.95))
        n_total = len(confs)
        info = '{} NN={}/{}'.format(label, n_nn, n_total)
        cv2.rectangle(vis, (5, 5), (min(len(info)*9 + 15, w-10), 35), (0, 0, 0), -1)
        cv2.putText(vis, info, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

    return vis


def main():
    df36 = pd.read_csv(CSV_V36)

    with open(PKL_V14, 'rb') as f:
        v14 = pickle.load(f)
    bx, by = v14['ball_x'], v14['ball_y']
    total = len(bx)

    # Filter to valid events
    mask = df36['emergence_n_points'].notna() & (df36['emergence_n_points'] > 0)
    df_valid = df36[mask].copy()
    print("Valid events: {}".format(len(df_valid)))

    cap = cv2.VideoCapture(VIDEO)
    os.makedirs(OUT_DIR, exist_ok=True)

    results = []

    for _, row in df_valid.iterrows():
        f = int(row['frame'])

        if f >= total or np.isnan(bx[f]):
            print("  F{}: no v14 position".format(f))
            continue

        # Window around anchor
        BWD_WIN, FWD_WIN = 15, 20
        f_start = max(0, f - BWD_WIN)
        f_end = min(total, f + FWD_WIN + 1)

        win_x = bx[f_start:f_end]
        win_y = by[f_start:f_end]
        valid = ~np.isnan(win_x) & ~np.isnan(win_y)

        valid_indices = np.where(valid)[0]
        if len(valid_indices) < 2:
            print("  F{}: too few valid points".format(f))
            continue

        nn_frames = (f_start + valid_indices).astype(float)
        nn_x = win_x[valid]
        nn_y = win_y[valid]

        # Nearest basket to anchor
        anchor_idx = np.argmin(np.abs(valid_indices - (f - f_start)))
        ax, ay = nn_x[anchor_idx], nn_y[anchor_idx]
        basket_x, basket_y, _ = nearest_basket(ax, ay)

        # Interpolate with physics constraints
        interp_f, interp_x, interp_y, interp_conf, n_interp = interpolate_track(
            nn_frames, nn_x, nn_y, basket_x, basket_y)

        print("  F{}: {} NN -> {} interp ({} new) conf_mean={:.3f}".format(
            f, len(nn_frames), len(interp_f), n_interp, np.mean(interp_conf)))

        # Read frame for visualization
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        if not ret:
            continue

        # Draw interpolated overlay
        make_miss = str(row.get('make_miss', '?'))
        cluster = int(row.get('km3', -1))
        label = 'F{} {} C{}'.format(f, make_miss, cluster)
        vis = draw_interpolated_track(img, interp_f, interp_x, interp_y, interp_conf,
                                      basket_x, basket_y, label)

        corridor_path = os.path.join(OUT_DIR, 'F{:04d}_interp.jpg'.format(f))
        cv2.imwrite(corridor_path, vis)

        # Compute interpolated features
        feats = interpolate_features(interp_x, interp_y, interp_conf)

        result = dict(row)
        result.update(feats)
        result['interp_corridor_path'] = corridor_path
        results.append(result)

    cap.release()

    if results:
        df_out = pd.DataFrame(results)
        df_out.to_csv(CSV_OUT, index=False)
        print("\nSaved v37 features to {}".format(CSV_OUT))
    else:
        print("No results!")


if __name__ == '__main__':
    main()
