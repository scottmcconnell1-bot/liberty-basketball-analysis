#!/usr/bin/env python3
"""v36: Gap structure features + confidence dimensions + audit packets.

New features:
  - mean_gap_len: mean frame gap between consecutive NN detections
  - max_gap_len: largest frame gap in window
  - visibility_ratio: fraction of frames with valid NN detection
  - pre_anchor_visibility: fraction of backward frames with valid detection
  - post_anchor_visibility: fraction of forward frames with valid detection
  - detection_confidence: mean NN confidence in window (if available)
  - trajectory_certainty: visibility_ratio * (1 / (1 + max_gap_len))
  - corridor_certainty: detection_confidence * trajectory_certainty

Also builds audit packets for F1650/F1780.
"""
import os, pickle, cv2
import numpy as np
import pandas as pd

VIDEO   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
PKL_V14 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl'
PKL_V8  = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v8.pkl'
CSV_V35 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v35.csv'
CSV_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v36.csv'
OUT_DIR = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/audit_v36'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0
BWD_WIN, FWD_WIN = 15, 20


def compute_gap_features(valid_mask, anchor_idx):
    """Compute gap structure features from boolean validity mask."""
    n = len(valid_mask)
    frames = np.arange(n)
    valid_frames = frames[valid_mask]

    if len(valid_frames) < 2:
        return {
            'mean_gap_len': float(n),
            'max_gap_len': float(n),
            'visibility_ratio': float(np.sum(valid_mask)) / max(n, 1),
            'pre_anchor_visibility': 0.0,
            'post_anchor_visibility': 0.0,
            'n_valid': int(np.sum(valid_mask)),
            'trajectory_certainty': 0.0,
            'corridor_certainty': 0.0,
        }

    # Gap lengths between consecutive valid frames
    gaps = np.diff(valid_frames)
    mean_gap = float(np.mean(gaps))
    max_gap = float(np.max(gaps))

    # Visibility ratio
    vis_ratio = float(np.sum(valid_mask)) / max(n, 1)

    # Pre-anchor visibility
    pre_mask = valid_mask[:anchor_idx] if anchor_idx > 0 else np.array([False])
    pre_vis = float(np.sum(pre_mask)) / max(len(pre_mask), 1)

    # Post-anchor visibility
    post_mask = valid_mask[anchor_idx+1:] if anchor_idx < n-1 else np.array([False])
    post_vis = float(np.sum(post_mask)) / max(len(post_mask), 1)

    # Trajectory certainty: high visibility + low max gap = high certainty
    traj_certainty = vis_ratio * (1.0 / (1.0 + max_gap))

    return {
        'mean_gap_len': round(mean_gap, 1),
        'max_gap_len': int(max_gap),
        'visibility_ratio': round(vis_ratio, 3),
        'pre_anchor_visibility': round(pre_vis, 3),
        'post_anchor_visibility': round(post_vis, 3),
        'n_valid': int(np.sum(valid_mask)),
        'trajectory_certainty': round(traj_certainty, 3),
    }


