"""Ball possession scoring with distance, containment, and temporal consistency.

Inspired by containment-ratio possession detectors used in research CV pipelines,
adapted for Liberty's SQLite detection schema (center + width/height boxes).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _bbox_from_row(row):
    """Convert center + size detection row to (x1, y1, x2, y2)."""
    w = float(row.get("width") or 0)
    h = float(row.get("height") or 0)
    if w <= 0 or h <= 0:
        size = 40.0
        w = h = size
    cx = float(row["x_center"])
    cy = float(row["y_center"])
    return cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0


def ball_containment_ratio(player_row, ball_row) -> float:
    """Intersection area over ball area (0..1)."""
    px1, py1, px2, py2 = _bbox_from_row(player_row)
    bx1, by1, bx2, by2 = _bbox_from_row(ball_row)

    ix1 = max(px1, bx1)
    iy1 = max(py1, by1)
    ix2 = min(px2, bx2)
    iy2 = min(py2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    intersection = (ix2 - ix1) * (iy2 - iy1)
    ball_area = max((bx2 - bx1) * (by2 - by1), 1.0)
    return float(intersection / ball_area)


def _auto_possession_threshold(detections_df: pd.DataFrame) -> float:
    x_max = min(detections_df["x_center"].quantile(0.99), 3840)
    y_max = min(detections_df["y_center"].quantile(0.99), 2160)
    diagonal = math.sqrt(x_max**2 + y_max**2)
    return diagonal * 0.10


def _frame_ball_holder(
    frame_players: pd.DataFrame,
    ball_row: pd.Series,
    possession_threshold: float,
    containment_threshold: float,
) -> tuple[int | None, float]:
    """Return (player_index, score) for the best holder on one frame."""
    best_idx = None
    best_score = -1.0

    for idx, player in frame_players.iterrows():
        dx = float(player["x_center"]) - float(ball_row["x_center"])
        dy = float(player["y_center"]) - float(ball_row["y_center"])
        distance = math.hypot(dx, dy)
        if distance > possession_threshold:
            continue

        containment = ball_containment_ratio(player, ball_row)
        if containment < containment_threshold * 0.5 and distance > possession_threshold * 0.6:
            continue

        distance_score = max(0.0, 1.0 - (distance / possession_threshold))
        score = (0.55 * distance_score) + (0.45 * min(containment, 1.0))
        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx, best_score


def apply_temporal_possession_filter(frame_identities: list[str | None], min_consecutive_frames: int) -> set[int]:
    """Return frame indices that survive a minimum consecutive-frame run."""
    if min_consecutive_frames <= 1:
        return {i for i, identity in enumerate(frame_identities) if identity is not None}

    confirmed: set[int] = set()
    run_start = 0
    while run_start < len(frame_identities):
        identity = frame_identities[run_start]
        if identity is None:
            run_start += 1
            continue

        run_end = run_start + 1
        while run_end < len(frame_identities) and frame_identities[run_end] == identity:
            run_end += 1

        if (run_end - run_start) >= min_consecutive_frames:
            confirmed.update(range(run_start, run_end))
        run_start = run_end

    return confirmed


def assign_ball_possession(
    detections_df: pd.DataFrame,
    *,
    possession_threshold: float | None = None,
    containment_threshold: float = 0.35,
    min_consecutive_frames: int = 3,
) -> pd.DataFrame:
    """Annotate person detections with ball_distance, has_ball, ball_containment."""
    detections_df = detections_df.sort_values("frame_number").reset_index(drop=True)
    detections_df["has_ball"] = False
    detections_df["ball_distance"] = float("inf")
    detections_df["ball_containment"] = 0.0

    if possession_threshold is None:
        possession_threshold = _auto_possession_threshold(detections_df)

    ball_df = (
        detections_df.loc[detections_df["class_name"] == "ball", ["frame_number", "x_center", "y_center", "width", "height"]]
        .groupby("frame_number", as_index=False)
        .first()
    )
    player_mask = detections_df["class_name"] == "person"
    if ball_df.empty or not player_mask.any():
        return detections_df

    player_df = detections_df.loc[player_mask].copy()
    frames = sorted(player_df["frame_number"].unique())
    frame_holders: list[tuple[int, str] | None] = []
    frame_meta: list[tuple[float, float] | None] = []

    for frame in frames:
        frame_players = player_df[player_df["frame_number"] == frame]
        ball_row = ball_df[ball_df["frame_number"] == frame]
        if ball_row.empty:
            frame_holders.append(None)
            frame_meta.append(None)
            continue

        best_idx, _best_score = _frame_ball_holder(
            frame_players,
            ball_row.iloc[0],
            possession_threshold,
            containment_threshold,
        )
        if best_idx is None:
            frame_holders.append(None)
            frame_meta.append(None)
            continue

        player = frame_players.loc[best_idx]
        tracker_id = player.get("tracker_id")
        if tracker_id is not None and not pd.isna(tracker_id):
            identity = f"t:{int(tracker_id)}"
        else:
            identity = f"r:{int(best_idx)}"

        dx = float(player["x_center"]) - float(ball_row.iloc[0]["x_center"])
        dy = float(player["y_center"]) - float(ball_row.iloc[0]["y_center"])
        dist = math.hypot(dx, dy)
        containment = ball_containment_ratio(player, ball_row.iloc[0])
        frame_holders.append((int(best_idx), identity))
        frame_meta.append((dist, containment))

    identity_sequence = [holder[1] if holder else None for holder in frame_holders]
    confirmed_frames = apply_temporal_possession_filter(identity_sequence, min_consecutive_frames)

    for frame_idx, holder in enumerate(frame_holders):
        if frame_idx not in confirmed_frames or holder is None:
            continue
        winner_idx, _identity = holder
        dist, containment = frame_meta[frame_idx] or (float("inf"), 0.0)
        detections_df.loc[winner_idx, "ball_distance"] = dist
        detections_df.loc[winner_idx, "ball_containment"] = containment
        detections_df.loc[winner_idx, "has_ball"] = True

    # Distance fallback for diagnostics on non-possession frames
    ball_lookup = ball_df.set_index("frame_number")
    for idx, row in player_df.iterrows():
        frame = row["frame_number"]
        if frame not in ball_lookup.index:
            continue
        ball = ball_lookup.loc[frame]
        dist = math.hypot(float(row["x_center"]) - float(ball["x_center"]), float(row["y_center"]) - float(ball["y_center"]))
        if detections_df.loc[idx, "ball_distance"] == float("inf"):
            detections_df.loc[idx, "ball_distance"] = dist

    return detections_df
