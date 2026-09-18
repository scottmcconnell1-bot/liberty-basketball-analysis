"""Orange rim + hanging net detector."""

import numpy as np

from court_memory import FrameCourtMemory, KeyPolygon
from net_detector import detect_hoop, detect_hoop_cv, hoop_at


def _rim_and_net_frame(w=640, h=360, cx=320, cy=70, cr=22):
    import cv2

    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:] = (30, 40, 25)
    cv2.circle(frame, (cx, cy), cr, (20, 90, 220), 5)
    cv2.rectangle(frame, (cx - cr, cy + 6), (cx + cr, cy + cr * 3), (210, 210, 210), -1)
    return frame


def test_detects_orange_rim_with_net_below():
    frame = _rim_and_net_frame()
    found = detect_hoop_cv(frame)
    assert found is not None
    assert abs(found["x"] - 320) < 40
    assert found["y"] < 140
    assert found["confidence"] >= 0.3
    assert found["net_bottom"] > found["y"]


def test_detects_red_rim_like_nfhs_camera():
    import cv2

    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    frame[:] = (90, 90, 90)
    cv2.rectangle(frame, (280, 20), (400, 78), (70, 70, 70), -1)
    cv2.ellipse(frame, (320, 82), (28, 8), 0, 0, 360, (0, 30, 210), 4)
    cv2.rectangle(frame, (300, 88), (340, 130), (200, 200, 200), -1)
    found = detect_hoop_cv(frame)
    assert found is not None
    assert abs(found["x"] - 320) < 50
    assert 50 <= found["y"] <= 120


def test_detect_hoop_ignores_empty_frame():
    assert detect_hoop(np.zeros((0, 0, 3), dtype=np.uint8)) is None
    blank = np.zeros((240, 320, 3), dtype=np.uint8)
    assert detect_hoop_cv(blank) is None


def test_hoop_at_picks_nearest_sample():
    samples = [
        {"timestamp_ms": 1000, "x": 10, "y": 20},
        {"timestamp_ms": 5000, "x": 80, "y": 40},
    ]
    hit = hoop_at(samples, 4800)
    assert hit["x"] == 80
    assert hoop_at(samples, 20000) is None


def test_detected_hoop_beats_key_estimate():
    mem = FrameCourtMemory()
    mem.key = KeyPolygon(300, 200, 500, 500)
    mem.detected_hoop = (410.0, 90.0)
    assert mem.hoop_xy() == (410.0, 90.0)
    assert mem.close_to_rim(400, 100)
