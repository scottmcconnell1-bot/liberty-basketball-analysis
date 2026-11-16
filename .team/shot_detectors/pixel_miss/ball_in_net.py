"""Read-only ball-detector-in-net measurement after the rim (Task 1 step 4).

Plan: .team/specs/16_ball_in_net_plan.md (VETTED + BINDING NOTES a, b).
Imports net_detector._net_box only; never edits core files. Nothing is applied
to any detector. Column A = 640x640 native window (not production scale);
Column B = full frame imgsz=640 (production scale).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from net_detector import _net_box  # noqa: E402

# --- constants (no config.yaml) ---
AFTER_OFFSETS = (1, 2, 3, 4, 5, 6)
WINDOW_SIZE = 640
IMGSZ = 640
BALL_CLASS_ID = 0
DEFAULT_BALL_CONFIDENCE = 0.25  # settings_store.py:13 — never lower
BALL_MODEL_PATH = ROOT / "models" / "ball_detector.pt"
DB_PATH = ROOT / "film_analysis.db"

EXPECTED_BUILD = 140
EXPECTED_MISSED_MAKES = 19
EXPECTED_CORRECT_MAKES = 28
EXPECTED_REAL_MISSES = 93

DEFAULT_OUT_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_in_net"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/ball_in_net"),
]

DEFAULT_RESULTS_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\net_moved_build_results.json"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/net_moved_build_results.json"),
]


def pick_existing(*candidates: Path) -> Optional[Path]:
    for cand in candidates:
        if cand is None:
            continue
        p = Path(cand)
        if p.exists():
            return p
    return None


def resolve_path(path_str: str) -> Path:
    """Return a Path that exists, accepting Windows or /mnt/c forms."""
    raw = Path(path_str)
    if raw.exists():
        return raw
    s = str(path_str)
    if len(s) >= 3 and s[1] == ":" and s[0].isalpha():
        drive = s[0].lower()
        rest = s[2:].replace("\\", "/").lstrip("/")
        alt = Path(f"/mnt/{drive}/{rest}")
        if alt.exists():
            return alt
    if s.startswith("/mnt/") and len(s) > 7:
        drive = s[5].upper()
        rest = s[7:].replace("/", "\\")
        alt = Path(f"{drive}:\\{rest}")
        if alt.exists():
            return alt
    return raw


def default_out_dir() -> Path:
    found = pick_existing(*DEFAULT_OUT_CANDIDATES)
    if found is not None:
        return found
    # Prefer the form that matches this OS's parent if it exists; else Windows form.
    parent_w = Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs")
    parent_u = Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs")
    if parent_u.exists():
        return parent_u / "ball_in_net"
    if parent_w.exists():
        return parent_w / "ball_in_net"
    return DEFAULT_OUT_CANDIDATES[0]


def default_results_path() -> Path:
    found = pick_existing(*DEFAULT_RESULTS_CANDIDATES)
    if found is not None:
        return found
    return DEFAULT_RESULTS_CANDIDATES[0]


def load_ball_confidence() -> Tuple[float, str]:
    """BINDING NOTE a: read-only URI; never call settings_store.load_all_settings."""
    db = resolve_path(str(DB_PATH))
    uri = f"file:{db.as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                ("ai.ball_confidence",),
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        print(f"WARNING: could not read app_settings ({exc}); using default")
        return DEFAULT_BALL_CONFIDENCE, "settings_store.py:13 default (DB read failed)"

    if row is None or row[0] is None or str(row[0]).strip() == "":
        return DEFAULT_BALL_CONFIDENCE, "settings_store.py:13 default (no saved row)"

    try:
        saved = float(row[0])
    except (TypeError, ValueError):
        return DEFAULT_BALL_CONFIDENCE, "settings_store.py:13 default (unparseable saved value)"

    # Never lower below the production default.
    if saved < DEFAULT_BALL_CONFIDENCE:
        print(
            f"WARNING: saved ball_confidence={saved} is below default "
            f"{DEFAULT_BALL_CONFIDENCE}; using {DEFAULT_BALL_CONFIDENCE} (never lower)"
        )
        return DEFAULT_BALL_CONFIDENCE, (
            f"settings_store.py:13 default (saved {saved} was lower; refused)"
        )
    return saved, f"film_analysis.db app_settings key ai.ball_confidence"


def dedupe_by_film_t(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the first row for each (film, t). Adrian tracks list some t twice."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        key = (row["film"], int(row["t"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def classify_shots(
    rows: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    missed = [r for r in rows if r.get("missed_make")]
    correct = [r for r in rows if r.get("gt_make") and r.get("rule_pred_make")]
    misses = [r for r in rows if not r.get("gt_make")]
    missed_sorted = sorted(
        missed, key=lambda r: (0 if r["film"] == "notus_a1" else 1, int(r["t"]))
    )
    correct_sorted = sorted(
        correct, key=lambda r: (0 if r["film"] == "notus_a1" else 1, int(r["t"]))
    )
    misses_sorted = sorted(
        misses, key=lambda r: (0 if r["film"] == "notus_a1" else 1, int(r["t"]))
    )
    return missed_sorted, correct_sorted, misses_sorted


def review_crop_shots(
    missed: List[Dict[str, Any]],
    correct: List[Dict[str, Any]],
    misses: List[Dict[str, Any]],
) -> List[Tuple[str, Dict[str, Any]]]:
    """Same 39 shots as build_review_page / net_check: 19 missed + 10 correct + 10 misses."""
    out: List[Tuple[str, Dict[str, Any]]] = []
    for i, row in enumerate(missed, start=1):
        out.append((f"missed_make_{i:02d}", row))
    correct_pick = sorted(correct, key=lambda r: int(r["t"]))[:10]
    for i, row in enumerate(correct_pick, start=1):
        out.append((f"correct_make_{i:02d}", row))
    miss_pick = sorted(misses, key=lambda r: int(r["t"]))[:10]
    for i, row in enumerate(miss_pick, start=1):
        out.append((f"miss_{i:02d}", row))
    return out


def has_crossing_from_row(row: Dict[str, Any]) -> bool:
    reason = row.get("peak_reason") or ""
    if reason == "crossing":
        return True
    if row.get("used_no_crossing_rule"):
        return False
    return reason == "crossing"


class FrameReader:
    def __init__(self, video_path: Path):
        self.path = video_path
        self.cap = cv2.VideoCapture(str(video_path))
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open video: {video_path}")
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps = float(fps) if fps and fps > 1e-6 else 25.0
        n = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
        self.total_frames = int(n) if n and n > 0 else 0

    def read(self, frame_idx: int):
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
        ok, frame = self.cap.read()
        if not ok:
            return None
        return frame

    def close(self) -> None:
        self.cap.release()


def extract_640_window(
    frame, net_box: Tuple[int, int, int, int]
) -> Tuple[Any, int, int]:
    """640x640 square centred on net box, clamped to frame; no resize (Column A)."""
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = net_box
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    half = WINDOW_SIZE // 2
    wx0 = int(round(cx - half))
    wy0 = int(round(cy - half))
    if w >= WINDOW_SIZE:
        wx0 = max(0, min(w - WINDOW_SIZE, wx0))
        wx1 = wx0 + WINDOW_SIZE
    else:
        wx0, wx1 = 0, w
    if h >= WINDOW_SIZE:
        wy0 = max(0, min(h - WINDOW_SIZE, wy0))
        wy1 = wy0 + WINDOW_SIZE
    else:
        wy0, wy1 = 0, h
    window = frame[wy0:wy1, wx0:wx1]
    return window, wx0, wy0


def centre_in_net(
    cx: float, cy: float, net_box: Tuple[int, int, int, int], hoop_y: float
) -> bool:
    x0, y0, x1, y1 = net_box
    return (x0 <= cx <= x1) and (y0 <= cy <= y1) and (cy > hoop_y)


def detections_from_result(
    result, offset_x: int = 0, offset_y: int = 0
) -> List[Dict[str, Any]]:
    """Map YOLO boxes to original-image coords (add window offset for Column A)."""
    out: List[Dict[str, Any]] = []
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return out
    xyxy = boxes.xyxy.cpu().numpy()
    confs = boxes.conf.cpu().numpy()
    for i in range(len(xyxy)):
        x1, y1, x2, y2 = [float(v) for v in xyxy[i]]
        x1 += offset_x
        x2 += offset_x
        y1 += offset_y
        y2 += offset_y
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        out.append(
            {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "cx": cx,
                "cy": cy,
                "conf": float(confs[i]),
            }
        )
    return out


def run_column(
    ball_model,
    image,
    conf: float,
    net_box: Tuple[int, int, int, int],
    hoop_y: float,
    offset_x: int = 0,
    offset_y: int = 0,
) -> Dict[str, Any]:
    results = ball_model.predict(
        image,
        conf=conf,
        classes=[BALL_CLASS_ID],
        imgsz=IMGSZ,
        verbose=False,
    )
    dets_all: List[Dict[str, Any]] = []
    if results:
        dets_all = detections_from_result(results[0], offset_x, offset_y)
    in_net = [
        d
        for d in dets_all
        if centre_in_net(d["cx"], d["cy"], net_box, hoop_y)
    ]
    return {
        "ball_in_net": len(in_net) > 0,
        "detections_in_net": in_net,
        "detections_all": dets_all,
    }


def measure_shot(
    row: Dict[str, Any],
    reader: FrameReader,
    ball_model,
    ball_confidence: float,
) -> Dict[str, Any]:
    peak_frame = int(row["peak_frame"])
    hoop_x = float(row["hoop_x"])
    hoop_y = float(row["hoop_y"])
    hoop_w = float(row["hoop_w"])
    rim_r = float(row.get("rim_r") or (hoop_w / 2.0))
    crossing = has_crossing_from_row(row)

    frames_out: List[Dict[str, Any]] = []
    col_a_hit_frames: List[int] = []
    col_b_hit_frames: List[int] = []
    col_a_confs: List[float] = []
    col_b_confs: List[float] = []

    for off in AFTER_OFFSETS:
        fidx = peak_frame + off
        frame = reader.read(fidx)
        entry: Dict[str, Any] = {
            "frame": fidx,
            "offset": off,
            "net_box": None,
            "column_a": {
                "ball_in_net": False,
                "detections_in_net": [],
                "window_xy": None,
            },
            "column_b": {
                "ball_in_net": False,
                "detections_in_net": [],
            },
        }
        if frame is None:
            frames_out.append(entry)
            continue

        box = _net_box(frame.shape, (hoop_x, hoop_y), rim_r)
        if box is None:
            frames_out.append(entry)
            continue
        entry["net_box"] = list(box)

        window, wx0, wy0 = extract_640_window(frame, box)
        entry["column_a"]["window_xy"] = [wx0, wy0]
        a = run_column(
            ball_model, window, ball_confidence, box, hoop_y, wx0, wy0
        )
        entry["column_a"]["ball_in_net"] = a["ball_in_net"]
        entry["column_a"]["detections_in_net"] = a["detections_in_net"]
        if a["ball_in_net"]:
            col_a_hit_frames.append(fidx)
            col_a_confs.extend(d["conf"] for d in a["detections_in_net"])

        b = run_column(ball_model, frame, ball_confidence, box, hoop_y)
        entry["column_b"]["ball_in_net"] = b["ball_in_net"]
        entry["column_b"]["detections_in_net"] = b["detections_in_net"]
        if b["ball_in_net"]:
            col_b_hit_frames.append(fidx)
            col_b_confs.extend(d["conf"] for d in b["detections_in_net"])

        frames_out.append(entry)

    return {
        "t": int(row["t"]),
        "film": row["film"],
        "start": row.get("start") or "",
        "quarter": row.get("quarter") or "",
        "label": row.get("label") or "",
        "player": row.get("player") or "",
        "gt_make": bool(row.get("gt_make")),
        "rule_pred_make": bool(row.get("rule_pred_make")),
        "missed_make": bool(row.get("missed_make")),
        "is_miss": bool(row.get("is_miss"))
        if "is_miss" in row
        else (not bool(row.get("gt_make"))),
        "peak_frame": peak_frame,
        "peak_reason": row.get("peak_reason") or "",
        "has_crossing": crossing,
        "hoop_x": hoop_x,
        "hoop_y": hoop_y,
        "hoop_w": hoop_w,
        "rim_r": rim_r,
        "frames": frames_out,
        "column_a_hit": len(col_a_hit_frames) > 0,
        "column_b_hit": len(col_b_hit_frames) > 0,
        "column_a_frames": col_a_hit_frames,
        "column_b_frames": col_b_hit_frames,
        "column_a_confs": col_a_confs,
        "column_b_confs": col_b_confs,
        "video_path": row.get("video_path") or "",
        "tracks_path": row.get("tracks_path") or "",
        "applied_to_core": False,
    }


def crop_square(
    frame, hoop_x: float, hoop_y: float, hoop_w: float
) -> Tuple[Any, int, int, int]:
    h, w = frame.shape[:2]
    size = int(max(hoop_w * 3.0, 240.0))
    cx, cy = int(round(hoop_x)), int(round(hoop_y))
    half = size // 2
    x0 = max(0, cx - half)
    y0 = max(0, cy - half)
    x1 = min(w, x0 + size)
    y1 = min(h, y0 + size)
    x0 = max(0, x1 - size)
    y0 = max(0, y1 - size)
    crop = frame[y0:y1, x0:x1].copy()
    return crop, x0, y0, size


def first_detected_frame(m: Dict[str, Any]) -> int:
    frames_a = m.get("column_a_frames") or []
    frames_b = m.get("column_b_frames") or []
    combined = sorted(set(frames_a) | set(frames_b))
    if combined:
        return int(combined[0])
    return int(m["peak_frame"]) + 2


def detections_on_frame(m: Dict[str, Any], frame_idx: int) -> List[Dict[str, Any]]:
    """In-net detections from either column on this frame (for crop drawing)."""
    out: List[Dict[str, Any]] = []
    for fr in m.get("frames") or []:
        if int(fr["frame"]) != int(frame_idx):
            continue
        for col in ("column_a", "column_b"):
            for d in fr.get(col, {}).get("detections_in_net") or []:
                out.append(d)
    # Deduplicate near-identical boxes from both columns
    uniq: List[Dict[str, Any]] = []
    for d in out:
        if any(
            abs(d["cx"] - u["cx"]) < 2 and abs(d["cy"] - u["cy"]) < 2 for u in uniq
        ):
            continue
        uniq.append(d)
    return uniq


def draw_ball_in_net_crop(
    frame,
    hoop_x: float,
    hoop_y: float,
    hoop_w: float,
    rim_r: float,
    detections: List[Dict[str, Any]],
) -> Any:
    """Square crop: net ROI blue, ball boxes green + confidence text."""
    if frame is None:
        size = int(max(hoop_w * 3.0, 240.0))
        return np.zeros((size, size, 3), dtype=np.uint8)
    crop, crop_x, crop_y, _size = crop_square(frame, hoop_x, hoop_y, hoop_w)
    box = _net_box(frame.shape, (hoop_x, hoop_y), rim_r)
    if box is not None:
        x0, y0, x1, y1 = box
        cv2.rectangle(
            crop,
            (x0 - crop_x, y0 - crop_y),
            (x1 - crop_x, y1 - crop_y),
            (255, 0, 0),
            2,
        )
    for d in detections:
        x1 = int(round(d["x1"] - crop_x))
        y1 = int(round(d["y1"] - crop_y))
        x2 = int(round(d["x2"] - crop_x))
        y2 = int(round(d["y2"] - crop_y))
        cv2.rectangle(crop, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"{d['conf']:.2f}"
        cv2.putText(
            crop,
            label,
            (x1, max(12, y1 - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )
    return crop


def write_markdown_outputs(
    out_dir: Path,
    results: List[Dict[str, Any]],
    missed: List[Dict[str, Any]],
    correct: List[Dict[str, Any]],
    misses: List[Dict[str, Any]],
) -> None:
    def caught(rows: List[Dict[str, Any]], col: str) -> int:
        key = "column_a_hit" if col == "A" else "column_b_hit"
        return sum(1 for r in rows if r[key])

    mm_cross = [r for r in missed if r["has_crossing"]]
    mm_nocross = [r for r in missed if not r["has_crossing"]]

    summary_lines = [
        "# Ball In Net Summary (read-only measurement)",
        "",
        "Column A = 640x640 native window (NOT production scale).",
        "Column B = full frame at imgsz=640 (production scale).",
        "",
        f"Build shots: {len(results)}",
        f"Missed makes: {len(missed)}",
        f"  Column A caught: {caught(missed, 'A')}",
        f"    Has crossing: {caught(mm_cross, 'A')} / {len(mm_cross)}",
        f"    No crossing: {caught(mm_nocross, 'A')} / {len(mm_nocross)}",
        f"  Column B caught: {caught(missed, 'B')}",
        f"    Has crossing: {caught(mm_cross, 'B')} / {len(mm_cross)}",
        f"    No crossing: {caught(mm_nocross, 'B')} / {len(mm_nocross)}",
        f"Correct makes: {len(correct)}",
        f"  Column A caught: {caught(correct, 'A')}",
        f"  Column B caught: {caught(correct, 'B')}",
        f"Real misses: {len(misses)}",
        f"  Column A fired on: {caught(misses, 'A')}",
        f"  Column B fired on: {caught(misses, 'B')}",
        "",
        "Nothing is applied to any detector.",
        "",
    ]
    (out_dir / "summary.md").write_text(
        "\n".join(summary_lines) + "\n", encoding="utf-8"
    )

    mm_lines = [
        "# Missed makes detail",
        "",
        "| # | film | t | start | A frames | A confs | B frames | B confs | crossing |",
        "|---|------|---|-------|----------|---------|----------|---------|----------|",
    ]
    for i, r in enumerate(missed, start=1):
        mm_lines.append(
            f"| {i} | {r['film']} | {r['t']} | {r.get('start','')} | "
            f"{r['column_a_frames']} | {[round(c, 3) for c in r['column_a_confs']]} | "
            f"{r['column_b_frames']} | {[round(c, 3) for c in r['column_b_confs']]} | "
            f"{r['has_crossing']} |"
        )
    mm_lines.append("")
    (out_dir / "missed_makes_detail.md").write_text(
        "\n".join(mm_lines) + "\n", encoding="utf-8"
    )

    cm_lines = [
        "# Correct makes detail (sanity check)",
        "",
        "| # | film | t | start | A hit | A frames | B hit | B frames | crossing |",
        "|---|------|---|-------|-------|----------|-------|----------|----------|",
    ]
    for i, r in enumerate(correct, start=1):
        cm_lines.append(
            f"| {i} | {r['film']} | {r['t']} | {r.get('start','')} | "
            f"{r['column_a_hit']} | {r['column_a_frames']} | "
            f"{r['column_b_hit']} | {r['column_b_frames']} | "
            f"{r['has_crossing']} |"
        )
    cm_lines.append("")
    (out_dir / "correct_makes_detail.md").write_text(
        "\n".join(cm_lines) + "\n", encoding="utf-8"
    )

    fired = [r for r in misses if r["column_a_hit"] or r["column_b_hit"]]
    fired_lines = [
        "# Misses fired on (either column)",
        "",
        f"Count: {len(fired)}",
        "",
    ]
    if not fired:
        fired_lines.append("(none)")
    else:
        fired_lines.append(
            "| film | t | start | A frames | B frames |"
        )
        fired_lines.append("|------|---|-------|----------|----------|")
        for r in fired:
            fired_lines.append(
                f"| {r['film']} | {r['t']} | {r.get('start','')} | "
                f"{r['column_a_frames']} | {r['column_b_frames']} |"
            )
    fired_lines.append("")
    (out_dir / "misses_fired_on.md").write_text(
        "\n".join(fired_lines) + "\n", encoding="utf-8"
    )


def print_console_summary(
    out_dir: Path,
    results: List[Dict[str, Any]],
    missed: List[Dict[str, Any]],
    correct: List[Dict[str, Any]],
    misses: List[Dict[str, Any]],
    crop_count: int,
    extra_miss_crops: int,
) -> None:
    def caught(rows: List[Dict[str, Any]], col: str) -> int:
        key = "column_a_hit" if col == "A" else "column_b_hit"
        return sum(1 for r in rows if r[key])

    mm_cross = [r for r in missed if r["has_crossing"]]
    mm_nocross = [r for r in missed if not r["has_crossing"]]

    print("=== BALL IN NET SUMMARY ===")
    print(f"Build shots: {len(results)}")
    print(f"Missed makes: {len(missed)}")
    print("  Column A (640x640 window):")
    print(f"    Caught (≥1 frame with ball in net): {caught(missed, 'A')}")
    print("    By crossing status:")
    print(f"      Has crossing: {caught(mm_cross, 'A')} caught / {len(mm_cross)}")
    print(f"      No crossing:  {caught(mm_nocross, 'A')} caught / {len(mm_nocross)}")
    print("  Column B (full frame):")
    print(f"    Caught (≥1 frame with ball in net): {caught(missed, 'B')}")
    print("    By crossing status:")
    print(f"      Has crossing: {caught(mm_cross, 'B')} caught / {len(mm_cross)}")
    print(f"      No crossing:  {caught(mm_nocross, 'B')} caught / {len(mm_nocross)}")
    print(f"Correct makes: {len(correct)}")
    print(
        f"  Column A: Caught (≥1 frame with ball in net): {caught(correct, 'A')}   <-- sanity check"
    )
    print(
        f"  Column B: Caught (≥1 frame with ball in net): {caught(correct, 'B')}   <-- sanity check"
    )
    print(f"Real misses: {len(misses)}")
    miss_a = caught(misses, "A")
    miss_b = caught(misses, "B")
    print(f"  Column A: Fired on (≥1 frame with ball in net): {miss_a}   <-- MUST BE 0")
    print(f"  Column B: Fired on (≥1 frame with ball in net): {miss_b}   <-- MUST BE 0")
    if miss_a != 0:
        print(f"FAIL: Column A expected 0 real misses fired, got {miss_a}")
    if miss_b != 0:
        print(f"FAIL: Column B expected 0 real misses fired, got {miss_b}")

    print("")
    print("Per missed make:")
    for i, r in enumerate(missed, start=1):
        cols = []
        if r["column_a_hit"]:
            cols.append("A")
        if r["column_b_hit"]:
            cols.append("B")
        col_s = ",".join(cols) if cols else "-"
        frames = sorted(set(r["column_a_frames"]) | set(r["column_b_frames"]))
        confs = r["column_a_confs"] + r["column_b_confs"]
        print(
            f"  missed_make_{i:02d} ({r['film']} t={r['t']}):  "
            f"detected at frames {frames}  "
            f"conf={[round(c, 2) for c in confs]}  "
            f"crossing={r['has_crossing']}  column={col_s}"
        )

    print("")
    print(f"Wrote: {out_dir / 'build_results.json'}")
    print(f"Wrote: {out_dir / 'summary.md'}")
    print(f"Wrote: {out_dir / 'missed_makes_detail.md'}")
    print(f"Wrote: {out_dir / 'correct_makes_detail.md'}")
    print(f"Wrote: {out_dir / 'misses_fired_on.md'}")
    print(
        f"Crops: {crop_count} PNGs in crops/ + {extra_miss_crops} real-miss crops"
    )
    print("STOP — measurement complete, no detector changes")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output folder (default: Liberty_Shot_Outputs/ball_in_net)",
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=None,
        help="Step-1 build results JSON (default: Liberty_Shot_Outputs/net_moved_build_results.json)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out is not None else default_out_dir()
    results_arg = Path(args.results) if args.results is not None else default_results_path()
    results_path = resolve_path(str(results_arg))
    if not results_path.exists():
        print(f"ERROR: results file not found: {results_arg} (resolved {results_path})")
        return 1

    ball_confidence, conf_source = load_ball_confidence()
    print(f"ball_confidence={ball_confidence} (from {conf_source})")

    raw_rows = json.loads(results_path.read_text(encoding="utf-8"))
    if not isinstance(raw_rows, list):
        print("ERROR: results JSON must be a list of shot rows")
        return 1

    rows = dedupe_by_film_t([r for r in raw_rows if r.get("set", "build") == "build"])
    missed_src, correct_src, misses_src = classify_shots(rows)

    print(
        f"Shot counts after dedupe: build={len(rows)} "
        f"missed_makes={len(missed_src)} correct_makes={len(correct_src)} "
        f"real_misses={len(misses_src)}"
    )
    if (
        len(rows) != EXPECTED_BUILD
        or len(missed_src) != EXPECTED_MISSED_MAKES
        or len(correct_src) != EXPECTED_CORRECT_MAKES
        or len(misses_src) != EXPECTED_REAL_MISSES
    ):
        print(
            "ERROR: expected "
            f"{EXPECTED_BUILD} shots = {EXPECTED_MISSED_MAKES} missed makes + "
            f"{EXPECTED_CORRECT_MAKES} correct makes + {EXPECTED_REAL_MISSES} real misses; "
            f"got {len(rows)} = {len(missed_src)} + {len(correct_src)} + {len(misses_src)}"
        )
        return 1

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        print(
            f"ERROR: ultralytics/torch not available ({exc}). "
            "Checker must run with the Windows venv."
        )
        return 1

    model_path = resolve_path(str(BALL_MODEL_PATH))
    if not model_path.exists():
        print(f"ERROR: ball detector not found: {BALL_MODEL_PATH}")
        return 1

    ball_model = YOLO(str(model_path))

    out_dir.mkdir(parents=True, exist_ok=True)
    crops_root = out_dir / "crops"
    crops_root.mkdir(parents=True, exist_ok=True)

    reader_cache: Dict[str, FrameReader] = {}

    def reader_for(row: Dict[str, Any]) -> FrameReader:
        key = row["video_path"]
        if key not in reader_cache:
            vp = resolve_path(key)
            if not vp.exists():
                raise FileNotFoundError(f"video not found: {key} -> {vp}")
            reader_cache[key] = FrameReader(vp)
        return reader_cache[key]

    try:
        measured: List[Dict[str, Any]] = []
        by_key: Dict[Tuple[str, int], Dict[str, Any]] = {}

        for i, row in enumerate(rows, start=1):
            reader = reader_for(row)
            m = measure_shot(row, reader, ball_model, ball_confidence)
            measured.append(m)
            by_key[(m["film"], m["t"])] = m
            print(
                f"[{i}/{len(rows)}] {m['film']} t={m['t']} "
                f"peak={m['peak_frame']} "
                f"A={m['column_a_hit']} B={m['column_b_hit']} "
                f"crossing={m['has_crossing']}",
                flush=True,
            )

        missed = [by_key[(r["film"], int(r["t"]))] for r in missed_src]
        correct = [by_key[(r["film"], int(r["t"]))] for r in correct_src]
        misses = [by_key[(r["film"], int(r["t"]))] for r in misses_src]

        (out_dir / "build_results.json").write_text(
            json.dumps(measured, indent=2), encoding="utf-8"
        )
        write_markdown_outputs(out_dir, measured, missed, correct, misses)

        # Crops for the 39 review-page shots
        crop_pairs = review_crop_shots(missed_src, correct_src, misses_src)
        review_keys = {(src["film"], int(src["t"])) for _, src in crop_pairs}
        crop_count = 0
        for shot_id, src_row in crop_pairs:
            key = (src_row["film"], int(src_row["t"]))
            m = by_key[key]
            reader = reader_for(src_row)
            frame_idx = first_detected_frame(m)
            frame = reader.read(frame_idx)
            dets = detections_on_frame(m, frame_idx)
            crop = draw_ball_in_net_crop(
                frame,
                m["hoop_x"],
                m["hoop_y"],
                m["hoop_w"],
                m["rim_r"],
                dets,
            )
            shot_dir = crops_root / shot_id
            shot_dir.mkdir(parents=True, exist_ok=True)
            out_png = shot_dir / "ball_in_net_010.png"
            cv2.imwrite(str(out_png), crop)
            crop_count += 1

        # Extra crops: every real miss either column fires on (front-of-rim risk)
        extra_miss_crops = 0
        for i, m in enumerate(misses, start=1):
            if not (m["column_a_hit"] or m["column_b_hit"]):
                continue
            key = (m["film"], m["t"])
            # Skip if already in the 10 review miss slots
            already = key in review_keys
            shot_id = f"miss_fired_{i:02d}_{m['film']}_t{m['t']}"
            if already:
                # Still write a dedicated fired crop so Scott can find all fires
                pass
            reader = reader_for(m)
            frame_idx = first_detected_frame(m)
            frame = reader.read(frame_idx)
            dets = detections_on_frame(m, frame_idx)
            crop = draw_ball_in_net_crop(
                frame,
                m["hoop_x"],
                m["hoop_y"],
                m["hoop_w"],
                m["rim_r"],
                dets,
            )
            shot_dir = crops_root / shot_id
            shot_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(shot_dir / "ball_in_net_010.png"), crop)
            extra_miss_crops += 1

        print("")
        print_console_summary(
            out_dir,
            measured,
            missed,
            correct,
            misses,
            crop_count,
            extra_miss_crops,
        )
        return 0
    finally:
        for r in reader_cache.values():
            r.close()


if __name__ == "__main__":
    raise SystemExit(main())
