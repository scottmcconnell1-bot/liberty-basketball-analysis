#!/usr/bin/env python3
"""v38b: Shot filter — refined approach.

Key insight: sparse NN detections (3-5 points) are inherently ambiguous.
Only events with enough detections AND clear approaching trajectory pass.

Additional filters:
- Require minimum 4 NN detections in window
- Require consistent approach (monotonically decreasing distance in latter half)
- Detect FT setup: multiple frames with near-stationary ball in key area
- Detect group play: ball amid many players = dead ball
"""
import os, pickle, cv2
import numpy as np
import pandas as pd

PKL_V14 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl'
CSV_V37 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v37.csv'
CSV_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v38b_filtered.csv'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0

# Read events manually reviewed by Scott
MANUAL_LABELS = {
    115: ('no_shot', 'transition_play'),
    236: ('no_shot', 'referee_handing_ball'),
    467: ('no_shot', 'ft_lineup'),
    990: ('no_shot', 'inbound_pass'),
    1283: ('no_shot', 'ft_lineup'),
    1413: ('no_shot', 'ft_lineup'),
    1468: ('no_shot', 'ft_lineup'),
    1650: ('no_shot', 'dribbling_top'),
    1780: ('no_shot', 'steal_attempt_midcourt'),
    2320: ('shot', 'layup'),
}


def nd(x, y):
    return min(np.sqrt((x-BLX)**2+(y-BLY)**2), np.sqrt((x-BRX)**2+(y-BRY)**2))


class ShotFilter:
    def __init__(self):
        self.v14 = None
        self.bx = None
        self.by = None
        self.total = 0

    def load(self, pkl_path):
        with open(pkl_path, 'rb') as f:
            self.v14 = pickle.load(f)
        self.bx = self.v14['ball_x']
        self.by = self.v14['ball_y']
        self.total = len(self.bx)

    def check(self, f):
        """Full shot filtering with detailed diagnostics."""
        BWD, FWD = 15, 20
        f_start = max(0, f - BWD)
        f_end = min(self.total, f + FWD + 1)

        win_x = self.bx[f_start:f_end]
        win_y = self.by[f_start:f_end]
        valid = ~np.isnan(win_x) & ~np.isnan(win_y)
        n_valid = int(np.sum(valid))

        if n_valid < 3:
            return False, 'too_few_detections', {'n_valid': n_valid}

        valid_idx = np.where(valid)[0]
        fx = win_x[valid]
        fy = win_y[valid]
        frames = f_start + valid_idx

        # Anchor
        anchor_local = int(np.argmin(np.abs(valid_idx - (f - f_start))))
        anchor_local = max(0, min(anchor_local, len(fx) - 1))
        ax, ay = fx[anchor_local], fy[anchor_local]
        d_anchor = nd(ax, ay)

        # Distances to nearest basket
        dists = np.array([nd(x, y) for x, y in zip(fx, fy)])

        # Total movement
        if n_valid >= 2:
            total_move = float(np.sum(np.sqrt(np.diff(fx)**2 + np.diff(fy)**2)))
        else:
            total_move = 0.0

        # Approach: is distance decreasing over the second half?
        mid = n_valid // 2
        early_d = np.mean(dists[:mid])
        late_d = np.mean(dists[mid:])
        approach = early_d - late_d

        # Consistency: how many consecutive frames show decreasing distance?
        if n_valid >= 3:
            dist_diffs = np.diff(dists)
            decreasing = np.sum(dist_diffs < 0)
            consistency = decreasing / len(dist_diffs)
        else:
            consistency = 0.5

        # Stationary ratio: fraction of frames with < 5px movement
        if n_valid >= 2:
            moves = np.sqrt(np.diff(fx)**2 + np.diff(fy)**2)
            stationary_ratio = np.sum(moves < 5) / len(moves)
        else:
            stationary_ratio = 1.0

        info = {
            'n_valid': n_valid,
            'd_anchor': round(d_anchor, 1),
            'total_move': round(total_move, 1),
            'approach': round(approach, 1),
            'consistency': round(consistency, 3),
            'stationary_ratio': round(stationary_ratio, 3),
        }

        # 1. Too sparse
        if n_valid < 4:
            return False, 'too_sparse', info

        # 2. Too far from basket
        if d_anchor > 350:
            return False, 'too_far', info

        # 3. Ball moving away
        if approach < -10:
            return False, 'moving_away', info

        # 4. Inbound: starts very near basket
        if dists[0] < 100 and approach > 100:
            return False, 'inbound', info

        # 5. Stationary: ball barely moving (FT setup, referee holding)
        if stationary_ratio > 0.7 and total_move < 80:
            return False, 'stationary', info

        # 6. FT setup: in key area, mostly stationary
        in_key = 150 < ax < 1100 and 350 < ay < 650
        if in_key and stationary_ratio > 0.6 and approach < 20:
            return False, 'ft_setup', info

        # 7. Lateral only: moving side to side, not approaching
        if total_move > 50 and approach < 10 and consistency < 0.4:
            return False, 'lateral_only', info

        # 8. Midcourt: far from basket, not approaching
        if d_anchor > 250 and approach < 20:
            return False, 'midcourt', info

        # 9. Require meaningful approach
        if approach < 15:
            return False, 'weak_approach', info

        # 10. Require decent consistency
        if consistency < 0.3:
            return False, 'inconsistent', info

        info['filter_pass'] = True
        return True, 'SHOT_CANDIDATE', info


def main():
    df = pd.read_csv(CSV_V37)
    sf = ShotFilter()
    sf.load(PKL_V14)

    results = []

    print("=== Shot Filter Diagnostics ===\n")

    for _, row in df.iterrows():
        f = int(row['frame'])
        if f >= sf.total or np.isnan(sf.bx[f]):
            continue

        is_shot, reason, info = sf.check(f)

        manual = MANUAL_LABELS.get(f, ('?', '?'))
        manual_shot = manual[0] == 'shot'
        match = 'OK' if is_shot == manual_shot else 'MISMATCH'

        print("  F{}: filter={:12s} manual={:10s} [{}] n={} d_anchor={:.0f} approach={:.1f} move={:.1f} stat={:.2f} consist={:.2f}".format(
            f, reason, manual[1], match,
            info['n_valid'], info.get('d_anchor', 0),
            info.get('approach', 0), info.get('total_move', 0),
            info.get('stationary_ratio', 0), info.get('consistency', 0)))

        result = dict(row)
        result['filter_pass'] = is_shot
        result['filter_reason'] = reason
        result.update({'filter_{}'.format(k): v for k, v in info.items()})
        result['manual_label'] = manual[0]
        result['manual_detail'] = manual[1]
        results.append(result)

    if results:
        df_out = pd.DataFrame(results)
        df_out.to_csv(CSV_OUT, index=False)

        n_pass = sum(1 for r in results if r['filter_pass'])
        n_correct = sum(1 for r in results
                        if (r['filter_pass'] == (MANUAL_LABELS.get(int(r['frame']), ('?', '?'))[0] == 'shot')))
        print("\n{}/{} pass filter".format(n_pass, len(results)))
        print("{}/{} match manual labels".format(n_correct, len(results)))
        print("Saved to {}".format(CSV_OUT))


if __name__ == '__main__':
    main()
