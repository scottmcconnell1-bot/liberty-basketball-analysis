"""Step 2: Track balls from saved hybrid2 detections."""
import cv2, numpy as np, pickle, os
from collections import defaultdict
import pandas as pd

OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output'

df = pd.read_csv(OUT + '/hybrid2_ball_detections.csv')
print("Loaded %d detections" % len(df))

# Build detections_by_frame
detections_by_frame = defaultdict(list)
for _, r in df.iterrows():
    detections_by_frame[int(r.frame)].append({
        'cx': r.cx, 'cy': r.cy, 'conf': r.conf
    })

print("Frames with detections: %d" % len(detections_by_frame))

# --- Tracking ---
def track_balls(detections_by_frame):
    tracks = []
    active_tracks = []
    all_frames = sorted(detections_by_frame.keys())

    for fn in all_frames:
        dets = detections_by_frame[fn]

        if not active_tracks:
            for d in dets:
                active_tracks.append([(fn, d['cx'], d['cy'], d['conf'])])
            continue

        used_dets = set()
        new_active = []

        for track in active_tracks:
            last_fn, last_cx, last_cy, last_conf = track[-1]
            frames_since_last = fn - last_fn

            if frames_since_last > 10:
                if len(track) >= 2:
                    tracks.append(track)
                continue

            best_det = None
            best_dist = float('inf')
            max_jump = min(200, 40 * frames_since_last)

            for i, d in enumerate(dets):
                if i in used_dets:
                    continue
                dist = np.sqrt((d['cx'] - last_cx)**2 + (d['cy'] - last_cy)**2)
                if dist < max_jump and dist < best_dist:
                    best_dist = dist
                    best_det = i

            if best_det is not None:
                d = dets[best_det]
                track.append((fn, d['cx'], d['cy'], d['conf']))
                used_dets.add(best_det)
                new_active.append(track)
            else:
                if len(track) >= 2:
                    tracks.append(track)

        for i, d in enumerate(dets):
            if i not in used_dets:
                new_active.append([(fn, d['cx'], d['cy'], d['conf'])])

        active_tracks = new_active

    for track in active_tracks:
        if len(track) >= 2:
            tracks.append(track)

    return tracks

print("Tracking...")
tracks = track_balls(detections_by_frame)
print("Found %d tracks" % len(tracks))

track_lengths = [len(t) for t in tracks]
track_durations = [(t[-1][0] - t[0][0]) for t in tracks]
print("Track lengths: min=%d max=%d mean=%.1f" % (
    min(track_lengths), max(track_lengths), np.mean(track_lengths)))
print("Track durations: min=%d max=%d mean=%.1f" % (
    min(track_durations), max(track_durations), np.mean(track_durations)))

# Save
with open(OUT + '/hybrid2_tracks.pkl', 'wb') as f:
    pickle.dump(tracks, f)
print("Saved tracks pickle")

track_dets = []
for track_id, track in enumerate(tracks):
    for fn, cx, cy, conf in track:
        track_dets.append({
            'track_id': track_id, 'frame': fn,
            'cx': round(cx, 1), 'cy': round(cy, 1),
            'conf': round(conf, 3)
        })
pd.DataFrame(track_dets).to_csv(OUT + '/hybrid2_tracks.csv', index=False)
print("Saved tracks CSV")

# Print top 20 longest tracks
print("\nTop 20 longest tracks:")
sorted_tracks = sorted(tracks, key=lambda t: -len(t))
for i, t in enumerate(sorted_tracks[:20]):
    dur = t[-1][0] - t[0][0]
    cx_mean = np.mean([p[1] for p in t])
    cy_mean = np.mean([p[2] for p in t])
    cx_std = np.std([p[1] for p in t])
    cy_std = np.std([[p[2] for p in t]])
    print("  T%03d: len=%d span=%d center=(%.0f,%.0f) spread=(%.0f,%.0f) conf=%.3f" % (
        tracks.index(t), len(t), dur, cx_mean, cy_mean, cx_std, cy_std, t[0][3]))

# Track length distribution
print("\nTrack length distribution:")
for lo, hi in [(2,5),(5,10),(10,20),(20,50),(50,100),(100,999)]:
    cnt = sum(1 for t in tracks if lo <= len(t) < hi)
    print("  %d-%d frames: %d tracks" % (lo, hi, cnt))
