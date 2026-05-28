#!/usr/bin/env python3
"""v39: Live-ball state classifier.

Reframes the problem: not "is this a shot?" but "what gameplay state is this?"
Uses ball elevation proxies + temporal state features + basket engagement.

New feature families:
1. Ball elevation proxies
   - ball_y_relative: ball y-position relative to court floor baseline
   - vertical_velocity: dy/dt of ball
   - arc_convexity: does trajectory curve upward then down (shot) or stay flat (dribble)
   - height_above_rim: apparent height relative to rim plane
   - ball_radius_proxy: apparent ball size (larger = closer to camera)

2. Possession continuity
   - stationary_dwell: consecutive frames with < 3px movement
   - velocity_variance: how much ball speed varies (steady transit vs stop-and-go)
   - min_velocity: lowest speed between consecutive detections
   - speed_profile: acceleration vs deceleration pattern

3. Basket engagement
   - rim_convergence: does trajectory end converging on rim cylinder
   - final_approach_angle: direction of motion in last 5 frames before rim
   - rim_proximity_decay: does distance to rim decrease monotonically?
   - terminates_in_hoop_zone: final detection within 50px of rim

4. Court entropy (context)
   - local_motion_variance: variance of ball motion direction
   - trajectory_straightness: how linear vs curved the path is
"""
import os, pickle, cv2
import numpy as np
import pandas as pd

PKL_V14 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl'
CSV_V37 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v37.csv'
CSV_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v39.csv'

BLX, BLY = 179.0, 525.0  # Left basket (x, y) in frame
BRX, BRY = 1009.0, 466.0  # Right basket (x, y) in frame

# Rim zones (approximate 3D cylinder projected to 2D)
RIM_RADIUS_PX = 45  # approximate rim radius in pixels


def nd(x, y):
    """Distance to nearest basket."""
    return min(
        np.sqrt((x - BLX)**2 + (y - BLY)**2),
        np.sqrt((x - BRX)**2 + (y - BRY)**2)
    )


def which_basket(x, y):
    """Return nearest basket coordinates."""
    dl = np.sqrt((x - BLX)**2 + (y - BLY)**2)
    dr = np.sqrt((x - BRX)**2 + (y - BRY)**2)
    if dl < dr:
        return BLX, BLY
    return BRX, BRY


def compute_elevation_features(fx, fy, frames, img_h):
    """Ball elevation proxy features."""
    n = len(fx)
    if n < 2:
        return {
            'ball_y_mean': float(np.mean(fy)),
            'ball_y_range': 0.0,
            'vertical_velocity': 0.0,
            'vertical_acceleration': 0.0,
            'arc_convexity': 0.0,
            'height_score': 0.5,
        }

    # y-position stats (lower y = higher in frame = further from camera typically)
    y_mean = float(np.mean(fy))
    y_range = float(np.max(fy) - np.min(fy))

    # Vertical velocity (dy/dt)
    if n >= 3:
        dt = np.diff(frames)
        dt[dt == 0] = 1
        dy = np.diff(fy)
        v_y = dy / dt
        vertical_velocity = float(np.mean(v_y))

        # Vertical acceleration
        if len(v_y) >= 2:
            dvy = np.diff(v_y)
            dt2 = dt[1:]
            dt2[dt2 == 0] = 1
            vertical_accel = float(np.mean(dvy / dt2))
        else:
            vertical_accel = 0.0

        # Arc convexity: fit quadratic to y vs t, check if it opens downward (shot arc)
        t = frames - frames[0]
        if len(t) >= 3 and t[-1] > 0:
            # y = a*t^2 + b*t + c, a < 0 means concave down (ball rises then falls)
            coeffs = np.polyfit(t, fy, 2)
            convexity = float(coeffs[0])  # a coefficient
        else:
            convexity = 0.0

        # Height score: how "elevated" is the ball path?
        # Normalize y to 0-1 (0 = top of frame, 1 = bottom)
        y_normalized = fy / img_h
        # Low y (high in frame) = ball is far, FROM camera perspective on a raised arc
        # High y (low in frame) = ball is near camera / on ground
        # A shot arc goes: high (release) -> low (apex) -> high (descending into hoop)
        # Actually in this top-down-ish camera, shots show lateral+approach motion
        # The key: shots have ball moving toward basket while at elevated position
        height_score = 1.0 - y_normalized.mean()  # higher score = ball is higher in frame
    else:
        vertical_velocity = 0.0
        vertical_accel = 0.0
        convexity = 0.0
        height_score = 0.5

    return {
        'ball_y_mean': round(y_mean, 1),
        'ball_y_range': round(y_range, 1),
        'vertical_velocity': round(vertical_velocity, 3),
        'vertical_acceleration': round(vertical_accel, 3),
        'arc_convexity': round(convexity, 5),
        'height_score': round(height_score, 3),
    }


