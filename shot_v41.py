#!/usr/bin/env python3
"""v41: Multi-class gameplay state classifier + rim engagement score.

State taxonomy (from Scott's visual audit):
  live_attack     - F0582 type: ball converging into rim space
  rim_attack      - ball in lane→rim funnel, terminal hoop approach
  rebound_scramble - post-rim dispersion, chaotic near basket
  transition      - ball advancing up court, no rim engagement
  dead_ball       - FT lineup, structured, stationary
  inbound         - under-basket reset
  FT_setup        - referee holding ball at FT line
  perimeter_circulation - ball moving around top/wings, no depth

Key new feature: rim_engagement_score
  - min_dist_to_rim: closest approach to basket center
  - monotonicity: fraction of frames where distance decreases
  - lane_occupancy: fraction of detections inside the lane/funnel
  - vertical_collapse: y-compression near rim plane
  - terminal_hoop: final detection within 2 rim-radii of hoop
  - post_rim_dispersion: high-variance positions after rim approach

Visibility bias correction:
  - High detection count in stationary contexts = dead ball, not shot
  - Long dwell time + structured spacing = FT setup, not shot
  - Low variance + low speed = possession state, not live attack
"""
import os, pickle, cv2
import numpy as np
import pandas as pd

PKL_V14 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl'
PKL_V8  = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v8.pkl'
CSV_V40 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_candidates_v40.csv'
CSV_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v41.csv'

# Basket/rim geometry
BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0
RIM_RADIUS = 45       # approximate rim radius in px
HOOP_ZONE = 90        # 2x rim radius for "terminates in hoop"
LANE_HALF_W = 100     # half-width of lane funnel from basket

# Y-coordinate of rim plane (approximate)
RIM_Y_LEFT = BLY     # ~525
RIM_Y_RIGHT = BRY    # ~466

BWD, FWD = 15, 20


def nd(x, y):
    """Distance to nearest basket."""
    dl = np.sqrt((x - BLX)**2 + (y - BLY)**2)
    dr = np.sqrt((x - BRX)**2 + (y - BRY)**2)
    return min(dl, dr)


def nearest_basket(x, y):
    dl = np.sqrt((x - BLX)**2 + (y - BLY)**2)
    dr = np.sqrt((x - BRX)**2 + (y - BRY)**2)
    if dl < dr:
        return BLX, BLY
    return BRX, BRY


def in_lane_funnel(x, y, basket_x, basket_y):
    """Check if position is inside the lane-to-rim funnel.

    The funnel extends from the basket outward toward halfcourt,
    narrowing from lane width to the rim.
    """
    dx = abs(x - basket_x)
    dy = y - basket_y  # signed: positive = below basket in frame

    # Funnel: within lane width when close to basket,
    # widens linearly with distance
    max_x_at_dist = LANE_HALF_W + 0.3 * abs(dy)
    return dx < max_x_at_dist and dy > -50


