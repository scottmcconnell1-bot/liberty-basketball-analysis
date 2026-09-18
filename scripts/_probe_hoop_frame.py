import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
from net_detector import detect_hoop, detect_hoop_cv

video = "uploads/nfhs_gam0a66d85e12.mp4"
cap = cv2.VideoCapture(video)
fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
ms = 120800
fn = int(round((ms / 1000.0) * fps))
cap.set(cv2.CAP_PROP_POS_FRAMES, fn)
ok, frame = cap.read()
cap.release()
print("open", ok, "fps", fps, "frame", fn, "shape", None if not ok else frame.shape)
if ok:
    print("cv", detect_hoop_cv(frame))
    print("combined", detect_hoop(frame))
