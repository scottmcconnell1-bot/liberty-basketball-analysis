#!/usr/bin/env python3
"""v42: Corrected shot filter with 3 critical fixes from visual audit.

Fixes:
1. COURT-HALF GATE: Reject candidates past half-court (x > 640 for left-side camera)
2. MONOTONIC APPROACH: Require progressive distance decrease toward rim
   (not just anchor close — the TRAJECTORY must converge)
3. VERTICAL CLUSTERING: Penalize horizontal spread (FT lineups, crowds)
   Reward vertical movement (shots have low std(x)/std(y) ratio)

Also: F0988-type fix — don't over reward anchor proximity alone.
Real shots (F0582, F0617) have:
  - Ball on correct half of court
  - Progressive rim convergence across the full window
  - Vertically clustered dots (shot arc)
  - Not-stationary anchor

False positives have:
  - Ball visible during dead-ball/clear-floor states
  - Random or flat distance-to-rim profiles
  - Horizontal dot spread (FT lineups, crowds)
  - Wrong court half
"""
import os, pickle, cv2
import numpy as np
import pandas as pd

PKL_V14 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl'
VIDEO   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
CSV_V40 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_candidates_v40.csv'
CSV_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v42.csv'
OUT_DIR = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/audit_v42'

# Court geometry
BLX, BLY = 179.0, 525.0   # Left basket
BRX, BRY = 1009.0, 466.0  # Right basket
HALFCOURT_X = 640.0        # Approximate half-court line

# Hoop zone: within this many pixels of rim = "engaged"
HOOP_ZONE = 90
# Lane area: within this lateral distance of basket centerline
LANE_HALF = 150

BWD, FWD = 15, 20


def nd(x, y):
    return min(np.sqrt((x-BLX)**2+(y-BLY)**2), np.sqrt((x-BRX)**2+(y-BRY)**2))


def nearest_basket(x, y):
    dl = np.sqrt((x-BLX)**2+(y-BLY)**2)
    dr = np.sqrt((x-BRX)**2+(y-BRY)**2)
    return (BLX, BLY) if dl < dr else (BRX, BRY)


