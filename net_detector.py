"""Hoop / net detector for a sideline NFHS camera.

Person+ball YOLO cannot see nylon. This finds the orange rim and the net
hanging under it in a video frame. Optional court-pose keypoints are a
fallback when orange is washed out.

Does not change models/ball_detector.pt.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent
TRACK_DIR = ROOT / "data" / "hoop_tracks"
COURT_POSE_PATH = ROOT / "models" / "court_keypoint_detector.pt"


def _safe_name(game_id: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", (game_id or "").strip())[:180] or "unknown"


def track_path(game_id: str) -> Path:
    return TRACK_DIR / f"{_safe_name(game_id)}.json"


def detect_hoop(frame_bgr: np.ndarray) -> dict[str, Any] | None:
    """Return {x, y, r, net_bottom, confidence, source} or None."""
    if frame_bgr is None or getattr(frame_bgr, "size", 0) == 0:
        return None
    found = detect_hoop_cv(frame_bgr)
    if found and float(found.get("confidence") or 0) >= 0.35:
        return found
    pose = detect_hoop_from_court_pose(frame_bgr)
    if pose is None:
        return found
    if found is None or float(pose.get("confidence") or 0) > float(found.get("confidence") or 0):
        return pose
    return found


def detect_hoop_cv(frame_bgr: np.ndarray) -> dict[str, Any] | None:
    """Find the red/orange rim; the net hanging under it confirms."""
    import cv2

    h, w = frame_bgr.shape[:2]
    top = max(80, int(h * 0.42))
    roi = frame_bgr[0:top, :]
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    rims = _red_rims(hsv, roi, h)
    if rims:
        rims.sort(key=lambda c: (-c["confidence"], -c.get("area", 0)))
        return rims[0]
    board = _best_backboard(hsv)
    if board is not None:
        hit = _hoop_from_backboard(board, hsv, roi, h)
        if hit["confidence"] >= 0.5:
            return hit
    hanging = [c for c in _hanging_nets(hsv, roi) if c["y"] < top * 0.72]
    if hanging:
        hanging.sort(key=lambda c: c["confidence"], reverse=True)
        return hanging[0]
    return None


def _rim_mask(hsv: np.ndarray) -> np.ndarray:
    """Gym rims are red-orange. Floor wood is duller orange-brown — keep sat high."""
    import cv2

    red1 = cv2.inRange(hsv, (0, 70, 70), (14, 255, 255))
    red2 = cv2.inRange(hsv, (165, 70, 70), (180, 255, 255))
    orange = cv2.inRange(hsv, (8, 90, 90), (22, 255, 255))
    mask = cv2.bitwise_or(cv2.bitwise_or(red1, red2), orange)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 5))
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)


def _red_rims(hsv: np.ndarray, roi_bgr: np.ndarray, frame_h: int) -> list[dict[str, Any]]:
    import cv2

    mask = _rim_mask(hsv)
    h, w = mask.shape[:2]
    nlab, _labels, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, nlab):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 80 or area > 8000:
            continue
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        if bw < 12 or bh < 4 or bw > 160 or bh > 70:
            continue
        if bh > bw * 1.5:
            continue
        cx = int(cents[i][0])
        cy = int(cents[i][1])
        if cy < int(h * 0.10) or cy > int(h * 0.72):
            continue
        if cx > w * 0.88 and cy < int(h * 0.18):
            continue
        if cx < w * 0.04 and cy < int(h * 0.18):
            continue
        cr = max(8, int(max(bw * 0.45, bh * 0.7)))
        net = _net_score(roi_bgr, hsv, cx, cy, cr)
        bright = _bright_net_score(hsv, cx, cy, cr)
        # Wall cans sit lower than a backboard. Bright nylon is the hoop.
        if bright < 0.08 and cy > int(h * 0.52):
            continue
        dark_above = _dark_above_score(hsv, cx, cy, cr)
        height_bonus = max(0.0, 1.0 - cy / max(h * 0.7, 1))
        area_bonus = min(1.0, area / 1400.0)
        conf = 0.22 + 0.28 * area_bonus + 0.30 * max(bright, net * 0.5) + 0.20 * height_bonus
        if dark_above > 0.4:
            conf = min(0.97, conf + 0.05)
        if conf < 0.30:
            continue
        out.append(
            {
                "x": float(cx),
                "y": float(cy),
                "r": float(cr),
                "net_bottom": float(min(frame_h - 1, cy + cr * 3.2)),
                "confidence": round(float(min(0.97, conf)), 3),
                "source": "cv_rim",
                "area": area,
            }
        )
    return out


def _dark_above_score(hsv: np.ndarray, cx: int, cy: int, cr: int) -> float:
    h, w = hsv.shape[:2]
    x0 = max(0, cx - int(cr * 2.2))
    x1 = min(w, cx + int(cr * 2.2))
    y0 = max(0, cy - int(cr * 3.5))
    y1 = max(y0 + 4, cy - max(2, cr // 4))
    if x1 - x0 < 6 or y1 - y0 < 4:
        return 0.0
    crop = hsv[y0:y1, x0:x1]
    return float(np.mean(crop[:, :, 2] < 130))


def _bright_net_score(hsv: np.ndarray, cx: int, cy: int, cr: int) -> float:
    """White nylon under the rim. Gray wall and wood must not count."""
    import cv2

    h, w = hsv.shape[:2]
    x0 = max(0, cx - int(cr * 1.2))
    x1 = min(w, cx + int(cr * 1.2))
    y0 = min(h - 1, cy + max(2, cr // 5))
    y1 = min(h, cy + int(cr * 2.8))
    if x1 - x0 < 4 or y1 - y0 < 6:
        return 0.0
    crop = hsv[y0:y1, x0:x1]
    white = cv2.inRange(crop, (0, 0, 155), (180, 55, 255))
    return min(1.0, cv2.countNonZero(white) / max(1, white.size) * 2.2)


def _gray_hang_score(hsv: np.ndarray, cx: int, cy: int, cr: int) -> float:
    """Nylon is dull gray under the rim, not bright floor or a jersey."""
    import cv2

    h, w = hsv.shape[:2]
    x0 = max(0, cx - int(cr * 1.4))
    x1 = min(w, cx + int(cr * 1.4))
    y0 = min(h - 1, cy + max(2, cr // 4))
    y1 = min(h, cy + int(cr * 3.4))
    if x1 - x0 < 4 or y1 - y0 < 6:
        return 0.0
    crop = hsv[y0:y1, x0:x1]
    gray = cv2.inRange(crop, (0, 0, 70), (180, 55, 190))
    return min(1.0, cv2.countNonZero(gray) / max(1, gray.size) * 1.8)


def _hanging_nets(hsv: np.ndarray, roi_bgr: np.ndarray) -> list[dict[str, Any]]:
    import cv2

    h, w = hsv.shape[:2]
    white = cv2.inRange(hsv, (0, 0, 155), (180, 60, 255))
    white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    nlab, labels, stats, cents = cv2.connectedComponentsWithStats(white, 8)
    out = []
    for i in range(1, nlab):
        area = int(stats[i, cv2.CC_STAT_AREA])
        x = int(stats[i, cv2.CC_STAT_LEFT])
        y = int(stats[i, cv2.CC_STAT_TOP])
        bw = int(stats[i, cv2.CC_STAT_WIDTH])
        bh = int(stats[i, cv2.CC_STAT_HEIGHT])
        if area < 60 or area > 9000:
            continue
        if bh < 14 or bw < 8:
            continue
        if bw > bh * 2.2:
            continue
        cx = int(cents[i][0])
        if y < int(h * 0.10):
            continue
        if cx > w * 0.80 and y < int(h * 0.22):
            continue
        if cx < w * 0.08 and y < int(h * 0.22):
            continue
        rim_y = y + max(2, int(bh * 0.12))
        if _looks_like_floor(hsv, cx, rim_y, max(bw, bh) // 2):
            continue
        # Prefer objects with darker glass/backboard above.
        above = hsv[max(0, y - max(16, bh)): y, max(0, x - 8): min(w, x + bw + 8)]
        dark_above = 0.0
        if above.size:
            dark_above = float(np.mean(above[:, :, 2] < 140))
        conf = 0.35 + 0.35 * min(1.0, bh / 40.0) + 0.30 * dark_above
        out.append(
            {
                "x": float(cx),
                "y": float(rim_y),
                "r": float(max(8, bw / 2.0)),
                "net_bottom": float(y + bh),
                "confidence": round(float(min(0.95, conf)), 3),
                "source": "cv_net",
            }
        )
    return out


def _best_backboard(hsv: np.ndarray) -> tuple[int, int, int, int] | None:
    import cv2

    pale = cv2.inRange(hsv, (0, 0, 150), (180, 55, 255))
    pale = cv2.morphologyEx(pale, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)
    contours, _ = cv2.findContours(pale, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = hsv.shape[:2]
    best = None
    best_area = 0
    for cnt in contours:
        x, y, bw, bh = cv2.boundingRect(cnt)
        area = bw * bh
        if area < (w * h * 0.01) or area > (w * h * 0.25):
            continue
        if bh < 20 or bw < 40:
            continue
        if y > h * 0.45:
            continue
        ratio = bw / max(bh, 1)
        if ratio < 0.7 or ratio > 4.5:
            continue
        if area > best_area:
            best_area = area
            best = (x, y, bw, bh)
    return best


def _near_backboard(board: tuple[int, int, int, int] | None, cx: int, cy: int) -> float:
    if board is None:
        return 0.15
    x, y, bw, bh = board
    rim_x = x + bw / 2.0
    rim_y = y + bh
    dist = ((cx - rim_x) ** 2 + (cy - rim_y) ** 2) ** 0.5
    return max(0.0, 1.0 - dist / max(bw, 80))


def _hoop_from_backboard(board: tuple[int, int, int, int], hsv, roi, frame_h: int) -> dict[str, Any]:
    x, y, bw, bh = board
    cx = x + bw / 2.0
    cy = y + bh * 0.92
    cr = max(10.0, min(bw, bh) * 0.18)
    net = _net_score(roi, hsv, int(cx), int(cy), int(cr))
    return {
        "x": float(cx),
        "y": float(cy),
        "r": float(cr),
        "net_bottom": float(min(frame_h - 1, cy + cr * 3.0)),
        "confidence": round(float(0.45 + 0.4 * net), 3),
        "source": "cv_backboard",
    }


def _looks_like_floor(hsv: np.ndarray, cx: int, cy: int, cr: int) -> bool:
    """True when the hanging-net box is gym floor, not nylon."""
    import cv2

    h, w = hsv.shape[:2]
    x0, x1 = max(0, cx - cr), min(w, cx + cr)
    y0, y1 = min(h - 1, cy + max(2, cr // 2)), min(h, cy + cr * 3)
    if x1 <= x0 or y1 <= y0:
        return False
    crop = hsv[y0:y1, x0:x1]
    if crop.size == 0:
        return False
    sat = float(np.mean(crop[:, :, 1]))
    val = float(np.mean(crop[:, :, 2]))
    hue = float(np.mean(crop[:, :, 0]))
    return 8 <= hue <= 35 and sat >= 50 and val < 200


def _ring_orange_score(mask: np.ndarray, cx: int, cy: int, cr: int) -> float:
    import cv2

    h, w = mask.shape[:2]
    ring = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(ring, (cx, cy), max(cr, 1), 255, max(2, cr // 4))
    hit = cv2.countNonZero(cv2.bitwise_and(mask, ring))
    area = max(1, cv2.countNonZero(ring))
    return min(1.0, hit / area)


def _net_score(roi_bgr: np.ndarray, hsv: np.ndarray, cx: int, cy: int, cr: int) -> float:
    """White/gray mesh hanging under the rim, not a random bright patch."""
    import cv2

    h, w = hsv.shape[:2]
    x0 = max(0, cx - int(cr * 1.3))
    x1 = min(w, cx + int(cr * 1.3))
    y0 = min(h - 1, cy + max(2, cr // 3))
    y1 = min(h, cy + int(cr * 3.2))
    if x1 - x0 < 6 or y1 - y0 < 8:
        return 0.0
    crop = hsv[y0:y1, x0:x1]
    white = cv2.inRange(crop, (0, 0, 110), (180, 70, 255))
    frac = cv2.countNonZero(white) / max(1, white.size)
    # Nets are taller than wide relative to the rim.
    height_ok = (y1 - y0) >= cr
    return min(1.0, frac * 2.4) * (1.0 if height_ok else 0.4)


def _hoop_from_orange_blob(orange, hsv, roi, frame_w, frame_h) -> dict[str, Any] | None:
    import cv2

    contours, _ = cv2.findContours(orange, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_score = 0.0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 40 or area > (frame_w * frame_h * 0.04):
            continue
        (cx, cy), rad = cv2.minEnclosingCircle(cnt)
        cx, cy, cr = int(cx), int(cy), int(max(rad, 6))
        net = _net_score(roi, hsv, cx, cy, cr)
        score = 0.3 + 0.7 * net
        if score > best_score:
            best_score = score
            best = {
                "x": float(cx),
                "y": float(cy),
                "r": float(cr),
                "net_bottom": float(min(frame_h - 1, cy + int(cr * 2.8))),
                "confidence": round(float(min(0.85, score)), 3),
                "source": "cv_orange_blob",
            }
    return best


def detect_hoop_from_court_pose(frame_bgr: np.ndarray, model_path: Path | None = None) -> dict[str, Any] | None:
    """Use the existing 18-keypoint court pose model; hoop ≈ two highest close keypoints."""
    path = Path(model_path or COURT_POSE_PATH)
    if not path.is_file():
        return None
    try:
        from ultralytics import YOLO
    except ImportError:
        return None
    model = YOLO(str(path), verbose=False)
    result = model.predict(frame_bgr, conf=0.25, verbose=False)[0]
    if result.keypoints is None or len(result.keypoints) == 0:
        return None
    xy = result.keypoints.xy[0].cpu().numpy()
    pts = [(float(x), float(y), i) for i, (x, y) in enumerate(xy) if x > 1 and y > 1]
    if len(pts) < 2:
        return None
    pts.sort(key=lambda p: p[1])
    hoop_pts = pts[:4]
    xs = [p[0] for p in hoop_pts]
    ys = [p[1] for p in hoop_pts]
    hoop_x = sum(xs) / len(xs)
    hoop_y = sum(ys) / len(ys)
    span = max(xs) - min(xs) if xs else 40.0
    return {
        "x": hoop_x,
        "y": hoop_y,
        "r": max(12.0, min(80.0, span / 2.0)),
        "net_bottom": hoop_y + max(40.0, span),
        "confidence": 0.4,
        "source": "court_pose",
        "keypoint_ids": [p[2] for p in hoop_pts],
    }


def load_hoop_track(game_id: str) -> list[dict[str, Any]]:
    path = track_path(game_id)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, dict):
        return list(data.get("samples") or [])
    if isinstance(data, list):
        return data
    return []


def save_hoop_track(game_id: str, samples: list[dict[str, Any]], video: str = "") -> Path:
    TRACK_DIR.mkdir(parents=True, exist_ok=True)
    path = track_path(game_id)
    payload = {
        "game_id": game_id,
        "video": video,
        "samples": samples,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def hoop_at(samples: list[dict[str, Any]], timestamp_ms: int, max_dt_ms: int = 4000) -> dict[str, Any] | None:
    if not samples:
        return None
    best = None
    best_dt = None
    for row in samples:
        dt = abs(int(row.get("timestamp_ms") or 0) - int(timestamp_ms))
        if dt > max_dt_ms:
            continue
        if best_dt is None or dt < best_dt:
            best_dt = dt
            best = row
    return best
