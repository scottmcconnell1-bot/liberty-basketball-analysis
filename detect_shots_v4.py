#!/usr/bin/env python3
"""
Shot detection v4: Focus on short parabolic ball tracks.
- Ball trajectories are SHORT (8-30 frames) and PARABOLIC
- Players are LONG tracks (50+ frames) - ignore them
- Group detections by spatiotemporal proximity to find ball arcs
- Use per-frame hoop position for shot classification
"""

import csv
import numpy as np

HOOP_PATH = "hoop_Q1.npy"
BALL_CSV = "ball_v3_tracks.csv"
SHOT_CSV = "shots_v4.csv"

HOOP_RADIUS_FT = 0.75
FT_LINE_FT = 22.0

def load_hoop():
    data = np.load(HOOP_PATH, allow_pickle=True).item()
    frame_data = {}
    for i, f in enumerate(data['frame_indices']):
        r = data['radii'][i]
        frame_data[f] = {
            'c': data['centers'][i],
            'fpr': HOOP_RADIUS_FT / r if r > 0 else 0.0053
        }
    return frame_data

def get_hp(fi, hd):
    if fi in hd: return hd[fi]
    nearest = min(hd.keys(), key=lambda x: abs(x-fi))
    return hd[nearest]

def main():
    hd = load_hoop()
    
    # Load all detections
    dets = []
    with open(BALL_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            dets.append({
                'tid': int(row['track_id']),
                'f': int(row['frame']),
                'cx': float(row['cx']), 'cy': float(row['cy']),
                'diam': float(row['diam']), 'circ': float(row['circ']),
                'hits': int(row['track_hits'])
            })
    
    print(f"Total detections: {len(dets)}")
    
    # Group by track
    tracks = {}
    for d in dets:
        if d['tid'] not in tracks:
            tracks[d['tid']] = []
        tracks[d['tid']].append(d)
    for tid in tracks:
        tracks[tid].sort(key=lambda x: x['f'])
    
    print(f"Total tracks: {len(tracks)}")
    
    # Filter: ball tracks are 6-35 frames, parabolic, pass near hoop
    ball_tracks = []
    for tid, track in tracks.items():
        n = len(track)
        if n < 6 or n > 40:
            continue
        
        frames = [d['f'] for d in track]
        cxs = np.array([d['cx'] for d in track])
        cys = np.array([d['cy'] for d in track])
        
        # Check parabolic: fit quadratic to Y
        try:
            fr = np.array(frames, dtype=float)
            if len(set(fr)) < 3:
                continue
            coeffs = np.polyfit(fr, cys, 2)
            if coeffs[0] <= 0:  # must open downward (Y increases downward)
                continue
            y_fit = np.polyval(coeffs, fr)
            residual = float(np.mean((cys - y_fit)**2))
            if residual > 3000:
                continue
        except:
            continue
        
        # Find closest approach to hoop
        min_dist = 999
        min_i = -1
        for i, d in enumerate(track):
            hp = get_hp(d['f'], hd)
            dist = np.sqrt((d['cx']-hp['c'][0])**2 + (d['cy']-hp['c'][1])**2) * hp['fpr']
            if dist < min_dist:
                min_dist = dist
                min_i = i
        
        if min_dist > 3.0:  # must pass within 3ft
            continue
        
        # Release distance
        hp_min = get_hp(track[min_i]['f'], hd)
        release_dist = np.sqrt((cxs[0]-hp_min['c'][0])**2 + (cys[0]-hp_min['c'][1])**2) * hp_min['fpr']
        
        # Total travel distance
        total_dist = float(np.sum(np.sqrt(np.diff(cxs)**2 + np.diff(cys)**2)))
        
        # Ball should travel at least 50px and at least 3ft
        if total_dist < 50 or release_dist < 2.0:
            continue
        
        # Peak frame
        peak_i = np.argmin(cys)
        
        # Make/miss: does Y increase (descend) after peak?
        after = track[peak_i:]
        make = False
        if len(after) >= 3:
            y_after = [d['cy'] for d in after]
            desc_count = sum(1 for i in range(len(y_after)-1) if y_after[i+1] > y_after[i])
            make = desc_count >= len(y_after) * 0.5
        
        shot_type = "3PT" if release_dist > FT_LINE_FT else "2PT"
        
        ball_tracks.append({
            'tid': tid, 'n': n, 'peak_frame': track[peak_i]['f'],
            'peak_cx': cxs[peak_i], 'peak_cy': cys[peak_i],
            'closest_ft': round(min_dist, 2),
            'release_ft': round(release_dist, 1),
            'travel_px': round(total_dist, 0),
            'residual': round(residual, 0),
            'shot_type': shot_type, 'make': make,
            'start_f': frames[0], 'end_f': frames[-1],
            'coeff_a': round(coeffs[0], 4)
        })
    
    print(f"Ball-like parabolic tracks near hoop: {len(ball_tracks)}")
    
    # Sort and dedup
    ball_tracks.sort(key=lambda x: x['peak_frame'])
    
    # Merge tracks within 20 frames
    merged = []
    i = 0
    while i < len(ball_tracks):
        group = [ball_tracks[i]]
        j = i + 1
        while j < len(ball_tracks) and ball_tracks[j]['peak_frame'] - group[0]['peak_frame'] < 20:
            group.append(ball_tracks[j]); j += 1
        # Best = closest to hoop, then highest coeff_a (most parabolic)
        group.sort(key=lambda s: (s['closest_ft'], -abs(s['coeff_a'])))
        merged.append(group[0])
        i = j
    
    print(f"After merge: {len(merged)} shots")
    
    # Stats
    m2 = sum(1 for s in merged if s['shot_type']=='2PT' and s['make'])
    t2 = sum(1 for s in merged if s['shot_type']=='2PT')
    m3 = sum(1 for s in merged if s['shot_type']=='3PT' and s['make'])
    t3 = sum(1 for s in merged if s['shot_type']=='3PT')
    
    print(f"\nResults:")
    print(f"  2PT: {m2}/{t2} makes = {m2*2} pts")
    print(f"  3PT: {m3}/{t3} makes = {m3*3} pts")
    print(f"  Total: {m2+m3} makes / {t2+t3} attempts = {m2*2+m3*3} pts")
    print(f"\n(Target: 2PT 2/7, 3PT 1/2 -> 8 pts)")
    
    print(f"\nAll shots:")
    for s in merged:
        print(f"  F{s['peak_frame']:4d} {'MAKE' if s['make'] else 'MISS':4s} {s['shot_type']:3s} "
              f"close={s['closest_ft']:.1f}ft rel={s['release_ft']:.0f}ft "
              f"travel={s['travel_px']:.0f}px resid={s['residual']:.0f}")
    
    with open(SHOT_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'tid','n','peak_frame','peak_cx','peak_cy','closest_ft',
            'release_ft','travel_px','residual','shot_type','make',
            'start_f','end_f','coeff_a'
        ])
        writer.writeheader()
        for s in merged:
            writer.writerow(s)
    print(f"\nSaved to {SHOT_CSV}")

if __name__ == "__main__":
    main()