def compute_shot_score(f, bx, by, total):
    """Compute corrected shot quality score + sub-features.

    Returns (score, features_dict, is_shot, reason)
    """
    f_start = max(0, f - BWD)
    f_end = min(total, f + FWD + 1)

    win_x = bx[f_start:f_end]
    win_y = by[f_start:f_end]
    valid = ~np.isnan(win_x) & ~np.isnan(win_y)
    n_valid = int(np.sum(valid))

    if n_valid < 3:
        return 0, {'n_valid': n_valid, 'mono_score': 0, 'vertical_score': 0, 'correct_half': False}, False, 'too_few'

    valid_idx = np.where(valid)[0]
    fx = win_x[valid].astype(float)
    fy = win_y[valid].astype(float)
    frames = f_start + valid_idx

    # Anchor = closest to basket
    dists_all = np.array([nd(x, y) for x, y in zip(fx, fy)])
    anchor_local = int(np.argmin(dists_all))
    ax, ay = fx[anchor_local], fy[anchor_local]
    d_anchor = float(dists_all[anchor_local])
    basket_x, basket_y = nearest_basket(ax, ay)

    # Distances to nearest basket over time
    dists = np.array([np.sqrt((x - basket_x)**2 + (y - basket_y)**2) for x, y in zip(fx, fy)])

    # --- Feature computation ---

    # 1. COURT-HALF GATE
    # Check if anchor is on correct half relative to nearest basket
    # Left basket (BL): correct half is right side (x < HALFCOURT_X for this camera)
    # Right basket (BR): correct half is left side (x > HALFCOURT_X)
    if basket_x == BLX:
        correct_half = ax < HALFCOURT_X + 100  # generous margin
    else:
        correct_half = ax > HALFCOURT_X - 100

    # 2. MONOTONIC APPROACH
    # Real shots show progressive decrease in distance to rim
    # Compute correlation between frame index and distance (should be negative)
    if n_valid >= 4:
        frame_corr = np.corrcoef(frames.astype(float), dists)[0, 1]
        # Negative correlation = distance decreases as frames progress
        mono_score = max(0, -frame_corr)  # 0 to 1, higher = more monotonic decrease
    else:
        mono_score = 0.5  # uncertain

    # Also: fraction of consecutive frames showing decrease
    if n_valid >= 3:
        dist_diffs = np.diff(dists)
        decr_ratio = float(np.sum(dist_diffs < 0) / len(dist_diffs))
    else:
        decr_ratio = 0.5

    # 3. VERTICAL CLUSTERING (cluster aspect ratio)
    # Real shots: vertical movement > horizontal (low std_x / std_y)
    # FT lineups/crowds: horizontal spread (high std_x / std_y)
    sx = float(np.std(fx))
    sy = float(np.std(fy))
    if sy > 0:
        aspect_ratio = sx / sy  # < 1 = vertical, > 1 = horizontal
    else:
        aspect_ratio = 999  # all same y = total horizontal line

    vertical_score = 1.0 / (1.0 + aspect_ratio)  # high = vertical

    # 4. RIM ENGAGEMENT
    min_dist = float(np.min(dists))
    terminal_hoop = bool(dists[-1] < HOOP_ZONE)

    # Score rim engagement
    rim_score = 0.0
    if min_dist < HOOP_ZONE:
        rim_score += 4
    elif min_dist < HOOP_ZONE * 2:
        rim_score += 2.5
    elif min_dist < HOOP_ZONE * 3:
        rim_score += 1

    if terminal_hoop:
        rim_score += 2

    if mono_score > 0.5:
        rim_score += 2
    elif mono_score > 0.3:
        rim_score += 1

    if vertical_score > 0.5:
        rim_score += 1

    # 5. MOVEMENT (reject stationary)
    if n_valid >= 2:
        total_move = float(np.sum(np.sqrt(np.diff(fx)**2 + np.diff(fy)**2)))
        dt = np.diff(frames).astype(float)
        dt[dt == 0] = 1
        speeds = np.sqrt(np.diff(fx)**2 + np.diff(fy)**2) / dt
        mean_speed = float(np.mean(speeds))
        stat_ratio = float(np.sum(speeds < 5) / len(speeds))
    else:
        total_move = 0.0
        mean_speed = 0.0
        stat_ratio = 1.0

    # Penalty for stationary
    if stat_ratio > 0.7:
        rim_score -= 3

    # 6. ANCHOR DISTANCE (less weight than before)
    # Don't over-reward being close — F0988 scored 9.0 because of this
    if d_anchor < 100:
        rim_score += 1  # small bonus
    elif d_anchor < 150:
        rim_score += 0.5
    # No bonus for d > 150

    # Build features
    features = {
        'n_valid': n_valid,
        'anchor_dist': round(d_anchor, 1),
        'basket_x': round(basket_x, 0),
        'correct_half': correct_half,
        'mono_correlation': round(float(frame_corr) if n_valid >= 4 else 0, 3),
        'mono_score': round(mono_score, 3),
        'decrease_ratio': round(decr_ratio, 3),
        'aspect_ratio': round(aspect_ratio, 3),
        'vertical_score': round(vertical_score, 3),
        'min_dist': round(min_dist, 1),
        'terminal_hoop': terminal_hoop,
        'total_movement': round(total_move, 1),
        'mean_speed': round(mean_speed, 2),
        'stationary_ratio': round(stat_ratio, 3),
        'rim_score': round(rim_score, 1),
    }

    # --- Final shot gate ---
    # Hard filters first
    if not correct_half:
        return rim_score, features, False, 'wrong_half'

    if n_valid < 3:
        return rim_score, features, False, 'too_few'

    if stat_ratio > 0.8:
        return rim_score, features, False, 'stationary'

    if d_anchor > 300:
        return rim_score, features, False, 'too_far'

    # Main threshold
    is_shot = rim_score >= 5.0
    reason = 'score={:.1f}'.format(rim_score)

    return rim_score, features, is_shot, reason


