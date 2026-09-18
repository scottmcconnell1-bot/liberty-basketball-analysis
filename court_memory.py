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
    prev_people: list[dict[str, Any]] = field(default_factory=list)
    last_formation: str | None = None
    detected_hoop: tuple[float, float] | None = None
    detected_rim_r: float | None = None

    def observe(self, people: Iterable[dict[str, Any]], ball: dict[str, Any] | None = None) -> None:
        boxes = list(people or [])
        prior = list(self.prev_people)
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

        formation = detect_ft_formation(
            boxes,
            ball,
            abs(self.pan_dx),
            prev_people=prior,
            dead_ball=self.dead_ball,
        )
        self.last_formation = formation
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
        self.prev_people = boxes

    def in_paint(self, x: float | None, y: float | None) -> bool:
        if self.key is None or x is None or y is None:
            return False
        return self.key.contains(float(x), float(y))

    def near_basket(self, x: float | None, y: float | None, x_scale: float = 1.8, y_pad: float = 140.0) -> bool:
        """True when (x, y) is at the hoop, not merely high in the frame.

        Sideline camera: hoop sits at the top-center of the locked key. A pass
        that peaks on the sideline is not a shot even if the ball rose a lot.
        """
        if self.key is None or x is None or y is None:
            return False
        cx = (self.key.x0 + self.key.x1) / 2.0
        half_w = abs(self.key.x1 - self.key.x0) / 2.0 * x_scale
        hoop_y = min(self.key.y0, self.key.y1)
        floor_y = max(self.key.y0, self.key.y1)
        key_h = max(floor_y - hoop_y, 1.0)
        return abs(float(x) - cx) <= half_w and (hoop_y - y_pad) <= float(y) <= (hoop_y + key_h * 0.65)

    def aimed_at_hoop(self, x: float | None, y: float | None, max_dx: float = 780.0) -> bool:
        """Live-shot gate: keep arcs toward this hoop; drop the other end / frame edge.

        Stricter than a high-ball check, looser than near_basket (used for makes).
        """
        if self.key is None or x is None:
            return True
        if float(x) <= 48 or float(x) >= 1872:
            return False
        cx = (self.key.x0 + self.key.x1) / 2.0
        return abs(float(x) - cx) <= max_dx

    def hoop_xy(self) -> tuple[float, float] | None:
        """Rim in image pixels. Pixel detector wins over a key estimate."""
        if self.detected_hoop is not None:
            return self.detected_hoop
        if self.key is None:
            return None
        hoop_x = (self.key.x0 + self.key.x1) / 2.0
        floor_y = max(self.key.y0, self.key.y1)
        line_y = min(self.key.y0, self.key.y1)
        key_h = max(floor_y - line_y, 1.0)
        hoop_y = max(12.0, line_y - 0.4 * key_h)
        return (hoop_x, hoop_y)

    def close_to_rim(self, x: float | None, y: float | None, max_dist: float = 280.0) -> bool:
        """Attempt gate: the ball got near this hoop, not merely high in the frame."""
        hoop = self.hoop_xy()
        if hoop is None or x is None or y is None:
            return False
        dx = float(x) - hoop[0]
        dy = float(y) - hoop[1]
        return (dx * dx + dy * dy) ** 0.5 <= max_dist


def ball_through_rim(
    ball_track,
    peak_frame: int | None,
    hoop: tuple[float, float] | None,
    *,
    rim_r: float = 72.0,
    net_depth: float = 180.0,
    window: int = 24,
) -> bool:
    """True when the ball hits the iron then drops through the same column (the net).

    Sideline camera, sparse YOLO: this is hoop-relative, not 'any high arc'.
    """
    if hoop is None or peak_frame is None or ball_track is None or getattr(ball_track, "empty", True):
        return False
    hoop_x, hoop_y = hoop
    track = ball_track
    window_rows = track[
        (track["frame_number"] >= int(peak_frame) - 2)
        & (track["frame_number"] <= int(peak_frame) + int(window))
    ]
    if getattr(window_rows, "empty", True) or len(window_rows) < 2:
        return False
    at_iron = False
    through = False
    for row in window_rows.sort_values("frame_number").itertuples(index=False):
        x = float(row.x_center)
        y = float(row.y_center)
        dist = ((x - hoop_x) ** 2 + (y - hoop_y) ** 2) ** 0.5
        in_column = abs(x - hoop_x) <= rim_r * 1.15
        if dist <= rim_r and y <= hoop_y + 40:
            at_iron = True
        if at_iron and in_column and (hoop_y + 48) <= y <= (hoop_y + net_depth):
            through = True
            break
    return through


def classify_zoom(median_h: float | None, baseline_h: float | None) -> str:
    if not median_h or not baseline_h:
        return "unknown"
    ratio = median_h / baseline_h
    if ratio <= 0.82:
        return "out"
    if ratio >= 0.95:
        return "in"
    return "mid"


def _person_xy(person: dict[str, Any]) -> tuple[float, float]:
    return (
        float(person.get("x") or person.get("x_center") or 0),
        float(person.get("y") or person.get("y_center") or 0),
    )


