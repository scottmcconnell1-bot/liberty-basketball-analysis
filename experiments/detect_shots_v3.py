#!/usr/bin/env python3
"""Shot detection using per-frame hoop position. Tight thresholds."""

import csv
import numpy as np

HOOP_PATH = "hoop_Q1.npy"
BALL_CSV = "ball_v3_tracks.csv"
SHOT_CSV = "shots_v3.csv"

HOOP_RADIUS_FT = 0.75
SHOT_PROXIMITY_FT = 2.0
MIN_TRACK_LEN = 8
MIN_RELEASE_DIST_FT = 3.0
MAX_RELEASE_DIST_FT = 30.0
FT_LINE_FT = 22.0
MERGE_WINDOW = 30  # merge shots within this many frames

def load_hoop():
    data = np.load(HOOP_PATH, allow_pickle=True).item()
    frame_data = {}
    for i, f in enumerate(data['frame_indices']):
        r = data['radii'][i]
        frame_data[f] = {
            'center': data['centers'][i],
            'ft_per_px': HOOP_RADIUS_FT / r if r > 0 else 0.0053
        }
    return frame_data

def get_hoop(frame_idx, hoop_data):
    if frame_idx in hoop_data:
        return hoop_data[frame_idx]
    frames = sorted(hoop_data.keys())
    nearest = min(frames, key=lambda f: abs(f - frame_idx))
    return hoop_data[nearest]

def load_tracks():
    tracks = {}
    with open(BALL_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            tid = int(row['track_id'])
            if tid not in tracks:
                tracks[tid] = []
            tracks[tid].append({
                'frame': int(row['frame']),
                'cx': float(row['cx']), 'cy': float(row['cy']),
                'diam': float(row['diam']), 'circ': float(row['circ'])
            })
    for tid in tracks:
        tracks[tid].sort(key=lambda x: x['frame'])
    return tracks

def main():
    hoop_data = load_hoop()
    tracks = load_tracks()
    print(f"Hoop: {len(hoop_data)} frames, Tracks: {len(tracks)}")

    shots = []
    for tid, track in tracks.items():
        if len(track) < MIN_TRACK_LEN:
            continue

        frames = [p['frame'] for p in track]
        cxs = np.array([p['cx'] for p in track])
        cys = np.array([p['cy'] for p in track])

        # Find closest approach to hoop
        min_dist_ft = 999
        min_idx = -1
        for i, (f, x, y) in enumerate(zip(frames, cxs, cys)):
            hp = get_hoop(f, hoop_data)
            d = np.sqrt((x - hp['center'][0])**2 + (y - hp['center'][1])**2) * hp['ft_per_px']
            if d < min_dist_ft:
                min_dist_ft = d
                min_idx = i

        if min_dist_ft > SHOT_PROXIMITY_FT:
            continue

        # Peak near hoop (highest point = min Y)
        peak_idx = min_idx
        peak_y = cys[min_idx]
        for i in range(max(0, min_idx-6), min(len(cys), min_idx+7)):
            if cys[i] < peak_y:
                peak_y = cys[i]; peak_idx = i

        hp = get_hoop(frames[peak_idx], hoop_data)
        peak_dist_ft = np.sqrt((cxs[peak_idx]-hp['center'][0])**2 + (cys[peak_idx]-hp['center'][1])**2) * hp['ft_per_px']
        if peak_dist_ft > 4.0:
            continue

        # Release distance = distance from hoop at track start
        release_dist_ft = np.sqrt((cxs[0]-hp['center'][0])**2 + (cys[0]-hp['center'][1])**2) * hp['ft_per_px']
        if release_dist_ft < MIN_RELEASE_DIST_FT or release_dist_ft > MAX_RELEASE_DIST_FT:
            continue

        # Make/miss: does ball descend past hoop after peak?
        after = track[peak_idx:]
        make = False
        if len(after) >= 3:
            y_after = [p['cy'] for p in after]
            y_increased = sum(1 for i in range(len(y_after)-1) if y_after[i+1] > y_after[i])
            make = y_increased >= len(y_after) * 0.6  # Y increasing (descending) 60%+ of time

        shot_type = "3PT" if release_dist_ft > FT_LINE_FT else "2PT"

        shots.append({
            'track_id': tid, 'peak_frame': frames[peak_idx],
            'peak_cx': round(cxs[peak_idx], 1), 'peak_cy': round(cys[peak_idx], 1),
            'closest_dist_ft': round(min_dist_ft, 2), 'release_dist_ft': round(release_dist_ft, 1),
            'peak_dist_ft': round(peak_dist_ft, 1), 'shot_type': shot_type,
            'make': make, 'track_len': len(track),
            'start_frame': frames[0], 'end_frame': frames[-1]
        })

    shots.sort(key=lambda x: x['peak_frame'])

    # Merge nearby shots (same event)
    merged = []
    i = 0
    while i < len(shots):
        group = [shots[i]]
        j = i + 1
        while j < len(shots) and shots[j]['peak_frame'] - group[0]['peak_frame'] < MERGE_WINDOW:
            group.append(shots[j]); j += 1
        # Keep best (closest to hoop, longest track)
        group.sort(key=lambda s: (s['closest_dist_ft'], -s['track_len']))
        merged.append(group[0])
        i = j

    # Stats
    makes_2 = sum(1 for s in merged if s['shot_type']=='2PT' and s['make'])
    tota_2 = sum(1 for s in merged if s['shot_type']=='2PT')
    makes_3 = sum(1 for s in merged if s['shot_type']=='3PT' and s['make'])
    tota_3 = sum(1 for s in merged if s['shot_type']=='3PT')

    print(f"\nShots: {len(merged)} total")
    print(f"  2PT: {makes_2}/{tota_2} makes = {makes_2*2} pts")
    print(f"  3PT: {makes_3}/{tota_3} makes = {makes_3*3} pts")
    print(f"  Total points: {makes_2*2 + makes_3*3}")
    print(f"\n(Your manual: 2PT 2/7, 3PT 1/2 -> 8 pts)")

    print(f"\nAll shots:")
    for s in merged:
        print(f"  F{s['peak_frame']:4d} {'MAKE' if s['make'] else 'MISS':4s} {s['shot_type']:3s} "
              f"rel={s['release_dist_ft']:.0f}ft close={s['closest_dist_ft']:.1f}ft "
              f"len={s['track_len']}")

    with open(SHOT_CSV, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'track_id','peak_frame','peak_cx','peak_cy','closest_dist_ft',
            'release_dist_ft','peak_dist_ft','shot_type','make','track_len',
            'start_frame','end_frame'
        ])
        writer.writeheader()
        for s in merged:
            writer.writerow(s)
    print(f"\nSaved to {SHOT_CSV}")

if __name__ == "__main__":
    main()
