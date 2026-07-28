#!/usr/bin/env python3
"""v43: Corrected shot filter — fundamental fix.

Root problem: previous scorers rewarded observation quality (mono correlation,
clear-floor visibility) instead of actual shot trajectory toward basket.

Key insight: A real shot requires ALL of:
  1. Ball STARTS at meaningful distance from basket (d > 150px)
  2. Ball ENDS close to basket (d < 100px)
  3. Ball shows PROGRESSIVE convergence (not just noise around flat profile)
  4. Correct court half
  5. Not stationary dead-ball

F223/F988 false positive pattern: 3-6 detections at nearly same distance from
basket, perfect mono correlation because distance barely changes (all noise around
a flat line). Solution: require minimum distance RANGE across the window.

F0582 missed pattern: 16 detections but spread across a large area, so mono
correlation is diluted. Solution: look at convergence in the LATTER HALF of
detections only (the approach phase), not the whole window.

F0617 missed pattern: only 3 detections. Solution: lower the detection floor to
2+ and weight by trajectory shape, not observation count.
"""
import os, pickle, cv2
import numpy as np
import pandas as pd

PKL_V14 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl'
VIDEO   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
CSV_OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v43.csv'
OUT_DIR = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/audit_v43'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0
HALFCOURT_X = 640.0

BWD, FWD = 15, 20


def nd(x, y):
    return min(np.sqrt((x-BLX)**2+(y-BLY)**2), np.sqrt((x-BRX)**2+(y-BRY)**2))


def nearest_basket(x, y):
    dl = np.sqrt((x-BLX)**2+(y-BLY)**2)
    dr = np.sqrt((x-BRX)**2+(y-BRY)**2)
    return (BLX, BLY) if dl < dr else (BRX, BRY)


def compute_score(f, bx, by, total):
    f_start = max(0, f - BWD)
    f_end = min(total, f + FWD + 1)
    win_x = bx[f_start:f_end]
    win_y = by[f_start:f_end]
    valid = ~np.isnan(win_x) & ~np.isnan(win_y)
    n_valid = int(np.sum(valid))

    if n_valid < 2:
        return 0, {'n_valid': n_valid}, False, 'too_few'

    valid_idx = np.where(valid)[0]
    fx = win_x[valid].astype(float)
    fy = win_y[valid].astype(float)
    frames = f_start + valid_idx

    # Distances to nearest basket
    dists_all = np.array([nd(x, y) for x, y in zip(fx, fy)])
    anchor_local = int(np.argmin(dists_all))
    ax, ay = fx[anchor_local], fy[anchor_local]
    d_anchor = float(dists_all[anchor_local])
    basket_x, basket_y = nearest_basket(ax, ay)

    # Per-detection distances to nearest basket
    dists = np.array([np.sqrt((x-basket_x)**2 + (y-basket_y)**2) for x,y in zip(fx, fy)])

    feats = {'n_valid': n_valid, 'anchor_dist': round(d_anchor, 1)}

    # 1. CORRECT HALF
    if basket_x == BLX:
        correct_half = ax < HALFCOURT_X + 100
    else:
        correct_half = ax > HALFCOURT_X - 100
    feats['correct_half'] = bool(correct_half)

    if not correct_half:
        return 0, feats, False, 'wrong_half'

    # 2. DISTANCE RANGE: must span meaningful distance (reject flat profiles)
    d_range = float(np.max(dists) - np.min(dists))
    feats['dist_range'] = round(d_range, 1)
    if d_range < 80:
        return 0, feats, False, 'flat_profile'

    # 3. START FAR, END CLOSE: real shots start away, end near
    d_start = float(dists[0])
    d_end = float(dists[-1])
    d_min = float(np.min(dists))
    feats['dist_start'] = round(d_start, 1)
    feats['dist_end'] = round(d_end, 1)
    feats['dist_min'] = round(d_min, 1)

    approach = d_start - d_end  # positive = converging
    feats['approach'] = round(approach, 1)
    if approach < 20:
        return 0, feats, False, 'no_convergence'

    # 4. LATTER-HALF CONVERGENCE: look at last half of detections only
    # (the approach phase, discarding pre-approach noise)
    mid = n_valid // 2
    if n_valid >= 4:
        late_half_dist = np.mean(dists[mid:])
        early_half_dist = np.mean(dists[:mid])
        late_convergence = early_half_dist - late_half_dist
    else:
        late_convergence = approach
    feats['late_convergence'] = round(late_convergence, 1)

    # 5. STATIONARY REJECT
    if n_valid >= 2:
        dt = np.diff(frames).astype(float); dt[dt==0]=1
        speeds = np.sqrt(np.diff(fx)**2 + np.diff(fy)**2) / dt
        stat_ratio = float(np.sum(speeds < 5) / len(speeds))
        total_move = float(np.sum(np.sqrt(np.diff(fx)**2 + np.diff(fy)**2)))
    else:
        stat_ratio = 1.0; total_move = 0.0
    feats['stationary_ratio'] = round(stat_ratio, 3)
    feats['total_move'] = round(total_move, 1)
    if stat_ratio > 0.8 and total_move < 50:
        return 0, feats, False, 'stationary'

    # 6. ASPECT RATIO: vertical clustering preferred
    sx = float(np.std(fx)); sy = float(np.std(fy))
    ar = sx/sy if sy > 0 else 999
    feats['aspect_ratio'] = round(ar, 3)

    # --- Scoring ---
    score = 0.0

    # Distance range: must be substantial
    if d_range > 200: score += 2
    elif d_range > 100: score += 1.5
    else: score += 0.5

    # Start distance: real shots start from meaningful range
    if d_start > 200: score += 1
    elif d_start > 150: score += 0.5

    # End distance: real shots terminate near hoop
    if d_min < 80: score += 3
    elif d_min < 120: score += 2
    elif d_min < 200: score += 1

    # Approach magnitude
    if approach > 200: score += 2
    elif approach > 100: score += 1.5
    elif approach > 50: score += 1

    # Late convergence
    if late_convergence > 100: score += 1.5
    elif late_convergence > 50: score += 1

    # Vertical movement (lower aspect ratio = more vertical)
    if ar < 0.5: score += 1.5
    elif ar < 1.0: score += 1
    elif ar > 2.0: score -= 1  # penalize horizontal spread

    # Penalty for stationary
    if stat_ratio > 0.6: score -= 2

    feats['shot_score'] = round(score, 1)
    is_shot = score >= 5.0

    return score, feats, is_shot, 'score={:.1f}'.format(score)


