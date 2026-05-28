#!/usr/bin/env python3
"""v38: Shot filter.

Rejects events where the ball is not on an approaching shot trajectory toward the basket.
Uses only NN detections + geometry — no color, no pose estimation.

Filter criteria:
1. APPROACH: Ball must be getting closer to the basket over the window
   (distance to basket decreasing from start to anchor)
2. RANGE: Ball must be within shooting distance of basket at anchor (< 250px)
3. STATIONARY REJECT: Ball must move minimum total distance (> 30px over window)
4. FT LINE REJECT: Ball near FT line (y range) with low motion = FT setup
5. BASELINE REJECT: Ball moving parallel to baseline (high lateral, low depth change)
6. MIDCOURT REJECT: Ball too far from both baskets (> 400px) at anchor
"""
import os, pickle, cv2
import numpy as np
import pandas as pd

PKL_V14 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl'
CSV_V37 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v37.csv'
CSV_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v38_filtered.csv'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0


def nearest_basket_dist(x, y):
    dl = np.sqrt((x - BLX)**2 + (y - BLY)**2)
    dr = np.sqrt((x - BRX)**2 + (y - BRY)**2)
    return min(dl, dr)


def shot_filter(f, bx, by, total):
    """Return (pass: bool, reason: str) for whether this frame is a real shot candidate."""
    BWD, FWD = 15, 20
    f_start = max(0, f - BWD)
    f_end = min(total, f + FWD + 1)

    win_x = bx[f_start:f_end]
    win_y = by[f_start:f_end]
    valid = ~np.isnan(win_x) & ~np.isnan(win_y)

    if np.sum(valid) < 3:
        return False, "too_few_detections"

    valid_idx = np.where(valid)[0]
    fx = win_x[valid]
    fy = win_y[valid]
    frames = f_start + valid_idx

    # Anchor position
    anchor_local = int(np.argmin(np.abs(valid_idx - (f - f_start))))
    ax, ay = fx[anchor_local], fy[anchor_local]
    d_anchor = nearest_basket_dist(ax, ay)

    # 6. MIDCOURT REJECT: anchor too far from both baskets
    if d_anchor > 400:
        return False, "midcourt"

    # 1. APPROACH: is ball getting closer to basket over time?
    dists = np.array([nearest_basket_dist(x, y) for x, y in zip(fx, fy)])
    # Compare first third to last third
    n = len(dists)
    early_dist = np.mean(dists[:max(n//3, 1)])
    late_dist = np.mean(dists[-max(n//3, 1):])
    approach = early_dist - late_dist  # positive = getting closer

    if approach < -20:  # ball moving AWAY from basket
        return False, "moving_away"

    # 2. RANGE: anchor within shooting distance
    if d_anchor > 250:
        return False, "out_of_range"

    # 3. STATIONARY REJECT: minimum total movement
    if n >= 2:
        total_movement = np.sum(np.sqrt(np.diff(fx)**2 + np.diff(fy)**2))
    else:
        total_movement = 0

    if total_movement < 30:
        return False, "stationary"

    # 4. FT LINE REJECT: near FT line with low radial motion
    # FT line is roughly y=440-530 in this camera view, x near the key
    # Simplified: if ball is within the rectangle of the key area and not approaching strongly
    in_key_x = 150 < ax < 1050
    in_key_y = 400 < ay < 600
    if in_key_x and in_key_y and approach < 10 and total_movement < 50:
        return False, "ft_setup"

    # 5. BASELINE REJECT: moving mostly lateral AND not approaching basket
    if n >= 3:
        dx_total = abs(fx[-1] - fx[0])
        dy_total = abs(fy[-1] - fy[0])
        # Only reject if mostly lateral AND not showing approach
        if dy_total > 0 and dx_total / dy_total > 4 and approach < 15:
            return False, "lateral_no_approach"
        # Also reject if very far from basket and moving laterally
        if d_anchor > 200 and dx_total > 3 * dy_total:
            return False, "far_lateral"

    # 7. INBOUND REJECT: ball starts very near basket (referee holding it)
    if dists[0] < 80 and approach > 100:
        # Ball was under/near basket, now moving away = inbound/dead ball
        return False, "inbound_play"

    # Passed all filters
    filter_info = {
        'filter_pass': True,
        'filter_reason': 'SHOT_CANDIDATE',
        'approach_dist': round(approach, 1),
        'anchor_dist': round(d_anchor, 1),
        'total_movement': round(total_movement, 1),
        'n_detections': n,
    }
    return True, filter_info


def main():
    df37 = pd.read_csv(CSV_V37)

    with open(PKL_V14, 'rb') as f:
        v14 = pickle.load(f)
    bx, by = v14['ball_x'], v14['ball_y']
    total = len(bx)

    results = []

    for _, row in df37.iterrows():
        f = int(row['frame'])
        if f >= total or np.isnan(bx[f]):
            continue

        # Apply shot filter
        is_shot, info = shot_filter(f, bx, by, total)

        result = dict(row)
        if isinstance(info, dict):
            result.update(info)
        else:
            if not is_shot:
                result['filter_pass'] = False
                result['filter_reason'] = info
            else:
                result['filter_pass'] = True
                result['filter_reason'] = 'SHOT_CANDIDATE'

        results.append(result)

        status = "SHOT" if result['filter_pass'] else "REJECTED ({})".format(result['filter_reason'])
        print("  F{}: {} d_anchor={} approach={} movement={}".format(
            f, status,
            result.get('anchor_dist', '?'),
            result.get('approach_dist', '?'),
            result.get('total_movement', '?')))

    if results:
        df_out = pd.DataFrame(results)
        df_out.to_csv(CSV_OUT, index=False)
        n_shot = df_out['filter_pass'].sum()
        print("\n{}/{} events pass shot filter".format(n_shot, len(df_out)))
        print("Saved to {}".format(CSV_OUT))


if __name__ == '__main__':
    main()