def build_audit_packet(cap, f, bx, by, total, row, out_dir):
    """Build audit packet for a single event: corridor + stats + zoom."""
    f_start = max(0, f - BWD_WIN)
    f_end = min(total, f + FWD_WIN + 1)
    win_size = f_end - f_start

    win_x = bx[f_start:f_end]
    win_y = by[f_start:f_end]
    valid = ~np.isnan(win_x) & ~np.isnan(win_y)

    track_x = win_x[valid]
    track_y = win_y[valid]

    valid_indices = np.where(valid)[0]
    anchor_local = int(np.argmin(np.abs(valid_indices - (f - f_start))))
    anchor_local = max(0, min(anchor_local, len(track_x) - 1))

    # Read frame
    cap.set(cv2.CAP_PROP_POS_FRAMES, f)
    ret, img = cap.read()
    if not ret:
        return None

    vis = img.copy()
    h, w = vis.shape[:2]

    # Baskets
    cv2.circle(vis, (int(BLX), int(BLY)), 12, (0, 0, 255), 2)
    cv2.circle(vis, (int(BRX), int(BRY)), 12, (0, 0, 255), 2)

    # Draw NN detections
    for i, (fx, fy) in enumerate(zip(track_x, track_y)):
        fi_global = f_start + valid_indices[i]
        if i == anchor_local:
            cv2.circle(vis, (int(fx), int(fy)), 10, (0, 0, 255), 3)
            cv2.putText(vis, 'ANCHOR', (int(fx)+10, int(fy)-10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
        else:
            cv2.circle(vis, (int(fx), int(fy)), 6, (0, 255, 255), -1)
        cv2.putText(vis, str(fi_global), (int(fx)+5, int(fy)-5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.3, (200, 200, 200), 1)

    # Label with cluster + gap stats
    cluster = row.get('km3', '?')
    sector = row.get('origin_sector', '?')
    make_miss = row.get('make_miss', '?')
    stab = row.get('corridor_stability', '?')
    lat = row.get('origin_lateral_ft', '?')
    dist = row.get('origin_distance_ft', '?')

    label = 'F{} {} C{}({}) d={} lat={} stab={}'.format(
        f, make_miss, cluster, sector, dist, lat, stab)
    cv2.rectangle(vis, (5, 5), (min(len(label)*9 + 15, w-10), 70), (0, 0, 0), -1)
    cv2.putText(vis, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

    gap_label = 'NN: {}pts vis={:.0f}% gap_max={}'.format(
        int(np.sum(valid)), 100*np.sum(valid)/win_size, int(np.max(np.diff(valid_indices))) if len(valid_indices) > 1 else 0)
    cv2.putText(vis, gap_label, (10, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
    cv2.putText(vis, 'NN detections ONLY — no interpolation', (10, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (150, 150, 150), 1)

    # Save
    corridor_path = os.path.join(out_dir, 'F{:04d}_corridor.jpg'.format(f))
    cv2.imwrite(corridor_path, vis)

    # Zoomed around track
    if len(track_x) >= 2:
        margin = 100
        x1c = max(0, int(min(track_x)) - margin)
        y1c = max(0, int(min(track_y)) - margin)
        x2c = min(w, int(max(track_x)) + margin)
        y2c = min(h, int(max(track_y)) + margin)
        if x2c > x1c and y2c > y1c:
            zoom = vis[y1c:y2c, x1c:x2c]
            zoom_path = os.path.join(out_dir, 'F{:04d}_zoom.jpg'.format(f))
            cv2.imwrite(zoom_path, zoom)

    # Extract short clip around event (5 frames before to 10 after)
    clip_frames = []
    for fi in range(max(0, f-5), min(total, f+16)):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ret, cimg = cap.read()
        if ret:
            # Mark ball position if valid
            if fi - f_start >= 0 and fi - f_start < len(valid) and valid[fi - f_start]:
                bx_i = int(win_x[fi - f_start])
                by_i = int(win_y[fi - f_start])
                cv2.circle(cimg, (bx_i, by_i), 8, (0, 255, 255), 2)
            clip_frames.append(cimg)

    if clip_frames:
        clip_path = os.path.join(out_dir, 'F{:04d}_clip.mp4'.format(f))
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(clip_path, fourcc, 5, (clip_frames[0].shape[1], clip_frames[0].shape[0]))
        for cf in clip_frames:
            writer.write(cf)
        writer.release()

    return corridor_path


def main():
    df35 = pd.read_csv(CSV_V35)

    with open(PKL_V14, 'rb') as f:
        v14 = pickle.load(f)
    bx, by = v14['ball_x'], v14['ball_y']
    # Use ball_conf if available
    ball_conf = v14.get('ball_conf', None)
    total = len(bx)

    with open(PKL_V8, 'rb') as f:
        v8 = pickle.load(f)
    bl_x_arr, bl_y_arr = v8['basket_left']
    br_x_arr, br_y_arr = v8['basket_right']

    # Filter to valid events
    mask = df35['emergence_n_points'].notna() & (df35['emergence_n_points'] > 0)
    df_valid = df35[mask].copy()
    print("Valid events: {}".format(len(df_valid)))

    cap = cv2.VideoCapture(VIDEO)
    os.makedirs(OUT_DIR, exist_ok=True)

    audit_dir = os.path.join(OUT_DIR, 'audit_packets')
    os.makedirs(audit_dir, exist_ok=True)

    results = []

    for _, row in df_valid.iterrows():
        f = int(row['frame'])

        if f >= total or np.isnan(bx[f]):
            print("  F{}: no v14 position".format(f))
            continue

        # Window around anchor
        f_start = max(0, f - BWD_WIN)
        f_end = min(total, f + FWD_WIN + 1)
        win_size = f_end - f_start

        win_x = bx[f_start:f_end]
        win_y = by[f_start:f_end]
        valid = ~np.isnan(win_x) & ~np.isnan(win_y)

        valid_indices = np.where(valid)[0]
        if len(valid_indices) < 2:
            print("  F{}: too few valid points ({})".format(f, len(valid_indices)))
            continue

        anchor_idx = f - f_start
        # Find nearest valid to anchor
        anchor_local = int(np.argmin(np.abs(valid_indices - anchor_idx)))
        anchor_local = max(0, min(anchor_local, len(valid_indices) - 1))

        # Gap features
        gaps = compute_gap_features(valid, anchor_local)

        # Detection confidence (from v14 conf if available)
        if ball_conf is not None and f < len(ball_conf):
            det_conf = float(ball_conf[f]) if not np.isnan(ball_conf[f]) else 0.5
        else:
            det_conf = 0.5  # uniform prior

        corridor_conf = round(det_conf * gaps['trajectory_certainty'], 3)

        print("  F{}: {}pts vis={:.0f}% gap_mean={:.1f} gap_max={} traj_cert={:.3f}".format(
            f, gaps['n_valid'], 100*gaps['visibility_ratio'],
            gaps['mean_gap_len'], gaps['max_gap_len'], gaps['trajectory_certainty']))

        result = dict(row)
        result.update(gaps)
        result['detection_confidence'] = round(det_conf, 3)
        result['corridor_certainty'] = corridor_conf
        results.append(result)

        # Build audit packet
        packet_dir = os.path.join(audit_dir, 'F{:04d}'.format(f))
        os.makedirs(packet_dir, exist_ok=True)
        build_audit_packet(cap, f, bx, by, total, row, packet_dir)

    cap.release()

    if results:
        df_out = pd.DataFrame(results)
        df_out.to_csv(CSV_OUT, index=False)
        print("\nSaved v36 features to {}".format(CSV_OUT))
        print("Audit packets in {}".format(audit_dir))
    else:
        print("No results!")


if __name__ == '__main__':
    main()