def compute_possession_features(fx, fy, frames):
    """Possession continuity and velocity features."""
    n = len(fx)
    if n < 3:
        return {
            'stationary_dwell_max': 0,
            'stationary_dwell_mean': 0.0,
            'velocity_variance': 0.0,
            'min_velocity': 0.0,
            'mean_velocity': 0.0,
            'speed_changes': 0,
            'possession_score': 0.0,
        }

    dt = np.diff(frames)
    dt[dt == 0] = 1
    dx = np.diff(fx)
    dy = np.diff(fy)
    speeds = np.sqrt(dx**2 + dy**2) / dt
    directions = np.arctan2(dy, dx)

    # Stationary dwell: max consecutive frames with < 3px movement
    stationary_runs = []
    current_run = 0
    for s in speeds:
        if s < 3.0:
            current_run += 1
        else:
            if current_run > 0:
                stationary_runs.append(current_run)
            current_run = 0
    if current_run > 0:
        stationary_runs.append(current_run)

    max_dwell = max(stationary_runs) if stationary_runs else 0
    mean_dwell = float(np.mean(stationary_runs)) if stationary_runs else 0.0

    # Velocity variance
    vel_var = float(np.var(speeds)) if len(speeds) > 1 else 0.0
    min_vel = float(np.min(speeds))
    mean_vel = float(np.mean(speeds))

    # Direction changes (significant heading changes)
    dir_changes = 0
    if len(directions) >= 2:
        dd = np.diff(directions)
        dd = (dd + np.pi) % (2 * np.pi) - np.pi
        dir_changes = int(np.sum(np.abs(dd) > 0.5))

    # Possession score: high = likely referee/FT possession
    # Characteristics: long dwell times, low speed, low variance
    if mean_vel < 5 and max_dwell >= 2:
        possession_score = 0.8  # likely held ball
    elif mean_vel < 10 and vel_var < 20:
        possession_score = 0.5  # slow transit
    else:
        possession_score = 0.1  # active play

    return {
        'stationary_dwell_max': max_dwell,
        'stationary_dwell_mean': round(mean_dwell, 1),
        'velocity_variance': round(vel_var, 2),
        'min_velocity': round(min_vel, 2),
        'mean_velocity': round(mean_vel, 2),
        'speed_changes': dir_changes,
        'possession_score': round(possession_score, 2),
    }


