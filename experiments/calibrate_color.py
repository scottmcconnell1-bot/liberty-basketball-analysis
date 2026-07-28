"""Calibrate basketball color from existing v9f raw detections."""
import cv2, numpy as np
import pandas as pd

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
raw = pd.read_csv('/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/v9f_balls_raw.csv')

cap = cv2.VideoCapture(VIDEO)

hsv_samples = []
for _, r in raw.iterrows():
    if r.conf < 0.5:
        continue
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(r.frame))
    ret, frame = cap.read()
    if not ret: continue

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    cx, cy = int((r.x1+r.x2)/2), int((r.y1+r.y2)/2)
    roi = hsv[max(0,cy-3):cy+3, max(0,cx-3):cx+3]
    if roi.size > 0:
        hsv_samples.append(np.mean(roi.reshape(-1,3), axis=0))

cap.release()

hsv_arr = np.array(hsv_samples)
print("Samples: %d" % len(hsv_samples))
print("H: mean=%.1f std=%.1f range=[%.0f, %.0f]" % (hsv_arr[:,0].mean(), hsv_arr[:,0].std(), hsv_arr[:,0].min(), hsv_arr[:,0].max()))
print("S: mean=%.1f std=%.1f range=[%.0f, %.0f]" % (hsv_arr[:,1].mean(), hsv_arr[:,1].std(), hsv_arr[:,1].min(), hsv_arr[:,1].max()))
print("V: mean=%.1f std=%.1f range=[%.0f, %.0f]" % (hsv_arr[:,2].mean(), hsv_arr[:,2].std(), hsv_arr[:,2].min(), hsv_arr[:,2].max()))
print()

for pct_lo, pct_hi, label in [(5, 95, "Wide"), (10, 90, "Medium"), (25, 75, "Tight")]:
    print("%s bounds (%d-%d pctl):" % (label, pct_lo, pct_hi))
    lo = [int(np.percentile(hsv_arr[:,i], pct_lo)) for i in range(3)]
    hi = [int(np.percentile(hsv_arr[:,i], pct_hi)) for i in range(3)]
    print("  Lower: [%d, %d, %d]" % (lo[0], lo[1], lo[2]))
    print("  Upper: [%d, %d, %d]" % (hi[0], hi[1], hi[2]))
    print()