def compute_rim_engagement(fx, fy, basket_x, basket_y):
    """Compute rim engagement score and sub-features.

    High score = ball genuinely interacting with rim space.
    """
    n = len(fx)
    if n < 2:
        return {
            'rim_min_dist': 999, 'rim_monotonicity': 0.0,
            'rim_lane_occupancy': 0.0, 'rim_vertical_collapse': 0.0,
            'rim_terminal_hoop': False, 'rim_post_dispersion': 0.0,
            'rim_engagement_score': 0.0,
        }

    # Distance to nearest rim over time
    dists = np.array([np.sqrt((x - basket_x)**2 + (y - basket_y)**2)
                      for x, y in zip(fx, fy)])

    # Minimum approach distance
    min_dist = float(np.min(dists))

    # Monotonicity: fraction of consecutive frames showing decreasing distance
    if n >= 3:
        diffs = np.diff(dists)
        monotonicity = float(np.sum(diffs < 0) / len(diffs))
    else:
        monotonicity = 0.5

    # Lane occupancy: fraction of detections inside lane funnel
    in_lane = [in_lane_funnel(x, y, basket_x, basket_y) for x, y in zip(fx, fy)]
    lane_occupancy = float(np.sum(in_lane) / n)

    # Vertical collapse: how compressed are y-values near the end?
    if n >= 4:
        last_quarter = max(n // 4, 1)
        y_spread_early = float(np.std(fy[:-last_quarter])) if n > last_quarter else 1.0
        y_spread_late = float(np.std(fy[-last_quarter:]))
        # High ratio = collapse (spread decreases)
        if y_spread_late > 0:
            vertical_collapse = min(y_spread_early / y_spread_late, 5.0) / 5.0
        else:
            vertical_collapse = 1.0  # total collapse
    else:
        vertical_collapse = 0.0

    # Terminal hoop: final detection within hoop zone
    terminal_hoop = bool(dists[-1] < HOOP_ZONE)

    # Post-rim dispersion: variance of positions in last 3 detections
    if n >= 4:
        last3_x = fx[-3:]
        last3_y = fy[-3:]
        post_dispersion = float(np.std(last3_x) + np.std(last3_y)) / 2
        post_dispersion = min(post_dispersion / 50.0, 1.0)  # normalize
    else:
        post_dispersion = 0.0

    # Composite rim engagement score
    score = 0.0
    if min_dist < RIM_RADIUS * 2:    # Within 2 rim radii at closest
        score += 0.25
    elif min_dist < RIM_RADIUS * 4:
        score += 0.1

    score += 0.15 * monotonicity
    score += 0.15 * lane_occupancy
    score += 0.15 * vertical_collapse
    if terminal_hoop:
        score += 0.15
    if post_dispersion > 0.3:
        score += 0.10  # rebound-like dispersion

    return {
        'rim_min_dist': round(min_dist, 1),
        'rim_monotonicity': round(monotonicity, 3),
        'rim_lane_occupancy': round(lane_occupancy, 3),
        'rim_vertical_collapse': round(vertical_collapse, 3),
        'rim_terminal_hoop': terminal_hoop,
        'rim_post_dispersion': round(post_dispersion, 3),
        'rim_engagement_score': round(min(score, 1.0), 3),
    }


def compute_state_features(fx, fy, frames):
    """Features for multi-class state classification."""
    n = len(fx)
    if n < 2:
        return {
            'state_speed_mean': 0.0, 'state_speed_std': 0.0,
            'state_dwell_max': 0, 'state_stationary_ratio': 1.0,
            'state_spatial_spread': 0.0, 'state_direction_entropy': 0.0,
            'state_path_efficiency': 1.0,
            'state_height_variance': 0.0,
        }

    dt = np.diff(frames).astype(float)
    dt[dt == 0] = 1
    dx = np.diff(fx)
    dy = np.diff(fy)
    speeds = np.sqrt(dx**2 + dy**2) / dt

    # Speed stats
    speed_mean = float(np.mean(speeds))
    speed_std = float(np.std(speeds))

    # Dwell: max consecutive frames with < 5px movement
    dwells = []
    current = 0
    for s in speeds:
        if s < 5:
            current += 1
        else:
            if current > 0:
                dwells.append(current)
            current = 0
    if current > 0:
        dwells.append(current)
    dwell_max = max(dwells) if dwells else 0
    stationary_ratio = float(np.sum(speeds < 5) / len(speeds))

    # Spatial spread: area of bounding box
    x_range = float(np.max(fx) - np.min(fx))
    y_range = float(np.max(fy) - np.min(fy))
    spatial_spread = x_range * y_range / 10000.0  # normalize

    # Direction entropy
    angles = np.arctan2(dy, dx)
    R = np.sqrt(np.mean(np.cos(angles))**2 + np.mean(np.sin(angles))**2)
    dir_entropy = float(1 - R)

    # Path efficiency: direct distance / total path length
    path_length = float(np.sum(np.sqrt(dx**2 + dy**2)))
    if n >= 2 and path_length > 0:
        endpoint_dist = np.sqrt((fx[-1] - fx[0])**2 + (fy[-1] - fy[0])**2)
        path_eff = endpoint_dist / path_length
    else:
        path_eff = 1.0

    # Height variance (y-variance)
    height_var = float(np.var(fy)) / 1000.0

    return {
        'state_speed_mean': round(speed_mean, 2),
        'state_speed_std': round(speed_std, 2),
        'state_dwell_max': dwell_max,
        'state_stationary_ratio': round(stationary_ratio, 3),
        'state_spatial_spread': round(spatial_spread, 2),
        'state_direction_entropy': round(dir_entropy, 3),
        'state_path_efficiency': round(path_eff, 3),
        'state_height_variance': round(height_var, 3),
    }


def classify_state(rim_feats, state_feats, n_detections):
    """Multi-class state classifier.

    Returns: (state_label, confidence, explanation)
    """
    score = 0.0
    explanations = []

    re = rim_feats['rim_engagement_score']
    ss = state_feats
    d = n_detections

    # DEAD BALL: stationary + structured
    if ss['state_stationary_ratio'] > 0.6 and ss['state_dwell_max'] >= 2:
        return 'dead_ball', 0.8, 'stationary={:.0f}% dwell={}'.format(
            100*ss['state_stationary_ratio'], ss['state_dwell_max'])

    # FT SETUP: very slow + high dwell + low spatial spread
    if ss['state_speed_mean'] < 10 and ss['state_dwell_max'] >= 3:
        return 'ft_setup', 0.7, 'slow={:.1f} dwell={}'.format(
            ss['state_speed_mean'], ss['state_dwell_max'])

    # INBOUND: starts near basket, moves away
    if rim_feats['rim_min_dist'] < 100 and rim_feats['rim_monotonicity'] < 0.3:
        return 'inbound', 0.6, 'near_rim={:.0f} mono={:.2f}'.format(
            rim_feats['rim_min_dist'], rim_feats['rim_monotonicity'])

    # RIM ATTACK: high rim engagement
    if re > 0.5:
        return 'rim_attack', 0.8, 'engagement={:.2f} lane={:.0f}%'.format(
            re, 100*rim_feats['rim_lane_occupancy'])

    # LIVE ATTACK: moderate rim engagement + good approach
    if re > 0.3 and rim_feats['rim_monotonicity'] > 0.4:
        return 'live_attack', 0.6, 'engagement={:.2f} mono={:.2f}'.format(
            re, rim_feats['rim_monotonicity'])

    # REBOUND SCRAMBLE: high post-rim dispersion
    if rim_feats['rim_post_dispersion'] > 0.3 and rim_feats['rim_min_dist'] < 150:
        return 'rebound_scramble', 0.5, 'dispersion={:.2f}'.format(
            rim_feats['rim_post_dispersion'])

    # TRANSITION: medium speed, low rim engagement, directional
    if ss['state_speed_mean'] > 15 and re < 0.3 and ss['state_path_efficiency'] > 0.5:
        return 'transition', 0.5, 'speed={:.1f} eff={:.2f}'.format(
            ss['state_speed_mean'], ss['state_path_efficiency'])

    # PERIMETER CIRCULATION: low rim engagement, moderate speed, spread out
    if re < 0.3 and ss['state_spatial_spread'] > 5.0:
        return 'perimeter_circulation', 0.4, 'spread={:.1f}'.format(
            ss['state_spatial_spread'])

    return 'unknown', 0.1, 'no clear pattern'


def main():
    df40 = pd.read_csv(CSV_V40)

    with open(PKL_V14, 'rb') as f:
        v14 = pickle.load(f)
    bx, by = v14['ball_x'], v14['ball_y']
    total = len(bx)

    # Scott's visual labels for the 11 candidates
    VISUAL_LABELS = {
        182: 'unclear_weak',
        223: 'dead_ball',
        582: 'live_attack',      # THE REAL SHOT
        934: 'transition',
        988: 'inbound',
        1073: 'ft_setup',
        1292: 'dead_ball',       # FT lineup, 17 detections, structured
        1764: 'transition',
        2303: 'perimeter_circulation',
        617: 'possibly_shot',
        61: 'possibly_shot',
    }

    results = []

    for _, row in df40.iterrows():
        f = int(row['frame'])
        if f >= total or np.isnan(bx[f]):
            continue

        f_start = max(0, f - BWD)
        f_end = min(total, f + FWD + 1)
        win_x = bx[f_start:f_end]
        win_y = by[f_start:f_end]
        valid = ~np.isnan(win_x) & ~np.isnan(win_y)

        if np.sum(valid) < 2:
            continue

        fx = win_x[valid]
        fy = win_y[valid]
        n_valid = len(fx)

        # Nearest basket
        ax, ay = fx[n_valid // 2], fy[n_valid // 2]
        basket_x, basket_y = nearest_basket(ax, ay)

        # Rim engagement
        rim = compute_rim_engagement(fx, fy, basket_x, basket_y)

        # State features
        frames_arr = f_start + np.where(valid)[0]
        state = compute_state_features(fx, fy, frames_arr)

        # Classify
        state_label, state_conf, state_exp = classify_state(rim, state, n_valid)

        manual = VISUAL_LABELS.get(f, '?')
        match = 'OK' if (
            (state_label in manual) or
            (manual in state_label) or
            (state_label == 'dead_ball' and manual == 'ft_setup') or
            (state_label == 'live_attack' and 'shot' in manual)
        ) else 'MISMATCH'

        print("  F{}: pred={:22s} manual={:25s} [{}] n={} engagement={:.2f} conf={:.1f}".format(
            f, state_label, manual, match, n_valid,
            rim['rim_engagement_score'], state_conf))

        result = dict(row)
        result.update(rim)
        result.update(state)
        result['predicted_state'] = state_label
        result['state_confidence'] = state_conf
        result['state_explanation'] = state_exp
        result['manual_state'] = manual
        results.append(result)

    if results:
        df_out = pd.DataFrame(results)
        df_out.to_csv(CSV_OUT, index=False)

        # Accuracy
        correct = sum(1 for r in results
                      if (r['predicted_state'] in r['manual_state'] or
                          r['manual_state'] in r['predicted_state']))
        print("\n{}/{} match visual labels".format(correct, len(results)))

        # Rim engagement ranking
        print("\n=== Rim Engagement Score Ranking ===")
        for r in sorted(results, key=lambda x: x.get('rim_engagement_score', 0), reverse=True):
            print("  F{}: {:.3f} state={} manual={}".format(
                int(r['frame']), r.get('rim_engagement_score', 0),
                r['predicted_state'], r['manual_state']))

        print("\nSaved to {}".format(CSV_OUT))


if __name__ == '__main__':
    main()
