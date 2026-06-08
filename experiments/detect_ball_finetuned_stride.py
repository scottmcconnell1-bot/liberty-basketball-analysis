import cv2
import numpy as np
from ultralytics import YOLO
import pandas as pd
import sys

def main():
    model_path = sys.argv[1] if len(sys.argv) > 1 else 'runs/detect/train-2/weights/best.pt'
    video_path = sys.argv[2] if len(sys.argv) > 2 else 'uploads/Liberty_Vs_Riverstone_20260519_103815_segment_2min.webm'
    stride = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    conf_thresh = float(sys.argv[4]) if len(sys.argv) > 4 else 0.001
    model = YOLO(model_path)
    cap = cv2.VideoCapture(video_path)
    frame_idx = 0
    rows = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % stride != 0:
            frame_idx += 1
            continue
        results = model(frame, conf=conf_thresh, classes=[0], verbose=False)[0]
        if results.boxes.shape[0] > 0:
            boxes = results.boxes.xywhn.cpu().numpy()
            confs = results.boxes.conf.cpu().numpy()
            idx = np.argmax(confs)
            xc, yc, wn, hn = boxes[idx]
            rows.append({
                'frame': frame_idx,
                'xc': float(xc),
                'yc': float(yc),
                'wn': float(wn),
                'hn': float(hn),
                'conf': float(confs[idx])
            })
        frame_idx += 1
        if frame_idx % 100 == 0:
            print(f'Processed {frame_idx} frames')
    cap.release()
    df = pd.DataFrame(rows)
    out_csv = f'ball_finetuned_2min_stride{stride}.csv'
    df.to_csv(out_csv, index=False)
    print(f'Saved {len(df)} detections to {out_csv}')

if __name__ == '__main__':
    main()
