#!/usr/bin/env python3
"""v44: Extract video clips around all near-basket NN detection clusters.

For each candidate region, extract a short clip (.mp4) showing the ball movement.
Output organized by score tier for efficient human review.

This replaces the failing automatic classifier with a human-in-the-loop approach:
1. Extract clips for all 36 candidates
2. Sort by score tier (high/medium/low)
3. Human labels each clip
4. Use labels to train a proper classifier
"""
import os, pickle, cv2
import numpy as np
import pandas as pd

PKL_V14 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl'
VIDEO   = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
CSV_V43 = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_features_v43.csv'
OUT_BASE = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/clips_v44'

BLX, BLY = 179.0, 525.0
BRX, BRY = 1009.0, 466.0


def main():
    df = pd.read_csv(CSV_V43)
    with open(PKL_V14, 'rb') as f:
        v14 = pickle.load(f)
    bx, by = v14['ball_x'], v14['ball_y']
    total = len(bx)

    cap = cv2.VideoCapture(VIDEO)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    # Sort by score
    df = df.sort_values('shot_score', ascending=False)

    for tier, (lo, hi, label) in enumerate([
        (5, 999, 'HIGH'),
        (3, 4.9, 'MEDIUM'),
        (0, 2.9, 'LOW'),
    ]):
        tier_df = df[(df['shot_score'] >= lo) & (df['shot_score'] <= hi)]
        tier_dir = os.path.join(OUT_BASE, label)
        os.makedirs(tier_dir, exist_ok=True)

        for _, row in tier_df.iterrows():
            f = int(row['frame'])
            n_before = 10   # frames before anchor
            n_after = 15    # frames after anchor

            f_start = max(0, f - n_before)
            f_end = min(total, f + n_after + 1)

            # Video writer
            clip_path = os.path.join(tier_dir, 'F{:04d}_s{:.1f}.mp4'.format(f, row['shot_score']))
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')

            # Read first frame to get dimensions
            cap.set(cv2.CAP_PROP_POS_FRAMES, f_start)
            ret, first_frame = cap.read()
            if not ret:
                continue
            h, w = first_frame.shape[:2]
            writer = cv2.VideoWriter(clip_path, fourcc, fps/3, (w, h))  # slower fps for review

            for fi in range(f_start, f_end):
                cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
                ret, frame = cap.read()
                if not ret:
                    continue

                vis = frame.copy()

                # Draw baskets
                cv2.circle(vis, (int(BLX), int(BLY)), 10, (0, 0, 255), 2)
                cv2.circle(vis, (int(BRX), int(BRY)), 10, (0, 0, 255), 2)

                # Draw NN ball if valid
                if fi < total and not np.isnan(bx[fi]):
                    bpx, bpy = int(bx[fi]), int(by[fi])
                    cv2.circle(vis, (bpx, bpy), 8, (0, 255, 255), -1)
                    cv2.circle(vis, (bpx, bpy), 12, (0, 255, 255), 2)

                # Anchor frame marker
                if fi == f:
                    cv2.rectangle(vis, (0, 0), (w, h), (0, 0, 255), 3)

                # Label
                label_text = 'F{} {}/{} score={:.1f} {}'.format(
                    fi, fi - f_start, f_end - f_start - 1,
                    row['shot_score'], row.get('manual_shot', ''))
                cv2.rectangle(vis, (5, h-35), (len(label_text)*9+15, h-5), (0, 0, 0), -1)
                cv2.putText(vis, label_text, (10, h-15),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

                writer.write(vis)

            writer.release()
            print("  {} F{} score={:.1f} -> {}".format(label, f, row['shot_score'], clip_path))

    cap.release()

    # Summary
    for label in ['HIGH', 'MEDIUM', 'LOW']:
        clips = [f for f in os.listdir(os.path.join(OUT_BASE, label)) if f.endswith('.mp4')]
        print("{} tier: {} clips".format(label, len(clips)))

    print("\nClips saved to {}/".format(OUT_BASE))


if __name__ == '__main__':
    main()