def compute_basket_engagement(fx, fy, frames):
    """Basket engagement features."""
    n = len(fx)
    if n < 2:
        return {
            'rim_convergence': 0.0,
            'final_approach_angle': 0.0,
            'rim_proximity_decay': 0.0,
            'terminates_in_hoop': False,
            'basket_engagement_score': 0.0,
        }

    # Nearest basket for the anchor
    bx, by = which_basket(fx[n//2], fy[n//2])

    # Distance to nearest rim over time
    dists = np.array([np.sqrt((x - bx)**2 + (y - by)**2) for x, y in zip(fx, fy)])

    # Rim convergence: does distance decrease consistently?
    if n >= 3:
        dist_diffs = np.diff(dists)
        convergence = -np.mean(dist_diffs)  # positive = approaching
    else:
        convergence = 0.0

    # Final approach: average angle of last 3 movements
    if n >= 4:
        last_dx = fx[-1] - fx[-3]
        last_dy = fy[-1] - fy[-3]
        approach_angle = float(np.arctan2(last_dy, last_dx))
    else:
        approach_angle = 0.0

    # Monotonic decrease in distance (last half of observations)
    mid = n // 2
    last_dists = dists[mid:]
    if len(last_dists) >= 2:
        proximity_decay = float(np.sum(np.diff(last_dists) < 0) / len(np.diff(last_dists)))
    else:
        proximity_decay = 0.5

    # Terminates in hoop zone
    final_dist = dists[-1]
    terminates_in_hoop = bool(final_dist < RIM_RADIUS_PX * 2)

    # Basket engagement score
    engagement = 0.0
    if convergence > 5:
        engagement += 0.3
    if proximity_decay > 0.6:
        engagement += 0.3
    if terminates_in_hoop:
        engagement += 0.3
    if dists[-1] < 100:
        engagement += 0.1

    return {
        'rim_convergence': round(convergence, 2),
        'final_approach_angle': round(approach_angle, 3),
        'rim_proximity_decay': round(proximity_decay, 3),
        'terminates_in_hoop': terminates_in_hoop,
        'basket_engagement_score': round(min(engagement, 1.0), 3),
    }


def compute_trajectory_shape(fx, fy, frames):
    """Trajectory shape features."""
    n = len(fx)
    if n < 3:
        return {
            'path_straightness': 1.0,
            'path_curvature': 0.0,
            'direction_entropy': 0.0,
            'bounding_box_ratio': 1.0,
        }

    # Path straightness: ratio of endpoint distance to total path length
    endpoint_dist = np.sqrt((fx[-1] - fx[0])**2 + (fy[-1] - fy[0])**2)
    path_length = np.sum(np.sqrt(np.diff(fx)**2 + np.diff(fy)**2))
    if path_length > 0:
        straightness = endpoint_dist / path_length
    else:
        straightness = 1.0

    # Direction entropy: how much does heading change?
    if n >= 3:
        dx = np.diff(fx)
        dy = np.diff(fy)
        angles = np.arctan2(dy, dx)
        # Circular variance of angles
        R = np.sqrt(np.mean(np.cos(angles))**2 + np.mean(np.sin(angles))**2)
        direction_entropy = 1.0 - R
    else:
        direction_entropy = 0.0

    # Bounding box ratio: elongate vs compact path
    x_range = np.max(fx) - np.min(fx)
    y_range = np.max(fy) - np.min(fy)
    max_range = max(x_range, y_range)
    if max_range > 0:
        bb_ratio = min(x_range, y_range) / max_range
    else:
        bb_ratio = 1.0

    return {
        'path_straightness': round(straightness, 3),
        'direction_entropy': round(direction_entropy, 3),
        'bounding_box_ratio': round(bb_ratio, 3),
    }


def main():
    df = pd.read_csv(CSV_V37)

    with open(PKL_V14, 'rb') as f:
        v14 = pickle.load(f)
    bx, by = v14['ball_x'], v14['ball_y']
    total = len(bx)

    BWD, FWD = 15, 20

    # Manual labels for validation
    MANUAL = {
        115: ('no_shot', 'transition'),
        236: ('no_shot', 'referee_handoff'),
        467: ('no_shot', 'ft_lineup'),
        990: ('no_shot', 'inbound'),
        1283: ('no_shot', 'ft_lineup'),
        1413: ('no_shot', 'ft_lineup'),
        1468: ('no_shot', 'ft_lineup'),
        1650: ('no_shot', 'dribbling'),
        1780: ('no_shot', 'steal_attempt'),
        2320: ('shot', 'layup'),
    }

    results = []

    for _, row in df.iterrows():
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

        valid_idx = np.where(valid)[0]
        fx = win_x[valid]
        fy = win_y[valid]
        frames = f_start + valid_idx

        # Get frame for img_h reference
        cap = cv2.VideoCapture('/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm')
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ret, img = cap.read()
        cap.release()
        img_h = img.shape[0] if ret else 720

        # Compute all feature families
        elev = compute_elevation_features(fx, fy, frames, img_h)
        possession = compute_possession_features(fx, fy, frames)
        basket = compute_basket_engagement(fx, fy, frames)
        traj = compute_trajectory_shape(fx, fy, frames)

        result = dict(row)
        result.update(elev)
        result.update(possession)
        result.update(basket)
        result.update(traj)
        result['n_detections'] = len(fx)
        result['manual_label'] = MANUAL.get(f, ('?', '?'))[0]
        result['manual_detail'] = MANUAL.get(f, ('?', '?'))[1]
        results.append(result)

        print("  F{}: n={:2d} height={:.2f} possession={:.1f} engagement={:.2f} straight={:.3f} convexity={:.5f}".format(
            f, len(fx), elev['height_score'], possession['possession_score'],
            basket['basket_engagement_score'], traj['path_straightness'],
            elev['arc_convexity']))

    if results:
        df_out = pd.DataFrame(results)
        df_out.to_csv(CSV_OUT, index=False)
        print("\nSaved v39 features ({} events) to {}".format(len(results), CSV_OUT))

        # Quick analysis
        print("\n=== Feature Comparison: SHOT vs NON-SHOT ===")
        shots = df_out[df_out['manual_label'] == 'shot']
        nonshots = df_out[df_out['manual_label'] == 'no_shot']
        print("  Shots:     {}".format(list(shots['frame'].values)))
        print("  Non-shots: {}".format(list(nonshots['frame'].values)))

        for feat in ['height_score', 'possession_score', 'basket_engagement_score',
                     'mean_velocity', 'stationary_dwell_max', 'path_straightness']:
            if feat in df_out.columns:
                s_mean = shots[feat].mean() if len(shots) > 0 else 0
                n_mean = nonshots[feat].mean() if len(nonshots) > 0 else 0
                diff = s_mean - n_mean
                print("  {}: shot={:.3f} non-shot={:.3f} diff={:.3f}".format(
                    feat, s_mean, n_mean, diff))


if __name__ == '__main__':
    main()