def main():
    df40 = pd.read_csv(CSV_V40)

    with open(PKL_V14, 'rb') as f:
        v14 = pickle.load(f)
    bx, by = v14['ball_x'], v14['ball_y']
    total = len(bx)

    # Ground truth from Scott's + Perplexity's visual audit
    VISUAL_AUDIT = {
        61: ('no', 'transition_backcourt'),
        182: ('weak', 'unclear_paint'),
        223: ('no', 'dead_ball'),
        582: ('yes', 'putback_interior'),     # CONFIRMED REAL SHOT
        617: ('yes', 'jump_shot_wing'),       # CONFIRMED REAL SHOT
        934: ('no', 'dribble_midcourt'),
        988: ('no', 'inbound_transition'),    # Should NOT score high
        1073: ('no', 'ft_setup'),
        1292: ('no', 'ft_lineup'),            # 17 detections, structured
        1764: ('no', 'wrong_half_transition'),
        2303: ('weak', 'perimeter_circulation'),
    }

    results = []
    os.makedirs(OUT_DIR, exist_ok=True)

    cap = cv2.VideoCapture(VIDEO)

    for _, row in df40.iterrows():
        f = int(row['frame'])
        if f >= total or np.isnan(bx[f]):
            continue

        score, feats, is_shot, reason = compute_shot_score(f, bx, by, total)

        visual = VISUAL_AUDIT.get(f, ('?', '?'))
        visual_shot = visual[0] in ('yes', 'weak')
        match = 'OK' if is_shot == visual_shot else 'MISMATCH'
        # Count weak as acceptable if flagged
        if visual[0] == 'weak' and not is_shot:
            match = 'OK_WEAK'

        manual = '{} ({})'.format(visual[0], visual[1])

        print("  F{}: {:5s} score={:5.1f} manual={:30s} [{}] n={} mono={:.2f} vert={:.2f} correct_half={}".format(
            f, 'SHOT' if is_shot else 'REJECT', score, manual, match,
            feats.get('n_valid', 0), feats.get('mono_score', 0), feats.get('vertical_score', 0),
            feats['correct_half']))

        result = dict(row)
        result.update(feats)
        result['is_shot_v42'] = is_shot
        result['v42_reason'] = reason
        result['manual_shot'] = visual[0]
        result['manual_detail'] = visual[1]
        results.append(result)

        # Draw updated overlay
        if is_shot or score > 3:
            f_start = max(0, f - BWD)
            f_end = min(total, f + FWD + 1)
            win_x = bx[f_start:f_end]
            win_y = by[f_start:f_end]
            v = ~np.isnan(win_x) & ~np.isnan(win_y)

            cap.set(cv2.CAP_PROP_POS_FRAMES, f)
            ret, img = cap.read()
            if ret and np.sum(v) >= 2:
                vis = img.copy()
                fx = win_x[v].astype(float)
                fy = win_y[v].astype(float)

                cv2.circle(vis, (int(BLX), int(BLY)), 12, (0, 0, 255), 2)
                cv2.circle(vis, (int(BRX), int(BRY)), 12, (0, 0, 255), 2)
                cv2.line(vis, (int(HALFCOURT_X), 0), (int(HALFCOURT_X), vis.shape[0]), (100, 100, 100), 1)

                for x, y in zip(fx, fy):
                    cv2.circle(vis, (int(x), int(y)), 6, (0, 255, 255), -1)

                label = 'F{} {} score={:.1f} {}'.format(f, 'SHOT' if is_shot else 'REJ', score, reason)
                cv2.rectangle(vis, (5, 5), (len(label)*9 + 15, 35), (0, 0, 0), -1)
                cv2.putText(vis, label, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

                info = 'mono={:.2f} vert={:.2f} ar={:.2f}'.format(feats['mono_score'], feats['vertical_score'], feats['aspect_ratio'])
                cv2.putText(vis, info, (10, vis.shape[0]-15), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

                cv2.imwrite(os.path.join(OUT_DIR, 'F{:04d}.jpg'.format(f)), vis)

    cap.release()

    if results:
        df_out = pd.DataFrame(results)
        df_out.to_csv(CSV_OUT, index=False)

        n_shots = sum(1 for r in results if r['is_shot_v42'])
        n_ok = sum(1 for r in results
                   if (r['is_shot_v42'] == (r['manual_shot'] in ('yes', 'weak'))) or
                      (r['manual_shot'] == 'weak' and not r['is_shot_v42']))
        print("\n{}/{} pass v42 filter".format(n_shots, len(results)))
        print("{}/{} match visual audit".format(n_ok, len(results)))

        # Score ranking
        print("\n=== Rim Score Ranking ===")
        for r in sorted(results, key=lambda x: x.get('rim_score', 0), reverse=True):
            print("  F{}: {:.1f} {} manual={} n={} mono={:.2f} vert={:.2f}".format(
                int(r['frame']), r.get('rim_score', 0),
                'SHOT' if r['is_shot_v42'] else 'rej',
                r['manual_shot'], r['n_valid'],
                r.get('mono_score', 0), r.get('vertical_score', 0)))

        print("\nSaved to {}".format(CSV_OUT))


if __name__ == '__main__':
    main()
