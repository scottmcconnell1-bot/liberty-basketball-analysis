"""Align play-sheet PNGs to the SVG court: court crop + digit (1-5) positions.

Liberty scout pages are full-page images (header + half-court diagram). Mapping the
whole PNG into the SVG with meet letterboxing shifts the diagram down, so tokens
look too high relative to the grey underlay. This module finds the court rectangle
and the printed player digits inside it, then returns:
  - court_frac: normalized crop of the court within the PNG
  - positions: o1..o5 in SVG court space (500 x 470, basket at top)
"""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

COURT_W = 500.0
COURT_H = 470.0

_CACHE_DIR_NAME = "sheet_align_cache"


_CACHE_VERSION = "v10"  # v10: exact digit match + header trim (no o23 / title digits)


def _cache_dir(base: str | Path | None = None) -> Path:
    root = Path(base) if base else Path("data") / "playbook"
    d = root / _CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(path: Path) -> str:
    st = path.stat()
    raw = f"{_CACHE_VERSION}|{path.resolve()}|{st.st_mtime_ns}|{st.st_size}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def find_court_bbox(gray) -> tuple[int, int, int, int]:
    import cv2
    import numpy as np

    h, w = gray.shape[:2]
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_score = 0.0
    img_area = float(h * w)
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        area = float(cw * ch)
        if area < img_area * 0.15 or area > img_area * 0.95:
            continue
        aspect = cw / max(ch, 1)
        if aspect < 0.55 or aspect > 1.6:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        score = area * (1.25 if len(approx) >= 4 else 1.0)
        if score > best_score:
            best_score = score
            best = (x, y, x + cw, y + ch)
    if best is None:
        ink = gray < 200
        rows = ink.mean(axis=1)
        cols = ink.mean(axis=0)
        ys = np.where(rows > 0.02)[0]
        xs = np.where(cols > 0.02)[0]
        start = int(ys[0]) if len(ys) else 0
        for i in range(max(0, int(h * 0.05)), int(h * 0.45)):
            if rows[i] > 0.04 and rows[i : i + 30].mean() > 0.03:
                start = i
                break
        best = (
            int(xs[0]) if len(xs) else 0,
            start,
            int(xs[-1]) if len(xs) else w,
            int(ys[-1]) if len(ys) else h,
        )
    x0, y0, x1, y1 = best
    pad = 2
    court = (
        max(0, x0 - pad),
        max(0, y0 - pad),
        min(w, x1 + pad),
        min(h, y1 + pad),
    )
    return _snap_court_top_past_header(gray, court)


