#!/usr/bin/env python3
"""v40: Full Q1 shot detection pipeline.

1. Load v14 NN ball detections for entire Q1
2. Find all frames where ball is within shooting distance of either basket
3. Apply live-ball state classifier (v39 features)
4. Cluster surviving candidates
5. Output shot events with full feature set

This replaces the v34 emergence-based candidate generation with
NN-detection-based approach + gameplay state classification.
"""
import os, pickle, cv2
import numpy as np
import pandas as pd

PKL_V14 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl'
VIDEO   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
CSV_V39 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v39.csv'
CSV_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_candidates_v40.csv'
OUT_DIR = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/audit_v40'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0

# Shot filter thresholds (from v39 analysis)
MIN_DETECTIONS = 3          # minimum NN detections in window
MAX_ANCHOR_DIST = 350       # max px from basket at anchor
MIN_APPROACH = 10           # minimum distance decrease (early - late)
MAX_STATIONARY_RATIO = 0.8  # reject if >80% of frames are stationary
MIN_POSSESSION_SCORE = 0.7  # reject if possession score above this (held ball)
MIN_ENGAGEMENT = 0.5        # minimum basket engagement score


def nd(x, y):
    return min(np.sqrt((x-BLX)**2+(y-BLY)**2), np.sqrt((x-BRX)**2+(y-BRY)**2))


def which_basket(x, y):
    dl = np.sqrt((x-BLX)**2+(y-BLY)**2)
    dr = np.sqrt((x-BRX)**2+(y-BRY)**2)
    return (BLX, BLY) if dl < dr else (BRX, BRY)


def find_shot_candidates(bx, by, total):
    """Find all frames where ball is near either basket and approaching."""
    candidates = []

    # Sliding window: every frame within 300px of either basket
    near_basket = np.array([nd(bx[i], by[i]) < 300 if not np.isnan(bx[i]) else False
                            for i in range(total)])

    # Find contiguous regions of near-basket frames
    in_region = False
    region_start = 0
    for i in range(total):
        if near_basket[i] and not in_region:
            region_start = i
            in_region = True
        elif not near_basket[i] and in_region:
            # Region from region_start to i-1
            region_end = i
            # Pick the frame closest to basket as anchor
            region_dists = [nd(bx[j], by[j]) if not np.isnan(bx[j]) else 999
                           for j in range(region_start, region_end)]
            anchor = region_start + int(np.argmin(region_dists))

            # Require at least 3 valid NN detections in window
            win_start = max(0, anchor - 15)
            win_end = min(total, anchor + 20)
            valid_count = int(np.sum(~np.isnan(bx[win_start:win_end])))

            if valid_count >= 2:
                candidates.append(anchor)

            in_region = False

    # Handle case where region extends to end of video
    if in_region:
        region_end = total
        region_dists = [nd(bx[j], by[j]) if not np.isnan(bx[j]) else 999
                       for j in range(region_start, region_end)]
        anchor = region_start + int(np.argmin(region_dists))
        win_start = max(0, anchor - 15)
        win_end = min(total, anchor + 20)
        valid_count = int(np.sum(~np.isnan(bx[win_start:win_end])))
        if valid_count >= 2:
            candidates.append(anchor)

    return candidates