def main():
    with open(PKL_V14, 'rb') as f:
        v14 = pickle.load(f)
    bx, by = v14['ball_x'], v14['ball_y']
    total = len(bx)

    VISUAL = {
        61: ('no', 'transition'),
        182: ('weak', 'unclear'),
        223: ('no', 'dead_ball_halfcourt'),
        582: ('yes', 'putback'),         # REAL
        617: ('yes', 'jump_shot'),       # REAL
        934: ('no', 'dribble'),
        988: ('no', 'inbound'),
        1073: ('no', 'ft_setup'),
        1292: ('no', 'ft_lineup'),
        1764: ('no', 'wrong_half'),
        2303: ('weak', 'perimeter'),
    }

    # Process ALL candidates from the original 112 near-basket regions
    # Find candidates the same way v40 did
    near_basket = np.array([nd(bx[i], by[i]) < 300 if not np.isnan(bx[i]) else False
                            for i in range(total)])

    candidates = []
    in_region = False
    region_start = 0
    for i in range(total):
        if near_basket[i] and not in_region:
            region_start = i; in_region = True
        elif not near_basket[i] and in_region:
            region = (region_start, i)
            region_dists = [nd(bx[j], by[j]) if not np.isnan(bx[j]) else 999
                           for j in range(region[0], region[1])]
            anchor = region[0] + int(np.argmin(region_dists))
            win_valid = int(np.sum(~np.isnan(bx[max(0,anchor-15):min(total,anchor+20)])))
            if win_valid >= 2:
                candidates.append(anchor)
            in_region = False
    if in_region:
        region_dists = [nd(bx[j], by[j]) if not np.isnan(bx[j]) else 999
                       for j in range(region_start, total)]
        anchor = region_start + int(np.argmin(region_dists))
        win_valid = int(np.sum(~np.isnan(bx[max(0,anchor-15):min(total,anchor+20)])))
        if win_valid >= 2:
            candidates.append(anchor)

    # Dedup within 30 frames
    deduped = []
    for c in sorted(candidates):
        if deduped and c - deduped[-1] < 30:
            prev = deduped[-1]
            pv = int(np.sum(~np.isnan(bx[max(0,prev-15):min(total,prev+20)])))
            cv = int(np.sum(~np.isnan(bx[max(0,c-15):min(total,c+20)])))
            if cv > pv:
                deduped[-1] = c
        else:
            deduped.append(c)

    print("Candidates: {} initial, {} deduped".format(len(candidates), len(deduped)))

    results = []
    os.makedirs(OUT_DIR, exist_ok=True)
    cap = cv2.VideoCapture(VIDEO)

    for f in deduped:
        score, feats, is_shot, reason = compute_score(f, bx, by, total)

        visual = VISUAL.get(f, ('?', '?'))
        match = 'OK' if (is_shot == (visual[0] in ('yes','weak'))) or \
                       (visual[0] == 'weak' and not is_shot) else 'MISMATCH'

        print("  F{}: {:5s} score={:5.1f} visual={:30s} [{}] n={} range={:.0f} start={:.0f} end={:.0f} late_conv={:.1f}".format(
            f, 'SHOT' if is_shot else 'REJ', score, '{} ({})'.format(*visual), match,
            feats['n_valid'], feats.get('dist_range',0), feats.get('dist_start',0),
            feats.get('dist_end',0), feats.get('late_convergence',0)))

        result = {'frame': f, 'is_shot': is_shot, 'reason': reason, **feats,
                  'manual_shot': visual[0], 'manual_detail': visual[1]}
        results.append(result)

        # Overlay for shots and near-misses
        if is_shot or score > 3:
            f_start = max(0, f - BWD); f_end = min(total, f + FWD + 1)
            wx = bx[f_start:f_end]; wy = by[f_start:f_end]
            v = ~np.isnan(wx) & ~np.isnan(wy)
            cap.set(cv2.CAP_PROP_POS_FRAMES, f)
            ret, img = cap.read()
            if ret and np.sum(v) >= 2:
                vis = img.copy(); h_img, w_img = vis.shape[:2]
                cv2.circle(vis,(int(BLX),int(BLY)),12,(0,0,255),2)
                cv2.circle(vis,(int(BRX),int(BRY)),12,(0,0,255),2)
                cv2.line(vis,(int(HALFCOURT_X),0),(int(HALFCOURT_X),h_img),(100,100,100),1)
                for x,y in zip(wx[v].astype(float), wy[v].astype(float)):
                    cv2.circle(vis,(int(x),int(y)),7,(0,255,255),-1)
                lbl = 'F{} {} s={:.1f}'.format(f, 'SHOT' if is_shot else 'REJ', score)
                cv2.rectangle(vis,(5,5),(len(lbl)*9+15,35),(0,0,0),-1)
                cv2.putText(vis,lbl,(10,25),cv2.FONT_HERSHEY_SIMPLEX,0.55,(255,255,255),1)
                cv2.imwrite(os.path.join(OUT_DIR,'F{:04d}.jpg'.format(f)), vis)

    cap.release()

    if results:
        df = pd.DataFrame(results)
        df.to_csv(CSV_OUT, index=False)
        n_shots = sum(1 for r in results if r['is_shot'])
        n_ok = sum(1 for r in results if (r['is_shot'] == (r['manual_shot'] in ('yes','weak'))) or
                                            (r['manual_shot']=='weak' and not r['is_shot']))
        print("\n{}/{}/{} (shots/total/candidates)".format(n_shots, len(results), len(deduped)))
        print("{}/{} match visual".format(n_ok, len(results)))
        print("\n=== Shot Score Ranking ===")
        for r in sorted(results, key=lambda x: x.get('shot_score',0), reverse=True)[:15]:
            print("  F{}: {:.1f} {} manual={:20s} range={:.0f} late_conv={:.1f} ar={:.2f}".format(
                r['frame'], r.get('shot_score',0), 'SHOT' if r['is_shot'] else 'rej',
                r['manual_shot'], r.get('dist_range',0), r.get('late_convergence',0),
                r.get('aspect_ratio',0)))
        print("\nSaved to {}".format(CSV_OUT))


if __name__ == '__main__':
    main()