def _people_stationary(
    people: list[dict[str, Any]],
    prev_people: list[dict[str, Any]] | None,
    max_dx: float = 22.0,
) -> bool:
    """True when the same bodies barely moved — FT lane is set before the shot."""
    if not people or not prev_people:
        return False
    prev_xy = [_person_xy(p) for p in prev_people]
    if not prev_xy:
        return False
    deltas = []
    for person in people:
        x, y = _person_xy(person)
        nearest = min((x - px) ** 2 + (y - py) ** 2 for px, py in prev_xy)
        deltas.append(nearest ** 0.5)
    if not deltas:
        return False
    ordered = sorted(deltas)
    mid = ordered[len(ordered) // 2]
    return mid <= max_dx


def _on_court_people(
    people: list[dict[str, Any]],
    frame_w: float = 1920.0,
    margin: float = 48.0,
    min_height: float = 36.0,
) -> list[dict[str, Any]]:
    """Drop YOLO boxes glued to the frame edge (score table / huddle)."""
    kept = []
    for person in people or []:
        x, _y = _person_xy(person)
        height = float(person.get("height") or 0)
        if x <= margin or x >= frame_w - margin:
            continue
        if height and height < min_height:
            continue
        kept.append(person)
    return kept


def detect_ft_formation(
    people: list[dict[str, Any]],
    ball: dict[str, Any] | None,
    pan_abs: float,
    pan_max: float = 8.0,
    prev_people: list[dict[str, Any]] | None = None,
    dead_ball: bool = False,
) -> str | None:
    """NFHS FT from how the floor looks, not from the ball arc.

    Lane: players lined up on both sides of the key, stationary to start,
    shooter at the top of the key. Camera is not panning.

    Technical: one player at the top of the key, nobody else near the shooter.
    """
    if pan_abs > pan_max:
        return None
    people = _on_court_people(people)
    pts = [_person_xy(p) for p in (people or [])]
    if not pts:
        return None
    prev_people = _on_court_people(prev_people or [])
    prior_n = len(prev_people)
    stationary = _people_stationary(people, prev_people)
    # Technical is a whistle isolation, not a zoom-in on a live drive.
    if prior_n < 5 and _is_technical_ft(pts, ball, set_piece=bool(dead_ball)):
        return "technical"
    if not (dead_ball or stationary):
        return None
    return "lane" if _is_lane_ft(pts, ball) else None


def _ball_xy(ball: dict[str, Any] | None) -> tuple[float, float] | None:
    if not ball:
        return None
    return (
        float(ball.get("x") or ball.get("x_center") or 0),
        float(ball.get("y") or ball.get("y_center") or 0),
    )


def _is_technical_ft(
    pts: list[tuple[float, float]],
    ball: dict[str, Any] | None,
    set_piece: bool,
    clearance: float = 110.0,
) -> bool:
    """One shooter at the line; empty lane. Live ISO is not a technical."""
    if not set_piece or len(pts) > 2:
        return False
    shooter = _shooter_xy(pts, ball)
    if shooter is None:
        return False
    sx, sy = shooter
    for x, y in pts:
        if abs(x - sx) < 1 and abs(y - sy) < 1:
            continue
        if ((x - sx) ** 2 + (y - sy) ** 2) ** 0.5 < clearance:
            return False
    return True


def _shooter_xy(
    pts: list[tuple[float, float]],
    ball: dict[str, Any] | None,
) -> tuple[float, float] | None:
    if not pts:
        return None
    bxy = _ball_xy(ball)
    if bxy is not None:
        bx, by = bxy
        return min(pts, key=lambda p: (p[0] - bx) ** 2 + (p[1] - by) ** 2)
    # Top of the key is toward the basket (smaller y in this sideline crop).
    return min(pts, key=lambda p: p[1])


def _is_lane_ft(pts: list[tuple[float, float]], ball: dict[str, Any] | None) -> bool:
    """Two walls of the lane plus a shooter at the top of the key."""
    if len(pts) < 5:
        return False
    bxy = _ball_xy(ball)
    cx = bxy[0] if bxy is not None else _median([p[0] for p in pts])
    left = [p for p in pts if p[0] < cx - 28]
    right = [p for p in pts if p[0] > cx + 28]
    if len(left) < 2 or len(right) < 2:
        return False
    shooter = _shooter_xy(pts, ball)
    if shooter is None:
        return False
    sx, sy = shooter
    # Shooter stands in the gap / at the line, not as a third body on one wall.
    on_left_wall = sum(1 for p in left if abs(p[0] - sx) < 20) >= 2
    on_right_wall = sum(1 for p in right if abs(p[0] - sx) < 20) >= 2
    if on_left_wall or on_right_wall:
        return False
    # Top of the key: shooter is on the high side of the lane cluster (FT line).
    lane_ys = [p[1] for p in left + right]
    if not lane_ys:
        return False
    lane_mid_y = _median(lane_ys)
    if sy > lane_mid_y + 50:
        return False
    span = max(p[0] for p in pts) - min(p[0] for p in pts)
    if span < 80:
        return False
    return True


def key_from_people(people: list[dict[str, Any]], ball: dict[str, Any] | None) -> KeyPolygon | None:
    people = _on_court_people(people)
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