def compute_features_for_candidate(f, bx, by, total, img_h=720):
    """Compute full feature set for a candidate shot frame."""
    BWD, FWD = 15, 20
    f_start = max(0, f - BWD)
    f_end = min(total, f + FWD + 1)

    win_x = bx[f_start:f_end]
    win_y = by[f_start:f_end]
    valid = ~np.isnan(win_x) & ~np.isnan(win_y)
    n_valid = int(np.sum(valid))

    if n_valid < 2:
        return None

    valid_idx = np.where(valid)[0]
    fx = win_x[valid]
    fy = win_y[valid]
    frames = f_start + valid_idx

    # Anchor: closest to basket
    dists_to_basket = np.array([nd(x, y) for x, y in zip(fx, fy)])
    anchor_local = int(np.argmin(dists_to_basket))
    ax, ay = fx[anchor_local], fy[anchor_local]
    d_anchor = dists_to_basket[anchor_local]
    basket_x, basket_y = which_basket(ax, ay)

    # Distances over time
    dists = np.array([np.sqrt((x - basket_x)**2 + (y - basket_y)**2) for x, y in zip(fx, fy)])

    # Approach
    mid = n_valid // 2
    early_d = np.mean(dists[:max(mid, 1)])
    late_d = np.mean(dists[-max(n_valid - mid, 1):])
    approach = early_d - late_d

    # Movement
    if n_valid >= 2:
        total_move = float(np.sum(np.sqrt(np.diff(fx)**2 + np.diff(fy)**2)))
        dt = np.diff(frames)
        dt[dt == 0] = 1
        speeds = np.sqrt(np.diff(fx)**2 + np.diff(fy)**2) / dt
        mean_speed = float(np.mean(speeds))
        stationary_ratio = float(np.sum(speeds < 5) / len(speeds))
    else:
        total_move = 0.0
        mean_speed = 0.0
        stationary_ratio = 1.0

    # Velocity direction consistency
    if n_valid >= 3:
        dx = np.diff(fx)
        dy = np.diff(fy)
        angles = np.arctan2(dy, dx)
        R = np.sqrt(np.mean(np.cos(angles))**2 + np.mean(np.sin(angles))**2)
        direction_consistency = float(R)
    else:
        direction_consistency = 0.5

    # Basket engagement
    rim_convergence = float(np.mean(-np.diff(dists))) if len(dists) > 1 else 0
    final_dist = dists[-1]
    proximity_decay = float(np.sum(np.diff(dists[mid:]) < 0) / max(len(np.diff(dists[mid:])), 1))
    terminates_in_hoop = bool(final_dist < 90)
    engagement = 0.0
    if rim_convergence > 2: engagement += 0.25
    if proximity_decay > 0.5: engagement += 0.25
    if terminates_in_hoop: engagement += 0.3
    if d_anchor < 100: engagement += 0.2
    engagement = min(engagement, 1.0)

    # Height score
    height_score = 1.0 - float(np.mean(fy)) / img_h

    # Possession score
    if mean_speed < 8 and stationary_ratio > 0.6:
        possession_score = 0.8
    elif mean_speed < 15 and stationary_ratio > 0.4:
        possession_score = 0.5
    else:
        possession_score = 0.1

    # Path straightness
    if n_valid >= 2:
        endpoint_dist = np.sqrt((fx[-1] - fx[0])**2 + (fy[-1] - fy[0])**2)
        path_length = float(np.sum(np.sqrt(np.diff(fx)**2 + np.diff(fy)**2)))
        straightness = endpoint_dist / path_length if path_length > 0 else 1.0
    else:
        straightness = 1.0

    return {
        'frame': f,
        'n_valid': n_valid,
        'anchor_dist': round(d_anchor, 1),
        'basket_x': round(basket_x, 0),
        'basket_y': round(basket_y, 0),
        'approach': round(approach, 1),
        'total_movement': round(total_move, 1),
        'mean_speed': round(mean_speed, 2),
        'stationary_ratio': round(stationary_ratio, 3),
        'direction_consistency': round(direction_consistency, 3),
        'rim_convergence': round(rim_convergence, 2),
        'proximity_decay': round(proximity_decay, 3),
        'terminates_in_hoop': terminates_in_hoop,
        'basket_engagement': round(engagement, 3),
        'height_score': round(height_score, 3),
        'possession_score': round(possession_score, 2),
        'path_straightness': round(straightness, 3),
    }


