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


_CACHE_VERSION = "v9"


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
    return (
        max(0, x0 - pad),
        max(0, y0 - pad),
        min(w, x1 + pad),
        min(h, y1 + pad),
    )


def _digit_blob_candidates(crop_gray):
    """Return list of (cx, cy, w, h, area) in crop pixel space."""
    import cv2
    import numpy as np

    ch, cw = crop_gray.shape[:2]
    up = cv2.resize(crop_gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, bw = cv2.threshold(
        cv2.GaussianBlur(up, (5, 5), 0), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    hker = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, up.shape[1] // 6), 1))
    vker = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, up.shape[0] // 6)))
    lines = cv2.morphologyEx(bw, cv2.MORPH_OPEN, hker) | cv2.morphologyEx(bw, cv2.MORPH_OPEN, vker)
    lines = cv2.dilate(lines, np.ones((3, 3), np.uint8), 1)
    clean = cv2.subtract(bw, lines)
    clean = cv2.morphologyEx(clean, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    clean = cv2.morphologyEx(clean, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, _labels, stats, _centroids = cv2.connectedComponentsWithStats(clean, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 250 or area > 20000:
            continue
        if h < 30 or h > 160 or w < 16 or w > 120:
            continue
        aspect = h / max(w, 1)
        if aspect < 0.6 or aspect > 3.8:
            continue
        # Back to crop coords (undo 2x upscale)
        cx = (x + w / 2) / 2.0
        cy = (y + h / 2) / 2.0
        out.append((cx, cy, w / 2.0, h / 2.0, area / 4.0))
    # Prefer larger blobs; drop near-duplicate centers
    out.sort(key=lambda t: -t[4])
    kept = []
    for cand in out:
        cx, cy = cand[0], cand[1]
        if any((cx - k[0]) ** 2 + (cy - k[1]) ** 2 < 20 ** 2 for k in kept):
            continue
        kept.append(cand)
        if len(kept) >= 12:
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
            if t in "12345" and float(conf) > best_c:
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
        pad_x = max(4, w * 0.35)
        pad_y = max(4, h * 0.35)
        x_a = max(0, int(cx - w / 2 - pad_x))
        y_a = max(0, int(cy - h / 2 - pad_y))
        x_b = min(cw, int(cx + w / 2 + pad_x))
        y_b = min(ch, int(cy + h / 2 + pad_y))
        roi = crop[y_a:y_b, x_a:x_b]
        digit, conf = _classify_roi(roi)
        # EasyOCR sometimes returns ~0.3 on bold stencil digits; keep modest floor.
        if not digit or conf < 0.28:
            continue
        prev = by_digit.get(digit)
        if prev is None or conf > prev[0]:
            by_digit[digit] = (conf, cx, cy)

    out: dict[str, dict[str, float]] = {}
    for d, (conf, cx, cy) in by_digit.items():
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


def _stroke_mask(crop_gray):
    """Binary mask of play ink (arrows/digits) with thick court lines suppressed."""
    import cv2
    import numpy as np

    ch, cw = crop_gray.shape[:2]
    blur = cv2.GaussianBlur(crop_gray, (3, 3), 0)
    _, bw = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Remove long horizontal/vertical court lines
    hker = cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, cw // 4), 1))
    vker = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(40, ch // 4)))
    long_lines = cv2.morphologyEx(bw, cv2.MORPH_OPEN, hker) | cv2.morphologyEx(bw, cv2.MORPH_OPEN, vker)
    long_lines = cv2.dilate(long_lines, np.ones((5, 5), np.uint8), 1)
    stroke = cv2.subtract(bw, long_lines)
    # Connect dashed / squiggle segments, then thin for a walkable centerline
    stroke = cv2.morphologyEx(
        stroke, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    )
    return stroke


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

    # Prefer the path that hugs the skeleton most, among reasonable-length options.
    inked = [
        (pts, _path_ink_fraction(skel, pts, radius=5))
        for pts in candidates
        if _ok(pts)
    ]
    if inked:
        # High ink + longer path wins (follows the curve). Low ink: prefer shorter.
        def _rank(t):
            pts, ink = t
            plen = _path_len(pts)
            if ink >= 0.7 and plen >= straight_len * 1.12:
                return (ink, plen)
            if ink >= 0.7 and len(pts) <= 2:
                return (ink - 0.25, plen)  # endpoints-only on digit blobs ≠ real stroke
            return (ink, -plen)

        best_ink = max(inked, key=_rank)
        if best_ink[1] >= 0.35:
            path_px = best_ink[0]
        else:
            path_px = min(
                (pts for pts in candidates if pts and len(pts) >= 2),
                key=_path_len,
                default=corridor,
            )
    else:
        path_px = corridor if len(corridor) >= 2 else [(sx, sy), (ex, ey)]

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



def trace_paths_for_transition(
    image_path: str | Path,
    from_positions: dict,
    to_positions: dict,
    cache_base: str | Path | None = None,
) -> dict[str, list[dict[str, float]]]:
    """Trace ink polylines for each offense player that moved between sheets."""
    import cv2

    path = Path(image_path)
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Could not read image: {path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    court = find_court_bbox(gray)
    x0, y0, x1, y1 = court
    crop = gray[y0:y1, x0:x1]
    # Use known start digits as mask centers (avoid re-running OCR here).
    digit_pos = {}
    for src in (from_positions or {}, to_positions or {}):
        for k, v in src.items():
            if _has_xy(v):
                digit_pos[k] = {"x": float(v["x"]), "y": float(v["y"])}

    paths: dict[str, list[dict[str, float]]] = {}
    for i in range(1, 6):
        oid = f"o{i}"
        a = (from_positions or {}).get(oid)
        b = (to_positions or {}).get(oid)
        if not a or not b:
            continue
        if abs(float(a["x"]) - float(b["x"])) < 8 and abs(float(a["y"]) - float(b["y"])) < 8:
            continue
        poly = trace_ink_polyline(crop, a, b, digit_positions=digit_pos)
        if len(poly) >= 2:
            paths[oid] = poly
    return paths


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
    # Strip confidence from public positions map used by the animator
    pos_public = {k: {"x": v["x"], "y": v["y"]} for k, v in positions.items()}
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
