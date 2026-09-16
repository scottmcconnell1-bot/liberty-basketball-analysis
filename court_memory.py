"""Court memory for a sideline NFHS camera.

Scott: zoom in on live play, zoom out on dead balls, otherwise pan left–right.
Lock the key on a zoomed-out (or FT) view and scale/shift it with pan/zoom.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass
class KeyPolygon:
    """Axis-aligned key in image pixels (lane). Updated as the camera moves."""

    x0: float
    y0: float
    x1: float
    y1: float

    def contains(self, x: float, y: float) -> bool:
        lo_x, hi_x = (self.x0, self.x1) if self.x0 <= self.x1 else (self.x1, self.x0)
        lo_y, hi_y = (self.y0, self.y1) if self.y0 <= self.y1 else (self.y1, self.y0)
        return lo_x <= x <= hi_x and lo_y <= y <= hi_y

    def shifted(self, dx: float, dy: float, scale: float, cx: float, cy: float) -> "KeyPolygon":
        def map_x(x: float) -> float:
            return cx + (x - cx) * scale + dx

        def map_y(y: float) -> float:
            return cy + (y - cy) * scale + dy

        return KeyPolygon(map_x(self.x0), map_y(self.y0), map_x(self.x1), map_y(self.y1))


@dataclass
class FrameCourtMemory:
    baseline_height: float | None = None
    last_median_x: float | None = None
    last_median_h: float | None = None
    key: KeyPolygon | None = None
    zoom: str = "unknown"  # in | out | mid | unknown
    pan_dx: float = 0.0
    dead_ball: bool = False
    recent_heights: list[float] = field(default_factory=list)

    def observe(self, people: Iterable[dict[str, Any]], ball: dict[str, Any] | None = None) -> None:
        boxes = list(people or [])
        heights = [float(p.get("height") or 0) for p in boxes if float(p.get("height") or 0) > 0]
        xs = [float(p.get("x") or p.get("x_center") or 0) for p in boxes]
        median_h = _median(heights) if heights else None
        median_x = _median(xs) if xs else None

        if median_h:
            self.recent_heights.append(median_h)
            self.recent_heights = self.recent_heights[-90:]
            peak = max(self.recent_heights)
            if self.baseline_height is None or peak > self.baseline_height:
                self.baseline_height = peak

        self.pan_dx = 0.0
        if median_x is not None and self.last_median_x is not None:
            self.pan_dx = median_x - self.last_median_x

        scale = 1.0
        if median_h and self.last_median_h:
            scale = median_h / self.last_median_h if self.last_median_h else 1.0

        self.zoom = classify_zoom(median_h, self.baseline_height)
        was_dead = self.dead_ball
        self.dead_ball = self.zoom == "out"
        if self.key is not None and median_x is not None:
            cx = (self.key.x0 + self.key.x1) / 2.0
            cy = (self.key.y0 + self.key.y1) / 2.0
            self.key = self.key.shifted(self.pan_dx, 0.0, scale, cx, cy)

        formation = detect_ft_formation(boxes, ball, abs(self.pan_dx))
        if formation and boxes:
            locked = key_from_people(boxes, ball)
            if locked is not None:
                self.key = locked

        if not was_dead and self.dead_ball and boxes:
            locked = key_from_people(boxes, ball)
            if locked is not None:
                self.key = locked

        self.last_median_x = median_x
        self.last_median_h = median_h

    def in_paint(self, x: float | None, y: float | None) -> bool:
        if self.key is None or x is None or y is None:
            return False
        return self.key.contains(float(x), float(y))


def classify_zoom(median_h: float | None, baseline_h: float | None) -> str:
    if not median_h or not baseline_h:
        return "unknown"
    ratio = median_h / baseline_h
    if ratio <= 0.82:
        return "out"
    if ratio >= 0.95:
        return "in"
    return "mid"


def detect_ft_formation(
    people: list[dict[str, Any]],
    ball: dict[str, Any] | None,
    pan_abs: float,
    pan_max: float = 8.0,
) -> str | None:
    """Lane lined up around the key. Technical = one shooter, empty lane. No pan."""
    if pan_abs > pan_max:
        return None
    n = len(people)
    if n <= 3:
        if n >= 1 and ball is not None:
            return "technical"
        return None
    if n < 6:
        return None
    xs = sorted(float(p.get("x") or p.get("x_center") or 0) for p in people)
    if len(xs) < 6:
        return None
    gaps = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
    max_gap = max(gaps)
    gap_i = gaps.index(max_gap)
    left, right = xs[: gap_i + 1], xs[gap_i + 1 :]
    # Two lines of the lane with a hole down the middle (not a wing outlier).
    if len(left) < 3 or len(right) < 3:
        return None
    span = xs[-1] - xs[0]
    if span <= 0 or max_gap < max(40.0, span * 0.18):
        return None
    return "lane"


def key_from_people(people: list[dict[str, Any]], ball: dict[str, Any] | None) -> KeyPolygon | None:
    xs = [float(p.get("x") or p.get("x_center") or 0) for p in people]
    ys = [float(p.get("y") or p.get("y_center") or 0) for p in people]
    if len(xs) < 4:
        return None
    xs_s = sorted(xs)
    inner = xs_s[1:-1] if len(xs_s) > 4 else xs_s
    x0, x1 = min(inner), max(inner)
    y_top = min(ys)
    y_bot = _median(ys)
    if ball:
        bx = float(ball.get("x") or ball.get("x_center") or (x0 + x1) / 2)
        by = float(ball.get("y") or ball.get("y_center") or y_top)
        x0, x1 = min(x0, bx), max(x1, bx)
        y_top = min(y_top, by)
    if x1 - x0 < 20 or y_bot - y_top < 20:
        return None
    return KeyPolygon(x0, y_top, x1, y_bot)


def people_from_detections(frame_rows) -> list[dict[str, Any]]:
    people = []
    for row in frame_rows:
        cls = str(row.get("class_name") or row.get("object_class") or "")
        if cls not in {"person", "player"}:
            continue
        people.append({
            "x": float(row.get("x_center") or 0),
            "y": float(row.get("y_center") or 0),
            "height": float(row.get("height") or 0),
            "width": float(row.get("width") or 0),
            "player": row.get("cluster_id", row.get("tracker_id")),
        })
    return people


def ball_from_detections(frame_rows) -> dict[str, Any] | None:
    balls = []
    for row in frame_rows:
        cls = str(row.get("class_name") or row.get("object_class") or "")
        if cls in {"ball", "sports ball", "sports_ball"}:
            balls.append({
                "x": float(row.get("x_center") or 0),
                "y": float(row.get("y_center") or 0),
                "confidence": float(row.get("confidence") or 0),
            })
    if not balls:
        return None
    balls.sort(key=lambda b: b["confidence"], reverse=True)
    return balls[0]


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0
