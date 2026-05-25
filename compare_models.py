"""Compare abdullahtarek vs YOLOv8m for ball detection on Q1."""
import cv2, numpy as np, time
from ultralytics import YOLO

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'

ball_m = YOLO('/home/monk-admin/PROJECTS/liberty-basketball-analysis/models/ball_detector.pt')
yolo_m = YOLO('yolov8m.pt')

cap = cv2.VideoCapture(VIDEO)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

print("Frame | abdullahtarek Ball | YOLOv8m sports_ball")
print("-" * 75)

abd_count = 0
yolo_count = 0
both_count = 0
abd_close_to_hoop = 0
yolo_close_to_hoop = 0

for fn in range(0, total, 50):
    cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
    ret, frame = cap.read()
    if not ret: continue

    r1 = ball_m.predict(frame, conf=0.1, verbose=False)[0]
    abd_balls = []
    if r1.boxes is not None:
        for box in r1.boxes:
            cls = ball_m.names[int(box.cls[0])]
            cf = float(box.conf[0])
            if cls == 'Ball':
                x1,y1,x2,y2 = box.xyxy[0].tolist()
                abd_balls.append(((x1+x2)/2, (y1+y2)/2, cf))

    r2 = yolo_m.predict(frame, conf=0.1, verbose=False)[0]
    yolo_balls = []
    if r2.boxes is not None:
        for box in r2.boxes:
            cls = yolo_m.names[int(box.cls[0])]
            cf = float(box.conf[0])
            if 'ball' in cls.lower():
                x1,y1,x2,y2 = box.xyxy[0].tolist()
                yolo_balls.append(((x1+x2)/2, (y1+y2)/2, cf))

    if abd_balls:
        abd_count += 1
    if yolo_balls:
        yolo_count += 1
    if abd_balls and yolo_balls:
        both_count += 1

    abd_str = "; ".join(["(%.0f,%.0f,%.2f)" % (b[0], b[1], b[2]) for b in abd_balls[:3]])
    yolo_str = "; ".join(["(%.0f,%.0f,%.2f)" % (b[0], b[1], b[2]) for b in yolo_balls[:3]])
    print("%5d | %-40s | %s" % (fn, abd_str or 'none', yolo_str or 'none'))

cap.release()
print()
print("Summary (sampled every 50 frames, %d frames):" % (total/50))
print("  abdullahtarek ball detections: %d (%.1f%%)" % (abd_count, abd_count/(total/50)*100))
print("  YOLOv8m sports ball detections: %d (%.1f%%)" % (yolo_count, yolo_count/(total/50)*100))
print("  Both detect: %d" % both_count)
