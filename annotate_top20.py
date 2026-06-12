"""
Extract annotated frames for the top-20 detections.
Draw a cross and label at each detection point so we can visually inspect.
"""
import cv2
import numpy as np
import pickle

with open('/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/shot_v14.pkl','rb') as f:
    v14 = pickle.load(f)

shots = sorted(v14['shots'], key=lambda s: s['conf'], reverse=True)[:20]
cap = cv2.VideoCapture('/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm')

# Classification results from automated audit
classifications = {
    0: ('Other', 'Low'),
    1: ('Other', 'Low'),
    2: ('Rim/backboard', 'Medium'),      # F467, dB=127
    3: ('Other', 'Low'),
    4: ('Other', 'Low'),
    5: ('Rim/backboard', 'Medium'),      # F2051, dB=134
    6: ('Other', 'Low'),
    7: ('Court marking/logo', 'Medium'),  # F1072, center
    8: ('Rim/backboard', 'High'),        # F1290, dB=10
    9: ('Rim/backboard', 'High'),        # F2318, dB=97
    10: ('Other', 'Low'),
    11: ('Rim/backboard', 'Medium'),     # F2591, dB=110
    12: ('Other', 'Low'),
    13: ('Rim/backboard', 'Medium'),     # F2505, dB=66
    14: ('Rim/backboard', 'Medium'),     # F33, dB=142
    15: ('Other', 'Low'),
    16: ('Other', 'Low'),
    17: ('Court marking/logo', 'Medium'), # F2642, center
    18: ('Rim/backboard', 'Medium'),     # F236, dB=63
    19: ('Rim/backboard', 'Medium'),     # F617, dB=138
}

detections_info = {
    0: (808, 977.7, 630.8, 0.0017),
    1: (120, 1106.1, 473.5, 0.0016),
    2: (467, 273.2, 440.4, 0.0016),
    3: (724, 466.8, 308.0, 0.0013),
    4: (2174, 915.1, 474.6, 0.0012),
    5: (2051, 304.6, 439.4, 0.0011),
    6: (990, 1043.1, 537.0, 0.0010),
    7: (1072, 433.8, 407.2, 0.0010),
    8: (1290, 693.3, 439.3, 0.0008),
    9: (2318, 785.0, 472.8, 0.0008),
    10: (2435, 948.7, 440.5, 0.0007),
    11: (2591, 785.3, 506.6, 0.0007),
    12: (1413, 853.5, 502.0, 0.0006),
    13: (2505, 756.6, 440.7, 0.0005),
    14: (33, 597.2, 342.4, 0.0004),
    15: (68, 212.3, 378.1, 0.0004),
    16: (259, 241.1, 280.5, 0.0004),
    17: (2642, 467.4, 507.5, 0.0004),
    18: (236, 241.4, 507.1, 0.0003),
    19: (617, 276.8, 429.3, 0.0003),
}

out_dir = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/pipeline_output/detector_audit/annotated_top20'
import os
os.makedirs(out_dir, exist_ok=True)

for idx, (fn, bx, by, conf) in detections_info.items():
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if not ret:
        continue
    
    # Draw cross at detection
    bx_i, by_i = int(bx), int(by)
    color = (0, 255, 0)  # green
    cv2.drawMarker(frame, (bx_i, by_i), color, cv2.MARKER_CROSS, 30, 3)
    cv2.circle(frame, (bx_i, by_i), 15, color, 2)
    
    # Label
    cls, audit_conf = classifications[idx]
    label = f"#{idx+1} F{fn} {cls} ({audit_conf})"
    cv2.putText(frame, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    cv2.putText(frame, f"conf={conf:.6f} ({bx:.0f},{by:.0f})", (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    
    out_path = f"{out_dir}/annotated_{idx+1:02d}_f{fn}.jpg"
    cv2.imwrite(out_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(f"Wrote {out_path}")

cap.release()
print(f"\nAll 20 annotated frames saved to {out_dir}/")
