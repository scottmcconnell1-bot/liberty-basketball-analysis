#!/usr/bin/env python3
"""Stage 1 keypoint measurement.

Measures the existing court keypoint detector on evenly spaced frames from
three films. Measurement only: no homography, no interpolation, no changes to
the model or any existing project file.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "court_keypoint_detector.pt"
OUT_ROOT = ROOT / ".team" / "stage1_keypoints"

GAMES = [
    {
        "game": "adrian",
        "dir": "adrian",
        "video": "uploads/nfhs_gam0a66d85e12.mp4",
        "gym": "Adrian's gym",
    },
    {
        "game": "notus_a1",
        "dir": "notus_a1",
        "video": "uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4",
        "gym": "Liberty (92 ft)",
    },
    {
        "game": "notus_a",
        "dir": "notus_a",
        "video": "uploads/LIBERTY_H_v_NOTUS_A_20260809_221334.mp4",
        "gym": "Liberty (92 ft)",
    },
]

FRAMES_PER_GAME = 20
CONF_THRESHOLD = 0.3
NUM_KEYPOINTS = 18

# Filled in after visual review of the generated overlays. Stage 1 makes no
# semantic commitment; these are hypotheses only.
LANDMARK_HYPOTHESES = {
    0: "UNCLEAR",
    1: "UNCLEAR",
    2: "UNCLEAR",
    3: "UNCLEAR",
    4: "UNCLEAR",
    5: "UNCLEAR",
    6: "center line at one sideline",
    7: "center line at the other sideline",
    8: "3-pt line junction (same landmark as 16)",
    9: "3-pt line junction, opposite side (same as 17)",
    10: "UNCLEAR",
    11: "UNCLEAR",
    12: "lane corner at FT line (hypothesis)",
    13: "lane corner at FT line (hypothesis)",
    14: "baseline lane corner near basket (same as 15)",
    15: "baseline lane corner near basket (same as 14)",
    16: "3-pt line junction (same landmark as 8)",
    17: "3-pt line junction, opposite side (same as 9)",
}


def choose_frames(total_frames: int) -> tuple[int, list[int]]:
    stride = max(1, total_frames // FRAMES_PER_GAME)
    frames = [i * stride for i in range(FRAMES_PER_GAME) if i * stride < total_frames]
    return stride, frames


def read_frame(cap: cv2.VideoCapture, idx: int):
    cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
    ok, frame = cap.read()
    if not ok:
        return None
    return frame


def detect_keypoints(model: YOLO, frame: np.ndarray):
    result = model.predict(frame, conf=CONF_THRESHOLD, verbose=False)[0]
    xy = np.full((NUM_KEYPOINTS, 2), np.nan, dtype=np.float64)
    conf = np.zeros(NUM_KEYPOINTS, dtype=np.float64)
    if result.keypoints is not None and len(result.keypoints) > 0:
        pts = result.keypoints[0].xy.cpu().numpy()
        if pts.ndim == 3:
            pts = pts[0]
        kconf = result.keypoints[0].conf
        if kconf is not None:
            kconf = kconf.cpu().numpy()
            if kconf.ndim == 2:
                kconf = kconf[0]
        else:
            kconf = np.zeros(NUM_KEYPOINTS, dtype=np.float64)
        n = min(NUM_KEYPOINTS, len(pts))
        xy[:n] = pts[:n]
        conf[:n] = kconf[:n]
    return xy, conf


def finite_xy(xy: np.ndarray) -> np.ndarray:
    return np.isfinite(xy[:, 0]) & np.isfinite(xy[:, 1])


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def draw_overlay(frame: np.ndarray, game: str, frame_idx: int, timestamp_ms: int,
                 xy: np.ndarray, conf: np.ndarray, detected: int) -> np.ndarray:
    out = frame.copy()
    valid = finite_xy(xy)
    for kp_id in range(NUM_KEYPOINTS):
        if not valid[kp_id]:
            continue
        x, y = int(round(xy[kp_id, 0])), int(round(xy[kp_id, 1]))
        c = float(conf[kp_id])
        if c >= 0.5:
            color = (0, 255, 0)
        elif c >= CONF_THRESHOLD:
            color = (0, 255, 255)
        else:
            color = (0, 0, 255)
        cv2.circle(out, (x, y), 6, color, 2)
        label = str(kp_id)
        pos = (x + 8, y - 8)
        cv2.putText(out, label, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(out, label, pos, cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                    (255, 255, 255), 1, cv2.LINE_AA)

    header = (f"Game: {game} | Frame: {frame_idx} | Time: {timestamp_ms}ms | "
              f"Keypoints >=0.3: {detected}")
    cv2.putText(out, header, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(out, header, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (255, 255, 255), 1, cv2.LINE_AA)
    return out


def measure_game(model: YOLO, spec: dict) -> dict:
    game = spec["game"]
    game_dir = OUT_ROOT / spec["dir"]
    game_dir.mkdir(parents=True, exist_ok=True)
    video_path = ROOT / spec["video"]

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    stride, frame_indices = choose_frames(total_frames)
    print(f"[{game}] total_frames={total_frames} fps={fps:.3f} stride={stride} "
          f"frames={frame_indices}", flush=True)

    freq = {str(i): 0 for i in range(NUM_KEYPOINTS)}
    per_frame = []

    for frame_idx in frame_indices:
        frame = read_frame(cap, frame_idx)
        if frame is None:
            raise RuntimeError(f"[{game}] could not read frame {frame_idx}")
        xy, conf = detect_keypoints(model, frame)
        valid = finite_xy(xy)
        n_detected = int(np.sum(valid & (conf >= CONF_THRESHOLD)))
        timestamp_ms = int(round(frame_idx / fps * 1000.0)) if fps > 0 else 0

        keypoints = []
        for kp_id in range(NUM_KEYPOINTS):
            if valid[kp_id]:
                x_val = round(float(xy[kp_id, 0]), 2)
                y_val = round(float(xy[kp_id, 1]), 2)
            else:
                x_val = None
                y_val = None
            keypoints.append({
                "id": kp_id,
                "x": x_val,
                "y": y_val,
                "conf": round(float(conf[kp_id]), 4),
                "label": f"UNKNOWN_{kp_id}",
            })
            if valid[kp_id] and conf[kp_id] >= CONF_THRESHOLD:
                freq[str(kp_id)] += 1

        record = {
            "game": game,
            "frame_idx": frame_idx,
            "timestamp_ms": timestamp_ms,
            "keypoints": keypoints,
            "keypoints_detected_conf_0_3": n_detected,
            "H_computed": False,
            "H_inliers": None,
            "reproj_error_px": None,
            "half_court_y_ft": None,
        }
        stem = f"frame_{frame_idx:04d}"
        write_json(game_dir / f"{stem}.json", record)
        overlay = draw_overlay(frame, game, frame_idx, timestamp_ms, xy, conf,
                               n_detected)
        cv2.imwrite(str(game_dir / f"{stem}_overlay.jpg"), overlay)

        per_frame.append({
            "frame_idx": frame_idx,
            "xy": xy,
            "conf": conf,
            "detected": n_detected,
        })
        print(f"[{game}] frame {frame_idx}: {n_detected}/{NUM_KEYPOINTS} "
              f"keypoints >= {CONF_THRESHOLD}", flush=True)

    cap.release()

    summary = {
        "game": game,
        "video_path": spec["video"],
        "total_frames": total_frames,
        "frames_analyzed": len(frame_indices),
        "frame_indices": frame_indices,
        "keypoint_detection_freq": freq,
    }
    write_json(game_dir / f"summary_{game}.json", summary)
    return {"spec": spec, "summary": summary, "per_frame": per_frame,
            "fps": fps, "stride": stride}


def evidence_for(per_frame: list[dict], kp_id: int, limit: int = 3) -> list[str]:
    rows = []
    for item in per_frame:
        xy = item["xy"]
        conf = item["conf"]
        if np.isfinite(xy[kp_id, 0]) and conf[kp_id] >= CONF_THRESHOLD:
            rows.append((float(conf[kp_id]), item["frame_idx"],
                         float(xy[kp_id, 0]), float(xy[kp_id, 1])))
    rows.sort(key=lambda r: r[0], reverse=True)
    return [f"{frame_idx} ({x:.0f},{y:.0f})"
            for _, frame_idx, x, y in rows[:limit]]


def build_report(results: list[dict]) -> str:
    lines = ["# Stage 1 Keypoint Measurement Report", ""]
    lines.append("Measurement only: no homography, no interpolation, no Stage 2 "
                 "gates. All counts use confidence >= 0.3. Keypoint labels are "
                 "intentionally `UNKNOWN_<id>` in Stage 1.")
    lines.append("")

    lines.append("## 1. Per-Game Summary")
    lines.append("")
    for result in results:
        spec = result["spec"]
        summary = result["summary"]
        lines.append(f"### {spec['game']}")
        lines.append("")
        lines.append(f"- Video: `{spec['video']}`")
        lines.append(f"- Gym: {spec['gym']}")
        lines.append(f"- Total frames: {summary['total_frames']}")
        lines.append(f"- Frames analyzed: {summary['frames_analyzed']}")
        lines.append(f"- Stride: {result['stride']}")
        lines.append(f"- Frame indices: {summary['frame_indices']}")
        lines.append("")
        lines.append("| Index | Frames detected (conf >= 0.3) |")
        lines.append("|-------|-------------------------------|")
        for kp_id in range(NUM_KEYPOINTS):
            lines.append(f"| {kp_id} | {summary['keypoint_detection_freq'][str(kp_id)]}"
                         f"/{summary['frames_analyzed']} |")
        lines.append("")

    lines.append("## 2. Keypoint Index Report")
    lines.append("")
    lines.append("| Index | Detection Rate (all games) | Likely Landmark | "
                 "Evidence Frames (game: frame_idx (image_xy)) |")
    lines.append("|-------|---------------------------|-----------------|"
                 "----------------------------------------------|")
    total_frames = sum(r["summary"]["frames_analyzed"] for r in results)
    for kp_id in range(NUM_KEYPOINTS):
        hits = sum(r["summary"]["keypoint_detection_freq"][str(kp_id)]
                   for r in results)
        rate = (100.0 * hits / total_frames) if total_frames else 0.0
        evidence_parts = []
        for result in results:
            ev = evidence_for(result["per_frame"], kp_id)
            if ev:
                evidence_parts.append(f"{result['spec']['game']}: " + ", ".join(ev))
        evidence = "; ".join(evidence_parts) if evidence_parts else "none"
        landmark = LANDMARK_HYPOTHESES.get(kp_id, "UNCLEAR")
        lines.append(f"| {kp_id} | {rate:.0f}% | {landmark} | {evidence} |")
    lines.append("")
    lines.append("Likely Landmark entries are visual hypotheses from the overlays; "
                 "UNCLEAR means the index is ambiguous in Stage 1.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    model = YOLO(str(MODEL_PATH), verbose=False)
    results = []
    for spec in GAMES:
        results.append(measure_game(model, spec))
    report = build_report(results)
    (OUT_ROOT / "measurement_report.md").write_text(report, encoding="utf-8")
    print(f"Wrote {OUT_ROOT / 'measurement_report.md'}", flush=True)


if __name__ == "__main__":
    main()
