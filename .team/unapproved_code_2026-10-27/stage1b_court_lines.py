#!/usr/bin/env python3
"""Stage 1b: per-frame painted court-line detection and NFHS model fit.

New code only.  The script reads a YAML config whose thresholds were frozen on
separate calibration frames (>= 60 s from every measurement frame), measures
each requested frame once, and writes overlays, per-frame JSON, per-game
summaries, and a measurement report under ``.team/stage1b_lines``.

No interpolation, no temporal smoothing, no tracking, no learned model.
"""
from __future__ import annotations

import argparse
import itertools
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Config and small helpers


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def round_or_none(value: Optional[float], places: int = 3) -> Optional[float]:
    if value is None:
        return None
    if not math.isfinite(float(value)):
        return None
    return round(float(value), places)


def jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jsonable(payload), indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Paint segmentation


def _floor_mask(frame: np.ndarray, cfg: Dict[str, Any]) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    low = np.array(cfg["detection"]["floor_hsv_low"], dtype=np.uint8)
    high = np.array(cfg["detection"]["floor_hsv_high"], dtype=np.uint8)
    floor = cv2.inRange(hsv, low, high)
    k = int(cfg["detection"]["floor_close_kernel_px"])
    d = int(cfg["detection"]["floor_dilate_kernel_px"])
    floor = cv2.morphologyEx(
        floor, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)),
    )
    floor = cv2.dilate(
        floor, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (d, d))
    )
    if cfg["detection"].get("floor_keep_bottom_components", True):
        n, labels, stats, _centroids = cv2.connectedComponentsWithStats(
            floor, 8)
        keep = np.zeros(n, dtype=bool)
        bottom = floor[-1, :] > 0
        h, w = floor.shape[:2]
        for label in range(1, n):
            area = stats[label, cv2.CC_STAT_AREA]
            if area < 0.02 * h * w:
                continue
            columns = np.nonzero(labels[-1, :] == label)[0]
            if bottom[columns].any():
                keep[label] = True
        if keep.any():
            floor = np.where(keep[labels], 255, 0).astype(np.uint8)
    if cfg["detection"].get("floor_use_convex_hull", True):
        contours, _ = cv2.findContours(
            floor, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            hull = cv2.convexHull(largest)
            region = np.zeros_like(floor)
            cv2.fillConvexPoly(region, hull, 255)
            # A hull around a nearly full-frame floor is still useful, but do
            # not let one stray bottom component swallow the whole image.
            if np.count_nonzero(region) > 0.15 * floor.size:
                floor = region
    return floor


def floor_region_mask(frame: np.ndarray, cfg: Dict[str, Any]) -> np.ndarray:
    """Wood-coloured floor region, used only to reject wall/bleacher fits."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    low = np.array(cfg["detection"]["floor_hsv_low"], dtype=np.uint8)
    high = np.array(cfg["detection"]["floor_hsv_high"], dtype=np.uint8)
    floor = cv2.inRange(hsv, low, high)
    floor = cv2.morphologyEx(
        floor, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    floor = cv2.dilate(
        floor, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    n, labels, stats, _centroids = cv2.connectedComponentsWithStats(floor, 8)
    keep = np.zeros(n, dtype=bool)
    h, w = floor.shape[:2]
    for label in range(1, n):
        if stats[label, cv2.CC_STAT_AREA] < 0.02 * h * w:
            continue
        if np.any(labels[-1, :] == label):
            keep[label] = True
    if keep.any():
        floor = np.where(keep[labels], 255, 0).astype(np.uint8)
    return floor


def build_paint_mask(frame: np.ndarray, gym: str, cfg: Dict[str, Any]) -> np.ndarray:
    """Return a binary mask of painted court lines on the wooden floor."""
    det = cfg["detection"]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    floor = _floor_mask(frame, cfg)
    k = int(det["thin_line_kernel_px"])
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))

    if gym == "liberty":
        spec = det["liberty"]
        paint = np.zeros_like(gray)
        for lo, hi in spec["red_hsv_ranges"]:
            paint = cv2.bitwise_or(
                paint,
                cv2.inRange(hsv, np.array(lo, dtype=np.uint8),
                            np.array(hi, dtype=np.uint8)),
            )
        if spec.get("use_blue", False):
            lo, hi = spec["blue_hsv_range"]
            paint = cv2.bitwise_or(
                paint,
                cv2.inRange(hsv, np.array(lo, dtype=np.uint8),
                            np.array(hi, dtype=np.uint8)),
            )
        paint = cv2.bitwise_and(paint, floor)
        if spec.get("use_tophat", False):
            # Keep thin painted lines; drop large solid colour blobs.
            mask = cv2.morphologyEx(paint, cv2.MORPH_TOPHAT, ker)
        else:
            mask = paint
    else:
        spec = det["adrian"]
        mask = np.zeros_like(gray)
        if spec.get("use_white_tophat", True):
            white_k = cv2.getStructuringElement(cv2.MORPH_RECT, (17, 17))
            top = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, white_k)
            light = ((top > int(spec["white_tophat_threshold"])) &
                     (floor > 0)).astype(np.uint8) * 255
            mask = cv2.bitwise_or(mask, light)
        if spec.get("use_dark_line", True):
            black_k = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
            bottom = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, black_k)
            dark = ((bottom > int(spec["dark_blackhat_threshold"])) &
                    (floor > 0)).astype(np.uint8) * 255
            mask = cv2.bitwise_or(mask, dark)

    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return mask


# ---------------------------------------------------------------------------
# Line extraction


def _line_params(p1: Tuple[float, float], p2: Tuple[float, float]):
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    length = float(math.hypot(dx, dy))
    if length < 1e-6:
        return None
    a, b = -dy / length, dx / length
    c = -(a * x1 + b * y1)
    return np.array([a, b, c], dtype=np.float64), length


def extract_lines(mask: np.ndarray, cfg: Dict[str, Any], scale: float
                  ) -> List[Dict[str, Any]]:
    det = cfg["detection"]
    edges = cv2.Canny(mask, int(det["canny_low"]), int(det["canny_high"]))
    min_len = max(12, int(round(det["hough_min_line_length_px_at_1280"] * scale)))
    max_gap = max(4, int(round(det["hough_max_line_gap_px_at_1280"] * scale)))
    raw_lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180.0,
        threshold=int(det["hough_threshold"]),
        minLineLength=min_len,
        maxLineGap=max_gap,
    )
    if raw_lines is None:
        return []

    raw: List[Dict[str, Any]] = []
    for line in raw_lines.reshape(-1, 4):
        p1 = (float(line[0]), float(line[1]))
        p2 = (float(line[2]), float(line[3]))
        params = _line_params(p1, p2)
        if params is None:
            continue
        normal, length = params
        raw.append({"p1": p1, "p2": p2, "n": normal, "len": length})
    raw.sort(key=lambda item: -item["len"])
    # Merging is quadratic; keep a generous pool of the longest segments.
    raw = raw[: max(200, int(det["max_lines_per_frame"]) * 20)]

    max_angle = float(det["merge_max_angle_deg"])
    max_offset = float(det["merge_max_offset_px"])
    max_gap_merge = float(det["merge_max_gap_px"])

    merged: List[Dict[str, Any]] = []
    for item in raw:
        placed = False
        normal = item["n"]
        angle = math.degrees(math.atan2(normal[1], normal[0])) % 180.0
        for current in merged:
            current_angle = math.degrees(
                math.atan2(current["n"][1], current["n"][0])
            ) % 180.0
            delta = abs(angle - current_angle)
            delta = min(delta, 180.0 - delta)
            if delta > max_angle:
                continue
            d1 = abs(current["n"] @ np.array(
                [item["p1"][0], item["p1"][1], 1.0]))
            d2 = abs(current["n"] @ np.array(
                [item["p2"][0], item["p2"][1], 1.0]))
            if max(d1, d2) > max_offset:
                continue
            direction = np.array([-current["n"][1], current["n"][0]])
            current_t = np.sort([current["p1"] @ direction,
                                 current["p2"] @ direction])
            item_t = np.sort([item["p1"] @ direction,
                              item["p2"] @ direction])
            gap = max(item_t[0] - current_t[1], current_t[0] - item_t[1], 0.0)
            if gap > max_gap_merge:
                continue
            points = np.array([current["p1"], current["p2"],
                               item["p1"], item["p2"]])
            order = np.argsort(points @ direction)
            low, high = points[order[0]], points[order[-1]]
            new_len = float(np.linalg.norm(high - low))
            if new_len < current["len"]:
                continue
            current["p1"] = tuple(low)
            current["p2"] = tuple(high)
            current["len"] = new_len
            placed = True
            break
        if not placed:
            merged.append(dict(item))

    merged = [item for item in merged if item["len"] >= min_len]
    merged.sort(key=lambda item: -item["len"])
    return merged[: int(det["max_lines_per_frame"])]


def line_intersection(n1: np.ndarray, n2: np.ndarray
                      ) -> Optional[Tuple[float, float]]:
    point = np.cross(n1, n2)
    if abs(point[2]) < 1e-10:
        return None
    return float(point[0] / point[2]), float(point[1] / point[2])


def homography_dlt_condition(H_img2court: np.ndarray,
                             image_points: np.ndarray,
                             court_points: np.ndarray) -> Optional[float]:
    """Condition number of the normalised four-point DLT system.

    The singular-value ratio of a projectivity itself is coordinate-system
    dependent and is routinely >1e4 for a perfectly valid image-to-feet
    homography.  The DLT condition is the numerically meaningful stability
    measure for the system that was solved.
    """
    if H_img2court is None or image_points is None or court_points is None:
        return None
    if len(image_points) != 4 or len(court_points) != 4:
        return None

    def normalise(points: np.ndarray):
        points = np.asarray(points, dtype=np.float64)
        centre = points.mean(axis=0)
        dist = np.sqrt(((points - centre) ** 2).sum(axis=1)).mean()
        if not math.isfinite(dist) or dist < 1e-9:
            return None
        scale = math.sqrt(2.0) / dist
        T = np.array([[scale, 0.0, -scale * centre[0]],
                      [0.0, scale, -scale * centre[1]],
                      [0.0, 0.0, 1.0]], dtype=np.float64)
        return (points - centre) * scale

    src = normalise(image_points)
    dst = normalise(court_points)
    if src is None or dst is None:
        return None
    rows = []
    for (x, y), (u, v) in zip(src, dst):
        rows.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y, -u])
        rows.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y, -v])
    singular = np.linalg.svd(np.asarray(rows), compute_uv=False)
    if len(singular) < 8 or singular[-2] <= 1e-12:
        return None
    return float(singular[0] / singular[-2])


# ---------------------------------------------------------------------------
# Court model and scoring


class CourtModel:
    def __init__(self, cfg: Dict[str, Any]):
        court = cfg["court"]
        self.base_y = -as_float(court["hoop_to_baseline_ft"])
        self.ft_y = as_float(court["ft_line_y_ft"])
        self.lane_x = as_float(court["lane_half_width_ft"])
        self.arc_r = as_float(court["three_point_radius_ft"])
        self.ft_circle_r = as_float(court["ft_circle_radius_ft"])
        self.corners = np.array(
            [[-self.lane_x, self.base_y], [self.lane_x, self.base_y],
             [self.lane_x, self.ft_y], [-self.lane_x, self.ft_y]],
            dtype=np.float64,
        )
        self.structures = self._make_structures()

    def _seg(self, x1, y1, x2, y2, n):
        return [(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
                for t in np.linspace(0.0, 1.0, n)]

    def _make_structures(self):
        arc = [(self.arc_r * math.cos(a), self.arc_r * math.sin(a))
               for a in np.linspace(math.radians(25.0),
                                    math.radians(155.0), 45)]
        ft_circle = [(self.ft_circle_r * math.cos(a),
                      self.ft_y + self.ft_circle_r * math.sin(a))
                     for a in np.linspace(0.0, 2.0 * math.pi, 45,
                                          endpoint=False)]
        return {
            "left_lane": self._seg(-self.lane_x, self.base_y,
                                   -self.lane_x, self.ft_y, 14),
            "right_lane": self._seg(self.lane_x, self.base_y,
                                    self.lane_x, self.ft_y, 14),
            "baseline": self._seg(-self.lane_x, self.base_y,
                                  self.lane_x, self.base_y, 14),
            "ft_line": self._seg(-self.lane_x, self.ft_y,
                                 self.lane_x, self.ft_y, 14),
            "three_pt_arc": arc,
            "ft_circle": ft_circle,
        }

    def project(self, H_img2court: np.ndarray, points: Sequence
                ) -> Tuple[np.ndarray, np.ndarray]:
        """Project court points to image using the inverse homography."""
        H_court2img = np.linalg.inv(H_img2court)
        pts = np.asarray(points, dtype=np.float64)
        hom = (H_court2img @ np.c_[pts, np.ones(len(pts))].T).T
        z = hom[:, 2]
        ok = np.abs(z) > 1e-9
        uv = hom[:, :2] / np.where(ok, z, 1.0)[:, None]
        return uv, ok


def _image_coverage(uv: np.ndarray, ok: np.ndarray, dist: np.ndarray,
                    shape: Tuple[int, int], inlier_px: float,
                    min_visible: int) -> Tuple[float, float, int, np.ndarray]:
    h, w = shape
    inside = ((uv[:, 0] >= 0) & (uv[:, 0] < w) &
              (uv[:, 1] >= 0) & (uv[:, 1] < h) & ok)
    count = int(inside.sum())
    if count == 0:
        return 0.0, 999.0, 0, np.array([], dtype=np.float64)
    xs = np.clip(uv[inside, 0].astype(int), 0, w - 1)
    ys = np.clip(uv[inside, 1].astype(int), 0, h - 1)
    d = dist[ys, xs]
    if count < min_visible:
        return 0.0, float(np.mean(d)), count, d
    return float(np.mean(d <= inlier_px)), float(np.mean(d)), count, d


def evaluate_homography(H_img2court: np.ndarray, dist: np.ndarray,
                        shape: Tuple[int, int], model: CourtModel,
                        cfg: Dict[str, Any],
                        floor_dist: Optional[np.ndarray] = None
                        ) -> Optional[Dict[str, Any]]:
    scoring = cfg["scoring"]
    h, w = shape
    image_area = float(h * w)

    try:
        H_court2img = np.linalg.inv(H_img2court)
    except np.linalg.LinAlgError:
        return None
    hom_corners = (H_court2img @ np.c_[model.corners, np.ones(4)].T).T
    z_corners = hom_corners[:, 2]
    if np.any(np.abs(z_corners) < 1e-9):
        return None
    image_corners = hom_corners[:, :2] / z_corners[:, None]
    if not np.all(np.isfinite(image_corners)):
        return None

    condition = homography_dlt_condition(
        H_img2court, image_corners, model.corners)
    if condition is None or not math.isfinite(condition) or condition > float(
            cfg["detection"]["max_condition_number"]):
        return None

    uv_corners = image_corners
    lane_area = abs(cv2.contourArea(uv_corners.astype(np.float32)))
    frac = lane_area / image_area
    if frac < float(scoring["min_lane_area_fraction"]):
        return None
    if frac > float(scoring["max_lane_area_fraction"]):
        return None

    inlier_px = float(scoring["inlier_distance_px"])
    min_visible = int(scoring["min_visible_samples"])
    weights = scoring["weights"]

    coverages: Dict[str, float] = {}
    distances: List[np.ndarray] = []
    visible: Dict[str, int] = {}
    for name, points in model.structures.items():
        uv, ok = model.project(H_img2court, points)
        cov, _mean, count, d = _image_coverage(
            uv, ok, dist, shape, inlier_px, min_visible)
        coverages[name] = cov
        visible[name] = count
        if d.size:
            distances.append(d)

    strong = [name for name, cov in coverages.items()
              if cov >= float(scoring["min_structure_coverage"])]
    if len(strong) < int(scoring["min_strong_structures"]):
        return None

    line_names = {"left_lane", "right_lane", "baseline", "ft_line"}
    line_inliers = sum(1 for name in line_names
                       if coverages[name] >= float(
                           scoring["min_structure_coverage"]))
    if line_inliers < int(scoring["min_inlier_lines"]):
        return None

    floor_coverage = None
    if floor_dist is not None:
        floor_tol = float(scoring["floor_distance_px"])
        floor_values = []
        for name, points in model.structures.items():
            if name not in ("left_lane", "right_lane", "baseline", "ft_line"):
                continue
            uv, ok = model.project(H_img2court, points)
            inside = ((uv[:, 0] >= 0) & (uv[:, 0] < w) &
                      (uv[:, 1] >= 0) & (uv[:, 1] < h) & ok)
            if int(inside.sum()) < min_visible:
                continue
            xs = np.clip(uv[inside, 0].astype(int), 0, w - 1)
            ys = np.clip(uv[inside, 1].astype(int), 0, h - 1)
            floor_values.append(float(np.mean(floor_dist[ys, xs] <= floor_tol)))
        if floor_values:
            floor_coverage = float(np.mean(floor_values))
            if floor_coverage < float(scoring["min_floor_coverage"]):
                return None
        else:
            return None

    # The half-court model extends from the rim toward the camera; in these
    # fixed views the lane centre must be lower in the image than the rim.
    hoop_hom = H_court2img @ np.array([0.0, 0.0, 1.0])
    if abs(hoop_hom[2]) > 1e-9:
        hoop_img = hoop_hom[:2] / hoop_hom[2]
        lane_centre = uv_corners.mean(axis=0)
        if lane_centre[1] <= hoop_img[1] + float(
                scoring["min_lane_centre_below_hoop_px"]):
            return None

    if distances:
        all_dist = np.concatenate(distances)
        median_error = float(np.median(all_dist))
        mean_error = float(np.mean(all_dist))
    else:
        median_error = float("inf")
        mean_error = float("inf")
    if median_error > float(scoring["min_median_reprojection_px"]):
        return None

    numerator = 0.0
    denominator = 0.0
    for name, cov in coverages.items():
        weight = float(weights.get(name, 1.0))
        numerator += weight * cov
        denominator += weight
    coverage = numerator / denominator if denominator else 0.0
    score = coverage - 0.004 * mean_error

    return {
        "score": float(score),
        "coverage": float(coverage),
        "median_error_px": median_error,
        "mean_error_px": mean_error,
        "lane_area_fraction": float(frac),
        "coverages": coverages,
        "visible": visible,
        "line_inliers": int(line_inliers),
        "strong_structures": len(strong),
        "condition_number": condition,
        "floor_coverage": floor_coverage,
    }


# ---------------------------------------------------------------------------
# Candidate homographies


def _candidate_from_four_lines(lines: List[Dict[str, Any]],
                               lanes: Tuple[int, int],
                               cross: Tuple[int, int],
                               corners: np.ndarray
                               ) -> Optional[np.ndarray]:
    n_l1 = lines[lanes[0]]["n"]
    n_l2 = lines[lanes[1]]["n"]
    n_b = lines[cross[0]]["n"]
    n_f = lines[cross[1]]["n"]
    p_lb = line_intersection(n_l1, n_b)
    p_rb = line_intersection(n_l2, n_b)
    p_rf = line_intersection(n_l2, n_f)
    p_lf = line_intersection(n_l1, n_f)
    if any(p is None for p in (p_lb, p_rb, p_rf, p_lf)):
        return None
    src = np.array([p_lb, p_rb, p_rf, p_lf], dtype=np.float64)
    if not np.all(np.isfinite(src)):
        return None
    if not cv2.isContourConvex(src.reshape(-1, 1, 2).astype(np.float32)):
        return None
    H = cv2.getPerspectiveTransform(
        src.astype(np.float32), corners.astype(np.float32)
    ).astype(np.float64)
    try:
        singular = np.linalg.svd(H, compute_uv=False)
    except np.linalg.LinAlgError:
        return None
    if singular[-1] <= 0:
        return None
    return H


def generate_candidates(lines: List[Dict[str, Any]], model: CourtModel,
                        cfg: Dict[str, Any], shape: Tuple[int, int]
                        ) -> Iterable[Tuple[np.ndarray, Tuple[int, int, int, int]]]:
    if len(lines) < 4:
        return
    det = cfg["detection"]
    h, w = shape
    image_area = float(h * w)
    min_area = image_area * 0.0005
    max_area = image_area * 1.5

    angles = []
    for line in lines:
        normal = line["n"]
        angles.append(math.degrees(math.atan2(normal[1], normal[0])) % 180.0)

    # 1. Pair-of-pairs candidates: lines that are nearly parallel in the image
    #    are candidate lanes / cross lines.  The correspondence is decided by
    #    the score, not by colour.
    pairs: List[Tuple[int, int]] = []
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            delta = abs(angles[i] - angles[j])
            delta = min(delta, 180.0 - delta)
            if delta > 40.0:
                continue
            offset = abs(lines[i]["n"] @ np.array(
                [lines[j]["p1"][0], lines[j]["p1"][1], 1.0]))
            if offset > 10.0:
                pairs.append((i, j))
    pairs.sort(key=lambda ij: -(lines[ij[0]]["len"] + lines[ij[1]]["len"]))
    pairs = pairs[: int(det["max_parallel_pairs"])]

    yield from _yield_from_pairs(lines, pairs, angles, model.corners,
                                 min_area, max_area)

    # 2. Exhaustive quadruples of the longest lines, all 24 role assignments.
    top = lines[: int(det["exhaustive_top_lines"])]
    for quad in itertools.combinations(range(len(top)), 4):
        for lanes in itertools.combinations(quad, 2):
            cross = tuple(k for k in quad if k not in lanes)
            for lane_order in (lanes, lanes[::-1]):
                for cross_order in (cross, cross[::-1]):
                    H = _candidate_from_four_lines(
                        top, lane_order, cross_order, model.corners)
                    if H is None:
                        continue
                    try:
                        H_court2img = np.linalg.inv(H)
                    except np.linalg.LinAlgError:
                        continue
                    hom = (H_court2img @ np.c_[
                        model.corners, np.ones(4)].T).T
                    z = hom[:, 2]
                    if np.any(np.abs(z) < 1e-9):
                        continue
                    uv = hom[:, :2] / z[:, None]
                    if not np.all(np.isfinite(uv)):
                        continue
                    area = abs(cv2.contourArea(uv.astype(np.float32)))
                    if min_area <= area <= max_area:
                        yield H, (lane_order[0], lane_order[1],
                                  cross_order[0], cross_order[1])


def _yield_from_pairs(lines, pairs, angles, corners, min_area, max_area):
    for ai in range(len(pairs)):
        first = pairs[ai]
        for bi in range(ai + 1, len(pairs)):
            second = pairs[bi]
            if len(set(first + second)) < 4:
                continue
            delta = abs(np.mean([angles[first[0]], angles[first[1]]]) -
                        np.mean([angles[second[0]], angles[second[1]]]))
            delta = min(delta, 180.0 - delta)
            if delta < 15.0:
                continue
            for lanes, cross in ((first, second), (second, first)):
                for lane_order in (lanes, lanes[::-1]):
                    for cross_order in (cross, cross[::-1]):
                        H = _candidate_from_four_lines(
                            lines, lane_order, cross_order, corners)
                        if H is None:
                            continue
                        try:
                            H_court2img = np.linalg.inv(H)
                        except np.linalg.LinAlgError:
                            continue
                        hom = (H_court2img @ np.c_[
                            corners, np.ones(4)].T).T
                        z = hom[:, 2]
                        if np.any(np.abs(z) < 1e-9):
                            continue
                        uv = hom[:, :2] / z[:, None]
                        if not np.all(np.isfinite(uv)):
                            continue
                        area = abs(cv2.contourArea(uv.astype(np.float32)))
                        if min_area <= area <= max_area:
                            yield H, (lane_order[0], lane_order[1],
                                      cross_order[0], cross_order[1])


# ---------------------------------------------------------------------------
# Post-fit measurements


def _line_at_court_coord(model: CourtModel, H_img2court: np.ndarray,
                         dist: np.ndarray, shape: Tuple[int, int],
                         axis: str, value: float, coordinate_min: float,
                         coordinate_max: float, samples: int,
                         inlier_px: float, min_visible: int
                         ) -> Tuple[float, float, int]:
    if axis == "y":
        points = [(value, t) for t in np.linspace(
            coordinate_min, coordinate_max, samples)]
    else:
        points = [(t, value) for t in np.linspace(
            coordinate_min, coordinate_max, samples)]
    uv, ok = model.project(H_img2court, points)
    cov, _mean, count, _d = _image_coverage(
        uv, ok, dist, shape, inlier_px, min_visible)
    return cov, _mean, count


def measure_center_line(model: CourtModel, H_img2court: np.ndarray,
                        dist: np.ndarray, shape: Tuple[int, int],
                        cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    spec = cfg["center_line"]
    inlier_px = float(cfg["scoring"]["inlier_distance_px"])
    best = None
    y_values = np.arange(
        float(spec["search_min_y_ft"]),
        float(spec["search_max_y_ft"]) + 1e-9,
        float(spec["search_step_ft"]),
    )
    for y in y_values:
        cov, mean, count = _line_at_court_coord(
            model, H_img2court, dist, shape, "y", float(y),
            float(spec["sample_x_min_ft"]), float(spec["sample_x_max_ft"]),
            int(spec["samples"]), inlier_px,
            int(spec["min_visible_samples"]),
        )
        if count < int(spec["min_visible_samples"]):
            continue
        score = cov - 0.002 * mean
        if best is None or score > best[0]:
            best = (score, float(y), cov, count)
    if best is None or best[2] < float(spec["min_coverage"]):
        return None
    return {"y_ft": best[1], "coverage": best[2],
            "visible_samples": best[3]}


def measure_sidelines(model: CourtModel, H_img2court: np.ndarray,
                      dist: np.ndarray, shape: Tuple[int, int],
                      cfg: Dict[str, Any]) -> Dict[str, Any]:
    spec = cfg["sideline"]
    inlier_px = float(cfg["scoring"]["inlier_distance_px"])
    center = measure_center_line(model, H_img2court, dist, shape, cfg)
    y_max = center["y_ft"] if center is not None else 46.0
    y_min = model.base_y
    results: Dict[str, Any] = {}
    for sign, key in ((-1.0, "left"), (1.0, "right")):
        best = None
        for half_width in np.arange(
                float(spec["search_half_width_min_ft"]),
                float(spec["search_half_width_max_ft"]) + 1e-9,
                float(spec["search_step_ft"])):
            x = sign * float(half_width)
            cov, mean, count = _line_at_court_coord(
                model, H_img2court, dist, shape, "x", x, y_min, y_max,
                int(spec["samples"]), inlier_px,
                int(spec["min_visible_samples"]),
            )
            if count < int(spec["min_visible_samples"]):
                continue
            score = cov - 0.002 * mean
            if best is None or score > best[0]:
                best = (score, float(half_width), cov, count)
        if best is not None and best[2] >= float(spec["min_coverage"]):
            results[key] = {"half_width_ft": best[1],
                            "coverage": best[2],
                            "visible_samples": best[3]}
        else:
            results[key] = None
    return results


# ---------------------------------------------------------------------------
# Per-frame analysis


def analyze_frame(frame: np.ndarray, gym: str, model: CourtModel,
                  cfg: Dict[str, Any]) -> Dict[str, Any]:
    h, w = frame.shape[:2]
    scale = max(h, w) / 1280.0
    mask = build_paint_mask(frame, gym, cfg)
    lines = extract_lines(mask, cfg, scale)
    dist = cv2.distanceTransform(255 - mask, cv2.DIST_L2, 5)
    floor_dist = cv2.distanceTransform(
        255 - floor_region_mask(frame, cfg), cv2.DIST_L2, 5)

    best: Optional[Dict[str, Any]] = None
    for H, ids in generate_candidates(lines, model, cfg, (h, w)):
        evaluation = evaluate_homography(
            H, dist, (h, w), model, cfg, floor_dist)
        if evaluation is None:
            continue
        if best is None or evaluation["score"] > best["evaluation"]["score"]:
            best = {"H": H, "ids": ids, "evaluation": evaluation}
        # Bound the search so a single frame cannot run for minutes.
        if best is not None and evaluation["score"] > 0.98:
            break

    result: Dict[str, Any] = {
        "mask": mask,
        "lines": lines,
        "dist": dist,
        "homography": None,
        "evaluation": None,
        "center_line": None,
        "sidelines": {k: None for k in ("left", "right")},
        "valid": False,
    }
    if best is None:
        return result

    H = best["H"]
    evaluation = best["evaluation"]
    result["homography"] = H
    result["evaluation"] = evaluation

    center_line = measure_center_line(model, H, dist, (h, w), cfg)
    result["center_line"] = center_line
    result["sidelines"] = measure_sidelines(model, H, dist, (h, w), cfg)

    half_court_y = center_line["y_ft"] if center_line is not None else None
    if half_court_y is not None:
        low = float(cfg["court"]["plausible_half_court_y_min_ft"])
        high = float(cfg["court"]["plausible_half_court_y_max_ft"])
        if not (low <= half_court_y <= high):
            result["valid"] = False
            return result
    result["valid"] = True
    return result


def court_length_from_half_court(half_court_y: Optional[float],
                                 baseline_offset: float) -> Optional[float]:
    if half_court_y is None:
        return None
    return 2.0 * (float(half_court_y) + float(baseline_offset))


# ---------------------------------------------------------------------------
# Overlay and JSON writers


def draw_overlay(frame: np.ndarray, model: CourtModel, H_img2court: np.ndarray,
                 result: Dict[str, Any], game: str, frame_idx: int,
                 timestamp_ms: int, half_court_y: Optional[float],
                 half_widths: Dict[str, Optional[float]]) -> np.ndarray:
    out = frame.copy()
    dist = result["dist"]
    h, w = out.shape[:2]

    # Detected line segments, thin cyan.
    for line in result["lines"]:
        p1 = tuple(int(round(v)) for v in line["p1"])
        p2 = tuple(int(round(v)) for v in line["p2"])
        cv2.line(out, p1, p2, (255, 255, 0), 1, cv2.LINE_AA)

    def draw_structure(points, colour, thickness):
        uv, ok = model.project(H_img2court, points)
        pts = []
        for (x, y), is_ok in zip(uv, ok):
            if is_ok and -w <= x <= 2 * w and -h <= y <= 2 * h:
                pts.append([int(round(x)), int(round(y))])
        if len(pts) >= 2:
            cv2.polylines(out, [np.array(pts, dtype=np.int32)], False,
                          colour, thickness, cv2.LINE_AA)

    draw_structure(model.structures["baseline"], (0, 0, 255), 2)
    draw_structure(model.structures["left_lane"], (0, 255, 0), 2)
    draw_structure(model.structures["right_lane"], (0, 255, 0), 2)
    draw_structure(model.structures["ft_line"], (255, 0, 0), 2)
    draw_structure(model.structures["ft_circle"], (255, 0, 0), 2)
    draw_structure(model.structures["three_pt_arc"], (0, 255, 255), 2)

    if half_court_y is not None:
        center_points = [(-25.0, half_court_y), (25.0, half_court_y)]
        draw_structure(center_points, (255, 0, 255), 2)
    for side, value in half_widths.items():
        if value is None:
            continue
        x = -value if side == "left" else value
        side_points = [(x, model.base_y), (x, half_court_y or 46.0)]
        draw_structure(side_points, (0, 128, 255), 1)

    # Inlier segments (model structures) are already drawn; mark detected
    # segments that lie close to the model in thick green.
    if result["evaluation"] is not None:
        inlier_px = 2.5
        for line in result["lines"]:
            midpoint = np.array(line["p1"]) * 0.5 + np.array(line["p2"]) * 0.5
            # map midpoint to court and back; a cheap inlier check is the
            # mask distance at the segment endpoints.
            p1 = np.clip(line["p1"], (0, 0), (w - 1, h - 1)).astype(int)
            p2 = np.clip(line["p2"], (0, 0), (w - 1, h - 1)).astype(int)
            if (dist[p1[1], p1[0]] <= inlier_px and
                    dist[p2[1], p2[0]] <= inlier_px):
                cv2.line(out, tuple(p1), tuple(p2), (0, 255, 0), 2,
                         cv2.LINE_AA)

    # Hoop centre (floor projection of the rim centre).
    hoop = np.linalg.inv(H_img2court) @ np.array([0.0, 0.0, 1.0])
    if abs(hoop[2]) > 1e-9:
        hx, hy = hoop[0] / hoop[2], hoop[1] / hoop[2]
        if 0 <= hx < w and 0 <= hy < h:
            cv2.drawMarker(out, (int(hx), int(hy)), (255, 255, 255),
                           cv2.MARKER_CROSS, 14, 2)

    ev = result["evaluation"]
    n_lines = 0
    if ev is not None:
        n_lines = sum(1 for name in ("left_lane", "right_lane", "baseline",
                                     "ft_line")
                      if ev["coverages"][name] >= 0.4)
    lines_found = len(result["lines"])
    fit_error = ev["median_error_px"] if ev is not None else None
    success = result["valid"]
    hc_text = f"{half_court_y:.2f}" if half_court_y is not None else "N/A"
    hw_values = [v for v in half_widths.values() if v is not None]
    hw_text = f"{max(hw_values):.2f}" if hw_values else "N/A"
    header = (f"{game} | frame {frame_idx} | t={timestamp_ms}ms | "
              f"segments={lines_found} | lines={n_lines} | "
              f"fit={fit_error:.2f}px | success={success} | "
              f"half_court_y={hc_text} ft | half_width={hw_text} ft")
    if ev is None:
        header = (f"{game} | frame {frame_idx} | t={timestamp_ms}ms | "
                  f"segments={lines_found} | lines=0 | fit=N/A | "
                  f"success=False | half_court_y=N/A ft | half_width=N/A ft")
    cv2.putText(out, header, (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(out, header, (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (255, 255, 255), 1, cv2.LINE_AA)
    return out


def make_frame_payload(game: str, frame_idx: int, timestamp_ms: int,
                       result: Dict[str, Any], model: CourtModel,
                       cfg: Dict[str, Any]) -> Dict[str, Any]:
    ev = result["evaluation"]
    H = result["homography"]
    center = result["center_line"]
    sideline = result["sidelines"]
    half_court_y = center["y_ft"] if center is not None else None
    court_length = court_length_from_half_court(
        half_court_y, cfg["court"]["hoop_to_baseline_ft"])
    hw_values = [v["half_width_ft"] for v in sideline.values() if v]

    lines_detected = {name: False for name in (
        "left_sideline", "right_sideline", "baseline", "ft_line",
        "left_lane", "right_lane", "center_line", "three_pt_arc",
        "ft_circle")}
    if ev is not None:
        coverages = ev["coverages"]
        threshold = float(cfg["scoring"]["min_structure_coverage"])
        lines_detected["baseline"] = coverages["baseline"] >= threshold
        lines_detected["ft_line"] = coverages["ft_line"] >= threshold
        lines_detected["left_lane"] = coverages["left_lane"] >= threshold
        lines_detected["right_lane"] = coverages["right_lane"] >= threshold
        lines_detected["three_pt_arc"] = coverages["three_pt_arc"] >= threshold
        lines_detected["ft_circle"] = coverages["ft_circle"] >= threshold
    lines_detected["center_line"] = center is not None
    lines_detected["left_sideline"] = sideline.get("left") is not None
    lines_detected["right_sideline"] = sideline.get("right") is not None

    if H is None:
        H_list = None
        hoop_xy = None
        scale_x = scale_y = None
    else:
        H_list = [[round(float(v), 8) for v in row] for row in H]
        H_inv = np.linalg.inv(H)
        hoop = H_inv @ np.array([0.0, 0.0, 1.0])
        if abs(hoop[2]) > 1e-9:
            hoop_xy = [round(float(hoop[0] / hoop[2]), 3),
                       round(float(hoop[1] / hoop[2]), 3)]
        else:
            hoop_xy = None
        scale_x, scale_y = scales_at_hoop(H, hoop_xy)

    inliers = ev["line_inliers"] if ev is not None else 0
    return {
        "game": game,
        "frame_idx": int(frame_idx),
        "timestamp_ms": int(timestamp_ms),
        "lines_detected": lines_detected,
        "line_segments_found": len(result["lines"]),
        "inlier_segments": int(inliers),
        "reprojection_error_px": round_or_none(
            ev["median_error_px"] if ev is not None else None),
        "condition_number": round_or_none(
            ev["condition_number"] if ev is not None else None),
        "homography_valid": bool(result["valid"]),
        "H_img2court": H_list,
        "hoop_img_xy": hoop_xy,
        "scale_x_ft_per_px": round_or_none(scale_x, 6),
        "scale_y_ft_per_px": round_or_none(scale_y, 6),
        "half_court_y_ft": round_or_none(half_court_y),
        "court_length_ft": round_or_none(court_length),
        "court_half_width_ft": round_or_none(
            max(hw_values) if hw_values else None),
        "success": bool(result["valid"]),
    }


def scales_at_hoop(H_img2court: np.ndarray,
                   hoop_xy: Optional[Sequence[float]]
                   ) -> Tuple[Optional[float], Optional[float]]:
    if hoop_xy is None:
        return None, None
    eps = 1.0
    p0 = H_img2court @ np.array([hoop_xy[0], hoop_xy[1], 1.0])
    px = H_img2court @ np.array([hoop_xy[0] + eps, hoop_xy[1], 1.0])
    py = H_img2court @ np.array([hoop_xy[0], hoop_xy[1] + eps, 1.0])
    if abs(p0[2]) < 1e-9 or abs(px[2]) < 1e-9 or abs(py[2]) < 1e-9:
        return None, None
    c0 = p0[:2] / p0[2]
    cx = px[:2] / px[2]
    cy = py[:2] / py[2]
    return (float(np.linalg.norm(cx - c0) / eps),
            float(np.linalg.norm(cy - c0) / eps))


# ---------------------------------------------------------------------------
# Frame reading


def read_frame(video_path: Path, frame_idx: int) -> Optional[np.ndarray]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None
    return frame


def timestamp_ms(frame_idx: int, fps: float) -> int:
    if fps <= 0:
        return 0
    return int(round(frame_idx / fps * 1000.0))


# ---------------------------------------------------------------------------
# Statistics and reports


def stats(values: Sequence[float]) -> Optional[Dict[str, float]]:
    values = [float(v) for v in values if v is not None and math.isfinite(v)]
    if not values:
        return None
    arr = np.asarray(values, dtype=np.float64)
    return {
        "mean": round(float(np.mean(arr)), 3),
        "median": round(float(np.median(arr)), 3),
        "std": round(float(np.std(arr)), 3),
        "min": round(float(np.min(arr)), 3),
        "max": round(float(np.max(arr)), 3),
        "p90": round(float(np.percentile(arr, 90)), 3),
    }


def load_keypoint(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"floor_points": None, "H_valid": None}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"floor_points": None, "H_valid": None}
    return {
        "floor_points": payload.get("keypoints_detected_conf_0_3"),
        "H_valid": payload.get("H_computed"),
    }


# ---------------------------------------------------------------------------
# Game and calibration runners


def run_game(game_spec: Dict[str, Any], frame_indices: Sequence[int],
             cfg: Dict[str, Any], out_root: Path, mode: str) -> Dict[str, Any]:
    game = game_spec["game"]
    gym = game_spec["gym"]
    video = ROOT / game_spec["video"]
    game_dir = out_root / game_spec["dir"]
    game_dir.mkdir(parents=True, exist_ok=True)
    model = CourtModel(cfg)
    fps = as_float(game_spec.get("fps"), 25.0)
    total_frames = int(game_spec.get("total_frames", 0))

    frame_records: List[Dict[str, Any]] = []
    overlay_paths: List[Tuple[int, Path, bool]] = []

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video}")
    reported_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if reported_fps > 0:
        fps = reported_fps
    if total_frames <= 0:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    try:
        for frame_idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError(f"[{game}] could not read frame {frame_idx}")
            ts = timestamp_ms(frame_idx, fps)
            t0 = time.time()
            result = analyze_frame(frame, gym, model, cfg)
            elapsed = time.time() - t0
            payload = make_frame_payload(game, frame_idx, ts, result, model, cfg)
            payload["analysis_seconds"] = round(elapsed, 3)

            if result["homography"] is not None:
                half_court_y = payload["half_court_y_ft"]
                half_widths = {
                    "left": (result["sidelines"]["left"] or {}).get(
                        "half_width_ft"),
                    "right": (result["sidelines"]["right"] or {}).get(
                        "half_width_ft"),
                }
                overlay = draw_overlay(
                    frame, model, result["homography"], result, game,
                    frame_idx, ts, half_court_y, half_widths)
            else:
                overlay = frame.copy()
            stem = f"frame_{frame_idx:04d}"
            overlay_path = game_dir / f"{stem}_overlay.png"
            if mode == "calibration":
                overlay_path = game_dir / f"calibration_{stem}_overlay.png"
            cv2.imwrite(str(overlay_path), overlay)
            overlay_paths.append((frame_idx, overlay_path, payload["success"]))

            json_path = game_dir / f"{stem}.json"
            if mode == "calibration":
                json_path = game_dir / f"calibration_{stem}.json"
            write_json(json_path, payload)
            frame_records.append(payload)
            print(
                f"[{game}] frame {frame_idx}: success={payload['success']} "
                f"segments={payload['line_segments_found']} "
                f"inliers={payload['inlier_segments']} "
                f"half_court_y={payload['half_court_y_ft']} "
                f"({elapsed:.1f}s)", flush=True)
    finally:
        cap.release()

    summary = build_summary(game_spec, frame_records, total_frames)
    summary_path = game_dir / f"summary_{game}.json"
    if mode == "calibration":
        summary_path = game_dir / f"summary_calibration_{game}.json"
    write_json(summary_path, summary)
    make_comparison_sheet(game_dir, game, overlay_paths, mode)
    return {"spec": game_spec, "records": frame_records, "summary": summary}


def build_summary(spec: Dict[str, Any], records: List[Dict[str, Any]],
                  total_frames: int) -> Dict[str, Any]:
    successes = [r for r in records if r["success"]]
    errors = [r["reprojection_error_px"] for r in successes
              if r["reprojection_error_px"] is not None]
    lines_found = [r["inlier_segments"] for r in records]
    half_court = [r["half_court_y_ft"] for r in successes
                  if r["half_court_y_ft"] is not None]
    court_length = [r["court_length_ft"] for r in successes
                    if r["court_length_ft"] is not None]
    half_width = [r["court_half_width_ft"] for r in successes
                  if r["court_half_width_ft"] is not None]

    comparison = {
        "frames_both_succeed": 0,
        "lines_succeeds_keypoints_fails": 0,
        "keypoints_succeeds_lines_fails": 0,
        "both_fail": 0,
    }
    keypoint_dir = spec.get("keypoint_dir")
    if keypoint_dir:
        kp_dir = ROOT / keypoint_dir
        for record in records:
            kp = load_keypoint(kp_dir / f"frame_{record['frame_idx']:04d}.json")
            # Stage 1 did not produce a homography; compare against the
            # keypoint floor-point count that would have been needed for one.
            kp_ok = (kp.get("floor_points") is not None and
                     int(kp.get("floor_points") or 0) >= 4)
            lines_ok = bool(record["success"])
            if lines_ok and kp_ok:
                comparison["frames_both_succeed"] += 1
            elif lines_ok and not kp_ok:
                comparison["lines_succeeds_keypoints_fails"] += 1
            elif kp_ok and not lines_ok:
                comparison["keypoints_succeeds_lines_fails"] += 1
            else:
                comparison["both_fail"] += 1

    n = len(records)
    return {
        "game": spec["game"],
        "video_path": spec["video"],
        "total_frames": int(total_frames),
        "frames_analyzed": n,
        "frame_indices": [r["frame_idx"] for r in records],
        "success_count": len(successes),
        "failure_count": n - len(successes),
        "success_rate": round(len(successes) / n, 4) if n else 0.0,
        "lines_found_per_frame": stats(lines_found),
        "reprojection_error_px": stats(errors),
        "half_court_y_ft": stats(half_court),
        "court_length_ft": stats(court_length),
        "court_half_width_ft": stats(half_width),
        "keypoint_model_comparison": comparison,
    }


def make_comparison_sheet(game_dir: Path, game: str,
                          overlays: List[Tuple[int, Path, bool]],
                          mode: str) -> None:
    if not overlays:
        return
    # best = first success (lowest frame index), median = middle record,
    # worst = first failure; if a class is missing, reuse the nearest.
    successes = [item for item in overlays if item[2]]
    failures = [item for item in overlays if not item[2]]
    best = successes[0] if successes else overlays[0]
    worst = failures[0] if failures else overlays[-1]
    median = overlays[len(overlays) // 2]
    chosen = [best, median, worst]
    tiles = []
    for frame_idx, path, success in chosen:
        image = cv2.imread(str(path))
        if image is None:
            continue
        tile = cv2.resize(image, (640, 360))
        label = f"frame {frame_idx} success={success}"
        cv2.putText(tile, label, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(tile, label, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (255, 255, 255), 1, cv2.LINE_AA)
        tiles.append(tile)
    if len(tiles) == 3:
        sheet = np.hstack(tiles)
    else:
        sheet = np.vstack(tiles)
    name = f"vetter_sheet_{game}.png"
    if mode == "calibration":
        name = f"vetter_sheet_calibration_{game}.png"
    cv2.imwrite(str(game_dir / name), sheet)


def build_measurement_report(results: List[Dict[str, Any]],
                             cfg: Dict[str, Any]) -> str:
    lines = ["# Stage 1b Court Lines Measurement Report", ""]
    lines.append(
        "Approach (A): painted-line detection plus an NFHS geometric fit. "
        "Each frame was fitted independently. No interpolation, no tracking, "
        "and no learned model. Thresholds were frozen on the calibration "
        "frames before the 60 measurement frames were measured."
    )
    lines.append("")
    lines.append("## Aggregate Results")
    lines.append("")
    lines.append("| Game | Frames | Success | Rate | Median error (px) | "
                 "Half-court Y mean (ft) | Court length mean (ft) |")
    lines.append("|------|--------|---------|------|-------------------|"
                 "------------------------|------------------------|")
    for result in results:
        summary = result["summary"]
        err = summary["reprojection_error_px"] or {}
        hc = summary["half_court_y_ft"] or {}
        cl = summary["court_length_ft"] or {}
        lines.append(
            f"| {summary['game']} | {summary['frames_analyzed']} | "
            f"{summary['success_count']} | "
            f"{100.0 * summary['success_rate']:.1f}% | "
            f"{err.get('median', 'N/A')} | {hc.get('mean', 'N/A')} | "
            f"{cl.get('mean', 'N/A')} |")
    lines.append("")

    lines.append("## Per-Frame Table")
    lines.append("")
    lines.append("| Game | Frame | Segments | Lines | Fit error (px) | "
                 "Success | Half-court Y (ft) | Court length (ft) | "
                 "Keypoint floor points | Keypoint H valid |")
    lines.append("|------|-------|----------|-------|----------------|"
                 "---------|-------------------|-------------------|"
                 "-----------------------|------------------|")
    for result in results:
        spec = result["spec"]
        kp_dir = ROOT / spec["keypoint_dir"] if spec.get("keypoint_dir") else None
        for record in result["records"]:
            kp = load_keypoint(
                kp_dir / f"frame_{record['frame_idx']:04d}.json"
                if kp_dir else Path("__missing__"))
            lines.append(
                f"| {record['game']} | {record['frame_idx']} | "
                f"{record['line_segments_found']} | "
                f"{record['inlier_segments']} | "
                f"{record['reprojection_error_px']} | "
                f"{record['success']} | {record['half_court_y_ft']} | "
                f"{record['court_length_ft']} | "
                f"{kp.get('floor_points')} | {kp.get('H_valid')} |")
    lines.append("")

    lines.append("## Comparison with Stage 1 Keypoints")
    lines.append("")
    for result in results:
        comp = result["summary"]["keypoint_model_comparison"]
        lines.append(
            f"- **{result['summary']['game']}**: both succeed "
            f"{comp['frames_both_succeed']}, lines succeed / keypoints fail "
            f"{comp['lines_succeeds_keypoints_fails']}, keypoints succeed / "
            f"lines fail {comp['keypoints_succeeds_lines_fails']}, both fail "
            f"{comp['both_fail']}.")
    lines.append("")
    lines.append(
        "Stage 1 used a homography only when at least 4 keypoints were found; "
        "the keypoint model did not compute a homography in Stage 1, so the "
        "keypoint H column is a conservative comparison."
    )
    lines.append("")

    lines.append("## Pass-Gate Check")
    lines.append("")
    by_game = {r["summary"]["game"]: r["summary"] for r in results}
    adrian = by_game.get("adrian")
    a1 = by_game.get("notus_a1")
    a = by_game.get("notus_a")
    checks = []
    if adrian:
        checks.append(("Adrian >= 80% success",
                       adrian["success_rate"] >= 0.80,
                       f"{100.0 * adrian['success_rate']:.1f}%"))
        adrian_lengths = adrian["court_length_ft"]
        if adrian_lengths:
            ok_length = 84.0 <= adrian_lengths["mean"] <= 100.0
            checks.append((
                "Adrian court lengths physically plausible (mean 84-100 ft)",
                ok_length, f"{adrian_lengths['mean']} ft"))
        else:
            checks.append((
                "Adrian court lengths physically plausible (mean 84-100 ft)",
                False, "no successful length measurements"))
    if a1:
        hc = (a1["half_court_y_ft"] or {}).get("mean")
        err = (a1["reprojection_error_px"] or {}).get("median")
        ok_y = hc is not None and abs(hc - 40.75) <= 2.0
        ok_err = err is not None and err <= 1.5
        checks.append(("Notus A1 >= 70% success",
                       a1["success_rate"] >= 0.70,
                       f"{100.0 * a1['success_rate']:.1f}%"))
        checks.append(("Notus A1 half-court Y within 40.75 +/- 2.0 ft",
                       ok_y, f"{hc}" if hc is not None else "N/A"))
        checks.append(("Notus A1 median fit error <= 1.5 px",
                       ok_err, f"{err}" if err is not None else "N/A"))
    if a:
        checks.append(("Notus A >= 70% success",
                       a["success_rate"] >= 0.70,
                       f"{100.0 * a['success_rate']:.1f}%"))
        a_hc = (a["half_court_y_ft"] or {}).get("mean")
        a1_hc = (a1["half_court_y_ft"] or {}).get("mean") if a1 else None
        consistent = (a_hc is not None and a1_hc is not None and
                      abs(a_hc - a1_hc) <= 2.0)
        checks.append((
            "Notus A half-court Y within 2.0 ft of Notus A1",
            consistent,
            f"{a_hc} vs {a1_hc}" if a_hc is not None and a1_hc is not None
            else "N/A"))
    for label, passed, value in checks:
        lines.append(f"- {'PASS' if passed else 'FAIL'} - {label} ({value})")
    lines.append("")
    lines.append(
        "Verdict: approach (A) does not meet the Stage 2 gate unless every "
        "line above says PASS. The measured numbers are reported without "
        "retuning."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Calibration guard and entry point


def check_calibration_separation(game_spec: Dict[str, Any],
                                 calibration_frames: Sequence[int],
                                 cfg: Dict[str, Any]) -> None:
    fps = as_float(game_spec.get("fps"), 25.0)
    minimum = float(cfg["calibration"]["min_separation_seconds"]) * fps
    measurements = [int(v) for v in game_spec["frame_indices"]]
    for cal in calibration_frames:
        for measurement in measurements:
            if abs(int(cal) - measurement) < minimum:
                raise ValueError(
                    f"Calibration frame {cal} for {game_spec['game']} is "
                    f"within {cfg['calibration']['min_separation_seconds']} s "
                    f"of measurement frame {measurement}.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True,
                        help="Path to the Stage 1b YAML config")
    parser.add_argument("--mode", choices=("calibration", "measure", "both"),
                        default="measure",
                        help="Run calibration frames, measurement frames, or both")
    args = parser.parse_args(argv)

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    cfg = load_config(config_path)
    out_root = ROOT / cfg.get("output_root", ".team/stage1b_lines")
    out_root.mkdir(parents=True, exist_ok=True)

    results: List[Dict[str, Any]] = []
    calibration_results: List[Dict[str, Any]] = []

    for game_spec in cfg["games"]:
        game = game_spec["game"]
        if args.mode in ("calibration", "both"):
            cal_frames = [int(v) for v in
                          cfg["calibration"].get(game, [])]
            if cal_frames:
                check_calibration_separation(game_spec, cal_frames, cfg)
                print(f"[{game}] calibration frames: {cal_frames}", flush=True)
                calibration_results.append(
                    run_game(game_spec, cal_frames, cfg, out_root,
                             "calibration"))
        if args.mode in ("measure", "both"):
            frames = [int(v) for v in game_spec["frame_indices"]]
            print(f"[{game}] measurement frames: {frames}", flush=True)
            results.append(run_game(game_spec, frames, cfg, out_root,
                                    "measure"))

    if calibration_results:
        cal_payload = {
            "note": ("Thresholds were fixed on these frames and then frozen "
                     "in the YAML before measurement."),
            "calibration_frames": {
                r["spec"]["game"]: r["summary"]["frame_indices"]
                for r in calibration_results
            },
            "results": [r["summary"] for r in calibration_results],
        }
        write_json(out_root / "calibration_report.json", cal_payload)

    if results:
        report = build_measurement_report(results, cfg)
        (out_root / "measurement_report.md").write_text(
            report, encoding="utf-8")
        print(f"Wrote {out_root / 'measurement_report.md'}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