def _snap_court_top_past_header(gray, court: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Drop scout PDF title band (e.g. '21-22 - Liberty…') above the court ink.

    Press-break pages often return a bbox that starts on the title. After a dense
    header band and a white gap, snap y0 down to the court outline.
    """
    import numpy as np

    x0, y0, x1, y1 = court
    if y1 - y0 < 80 or x1 - x0 < 80:
        return court
    band = gray[y0:y1, x0:x1]
    rows = (band < 180).mean(axis=1)
    ch = len(rows)
    limit = int(ch * 0.50)
    i = 0
    while i < limit and rows[i] < 0.02:
        i += 1
    header_end = i
    while header_end < limit and rows[header_end] >= 0.02:
        header_end += 1
    # Walk through sparse "gap" ink (page crumbs) until a strong court line.
    # Faint marks (~0.03–0.06) after the title are NOT the court top.
    y = header_end
    white_run = 0
    saw_white = False
    court_y = None
    while y < limit:
        dens = float(rows[y])
        if dens < 0.03:
            white_run += 1
            if white_run >= 20:
                saw_white = True
        else:
            white_run = 0
        if saw_white and dens > 0.20:
            court_y = y
            break
        y += 1
    header_h = header_end - i
    if court_y is None or header_h < 6:
        return court
    new_y0 = y0 + court_y
    if new_y0 >= y1 - 60:
        return court
    return (x0, new_y0, x1, y1)


def _digit_blob_candidates(crop_gray):
    """Return list of (cx, cy, w, h, area) in crop pixel space."""
    import cv2
    import numpy as np

    ch, cw = crop_gray.shape[:2]
    up = cv2.resize(crop_gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, bw = cv2.threshold(
        cv2.GaussianBlur(up, (5, 5), 0), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    # Only strip long HORIZONTAL court lines. Vertical open would also eat
    # digits that share ink with downward cut/dribble arrows (press-break sheets).
    hker = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, up.shape[1] // 6), 1))
    lines = cv2.morphologyEx(bw, cv2.MORPH_OPEN, hker)
    lines = cv2.dilate(lines, np.ones((3, 3), np.uint8), 1)
    clean = cv2.subtract(bw, lines)
    # Break thin bridges where a digit shares ink with an arrow stem.
    clean = cv2.morphologyEx(
        clean, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    )
    clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(clean, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 120 or area > 28000:
            continue
        if h < 22 or h > 180 or w < 10 or w > 140:
            continue
        aspect = h / max(w, 1)
        if aspect < 0.45 or aspect > 4.2:
            continue
        # Circled ball-handler digits are wider; reject huge court-arc fragments.
        if w > 90 and aspect < 0.85:
            continue
        # Back to crop coords (undo 2x upscale)
        cx = (x + w / 2) / 2.0
        cy = (y + h / 2) / 2.0
        out.append((cx, cy, w / 2.0, h / 2.0, area / 4.0))
    # Prefer mid-sized digit-like blobs; drop near-duplicate centers
    out.sort(key=lambda t: -t[4])
    kept = []
    for cand in out:
        cx, cy = cand[0], cand[1]
        if any((cx - k[0]) ** 2 + (cy - k[1]) ** 2 < 20 ** 2 for k in kept):
            continue
        kept.append(cand)
        if len(kept) >= 20:
            break
    return kept


@lru_cache(maxsize=1)
def _easyocr_reader():
    try:
        import easyocr
    except ImportError:
        return None
    try:
        return easyocr.Reader(["en"], gpu=False, verbose=False)
    except Exception:
        return None


def _classify_roi(roi_bgr_or_gray) -> tuple[int, float]:
    """Return (digit 1-5 or 0, confidence)."""
    import cv2
    import numpy as np

    if roi_bgr_or_gray is None or roi_bgr_or_gray.size == 0:
        return 0, 0.0
    if roi_bgr_or_gray.ndim == 2:
        up = cv2.resize(roi_bgr_or_gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        vis = up
    else:
        up = cv2.resize(roi_bgr_or_gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        vis = up

    reader = _easyocr_reader()
    if reader is not None:
        try:
            results = reader.readtext(vis, allowlist="12345")
        except Exception:
            results = []
        best_d, best_c = 0, 0.0
        for _bbox, text, conf in results:
            t = (text or "").strip()
            # MUST be exact single digit — `"23" in "12345"` is True (substring bug).
            if t in ("1", "2", "3", "4", "5") and float(conf) > best_c:
                best_d, best_c = int(t), float(conf)
        if best_d:
            return best_d, best_c

    # Fallback: template correlation with Hershey digits
    if vis.ndim == 3:
        gray = cv2.cvtColor(vis, cv2.COLOR_BGR2GRAY)
    else:
        gray = vis
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    r = cv2.resize(bw, (48, 48))
    best_d, best_s = 0, -1.0
    for d in range(1, 6):
        canvas = np.zeros((48, 48), np.uint8)
        cv2.putText(canvas, str(d), (8, 36), cv2.FONT_HERSHEY_SIMPLEX, 1.15, 255, 2, cv2.LINE_AA)
        a = r.astype(float).ravel()
        b = canvas.astype(float).ravel()
        if a.std() < 1 or b.std() < 1:
            continue
        s = float(np.corrcoef(a, b)[0, 1])
        if s > best_s:
            best_s, best_d = s, d
    if best_s >= 0.25:
        return best_d, best_s
    return 0, 0.0


def detect_sheet_digits(gray, court: tuple[int, int, int, int]) -> dict[str, dict[str, float]]:
    import cv2

    x0, y0, x1, y1 = court
    crop = gray[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]
    if ch < 20 or cw < 20:
        return {}
    cands = _digit_blob_candidates(crop)
    by_digit: dict[int, tuple[float, float, float]] = {}
    for cx, cy, w, h, _area in cands:
        # Residual title digits sit in the top strip even after header snap.
        if cy < ch * 0.05:
            continue
        # Try a tight crop first (avoids circle rings / arrow stubs), then a padded one.
        roi_specs = (
            (max(2, w * 0.12), max(2, h * 0.12)),
            (max(4, w * 0.35), max(4, h * 0.35)),
        )
        digit, conf = 0, 0.0
        for pad_x, pad_y in roi_specs:
            x_a = max(0, int(cx - w / 2 - pad_x))
            y_a = max(0, int(cy - h / 2 - pad_y))
            x_b = min(cw, int(cx + w / 2 + pad_x))
            y_b = min(ch, int(cy + h / 2 + pad_y))
            roi = crop[y_a:y_b, x_a:x_b]
            d, c = _classify_roi(roi)
            if d in (1, 2, 3, 4, 5) and c > conf:
                digit, conf = d, c
        # EasyOCR sometimes returns ~0.3 on bold stencil digits; keep modest floor.
        if digit not in (1, 2, 3, 4, 5) or conf < 0.28:
            continue
        prev = by_digit.get(digit)
        if prev is None or conf > prev[0]:
            by_digit[digit] = (conf, cx, cy)

    out: dict[str, dict[str, float]] = {}
    for d, (conf, cx, cy) in by_digit.items():
        if d not in (1, 2, 3, 4, 5):
            continue
        out[f"o{d}"] = {
            "x": round(float(cx / cw) * COURT_W, 1),
            "y": round(float(cy / ch) * COURT_H, 1),
            "confidence": round(float(conf), 3),
        }
    return out


def _svg_to_crop(pt: dict, cw: int, ch: int) -> tuple[int, int]:
    x = int(max(0, min(cw - 1, round(float(pt["x"]) / COURT_W * cw))))
    y = int(max(0, min(ch - 1, round(float(pt["y"]) / COURT_H * ch))))
    return x, y


def _crop_to_svg(x: float, y: float, cw: int, ch: int) -> dict[str, float]:
    return {
        "x": round(float(x) / cw * COURT_W, 1),
        "y": round(float(y) / ch * COURT_H, 1),
    }


def _ink_mask_no_close(crop_gray):
    """Raw play-ink mask WITHOUT closing gaps — preserves dashed pass strokes."""
    import cv2
    import numpy as np

    ch, cw = crop_gray.shape[:2]
    blur = cv2.GaussianBlur(crop_gray, (3, 3), 0)
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    hker = cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, cw // 4), 1))
    vker = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(40, ch // 4)))
    long_lines = cv2.morphologyEx(bw, cv2.MORPH_OPEN, hker) | cv2.morphologyEx(bw, cv2.MORPH_OPEN, vker)
    long_lines = cv2.dilate(long_lines, np.ones((5, 5), np.uint8), 1)
    return cv2.subtract(bw, long_lines)


def _stroke_mask(crop_gray):
    """Binary mask of play ink (arrows/digits) with thick court lines suppressed."""
    import cv2

    stroke = _ink_mask_no_close(crop_gray)
    # Connect dashed / squiggle segments, then thin for a walkable centerline
    stroke = cv2.morphologyEx(
        stroke, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    )
    return stroke


def _polyline_px(poly_svg: list[dict], cw: int, ch: int) -> list[tuple[int, int]]:
    out = []
    for p in poly_svg or []:
        if not _has_xy(p):
            continue
        out.append(_svg_to_crop(p, cw, ch))
    return out


def _densify_path_px(path_px: list[tuple[int, int]], spacing: float = 2.0) -> list[tuple[int, int]]:
    """Insert points along segments so dash/T-bar probes see the stroke, not just vertices."""
    if not path_px:
        return []
    if len(path_px) == 1:
        return list(path_px)
    out = [path_px[0]]
    for i in range(1, len(path_px)):
        x0, y0 = path_px[i - 1]
        x1, y1 = path_px[i]
        dist = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        n = max(1, int(dist / max(spacing, 0.5)))
        for k in range(1, n + 1):
            t = k / n
            out.append((int(round(x0 + (x1 - x0) * t)), int(round(y0 + (y1 - y0) * t))))
    return out


def _dashiness_along_path(raw_mask, path_px, radius: int = 2) -> float:
    """Fraction of on→off transitions along a path (high = dashed pass mark)."""
    dense = _densify_path_px(path_px, spacing=2.0)
    if not dense or len(dense) < 8:
        return 0.0
    ch, cw = raw_mask.shape[:2]
    step = max(1, len(dense) // 48)
    samples = []
    for i in range(0, len(dense), step):
        x, y = dense[i]
        x0, x1 = max(0, x - radius), min(cw, x + radius + 1)
        y0, y1 = max(0, y - radius), min(ch, y + radius + 1)
        samples.append(1 if raw_mask[y0:y1, x0:x1].any() else 0)
    if len(samples) < 4:
        return 0.0
    flips = sum(1 for i in range(1, len(samples)) if samples[i] != samples[i - 1])
    return flips / (len(samples) - 1)


def _has_tbar_near_end(stroke, path_px, bar_len: int = 22) -> bool:
    """True if a screen T-bar (perpendicular ink) sits near the path end."""
    dense = _densify_path_px(path_px, spacing=2.0)
    if not dense or len(dense) < 3:
        return False
    ch, cw = stroke.shape[:2]
    ex, ey = dense[-1]
    # Direction from late segment
    sx, sy = dense[max(0, len(dense) - 12)]
    dx, dy = float(ex - sx), float(ey - sy)
    norm = (dx * dx + dy * dy) ** 0.5
    if norm < 4:
        dx, dy = 0.0, -1.0
        norm = 1.0
    ux, uy = dx / norm, dy / norm
    # Perpendicular unit
    px, py = -uy, ux
    on = 0
    total = 0
    for t in range(-bar_len, bar_len + 1):
        x = int(round(ex + px * t))
        y = int(round(ey + py * t))
        if x < 1 or y < 1 or x >= cw - 1 or y >= ch - 1:
            continue
        total += 1
        if stroke[y - 1 : y + 2, x - 1 : x + 2].any():
            on += 1
    if total < 8:
        return False
    # Strong crossbar coverage vs short stem sample
    stem_on = 0
    stem_tot = 0
    for t in range(-8, 9):
        x = int(round(ex - ux * abs(t) * 0.5))
        y = int(round(ey - uy * abs(t) * 0.5))
        # Probe beside the stem (not on it) to measure "extra" crossbar mass
        x2 = int(round(ex + px * (10 if t >= 0 else -10)))
        y2 = int(round(ey + py * (10 if t >= 0 else -10)))
        if x2 < 1 or y2 < 1 or x2 >= cw - 1 or y2 >= ch - 1:
            continue
        stem_tot += 1
        if stroke[y2 - 1 : y2 + 2, x2 - 1 : x2 + 2].any():
            stem_on += 1
    bar_frac = on / total
    # Require a clear crossbar; side probes confirm bar extends off the stem.
    side_frac = stem_on / max(stem_tot, 1)
    return bar_frac >= 0.40 and side_frac >= 0.25


def classify_polyline_mark(
    crop_gray,
    poly_svg: list[dict],
) -> str:
    """Classify a traced polyline by printed mark style: pass | screen | cut."""
    if not poly_svg or len(poly_svg) < 2:
        return "cut"
    ch, cw = crop_gray.shape[:2]
    path_px = _polyline_px(poly_svg, cw, ch)
    if len(path_px) < 2:
        return "cut"
    raw = _ink_mask_no_close(crop_gray)
    stroke = _stroke_mask(crop_gray)
    dash = _dashiness_along_path(raw, path_px)
    # Length in SVG units
    plen = 0.0
    for i in range(1, len(poly_svg)):
        a, b = poly_svg[i - 1], poly_svg[i]
        if _has_xy(a) and _has_xy(b):
            plen += ((b["x"] - a["x"]) ** 2 + (b["y"] - a["y"]) ** 2) ** 0.5
    if dash >= 0.22 and plen >= 40:
        return "pass"
    if plen <= 160 and _has_tbar_near_end(stroke, path_px):
        return "screen"
    return "cut"


def _morph_skeleton(binary):
    """Morphological skeleton (centerline) of a binary ink mask."""
    import cv2
    import numpy as np

    img = (binary > 0).astype(np.uint8) * 255
    skel = np.zeros_like(img)
    element = cv2.getStructuringElement(cv2.MORPH_CROSS, (3, 3))
    while True:
        eroded = cv2.erode(img, element)
        temp = cv2.morphologyEx(eroded, cv2.MORPH_OPEN, element)
        temp = cv2.subtract(img, temp)
        skel = cv2.bitwise_or(skel, temp)
        img = eroded
        if cv2.countNonZero(img) == 0:
            break
    # Keep skeleton as thin centerline for scoring; walkable copy is dilated separately
    if cv2.countNonZero(skel) > 0:
        pass
    return skel


def _greedy_ink_walk(stroke, sx, sy, ex, ey, max_steps: int = 1200):
    """Walk along connected ink from start, prefer neighbors nearer the goal."""
    import numpy as np

    ch, cw = stroke.shape[:2]
    x, y = sx, sy
    path = [(x, y)]
    visited = np.zeros_like(stroke, dtype=np.uint8)
    visited[y, x] = 1
    neighbors = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    for _ in range(max_steps):
        if abs(x - ex) + abs(y - ey) < 4:
            break
        best = None
        best_score = 1e18
        for dx, dy in neighbors:
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= cw or ny >= ch:
                continue
            if visited[ny, nx]:
                continue
            on = stroke[ny, nx] > 0
            dist_goal = ((nx - ex) ** 2 + (ny - ey) ** 2) ** 0.5
            score = dist_goal + (0 if on else 80)
            if score < best_score:
                best_score = score
                best = (nx, ny, on)
        if best is None:
            break
        nx, ny, on = best
        if not on and best_score > 60:
            break
        x, y = nx, ny
        visited[y, x] = 1
        path.append((x, y))
    path.append((ex, ey))
    return path


def _path_ink_fraction(stroke, path_px, radius: int = 3) -> float:
    if not path_px:
        return 0.0
    ch, cw = stroke.shape[:2]
    on = 0
    for x, y in path_px:
        x0, x1 = max(0, x - radius), min(cw, x + radius + 1)
        y0, y1 = max(0, y - radius), min(ch, y + radius + 1)
        if stroke[y0:y1, x0:x1].any():
            on += 1
    return on / len(path_px)


def trace_ink_polyline(
    crop_gray,
    start_svg: dict,
    end_svg: dict,
    digit_positions: dict | None = None,
    max_points: int = 56,
) -> list[dict[str, float]]:
    """Walk black sheet ink from start to end (A* on distance-to-ink costs).

    Prefers dark arrow strokes over straight shortcuts across white space.
    Endpoints are forced to the given SVG digit positions.
    """
    import heapq

    import cv2
    import numpy as np

    ch, cw = crop_gray.shape[:2]
    sx, sy = _svg_to_crop(start_svg, cw, ch)
    ex, ey = _svg_to_crop(end_svg, cw, ch)
    if abs(sx - ex) + abs(sy - ey) < 8:
        return [
            {"x": float(start_svg["x"]), "y": float(start_svg["y"])},
            {"x": float(end_svg["x"]), "y": float(end_svg["y"])},
        ]

    stroke_raw = _stroke_mask(crop_gray)
    if digit_positions:
        for p in digit_positions.values():
            if not _has_xy(p):
                continue
            cx, cy = _svg_to_crop(p, cw, ch)
            cv2.circle(stroke_raw, (cx, cy), 10, 255, -1)

    # Centerline for hugging arrows; slightly thicker walkable for connectivity
    skel = _morph_skeleton(stroke_raw)
    stroke = cv2.bitwise_or(skel, cv2.dilate(skel, np.ones((3, 3), np.uint8), 1))
    # Fallback if skeleton empty
    if cv2.countNonZero(stroke) < 20:
        stroke = cv2.dilate(stroke_raw, np.ones((3, 3), np.uint8), 1)
        skel = stroke

    # Soft cost: on-skeleton cheap, off-skeleton expensive (rejects white chords)
    dist_ink = cv2.distanceTransform(255 - skel, cv2.DIST_L2, 5)
    # Soft corridor still helps pick the right stroke among many
    yy, xx = np.mgrid[0:ch, 0:cw]
    vx, vy = float(ex - sx), float(ey - sy)
    seg2 = max(vx * vx + vy * vy, 1.0)
    t = np.clip(((xx - sx) * vx + (yy - sy) * vy) / seg2, 0.0, 1.0)
    proj_x = sx + t * vx
    proj_y = sy + t * vy
    lat = np.sqrt((xx - proj_x) ** 2 + (yy - proj_y) ** 2)
    band = max(80.0, 0.22 * max(cw, ch))

    step_cost = 1.0 + np.square(dist_ink) * 0.85
    step_cost = step_cost.astype(np.float64)
    step_cost += np.maximum(0.0, lat - band) * 0.05

    INF = 1e18
    gscore = np.full((ch, cw), INF, dtype=np.float64)
    came = np.full((ch, cw, 2), -1, dtype=np.int32)
    gscore[sy, sx] = 0.0
    open_h: list[tuple[float, int, int]] = []
    heapq.heappush(open_h, (0.0, sx, sy))
    found = False
    neighbors = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    expansions = 0
    max_exp = min(cw * ch, 900_000)

    while open_h and expansions < max_exp:
        f, x, y = heapq.heappop(open_h)
        expansions += 1
        if (x, y) == (ex, ey):
            found = True
            break
        if f > gscore[y, x] + 1e-6:
            continue
        for dx, dy in neighbors:
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= cw or ny >= ch:
                continue
            step = float(step_cost[ny, nx])
            if dx and dy:
                step *= 1.414
            ng = gscore[y, x] + step
            if ng + 1e-9 < gscore[ny, nx]:
                gscore[ny, nx] = ng
                came[ny, nx] = (x, y)
                # Heuristic uses same distance-to-ink so A* stays informed
                # Strong goal pull — avoid long ink detours / loops
                h = 1.15 * ((nx - ex) ** 2 + (ny - ey) ** 2) ** 0.5
                heapq.heappush(open_h, (ng + h, nx, ny))

    def _path_len(pts):
        total = 0.0
        for i in range(1, len(pts)):
            x0, y0 = pts[i - 1]
            x1, y1 = pts[i]
            total += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        return total

    def _corridor_snap(n_samp: int = 36):
        """Sample along start→end and snap each point onto nearby ink."""
        pts = [(sx, sy)]
        for i in range(1, n_samp - 1):
            t = i / (n_samp - 1)
            mx = int(round(sx + (ex - sx) * t))
            my = int(round(sy + (ey - sy) * t))
            rad = 14
            x0, x1 = max(0, mx - rad), min(cw, mx + rad + 1)
            y0, y1 = max(0, my - rad), min(ch, my + rad + 1)
            patch = stroke[y0:y1, x0:x1]
            if patch.any():
                yy, xx = np.mgrid[y0:y1, x0:x1]
                d2 = (xx - mx) ** 2 + (yy - my) ** 2
                d2 = np.where(patch > 0, d2, 1e12)
                j = int(np.argmin(d2))
                by, bx = divmod(j, patch.shape[1])
                pts.append((x0 + bx, y0 + by))
            else:
                pts.append((mx, my))
        pts.append((ex, ey))
        return pts

    if found:
        path_px = []
        cx, cy = ex, ey
        guard = 0
        while not (cx == sx and cy == sy) and guard < cw * ch:
            path_px.append((cx, cy))
            px, py = int(came[cy, cx, 0]), int(came[cy, cx, 1])
            if px < 0:
                break
            cx, cy = px, py
            guard += 1
        path_px.append((sx, sy))
        path_px.reverse()
    else:
        path_px = [(sx, sy), (ex, ey)]

    straight_len = max(((ex - sx) ** 2 + (ey - sy) ** 2) ** 0.5, 1.0)
    greedy = _greedy_ink_walk(stroke, sx, sy, ex, ey)
    corridor = _corridor_snap()
    candidates = [path_px, greedy, corridor]

    def _ok(pts):
        if not pts or len(pts) < 2:
            return False
        detour = _path_len(pts) / straight_len
        return detour <= 3.4

    def _mid_ink(pts) -> float:
        """Ink hit away from endpoints — ignores start/end digit blobs."""
        if not pts or len(pts) < 3:
            return 0.0
        # Spatial margin so OCR digit disks / blob wander don't fake a stroke.
        r2 = 28 * 28
        mid = [
            (x, y)
            for (x, y) in pts
            if (x - sx) * (x - sx) + (y - sy) * (y - sy) > r2
            and (x - ex) * (x - ex) + (y - ey) * (y - ey) > r2
        ]
        if len(mid) < 2:
            return 0.0
        return _path_ink_fraction(skel, mid, radius=5)

    # Prefer the path that hugs the skeleton most, among reasonable-length options.
    inked = [(pts, _mid_ink(pts)) for pts in candidates if _ok(pts)]
    short = min(
        (pts for pts in candidates if pts and len(pts) >= 2),
        key=_path_len,
        default=corridor,
    )
    if inked:
        # High mid-ink + longer path wins (follows the curve). Low mid-ink: prefer shorter.
        def _rank(t):
            pts, ink = t
            plen = _path_len(pts)
            if ink >= 0.55 and plen >= straight_len * 1.12:
                return (ink, plen)
            return (ink, -plen)

        best_ink = max(inked, key=_rank)
        # Require real mid-path ink before accepting a curved detour.
        if best_ink[1] >= 0.45 and _path_len(best_ink[0]) >= straight_len * 1.08:
            path_px = best_ink[0]
        else:
            path_px = short
    else:
        path_px = short if short and len(short) >= 2 else (
            corridor if len(corridor) >= 2 else [(sx, sy), (ex, ey)]
        )

    if len(path_px) < 2:
        path_px = [(sx, sy), (ex, ey)]

    dists = [0.0]
    for i in range(1, len(path_px)):
        x0, y0 = path_px[i - 1]
        x1, y1 = path_px[i]
        dists.append(dists[-1] + ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
    total = dists[-1] or 1.0
    n = max(2, min(max_points, max(2, int(total / 6) + 1)))
    pts = []
    for i in range(n):
        target = total * i / (n - 1)
        j = 1
        while j < len(dists) and dists[j] < target:
            j += 1
        j = min(j, len(path_px) - 1)
        # Linear interpolate between path pixels for smoother SVG
        if j > 0 and dists[j] > dists[j - 1]:
            u = (target - dists[j - 1]) / (dists[j] - dists[j - 1])
            x = path_px[j - 1][0] + u * (path_px[j][0] - path_px[j - 1][0])
            y = path_px[j - 1][1] + u * (path_px[j][1] - path_px[j - 1][1])
            pts.append((x, y))
        else:
            pts.append(path_px[j])

    out = [_crop_to_svg(x, y, cw, ch) for x, y in pts]
    out[0] = {"x": float(start_svg["x"]), "y": float(start_svg["y"])}
    out[-1] = {"x": float(end_svg["x"]), "y": float(end_svg["y"])}
    return out



def _poly_len_svg(poly: list[dict]) -> float:
    total = 0.0
    for i in range(1, len(poly or [])):
        a, b = poly[i - 1], poly[i]
        if _has_xy(a) and _has_xy(b):
            total += ((b["x"] - a["x"]) ** 2 + (b["y"] - a["y"]) ** 2) ** 0.5
    return total


def _mid_raw_ink_fraction(crop_gray, poly_svg: list[dict], start_svg: dict, end_svg: dict) -> float:
    """Fraction of mid-path samples that hit raw (unclosed) ink — rejects white chords."""
    if not poly_svg or len(poly_svg) < 3:
        return 0.0
    ch, cw = crop_gray.shape[:2]
    raw = _ink_mask_no_close(crop_gray)
    pts = _polyline_px(poly_svg, cw, ch)
    sx, sy = _svg_to_crop(start_svg, cw, ch)
    ex, ey = _svg_to_crop(end_svg, cw, ch)
    r2 = 28 * 28
    mid = [
        (x, y)
        for (x, y) in pts
        if (x - sx) * (x - sx) + (y - sy) * (y - sy) > r2
        and (x - ex) * (x - ex) + (y - ey) * (y - ey) > r2
    ]
    if len(mid) < 4:
        return 0.0
    return _path_ink_fraction(raw, mid, radius=5)


def _walk_skeleton_to_tip(skel, sx: int, sy: int, digit_px: list[tuple[int, int, int]], max_steps: int = 900):
    """Walk skeleton from a seed near a digit until tip or another digit.

    digit_px: list of (cx, cy, avoid_radius) — first entry is the start digit.
    Returns path pixels including start, or [].
    """
    import numpy as np

    ch, cw = skel.shape[:2]
    if sx < 0 or sy < 0 or sx >= cw or sy >= ch or skel[sy, sx] == 0:
        return []
    start = digit_px[0]
    scx, scy, srad = start
    visited = np.zeros_like(skel, dtype=np.uint8)
    # Block the start digit disk so we leave it once
    y0, y1 = max(0, scy - srad), min(ch, scy + srad + 1)
    x0, x1 = max(0, scx - srad), min(cw, scx + srad + 1)
    for yy in range(y0, y1):
        for xx in range(x0, x1):
            if (yy - scy) ** 2 + (xx - scx) ** 2 <= srad * srad:
                visited[yy, xx] = 1

    path = [(scx, scy), (sx, sy)]
    visited[sy, sx] = 1
    x, y = sx, sy
    neighbors = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    for _ in range(max_steps):
        # Hit another digit?
        for i, (cx, cy, rad) in enumerate(digit_px):
            if i == 0:
                continue
            if (x - cx) ** 2 + (y - cy) ** 2 <= rad * rad:
                path.append((cx, cy))
                return path
        options = []
        for dx, dy in neighbors:
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= cw or ny >= ch:
                continue
            if visited[ny, nx] or skel[ny, nx] == 0:
                continue
            away = (nx - scx) ** 2 + (ny - scy) ** 2
            options.append((away, nx, ny))
        if not options:
            break
        options.sort(reverse=True)
        _, x, y = options[0]
        visited[y, x] = 1
        path.append((x, y))
    return path if len(path) >= 3 else []


def _path_ink_fraction_stroke(crop_gray, poly_svg: list[dict], start_svg: dict, end_svg: dict) -> float:
    """Mid-path ink hit rate on the closed stroke mask (friendlier to squiggles)."""
    if not poly_svg or len(poly_svg) < 3:
        return 0.0
    ch, cw = crop_gray.shape[:2]
    stroke = _stroke_mask(crop_gray)
    pts = _polyline_px(poly_svg, cw, ch)
    sx, sy = _svg_to_crop(start_svg, cw, ch)
    ex, ey = _svg_to_crop(end_svg, cw, ch)
    r2 = 28 * 28
    mid = [
        (x, y)
        for (x, y) in pts
        if (x - sx) * (x - sx) + (y - sy) * (y - sy) > r2
        and (x - ex) * (x - ex) + (y - ey) * (y - ey) > r2
    ]
    if len(mid) < 4:
        return 0.0
    return _path_ink_fraction(stroke, mid, radius=5)


def discover_dash_pass_chains(crop_gray) -> list[list[dict[str, float]]]:
    """Find dashed-pass corridors as chains of small elongated ink fragments.

    Used when the pass does not connect two OCR digit centers (e.g. Rip page 122:
    pass leaves the dribble tip at the elbow toward the corner).
    """
    import cv2

    ch, cw = crop_gray.shape[:2]
    raw = _ink_mask_no_close(crop_gray)
    n, _labels, stats, cents = cv2.connectedComponentsWithStats(raw, 8)
    frags: list[tuple[float, float]] = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if 70 <= area <= 140 and 12 <= w <= 24 and 5 <= h <= 14:
            frags.append((float(cents[i][0]), float(cents[i][1])))
    if len(frags) < 4:
        return []

    remaining = list(frags)
    chains_px: list[list[tuple[float, float]]] = []
    while len(remaining) >= 4:
        # Prefer a tip toward the basket-side corner (high x, low y with basket at top).
        start = max(remaining, key=lambda t: t[0] - 0.45 * t[1])
        chain = [start]
        remaining.remove(start)
        while remaining:
            last = chain[-1]
            nxt = min(remaining, key=lambda t: (t[0] - last[0]) ** 2 + (t[1] - last[1]) ** 2)
            dist = ((nxt[0] - last[0]) ** 2 + (nxt[1] - last[1]) ** 2) ** 0.5
            if dist > 58:
                break
            chain.append(nxt)
            remaining.remove(nxt)
        if len(chain) >= 4:
            chains_px.append(chain)
        else:
            # Don't spin forever on leftovers
            if len(remaining) < 4:
                break
            remaining = [t for t in remaining if t not in chain]

    out: list[list[dict[str, float]]] = []
    for chain in chains_px:
        # Order so index 0 is paint/elbow side, -1 is corner/tip side.
        a, b = chain[0], chain[-1]
        # Elbow/paint is closer to court center-x and higher y (farther from basket).
        score_a = abs(a[0] - cw * 0.5) + a[1] * 0.35
        score_b = abs(b[0] - cw * 0.5) + b[1] * 0.35
        if score_a > score_b:
            chain = list(reversed(chain))
        poly = [_crop_to_svg(x, y, cw, ch) for x, y in chain]
        # Fragment geometry is the evidence (centers fall in dash gaps, so
        # classify_polyline_mark often returns "cut"). Require a long-enough
        # corridor in court space.
        plen = _poly_len_svg(poly)
        if plen < 55 or len(chain) < 4:
            continue
        out.append(poly)
    return out


def discover_outgoing_routes(
    crop_gray,
    positions: dict,
    min_len_svg: float = 30.0,
) -> dict[str, Any]:
    """Discover cut/screen/dribble routes drawn on a sheet when digits stay put.

    Walks ink outward from each digit along the stroke skeleton to a tip.
    Erases digit disks first so walks cannot loop on glyph ink. Prefers real
    tip displacement over long self-intersecting loops on court residue.
    """
    import cv2
    import numpy as np

    ch, cw = crop_gray.shape[:2]
    stroke_raw = _stroke_mask(crop_gray)
    erased = stroke_raw.copy()
    digit_px: list[tuple[str, int, int, int]] = []
    for i in range(1, 6):
        oid = f"o{i}"
        p = (positions or {}).get(oid)
        if not _has_xy(p):
            continue
        cx, cy = _svg_to_crop(p, cw, ch)
        digit_px.append((oid, cx, cy, 16))
        # Smaller erase keeps screen stems attached to the glyph (Rip 4/5).
        erase_r = 12 if oid in ("o4", "o5") else 18
        cv2.circle(erased, (cx, cy), erase_r, 0, -1)

    skel = _morph_skeleton(erased)
    if cv2.countNonZero(skel) < 20:
        skel = cv2.dilate(erased, np.ones((3, 3), np.uint8), 1)
    walkable = cv2.bitwise_or(skel, cv2.dilate(skel, np.ones((3, 3), np.uint8), 1))

    paths: dict[str, list[dict[str, float]]] = {}
    marks: dict[str, str] = {}

    for oid, cx, cy, rad in digit_px:
        seeds = []
        # Wider annulus — screen stems / squiggles often start outside the glyph.
        for yy in range(max(0, cy - 34), min(ch, cy + 36)):
            for xx in range(max(0, cx - 34), min(cw, cx + 36)):
                d2 = (xx - cx) ** 2 + (yy - cy) ** 2
                if d2 < 14 ** 2 or d2 > 32 ** 2:
                    continue
                if walkable[yy, xx]:
                    seeds.append((xx, yy))
        if not seeds:
            continue

        best_poly = None
        best_kind = "cut"
        best_score = -1.0
        seen_seed = set()
        others = [(c, y, r) for (oid2, c, y, r) in digit_px if oid2 != oid]
        start_digits = [(cx, cy, rad)] + others
        for sx, sy in seeds:
            key = (sx // 5, sy // 5)
            if key in seen_seed:
                continue
            seen_seed.add(key)
            path_px = _walk_skeleton_to_tip(walkable, sx, sy, start_digits, max_steps=700)
            if len(path_px) < 5:
                continue
            svg_pts = [_crop_to_svg(x, y, cw, ch) for x, y in path_px]
            svg_pts[0] = {"x": float(positions[oid]["x"]), "y": float(positions[oid]["y"])}
            tip = svg_pts[-1]
            disp = ((tip["x"] - svg_pts[0]["x"]) ** 2 + (tip["y"] - svg_pts[0]["y"]) ** 2) ** 0.5
            plen = _poly_len_svg(svg_pts)
            if disp < min_len_svg or plen < min_len_svg:
                continue
            # Reject court-line wander: long loops with little net travel, or huge hauls.
            # Allow slightly longer stems for big-to-paint screens (Rip page 121 o5).
            max_plen = 310 if oid in ("o4", "o5") else 260
            if plen > max_plen or disp > 220:
                continue
            if plen / max(disp, 1.0) > 2.6:
                continue
            mid = max(
                _mid_raw_ink_fraction(crop_gray, svg_pts, svg_pts[0], tip),
                _path_ink_fraction_stroke(crop_gray, svg_pts, svg_pts[0], tip),
            )
            if mid < 0.35:
                continue
            kind = classify_polyline_mark(crop_gray, svg_pts)
            if kind == "pass":
                continue
            # Squiggle dribble: path much longer than chord.
            if kind == "cut" and plen / max(disp, 1.0) >= 1.45:
                kind = "dribble"
            # Prefer screens and dribbles; plain cuts need solid mid-ink + modest length.
            if kind == "cut" and (mid < 0.55 or disp > 170):
                continue
            score = disp + (40.0 if kind == "screen" else 0.0) + (25.0 if kind == "dribble" else 0.0)
            score += 30.0 * mid
            if score > best_score:
                best_score = score
                best_poly = svg_pts
                best_kind = kind

        if best_poly:
            paths[oid] = best_poly
            marks[oid] = best_kind

    return {"paths": paths, "marks": marks}


def discover_big_screen_routes(
    crop_gray,
    positions: dict,
) -> dict[str, Any]:
    """Invent reliable o4/o5 screen holds from leftward stems ending in T-bars.

    Skeleton tip-walks often miss Rip screener ink (broken stems / T-bar past the
    tip). Ray-cast a corridor from each big toward the basket side (lower x) and
    stop at the first strong T-bar. Page 120 pass sheets fail the density/length
    gates so we do not invent false screens there.
    """
    import cv2
    import numpy as np

    ch, cw = crop_gray.shape[:2]
    stroke = _stroke_mask(crop_gray)
    raw = _ink_mask_no_close(crop_gray)
    walk = cv2.bitwise_or(stroke, cv2.dilate(raw, np.ones((3, 3), np.uint8), 1))

    paths: dict[str, list[dict[str, float]]] = {}
    marks: dict[str, str] = {}

    for oid in ("o4", "o5"):
        p = (positions or {}).get(oid)
        if not _has_xy(p):
            continue
        cx, cy = _svg_to_crop(p, cw, ch)
        best = None  # (score, tip_svg, ang)
        for ang_deg in range(145, 220, 5):
            ang = float(np.deg2rad(ang_deg))
            ux, uy = float(np.cos(ang)), float(np.sin(ang))
            px, py = -uy, ux
            hit_rs: list[int] = []
            tbar_r = None
            for r in range(18, 360):
                x0 = cx + r * ux
                y0 = cy + r * uy
                on = False
                for s in range(-6, 7, 2):
                    x = int(round(x0 + s * px))
                    y = int(round(y0 + s * py))
                    if 0 <= x < cw and 0 <= y < ch and walk[y, x]:
                        on = True
                        break
                if not on:
                    continue
                hit_rs.append(r)
                if tbar_r is None and r >= 70:
                    stem = [
                        (int(round(cx + max(0, r - 16) * ux)), int(round(cy + max(0, r - 16) * uy))),
                        (int(round(x0)), int(round(y0))),
                    ]
                    if _has_tbar_near_end(stroke, stem, bar_len=30):
                        tbar_r = r
            if tbar_r is None or len(hit_rs) < 120:
                continue
            span = max(hit_rs) - min(hit_rs) + 1
            dens = len(hit_rs) / max(span, 1)
            if dens < 0.55:
                continue
            # Stem must reach past the digit neighborhood (reject cone/glyph T-bars).
            if tbar_r < 110:
                continue
            # Require ink near the digit so court-line rays do not count.
            near_hits = sum(1 for r in hit_rs if 18 <= r <= 55)
            if near_hits < 8:
                continue
            tip = _crop_to_svg(cx + tbar_r * ux, cy + tbar_r * uy, cw, ch)
            dx = float(p["x"]) - tip["x"]
            dy = abs(float(p["y"]) - tip["y"])
            if dx < 55 or dx > 200 or dy > 60:
                continue
            # Hold inside the paint / lane corridor (Rip screen tips).
            if tip["x"] < 170 or tip["x"] > 280:
                continue
            if tip["y"] < 55 or tip["y"] > 230:
                continue
            score = dens * 100.0 + min(len(hit_rs), 300) * 0.15 + dx * 0.2 - dy * 0.4
            # Prefer near-horizontal leftward screens (Rip 4/5).
            score += max(0.0, 25.0 - abs(ang_deg - 175) * 0.6)
            if best is None or score > best[0]:
                best = (score, tip, ang_deg)

        if not best:
            continue
        tip = best[1]
        paths[oid] = [
            {"x": float(p["x"]), "y": float(p["y"])},
            {"x": float(tip["x"]), "y": float(tip["y"])},
        ]
        marks[oid] = "screen"

    # Require a paired 4+5 screen set (Rip). Lone false rays on pass-only sheets
    # (page 120 court-line T-bars) are dropped.
    if not ({"o4", "o5"} <= set(marks.keys())):
        return {"paths": {}, "marks": {}}

    return {"paths": paths, "marks": marks}


def _pitt5_opening_formation(digit_pos: dict) -> bool:
    """Pitt 5 opening: 1+5 at top (1 right of 5), 2/3 wings, 4 right block."""
    o1 = (digit_pos or {}).get("o1")
    o2 = (digit_pos or {}).get("o2")
    o3 = (digit_pos or {}).get("o3")
    o4 = (digit_pos or {}).get("o4")
    o5 = (digit_pos or {}).get("o5")
    if not all(_has_xy(p) for p in (o1, o2, o3, o4, o5)):
        return False
    return (
        float(o1["y"]) > 250
        and float(o5["y"]) > 250
        and float(o1["x"]) > float(o5["x"]) + 40
        and float(o2["x"]) > 400
        and float(o3["x"]) < 120
        and float(o4["x"]) > 280
        and float(o4["y"]) < 160
    )


def _pitt5_screen_formation(digit_pos: dict) -> bool:
    """Pitt 5 after open: 1 left corner, 2 right corner, 5 still at top with ball."""
    o1 = (digit_pos or {}).get("o1")
    o2 = (digit_pos or {}).get("o2")
    o4 = (digit_pos or {}).get("o4")
    o5 = (digit_pos or {}).get("o5")
    if not all(_has_xy(p) for p in (o1, o2, o4, o5)):
        return False
    return (
        float(o1["x"]) < 80
        and float(o1["y"]) < 140
        and float(o2["x"]) > 420
        and float(o2["y"]) < 140
        and float(o5["y"]) > 240
        and float(o4["x"]) > 280
        and float(o4["y"]) < 160
    )


def _triangle_opening_formation(digit_pos: dict) -> bool:
    """Offense Triangle sheet 1: 1 at point, 2/3 wings, 5 high post."""
    o1 = (digit_pos or {}).get("o1")
    o2 = (digit_pos or {}).get("o2")
    o3 = (digit_pos or {}).get("o3")
    o5 = (digit_pos or {}).get("o5")
    if not all(_has_xy(p) for p in (o1, o2, o3, o5)):
        return False
    return (
        float(o1["y"]) > 280
        and 200 <= float(o1["x"]) <= 300
        and float(o2["x"]) > 380
        and float(o3["x"]) < 120
        and 150 <= float(o5["y"]) <= 230
        and 200 <= float(o5["x"]) <= 310
    )


def _triangle_wing_ball_formation(digit_pos: dict) -> bool:
    """Triangle mid sheets: 5 at top, 1 left wing, 2 right wing (ball side)."""
    o1 = (digit_pos or {}).get("o1")
    o2 = (digit_pos or {}).get("o2")
    o5 = (digit_pos or {}).get("o5")
    if not all(_has_xy(p) for p in (o1, o2, o5)):
        return False
    return (
        float(o5["y"]) > 250
        and 200 <= float(o5["x"]) <= 310
        and float(o1["x"]) < 120
        and float(o2["x"]) > 380
    )


def discover_solid_digit_cuts(
    crop_gray,
    digit_pos: dict,
    *,
    skip_pairs: set[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Solid ink between two digits → cut/relocate (not a dashed pass).

    Skeleton tip-walks often miss long Triangle cuts (1→3, 5→top). Tracing the
    printed solid corridor digit-to-digit recovers those routes.
    """
    skip = skip_pairs or set()
    paths: dict[str, list[dict[str, float]]] = {}
    marks: dict[str, str] = {}
    ids = [f"o{i}" for i in range(1, 6) if _has_xy((digit_pos or {}).get(f"o{i}"))]
    best_for: dict[str, tuple[float, list, str]] = {}
    for i, a_id in enumerate(ids):
        for b_id in ids[i + 1 :]:
            pair = (a_id, b_id)
            if pair in skip or (b_id, a_id) in skip:
                continue
            a = digit_pos[a_id]
            b = digit_pos[b_id]
            dist = ((float(a["x"]) - float(b["x"])) ** 2 + (float(a["y"]) - float(b["y"])) ** 2) ** 0.5
            if dist < 55 or dist > 280:
                continue
            poly = trace_ink_polyline(crop_gray, a, b, digit_positions=digit_pos)
            if len(poly) < 2:
                continue
            kind = classify_polyline_mark(crop_gray, poly)
            if kind == "pass":
                continue
            mid = _mid_raw_ink_fraction(crop_gray, poly, a, b)
            if mid < 0.55:
                continue
            # Assign the cut to the endpoint that is the natural mover: prefer
            # the digit farther from the basket (higher y) when ambiguous, else
            # the one whose tip lands nearer the other digit.
            tip = poly[-1]
            d_tip_b = ((tip["x"] - float(b["x"])) ** 2 + (tip["y"] - float(b["y"])) ** 2) ** 0.5
            d_tip_a = ((tip["x"] - float(a["x"])) ** 2 + (tip["y"] - float(a["y"])) ** 2) ** 0.5
            mover = a_id if d_tip_b <= d_tip_a else b_id
            dest = b if mover == a_id else a
            start = a if mover == a_id else b
            route = [dict(pt) for pt in poly]
            if mover == b_id:
                route = list(reversed(route))
            route[0] = {"x": float(start["x"]), "y": float(start["y"])}
            route[-1] = {"x": float(dest["x"]), "y": float(dest["y"])}
            score = mid * 100.0 + dist * 0.15
            prev = best_for.get(mover)
            if prev is None or score > prev[0]:
                best_for[mover] = (score, route, "cut" if kind != "screen" else "screen")
    for oid, (_score, route, kind) in best_for.items():
        paths[oid] = route
        marks[oid] = kind
    return {"paths": paths, "marks": marks}


def apply_triangle_sequence_routes(
    crop_gray,
    digit_pos: dict,
    paths: dict,
    marks: dict,
    passes: list,
    image_path: str | Path | None = None,
) -> None:
    """Scott's Triangle sequence overrides when sheet OCR/ink order is ambiguous.

    Opening sheet: Pass 1→2, Cut 1→3, Relocate 5→1's spot, Cut 3 toward 2.
    Entry sheet: Pass 2→5.
    Rotation sheet: Pass 5→1, Cut 5→2, Relocate 3→top, Cut 2→nail, Relocate 4 across.
    """
    if not digit_pos:
        return

    stem = Path(image_path).stem.lower() if image_path else ""
    # Known Offense Triangle pages in the Liberty bulk import.
    role = None
    if "0127" in stem or _triangle_opening_formation(digit_pos):
        role = "opening"
    elif "0128" in stem:
        role = "entry"
    elif "0129" in stem:
        role = "rotation"
    elif "0130" in stem or "0131" in stem:
        role = "finish"
    elif _triangle_wing_ball_formation(digit_pos):
        # Fallback without page id: 4 still on left + strong cross ink ⇒ rotation.
        o4 = digit_pos.get("o4")
        if _has_xy(o4) and float(o4["x"]) < 220:
            other = {"x": min(360.0, 500.0 - float(o4["x"])), "y": float(o4["y"])}
            poly4 = trace_ink_polyline(crop_gray, o4, other, digit_positions=digit_pos)
            mid4 = (
                _mid_raw_ink_fraction(crop_gray, poly4, o4, other)
                if len(poly4) >= 2
                else 0.0
            )
            role = "rotation" if mid4 >= 0.35 else "entry"
        else:
            role = "entry"
    else:
        return

    def _ensure_pass(frm: str, to: str) -> None:
        nonlocal passes
        if any(
            (not p.get("orphan")) and p.get("fromPid") == frm and p.get("toPid") == to
            for p in passes
        ):
            return
        a = digit_pos.get(frm)
        b = digit_pos.get(to)
        if not _has_xy(a) or not _has_xy(b):
            return
        poly = trace_ink_polyline(crop_gray, a, b, digit_positions=digit_pos)
        if len(poly) < 2:
            poly = [
                {"x": float(a["x"]), "y": float(a["y"])},
                {"x": float(b["x"]), "y": float(b["y"])},
            ]
        passes[:] = [
            p
            for p in passes
            if p.get("orphan")
            or not (
                {p.get("fromPid"), p.get("toPid")} == {frm, to}
                or (p.get("fromPid") == frm and p.get("toPid") != to)
            )
        ]
        passes.append({
            "fromPid": frm,
            "toPid": to,
            "points": poly,
            "type": "pass",
        })

    def _ensure_cut(oid: str, dest: dict, *, min_disp: float = 40.0) -> None:
        start = digit_pos.get(oid)
        if not _has_xy(start) or not _has_xy(dest):
            return
        disp = ((float(dest["x"]) - float(start["x"])) ** 2 + (float(dest["y"]) - float(start["y"])) ** 2) ** 0.5
        if disp < min_disp:
            return
        poly = trace_ink_polyline(crop_gray, start, dest, digit_positions=digit_pos)
        if len(poly) < 2 or _mid_raw_ink_fraction(crop_gray, poly, start, dest) < 0.18:
            poly = [
                {"x": float(start["x"]), "y": float(start["y"])},
                {"x": float(dest["x"]), "y": float(dest["y"])},
            ]
        else:
            poly = [dict(pt) for pt in poly]
            poly[0] = {"x": float(start["x"]), "y": float(start["y"])}
            poly[-1] = {"x": float(dest["x"]), "y": float(dest["y"])}
        paths[oid] = poly
        marks[oid] = "cut"

    if role == "opening":
        o1, o2, o3, o4, o5 = (digit_pos.get(f"o{i}") for i in range(1, 6))
        _ensure_pass("o1", "o2")
        _ensure_cut("o1", o3)
        _ensure_cut("o5", o1)
        toward_2 = {
            "x": float(o3["x"]) + (float(o2["x"]) - float(o3["x"])) * 0.55,
            "y": float(o3["y"]) + (float(o2["y"]) - float(o3["y"])) * 0.55,
        }
        ink_3 = trace_ink_polyline(crop_gray, o3, o2, digit_positions=digit_pos)
        if len(ink_3) >= 2 and _mid_raw_ink_fraction(crop_gray, ink_3, o3, o2) >= 0.18:
            tip = ink_3[min(len(ink_3) - 1, max(2, int(len(ink_3) * 0.65)))]
            toward_2 = {"x": float(tip["x"]), "y": float(tip["y"])}
        _ensure_cut("o3", toward_2, min_disp=35.0)
        # Scott step 3: after 3 cuts, 4 slides to the other side of the key.
        if _has_xy(o4) and float(o4["x"]) < 220:
            other = {"x": min(360.0, 500.0 - float(o4["x"])), "y": float(o4["y"])}
            _ensure_cut("o4", other, min_disp=50.0)
        paths.pop("o2", None)
        marks.pop("o2", None)
        passes[:] = [
            p for p in passes
            if not (
                p.get("orphan")
                and p.get("fromPid") == "o1"
                and p.get("toPid") == "o2"
            )
        ]
        return

    if role == "entry":
        o2, o5 = digit_pos.get("o2"), digit_pos.get("o5")
        _ensure_pass("o2", "o5")
        # Entry sheet: only the pass — drop invented rotation cuts.
        for oid in list(paths.keys()):
            if oid in ("o2", "o3", "o4", "o5", "o1"):
                # Keep only if it's a short settle; otherwise clear movers.
                paths.pop(oid, None)
                marks.pop(oid, None)
        return

    if role == "rotation":
        o1, o2, o3, o4, o5 = (digit_pos.get(f"o{i}") for i in range(1, 6))
        _ensure_pass("o5", "o1")
        if _has_xy(o2):
            _ensure_cut("o5", o2)
        top = {"x": float(o5["x"]), "y": float(o5["y"])} if _has_xy(o5) else {"x": 255.0, "y": 290.0}
        o3_pos = o3
        if not _has_xy(o3_pos):
            o3_pos = {"x": 250.0, "y": 200.0}
            digit_pos = dict(digit_pos)
            digit_pos["o3"] = o3_pos
        _ensure_cut("o3", top)
        if _has_xy(o2):
            _ensure_cut("o2", o3_pos)
        # Scott step 8: 4 shifts to the other side again. If sheet-1 already
        # slid 4 to the right (held), mirror back then... end pose is right, so
        # only animate when still on the left (printed ink / no early hold).
        if _has_xy(o4) and float(o4["x"]) < 220:
            other = {"x": min(360.0, 500.0 - float(o4["x"])), "y": float(o4["y"])}
            _ensure_cut("o4", other, min_disp=50.0)
        elif _has_xy(o4) and float(o4["x"]) > 280:
            # Already on right from sheet-1 hold — micro-shift stay (hold tip).
            tip = {"x": float(o4["x"]), "y": float(o4["y"])}
            # no-op cut skipped by min_disp
            pass
        # 1 receives — drop false cut up to 5.
        if marks.get("o1") == "cut":
            paths.pop("o1", None)
            marks.pop("o1", None)
        return

    if role == "finish":
        if "0131" in stem:
            paths.clear()
            marks.clear()
            passes[:] = [p for p in passes if p.get("orphan")]
            passes.clear()
            return
        o1, o3 = digit_pos.get("o1"), digit_pos.get("o3")
        if "0130" in stem and _has_xy(o1) and _has_xy(o3):
            _ensure_pass("o1", "o3")
            paths.pop("o1", None)
            marks.pop("o1", None)
        passes[:] = [
            p for p in passes
            if not (
                (not p.get("orphan"))
                and {p.get("fromPid"), p.get("toPid")} == {"o2", "o3"}
            )
        ]
        return


def apply_pitt5_sequence_routes(
    crop_gray,
    digit_pos: dict,
    paths: dict,
    marks: dict,
    passes: list,
    image_path: str | Path | None = None,
) -> None:
    """Scott's Pitt 5 sequence when OCR/ink order is wrong.

    Opening (page 172): Pass 1→5, Cut 1→left corner, Relocate 2→right corner
    (same phase as 1's cut).
    Screen (page 173): 4 screens for 5 (hold at T-bar tip near 3pt), 5 cuts
    around the screen to the right block, then 4 drops to the left block
    (encoded as paths['o4_drop'] so the animator can sequence-gate it).
    """
    if not digit_pos:
        return

    stem = Path(image_path).stem.lower() if image_path else ""
    role = None
    # Stem-gated so Pitt 1 / similar top-pair sheets are not rewritten.
    if "0172" in stem:
        role = "opening"
    elif "0173" in stem:
        role = "screen"
    else:
        return

    def _ensure_pass(frm: str, to: str) -> None:
        nonlocal passes
        if any(
            (not p.get("orphan")) and p.get("fromPid") == frm and p.get("toPid") == to
            for p in passes
        ):
            return
        a = digit_pos.get(frm)
        b = digit_pos.get(to)
        if not _has_xy(a) or not _has_xy(b):
            return
        poly = trace_ink_polyline(crop_gray, a, b, digit_positions=digit_pos)
        if len(poly) < 2:
            poly = [
                {"x": float(a["x"]), "y": float(a["y"])},
                {"x": float(b["x"]), "y": float(b["y"])},
            ]
        passes[:] = [
            p
            for p in passes
            if p.get("orphan")
            or not (
                {p.get("fromPid"), p.get("toPid")} == {frm, to}
                or (p.get("fromPid") == frm and p.get("toPid") != to)
            )
        ]
        # Drop orphan duplicates of this pass corridor.
        passes[:] = [
            p
            for p in passes
            if not (
                p.get("orphan")
                and {p.get("fromPid"), p.get("toPid")} == {frm, to}
            )
        ]
        passes.append({
            "fromPid": frm,
            "toPid": to,
            "points": poly,
            "type": "pass",
        })

    def _ensure_route(oid: str, dest: dict, kind: str, *, min_disp: float = 40.0) -> None:
        start = digit_pos.get(oid)
        if not _has_xy(start) or not _has_xy(dest):
            return
        disp = (
            (float(dest["x"]) - float(start["x"])) ** 2
            + (float(dest["y"]) - float(start["y"])) ** 2
        ) ** 0.5
        if disp < min_disp:
            return
        poly = trace_ink_polyline(crop_gray, start, dest, digit_positions=digit_pos)
        if len(poly) < 2 or _mid_raw_ink_fraction(crop_gray, poly, start, dest) < 0.15:
            poly = [
                {"x": float(start["x"]), "y": float(start["y"])},
                {"x": float(dest["x"]), "y": float(dest["y"])},
            ]
        else:
            poly = [dict(pt) for pt in poly]
            poly[0] = {"x": float(start["x"]), "y": float(start["y"])}
            poly[-1] = {"x": float(dest["x"]), "y": float(dest["y"])}
        paths[oid] = poly
        marks[oid] = kind

    if role == "opening":
        o1, o2, o4, o5 = (digit_pos.get(f"o{i}") for i in (1, 2, 4, 5))
        _ensure_pass("o1", "o5")
        left_corner = {"x": 22.0, "y": 78.0}
        right_corner = {"x": 478.0, "y": 76.0}
        # Prefer sheet ink tips when present.
        if _has_xy(o1):
            ink_1 = trace_ink_polyline(
                crop_gray, o1, left_corner, digit_positions=digit_pos
            )
            if len(ink_1) >= 2 and _mid_raw_ink_fraction(crop_gray, ink_1, o1, left_corner) >= 0.15:
                tip = ink_1[-1]
                if float(tip["x"]) < 120 and float(tip["y"]) < 160:
                    left_corner = {"x": float(tip["x"]), "y": float(tip["y"])}
        if _has_xy(o2):
            ink_2 = trace_ink_polyline(
                crop_gray, o2, right_corner, digit_positions=digit_pos
            )
            if len(ink_2) >= 2 and _mid_raw_ink_fraction(crop_gray, ink_2, o2, right_corner) >= 0.15:
                tip = ink_2[-1]
                if float(tip["x"]) > 380 and float(tip["y"]) < 160:
                    right_corner = {"x": float(tip["x"]), "y": float(tip["y"])}
        _ensure_route("o1", left_corner, "cut", min_disp=50.0)
        _ensure_route("o2", right_corner, "cut", min_disp=40.0)
        # Drop false receiver walk along the pass and idle bigs.
        for oid in ("o3", "o4", "o5"):
            if marks.get(oid) in ("cut", "dribble", "screen"):
                paths.pop(oid, None)
                marks.pop(oid, None)
        return

    # Screen sheet: 4 holds near 3pt → 5 curls around to right block → 4 drops left.
    o4, o5 = digit_pos.get("o4"), digit_pos.get("o5")
    if not _has_xy(o4) or not _has_xy(o5):
        return
    o4x, o4y = float(o4["x"]), float(o4["y"])
    o5x, o5y = float(o5["x"]), float(o5["y"])
    # Screen tip: along o4→o5 corridor, but keep token clearance from ball handler
    # (ink 85% tip sat ~35px from #5 and looked collided).
    screen_clearance = 65.0
    corridor = ((o4x - o5x) ** 2 + (o4y - o5y) ** 2) ** 0.5
    if corridor < 1.0:
        return
    # Point on the segment that is `screen_clearance` away from #5 toward #4.
    t_clear = min(0.78, max(0.22, screen_clearance / corridor))
    screen_spot = {
        "x": o5x + t_clear * (o4x - o5x),
        "y": o5y + t_clear * (o4y - o5y),
    }
    # Prefer printed T-bar tip when it already has enough spacing from #5.
    ink_screen = trace_ink_polyline(crop_gray, o4, o5, digit_positions=digit_pos)
    if len(ink_screen) >= 2 and _mid_raw_ink_fraction(crop_gray, ink_screen, o4, o5) >= 0.12:
        tip = ink_screen[min(len(ink_screen) - 1, max(2, int(len(ink_screen) * 0.72)))]
        tip_pt = {"x": float(tip["x"]), "y": float(tip["y"])}
        tip_gap = (
            (tip_pt["x"] - o5x) ** 2 + (tip_pt["y"] - o5y) ** 2
        ) ** 0.5
        if tip_gap >= screen_clearance - 4.0 and float(tip_pt["y"]) > 180.0:
            screen_spot = tip_pt
        elif tip_gap < screen_clearance - 4.0:
            # Pull the ink tip back toward #4 until clearance is met.
            back = (
                (o4x - tip_pt["x"]) ** 2 + (o4y - tip_pt["y"]) ** 2
            ) ** 0.5
            if back > 1.0:
                need = screen_clearance - tip_gap
                u = min(1.0, need / back)
                screen_spot = {
                    "x": tip_pt["x"] + u * (o4x - tip_pt["x"]),
                    "y": tip_pt["y"] + u * (o4y - tip_pt["y"]),
                }
    # Straight slide to the screen (do not follow squiggly T-bar stem ink).
    paths["o4"] = [
        {"x": o4x, "y": o4y},
        {"x": float(screen_spot["x"]), "y": float(screen_spot["y"])},
    ]
    marks["o4"] = "screen"

    right_block = {"x": o4x, "y": o4y}
    left_block = {
        "x": max(120.0, min(200.0, 500.0 - o4x)),
        "y": o4y,
    }
    # Finish on the right block (OCR #4 start); ignore left-leaning ink tips.
    sx, sy = float(screen_spot["x"]), float(screen_spot["y"])
    # #5 curls around the screener to the right (not through #4).
    # Waypoints sit clear to the screener's right / basket-side, then into the block.
    around_clear = 50.0
    wp_around = {
        "x": min(320.0, sx + around_clear),
        "y": max(150.0, sy - 18.0),
    }
    wp_elbow = {
        "x": min(float(right_block["x"]), (wp_around["x"] + float(right_block["x"])) * 0.5 + 18.0),
        "y": (wp_around["y"] + float(right_block["y"])) * 0.5,
    }
    paths["o5"] = [
        {"x": o5x, "y": o5y},
        wp_around,
        wp_elbow,
        {"x": float(right_block["x"]), "y": float(right_block["y"])},
    ]
    marks["o5"] = "cut"

    # #4's post-screen drop to the left block (second beat for same player).
    # Straight drop; frontend orders Screen o4 → Cut o5 → then this (pitt5Drop).
    drop_poly = [
        {"x": float(screen_spot["x"]), "y": float(screen_spot["y"])},
        {"x": float(left_block["x"]), "y": float(left_block["y"])},
    ]
    paths["o4_drop"] = drop_poly
    marks["o4_drop"] = "cut"

    # No passes / guard cuts on the screen sheet.
    for oid in ("o1", "o2", "o3"):
        paths.pop(oid, None)
        marks.pop(oid, None)
    passes[:] = [p for p in passes if p.get("orphan")]
    passes.clear()


def trace_marked_paths_for_transition(
    image_path: str | Path,
    from_positions: dict,
    to_positions: dict,
    cache_base: str | Path | None = None,
) -> dict[str, Any]:
    """Trace ink and classify marks for a sheet transition.

    Returns:
      {
        "paths": { "o1": [points...], ... },          # movers only (compat)
        "marks": { "o1": "cut"|"screen"|"pass", ... },
        "passes": [ {fromPid, toPid, points, type: "pass"}, ... ],
      }

    When digit endpoints barely move (common on multi-page play sheets), still
    discovers dashed passes between digits and outgoing cut/screen ink from each
    digit tip so Play All can follow the printed action.
    """
    import cv2

    path = Path(image_path)
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Could not read image: {path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    court = find_court_bbox(gray)
    x0, y0, x1, y1 = court
    crop = gray[y0:y1, x0:x1]
    digit_pos: dict[str, dict[str, float]] = {}
    # Prefer FROM-sheet anchors for ink discovery. Next-sheet OCR must not
    # overwrite current digits (Triangle page 129 was inventing cuts from
    # page-130 endpoints when the client passed to_positions ahead).
    for src in (to_positions or {}, from_positions or {}):
        for k, v in src.items():
            if _has_xy(v):
                digit_pos[k] = {"x": float(v["x"]), "y": float(v["y"])}

    paths: dict[str, list[dict[str, float]]] = {}
    marks: dict[str, str] = {}
    mover_pids: set[str] = set()

    for i in range(1, 6):
        oid = f"o{i}"
        a = (from_positions or {}).get(oid)
        b = (to_positions or {}).get(oid)
        if not a or not b:
            continue
        if abs(float(a["x"]) - float(b["x"])) < 8 and abs(float(a["y"]) - float(b["y"])) < 8:
            continue
        poly = trace_ink_polyline(crop, a, b, digit_positions=digit_pos)
        if len(poly) < 2:
            continue
        kind = classify_polyline_mark(crop, poly)
        # A dashed stroke on a mover is still a player cut that looks dashed —
        # only treat as pass when endpoints are different players (handled below).
        if kind == "pass":
            kind = "cut"
        paths[oid] = poly
        marks[oid] = kind
        mover_pids.add(oid)

    # Outgoing cut/screen/dribble discovery for stationary digits.
    # Also merge when some digits already moved — Triangle sheets need both.
    if digit_pos:
        outgoing = discover_outgoing_routes(crop, digit_pos)
        for oid, poly in (outgoing.get("paths") or {}).items():
            if oid in paths:
                continue
            kind = (outgoing.get("marks") or {}).get(oid) or "cut"
            paths[oid] = poly
            marks[oid] = kind
            mover_pids.add(oid)

    # Dashed pass marks between digits (ball-only). Prefer from-sheet digits.
    passes: list[dict[str, Any]] = []
    from_pos = from_positions or {}
    ids = [f"o{i}" for i in range(1, 6) if _has_xy(from_pos.get(f"o{i}"))]
    for i, a_id in enumerate(ids):
        for b_id in ids[i + 1 :]:
            a = from_pos[a_id]
            b = from_pos[b_id]
            dist = ((float(a["x"]) - float(b["x"])) ** 2 + (float(a["y"]) - float(b["y"])) ** 2) ** 0.5
            if dist < 35 or dist > 320:
                continue
            poly = trace_ink_polyline(crop, a, b, digit_positions=digit_pos)
            if len(poly) < 2:
                continue
            kind = classify_polyline_mark(crop, poly)
            if kind != "pass":
                continue
            # Reject white-space chords that only look dashed from noise.
            if _mid_raw_ink_fraction(crop, poly, a, b) < 0.45:
                continue
            # Skip if this is essentially the same as a mover's solid route
            skip = False
            for mid in (a_id, b_id):
                if mid not in paths:
                    continue
                mp = paths[mid]
                if abs(mp[-1]["x"] - b["x"]) < 12 and abs(mp[-1]["y"] - b["y"]) < 12:
                    if marks.get(mid) != "screen":
                        skip = True
            if skip:
                continue
            passes.append({
                "fromPid": a_id,
                "toPid": b_id,
                "points": poly,
                "type": "pass",
            })

    # Solid digit→digit cuts (Triangle 1→3 / 5→top, etc.) before pass filtering.
    pass_pair_skip = {
        (p["fromPid"], p["toPid"])
        for p in passes
        if p.get("fromPid") and p.get("toPid") and not p.get("orphan")
    }
    solid = discover_solid_digit_cuts(crop, digit_pos, skip_pairs=pass_pair_skip)
    for oid, poly in (solid.get("paths") or {}).items():
        # Never clobber an existing OCR transition / screen / outgoing tip.
        if oid in paths:
            continue
        paths[oid] = poly
        marks[oid] = (solid.get("marks") or {}).get(oid) or "cut"
        mover_pids.add(oid)

    # Drop false dribbles / pass-corridor walks when a digit-pair pass exists.
    # Triangle re-adds real Pass-then-Cut routes later via apply_triangle_sequence_routes.
    # Rip page 120/121: suppress guard "screens" onto other digits and pass-ink cuts.
    pass_digits = set()
    pass_recv: dict[str, set[str]] = {}
    for p in passes:
        if p.get("orphan"):
            continue
        frm, to = p.get("fromPid"), p.get("toPid")
        if frm:
            pass_digits.add(frm)
            pass_recv.setdefault(frm, set()).add(to or "")
        if to:
            pass_digits.add(to)
    has_digit_pass = any(not p.get("orphan") for p in passes)
    triangle_form = _triangle_opening_formation(digit_pos) or _triangle_wing_ball_formation(
        digit_pos
    )
    for oid in list(paths.keys()):
        kind = marks.get(oid)
        poly = paths.get(oid) or []
        tip = poly[-1] if poly else None
        # False guard screens (Rip page 120 o1→o5 glyph): tip lands on another digit.
        # Keep o4/o5 T-bar screens; those tips sit in empty paint, not on a digit.
        if kind == "screen" and tip and oid in ("o1", "o2", "o3"):
            for other, op in digit_pos.items():
                if other == oid or not str(other).startswith("o") or not _has_xy(op):
                    continue
                if ((tip["x"] - float(op["x"])) ** 2 + (tip["y"] - float(op["y"])) ** 2) ** 0.5 < 45:
                    del paths[oid]
                    marks.pop(oid, None)
                    mover_pids.discard(oid)
                    tip = None
                    break
            if oid not in paths:
                continue
        if kind == "screen":
            continue
        if has_digit_pass and kind == "dribble":
            del paths[oid]
            marks.pop(oid, None)
            mover_pids.discard(oid)
            continue
        if kind == "cut" and tip and oid in pass_digits:
            # Drop cuts that merely walk the pass into the receiver (false).
            receivers = pass_recv.get(oid) or set()
            near_digit = False
            for rid in receivers:
                rp = from_pos.get(rid) or digit_pos.get(rid)
                if not _has_xy(rp):
                    continue
                if ((tip["x"] - float(rp["x"])) ** 2 + (tip["y"] - float(rp["y"])) ** 2) ** 0.5 < 45:
                    near_digit = True
                    break
            # Rip reverse-pass sheets also invent receiver→post cuts along residue.
            if not near_digit and not triangle_form:
                for other, op in digit_pos.items():
                    if other == oid or not str(other).startswith("o") or not _has_xy(op):
                        continue
                    if ((tip["x"] - float(op["x"])) ** 2 + (tip["y"] - float(op["y"])) ** 2) ** 0.5 < 45:
                        near_digit = True
                        break
            if near_digit:
                del paths[oid]
                marks.pop(oid, None)
                mover_pids.discard(oid)
                continue
        # Rip page 120: no Triangle multi-cut — drop non-passer cuts that are
        # short dribble-like residue when the only real action is the pass.
        if (
            has_digit_pass
            and kind != "screen"
            and oid not in pass_digits
            and not triangle_form
        ):
            plen = _poly_len_svg(poly) if poly else 0
            if kind == "dribble" or plen < 90:
                del paths[oid]
                marks.pop(oid, None)
                mover_pids.discard(oid)

    # Rip-style big screens on reverse-pass sheets (e.g. page 121): ray-cast
    # o4/o5 to T-bar when skeleton walk missed. Only when a wing/guard digit
    # pass is present (o1–o3) — skip finish sheets with orphan dashes or false
    # chords involving the bigs (Rip page 122 o1→o4).
    wing_digit_pass = any(
        (not p.get("orphan"))
        and p.get("fromPid") in ("o1", "o2", "o3")
        and p.get("toPid") in ("o1", "o2", "o3")
        for p in passes
    )
    if wing_digit_pass and digit_pos:
        big_screens = discover_big_screen_routes(crop, digit_pos)
        for oid, poly in (big_screens.get("paths") or {}).items():
            if oid in paths and marks.get(oid) == "screen":
                continue
            if oid in paths and marks.get(oid) != "screen":
                paths.pop(oid, None)
                marks.pop(oid, None)
                mover_pids.discard(oid)
            if oid in paths:
                continue
            paths[oid] = poly
            marks[oid] = "screen"
            mover_pids.add(oid)

    # Orphan dashed passes (not digit→digit), e.g. dribble-tip → corner.
    for chain in discover_dash_pass_chains(crop):
        if len(chain) < 2:
            continue
        start, end = chain[0], chain[-1]
        # Skip if a digit-pair pass already covers this corridor.
        overlap = False
        for p in passes:
            pts = p.get("points") or []
            if len(pts) < 2:
                continue
            a, b = pts[0], pts[-1]
            d1 = min(
                ((a["x"] - start["x"]) ** 2 + (a["y"] - start["y"]) ** 2) ** 0.5,
                ((b["x"] - start["x"]) ** 2 + (b["y"] - start["y"]) ** 2) ** 0.5,
            )
            d2 = min(
                ((a["x"] - end["x"]) ** 2 + (a["y"] - end["y"]) ** 2) ** 0.5,
                ((b["x"] - end["x"]) ** 2 + (b["y"] - end["y"]) ** 2) ** 0.5,
            )
            if d1 < 40 and d2 < 40:
                overlap = True
                break
        if overlap:
            continue

        # Attach solid routes from digits to each endpoint.
        # Euclidean-nearest is wrong for Rip page 122 (wing o2 is closer to the
        # elbow tip than point o1). Prefer the higher-y digit (farther from basket)
        # as the driver into the pass start; nearest other digit to the tip as receiver.
        def _digits_near(pt, max_dist):
            out = []
            for oid in ids:
                q = from_pos[oid]
                d = ((q["x"] - pt["x"]) ** 2 + (q["y"] - pt["y"]) ** 2) ** 0.5
                if d <= max_dist:
                    out.append((d, oid, q))
            return out

        start_cands = _digits_near(start, 240)
        end_cands = _digits_near(end, 200)
        from_pid = None
        to_pid = None
        if start_cands:
            # Driver: farthest from basket among those near the pass origin.
            from_pid = max(start_cands, key=lambda t: t[2]["y"])[1]
        if end_cands:
            recv = [t for t in end_cands if t[1] != from_pid]
            if recv:
                # Prefer the perimeter/wing receiver (higher y) over a baseline big
                # whose OCR sits nearer the corner tip (Rip: o2 drop, not o4).
                to_pid = max(recv, key=lambda t: (t[2]["y"], -t[0]))[1]
            elif not from_pid:
                to_pid = min(end_cands, key=lambda t: t[0])[1]

        # Ball-handler dribble into the pass start (squiggle / solid).
        # Overwrite a prior from→to cut invented by stale heldLandings tips
        # (Rip page 122: o1 must dribble to the elbow, not cut back to o5).
        prior_driver = marks.get(from_pid) if from_pid else None
        if from_pid and (from_pid not in paths or prior_driver in ("cut", "dribble", None)):
            a = from_pos[from_pid]
            route = trace_ink_polyline(crop, a, start, digit_positions=digit_pos)
            if len(route) >= 2:
                plen = _poly_len_svg(route)
                disp = ((start["x"] - a["x"]) ** 2 + (start["y"] - a["y"]) ** 2) ** 0.5
                mid = max(
                    _mid_raw_ink_fraction(crop, route, a, start),
                    _path_ink_fraction_stroke(crop, route, a, start),
                )
                # Driver into an orphan dash tip is always a dribble/drive (Rip
                # page 122: 1 to the block). Do not leave it as a post-pass cut —
                # that reordered beats to Pass-then-Cut and yanked 1 after the ball.
                if disp >= 35 and plen < 360 and (mid >= 0.18 or disp >= 80):
                    tip_d = (
                        ((route[-1]["x"] - start["x"]) ** 2 + (route[-1]["y"] - start["y"]) ** 2) ** 0.5
                    )
                    # Prefer orphan tip over a conflicting held to_position cut.
                    replace_ok = from_pid not in paths or tip_d < 36 or mid >= 0.22
                    if replace_ok and prior_driver != "screen":
                        route = [dict(pt) for pt in route]
                        route[0] = {"x": float(a["x"]), "y": float(a["y"])}
                        route[-1] = {"x": float(start["x"]), "y": float(start["y"])}
                        paths[from_pid] = route
                        marks[from_pid] = "dribble"
                        mover_pids.add(from_pid)

        # Receiver cut into the pass end.
        if to_pid and to_pid not in paths:
            a = from_pos[to_pid]
            route = trace_ink_polyline(crop, a, end, digit_positions=digit_pos)
            if len(route) >= 2:
                plen = _poly_len_svg(route)
                disp = ((end["x"] - a["x"]) ** 2 + (end["y"] - a["y"]) ** 2) ** 0.5
                mid = max(
                    _mid_raw_ink_fraction(crop, route, a, end),
                    _path_ink_fraction_stroke(crop, route, a, end),
                )
                tip_near = (
                    ((route[-1]["x"] - end["x"]) ** 2 + (route[-1]["y"] - end["y"]) ** 2) ** 0.5
                    < 28
                )
                kind = classify_polyline_mark(crop, route)
                # Corner-drop arrowheads often false-trigger T-bar "screen".
                # When the tip is the orphan pass end, keep it as a cut.
                if kind in ("pass", "screen") and tip_near:
                    kind = "cut"
                elif kind == "pass":
                    kind = "cut"
                if disp >= 35 and plen < 300 and (mid >= 0.12 or disp >= 70) and (
                    kind != "screen" or tip_near
                ):
                    route = [dict(pt) for pt in route]
                    route[0] = {"x": float(a["x"]), "y": float(a["y"])}
                    route[-1] = {"x": float(end["x"]), "y": float(end["y"])}
                    paths[to_pid] = route
                    marks[to_pid] = "cut"
                    mover_pids.add(to_pid)

        passes.append({
            "fromPid": from_pid,
            "toPid": to_pid,
            "points": chain,
            "type": "pass",
            "orphan": True,
        })

    # Triangle (Scott): force Pass-then-Cut order + missing relocates when OCR/ink
    # invents the wrong set (same class of failure as Rip Pass-then-Cut).
    apply_triangle_sequence_routes(crop, digit_pos, paths, marks, passes, image_path=path)
    # Pitt 5 (Scott): Pass 1→5 + corner clears, then 4 screens / 5 to right block.
    apply_pitt5_sequence_routes(crop, digit_pos, paths, marks, passes, image_path=path)

    return {"paths": paths, "marks": marks, "passes": passes}


def trace_paths_for_transition(
    image_path: str | Path,
    from_positions: dict,
    to_positions: dict,
    cache_base: str | Path | None = None,
) -> dict[str, list[dict[str, float]]]:
    """Trace ink polylines for each offense player that moved between sheets."""
    marked = trace_marked_paths_for_transition(
        image_path, from_positions, to_positions, cache_base=cache_base
    )
    return marked.get("paths") or {}


def _has_xy(v) -> bool:
    return isinstance(v, dict) and isinstance(v.get("x"), (int, float)) and isinstance(v.get("y"), (int, float))


def analyze_sheet_image(image_path: str | Path, cache_base: str | Path | None = None) -> dict[str, Any]:
    """Analyze a play-sheet PNG. Returns court_frac + positions (cached)."""
    import cv2

    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(str(path))

    cache_path = _cache_dir(cache_base) / f"{_cache_key(path)}.json"
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("cache_version") == _CACHE_VERSION:
                return cached
        except (OSError, json.JSONDecodeError):
            pass

    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Could not read image: {path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    court = find_court_bbox(gray)
    x0, y0, x1, y1 = court
    positions = detect_sheet_digits(gray, court)
    # Strip confidence from public positions map used by the animator; o1..o5 only.
    pos_public = {
        k: {"x": v["x"], "y": v["y"]}
        for k, v in positions.items()
        if k in {f"o{i}" for i in range(1, 6)}
    }
    result = {
        "ok": True,
        "cache_version": _CACHE_VERSION,
        "size": [w, h],
        "court_bbox": [x0, y0, x1, y1],
        "court_frac": {
            "x0": x0 / w,
            "y0": y0 / h,
            "x1": x1 / w,
            "y1": y1 / h,
        },
        "positions": pos_public,
        "debug_positions": positions,
        "source": str(path).replace("\\", "/"),
    }
    try:
        cache_path.write_text(json.dumps(result), encoding="utf-8")
    except OSError:
        pass
    return result


def resolve_upload_path(url_or_path: str, app_root: str | Path | None = None) -> Path:
    """Map /uploads/... URL to a filesystem path under the app root."""
    raw = (url_or_path or "").strip()
    if not raw:
        raise FileNotFoundError("empty path")
    if raw.startswith("/uploads/"):
        rel = raw[len("/") :]
    elif raw.startswith("uploads/"):
        rel = raw
    elif os.path.isfile(raw):
        return Path(raw)
    else:
        rel = raw.lstrip("/")
    root = Path(app_root) if app_root else Path.cwd()
    path = (root / rel).resolve()
    # Stay inside project uploads
    uploads = (root / "uploads").resolve()
    if uploads not in path.parents and path != uploads:
        # still allow absolute paths under root
        if root not in path.parents and path != root:
            raise FileNotFoundError(f"path outside uploads: {url_or_path}")
    if not path.is_file():
        raise FileNotFoundError(str(path))
    return path