def apply_shot_filter(features):
    """Apply live-ball state classifier filter."""
    f = features['frame']

    # Hard reject: too few detections
    if features['n_valid'] < MIN_DETECTIONS:
        return False, 'too_few'

    # Hard reject: too far from basket
    if features['anchor_dist'] > MAX_ANCHOR_DIST:
        return False, 'too_far'

    # Hard reject: moving away from basket
    if features['approach'] < -20:
        return False, 'moving_away'

    # Soft scoring
    score = 0.0

    # Approach quality
    if features['approach'] > 50: score += 2
    elif features['approach'] > 20: score += 1
    elif features['approach'] > 10: score += 0.5

    # Not stationary
    if features['stationary_ratio'] < 0.3: score += 1
    elif features['stationary_ratio'] < 0.6: score += 0.5
    else: score -= 1

    # Not held ball
    if features['possession_score'] < 0.3: score += 1
    elif features['possession_score'] < 0.6: score += 0.3
    else: score -= 2

    # Basket engagement
    if features['basket_engagement'] > 0.7: score += 2
    elif features['basket_engagement'] > 0.5: score += 1
    elif features['basket_engagement'] > 0.3: score += 0.5

    # Direction consistency
    if features['direction_consistency'] > 0.7: score += 1
    elif features['direction_consistency'] > 0.5: score += 0.5

    # Straightness
    if features['path_straightness'] > 0.8: score += 0.5

    # Terminates in hoop
    if features['terminates_in_hoop']: score += 1.5

    # Threshold
    is_shot = score >= 3.0

    return is_shot, 'score={:.1f}'.format(score)


def main():
    with open(PKL_V14, 'rb') as f:
        v14 = pickle.load(f)
    bx, by = v14['ball_x'], v14['ball_y']
    total = len(bx)

    print("Q1 total frames: {}".format(total))
    print("Valid ball detections: {}".format(int(np.sum(~np.isnan(bx)))))

    # Find all near-basket candidates
    candidates = find_shot_candidates(bx, by, total)
    print("\nInitial candidates (near basket): {}".format(len(candidates)))

    # Dedup: merge candidates within 30 frames
    deduped = []
    for c in sorted(candidates):
        if deduped and c - deduped[-1] < 30:
            # Keep the one with more detections
            prev = deduped[-1]
            prev_valid = int(np.sum(~np.isnan(bx[max(0,prev-15):min(total,prev+20)])))
            curr_valid = int(np.sum(~np.isnan(bx[max(0,c-15):min(total,c+20)])))
            if curr_valid > prev_valid:
                deduped[-1] = c
        else:
            deduped.append(c)
    print("After dedup: {}".format(len(deduped)))

    # Compute features + filter
    results = []
    os.makedirs(OUT_DIR, exist_ok=True)

    for c in deduped:
        feats = compute_features_for_candidate(c, bx, by, total)
        if feats is None:
            continue

        is_shot, reason = apply_shot_filter(feats)
        feats['is_shot'] = is_shot
        feats['filter_reason'] = reason
        results.append(feats)

        status = "SHOT" if is_shot else "REJECT"
        print("  F{}: {} ({}) n={} dist={:.0f} approach={:.1f} engagement={:.2f} possession={:.1f}".format(
            c, status, reason, feats['n_valid'], feats['anchor_dist'],
            feats['approach'], feats['basket_engagement'], feats['possession_score']))

    if results:
        df = pd.DataFrame(results)
        df.to_csv(CSV_OUT, index=False)

        n_shots = df['is_shot'].sum()
        print("\n{}/{} pass filter (out of {} deduped, {} initial)".format(
            n_shots, len(df), len(deduped), len(candidates)))

        if n_shots > 0:
            shots = df[df['is_shot']]
            print("\n=== Shot Candidates ===")
            for _, s in shots.iterrows():
                print("  F{}: dist={:.0f} approach={:.1f} engagement={:.2f} straight={:.3f} n={}".format(
                    int(s['frame']), s['anchor_dist'], s['approach'],
                    s['basket_engagement'], s['path_straightness'], s['n_valid']))

        print("\nSaved to {}".format(CSV_OUT))


if __name__ == '__main__':
    main()
