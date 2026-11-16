"""Learned make/miss (spec 47). Labels, features, LOGO, final fit.

NEW file only. Settings S1-S9 fixed; Claude Code V1-V8 override Hermes text.
No video/models in tests. applied_to_core stays false.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import find_shots_measure as fsm  # noqa: E402

# S2 / V1 — named constant; do not change
MATCH_LABEL_MS = 4000

# S4 — fixed band and model settings
P_MAKE = 0.80
P_MISS = 0.20
LR_C = 1.0
LR_MAX_ITER = 1000
LR_CLASS_WEIGHT = "balanced"

FILMS = ("adrian", "notus", "gv")

FEATURE_NAMES = [
    "F1_v6_count",
    "F2_bodd_count",
    "F3_has_crossing",
    "F4_crossing_x_hw",
    "F5_max_depth_hw",
    "F6_in_column_count",
    "F7_max_upward_hw",
    "F8_max_x_10f_hw",
    "F9_bodd_has_crossing",
    "F10_bodd_crossing_x_hw",
    "F11_bodd_max_depth_hw",
    "F12_net_motion_after",
    "F13_net_motion_before",
    "F14_v6_new_pred",
    "F15_d2v1_new_pred",
]

FrameReader = Callable[[int], Optional[np.ndarray]]


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def load_moment_times(moments_paths: Sequence[Path]) -> List[int]:
    """Collect moment t_ms from one or more finder moments.json files."""
    times: List[int] = []
    seen: set[int] = set()

    def _add(t: int) -> None:
        if t not in seen:
            seen.add(t)
            times.append(t)

    for path in moments_paths:
        doc = _load_json(path)
        moments = doc.get("moments") if isinstance(doc, dict) else doc
        if isinstance(moments, list):
            for m in moments:
                _add(int(m["t_ms"]))
        elif isinstance(moments, dict):
            for k, v in moments.items():
                if isinstance(v, dict) and "t_ms" in v:
                    _add(int(v["t_ms"]))
                else:
                    _add(int(k))
        else:
            raise SystemExit(f"moments json must have a moments list/dict: {path}")
    times.sort()
    return times


def _in_span(t: int, span_start: Optional[int], span_end: Optional[int]) -> bool:
    if span_start is not None and t < int(span_start):
        return False
    if span_end is not None and t > int(span_end):
        return False
    return True


# ---------------------------------------------------------------------------
# labels (S2 + V1/V2/V6)
# ---------------------------------------------------------------------------


def _nearest_make_tag(
    moment_t: int, make_tag_times: Sequence[int]
) -> Tuple[Optional[int], Optional[int]]:
    if not make_tag_times:
        return None, None
    best_t = min(make_tag_times, key=lambda tt: abs(tt - moment_t))
    return int(best_t), int(best_t - moment_t)


def label_moments_from_tags(
    moment_times: Sequence[int],
    tags: Sequence[Dict[str, Any]],
    *,
    span_start_ms: Optional[int] = None,
    span_end_ms: Optional[int] = None,
    window_ms: int = MATCH_LABEL_MS,
) -> Dict[str, Any]:
    """Match finder moments to coach tags (Adrian/Notus). Tag time field is 't'."""
    moments = [
        int(t)
        for t in moment_times
        if _in_span(int(t), span_start_ms, span_end_ms)
    ]
    tag_rows = [
        tag
        for tag in tags
        if _in_span(int(tag["t"]), span_start_ms, span_end_ms)
    ]
    tag_times = [int(tag["t"]) for tag in tag_rows]
    make_tag_times = [
        int(tag["t"]) for tag in tag_rows if tag.get("result") == "Make"
    ]

    match = fsm.match_shot_indices(tag_times, moments, window_ms)
    matched_finder: Dict[int, Tuple[int, int]] = {}
    for ti, fi, _delta in match["matches"]:
        matched_finder[int(fi)] = (int(ti), int(tag_times[ti]))

    rows: List[Dict[str, Any]] = []
    excluded_list: List[Dict[str, Any]] = []
    n1 = n0 = n_ex = 0
    n1_tag = 0

    for fi, mt in enumerate(moments):
        if fi in matched_finder:
            ti, tag_t = matched_finder[fi]
            result = tag_rows[ti].get("result")
            label = 1 if result == "Make" else 0
            rows.append(
                {
                    "moment_t_ms": mt,
                    "label": label,
                    "source": "tag",
                    "matched_tag_t_ms": tag_t,
                    "excluded_reason": None,
                }
            )
            if label == 1:
                n1 += 1
                n1_tag += 1
            else:
                n0 += 1
            continue

        near_t, near_delta = _nearest_make_tag(mt, make_tag_times)
        if near_t is not None and abs(int(near_delta)) <= window_ms:
            rows.append(
                {
                    "moment_t_ms": mt,
                    "label": None,
                    "source": "tag",
                    "matched_tag_t_ms": None,
                    "excluded_reason": "near_make_tag",
                }
            )
            excluded_list.append(
                {
                    "moment_t_ms": mt,
                    "nearest_make_tag_t_ms": near_t,
                    "delta_ms": int(near_delta) if near_delta is not None else None,
                }
            )
            n_ex += 1
        else:
            rows.append(
                {
                    "moment_t_ms": mt,
                    "label": 0,
                    "source": "tag",
                    "matched_tag_t_ms": None,
                    "excluded_reason": None,
                }
            )
            n0 += 1

    finder_missed: List[Dict[str, Any]] = []
    for ti in match["unmatched_tags"]:
        tag = tag_rows[int(ti)]
        finder_missed.append(
            {
                "tag_t_ms": int(tag["t"]),
                "result": tag.get("result"),
            }
        )

    return {
        "rows": rows,
        "counts": {
            "label_1": n1,
            "label_0": n0,
            "excluded": n_ex,
            "finder_missed": len(finder_missed),
            "label_1_from_tag": n1_tag,
            "label_1_from_gv": 0,
        },
        "excluded": excluded_list,
        "finder_missed": finder_missed,
    }


def label_moments_from_gv(
    moment_times: Sequence[int],
    gv_labels: Dict[str, Any],
    *,
    span_start_ms: Optional[int] = None,
    span_end_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Label moments from 44_gv_labels.json (key = moment t_ms string)."""
    moments_map = gv_labels.get("moments") if isinstance(gv_labels, dict) else gv_labels
    if not isinstance(moments_map, dict):
        raise SystemExit("gv labels must be an object with moments")

    moments = [
        int(t)
        for t in moment_times
        if _in_span(int(t), span_start_ms, span_end_ms)
    ]
    rows: List[Dict[str, Any]] = []
    excluded_list: List[Dict[str, Any]] = []
    n1 = n0 = n_ex = 0
    n1_gv = 0

    for mt in moments:
        lab = moments_map.get(str(mt))
        if lab is None:
            # moment with no GV entry: treat as excluded (unclear)
            rows.append(
                {
                    "moment_t_ms": mt,
                    "label": None,
                    "source": "gv_labels",
                    "matched_tag_t_ms": None,
                    "excluded_reason": "missing_gv_label",
                }
            )
            excluded_list.append(
                {
                    "moment_t_ms": mt,
                    "nearest_make_tag_t_ms": None,
                    "delta_ms": None,
                }
            )
            n_ex += 1
            continue

        shot = lab.get("shot")
        result = lab.get("result")
        if shot == "unclear" or (
            shot == "yes" and result not in ("make", "miss")
        ):
            rows.append(
                {
                    "moment_t_ms": mt,
                    "label": None,
                    "source": "gv_labels",
                    "matched_tag_t_ms": None,
                    "excluded_reason": "unclear",
                }
            )
            excluded_list.append(
                {
                    "moment_t_ms": mt,
                    "nearest_make_tag_t_ms": None,
                    "delta_ms": None,
                }
            )
            n_ex += 1
            continue

        if shot == "yes" and result == "make":
            label = 1
            matched = mt  # marks real shot for false-make split
        elif shot == "yes" and result == "miss":
            label = 0
            matched = mt
        elif shot == "no":
            label = 0
            matched = None  # non-shot
        else:
            rows.append(
                {
                    "moment_t_ms": mt,
                    "label": None,
                    "source": "gv_labels",
                    "matched_tag_t_ms": None,
                    "excluded_reason": "unclear",
                }
            )
            excluded_list.append(
                {
                    "moment_t_ms": mt,
                    "nearest_make_tag_t_ms": None,
                    "delta_ms": None,
                }
            )
            n_ex += 1
            continue

        rows.append(
            {
                "moment_t_ms": mt,
                "label": label,
                "source": "gv_labels",
                "matched_tag_t_ms": matched,
                "excluded_reason": None,
            }
        )
        if label == 1:
            n1 += 1
            n1_gv += 1
        else:
            n0 += 1

    return {
        "rows": rows,
        "counts": {
            "label_1": n1,
            "label_0": n0,
            "excluded": n_ex,
            "finder_missed": 0,
            "label_1_from_tag": 0,
            "label_1_from_gv": n1_gv,
        },
        "excluded": excluded_list,
        "finder_missed": [],
    }


def build_labels_doc(
    film: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "film": film,
        "match_label_ms": MATCH_LABEL_MS,
        "rows": payload["rows"],
        "counts": payload["counts"],
        "excluded": payload["excluded"],
        "finder_missed": payload["finder_missed"],
    }


def cmd_labels(args: argparse.Namespace) -> int:
    film = str(args.film)
    moments = load_moment_times(list(args.moments_json))
    if film == "gv":
        if args.gv_labels is None:
            raise SystemExit("labels --film gv requires --gv-labels")
        gv = _load_json(args.gv_labels)
        payload = label_moments_from_gv(
            moments,
            gv,
            span_start_ms=args.span_start_ms,
            span_end_ms=args.span_end_ms,
        )
    else:
        if args.tags is None:
            raise SystemExit(f"labels --film {film} requires --tags")
        tags = fsm.load_shot_tags(Path(args.tags))
        payload = label_moments_from_tags(
            moments,
            tags,
            span_start_ms=args.span_start_ms,
            span_end_ms=args.span_end_ms,
            window_ms=MATCH_LABEL_MS,
        )
    doc = build_labels_doc(film, payload)
    out = Path(args.out)
    _write_json(out, doc)
    c = doc["counts"]
    print(
        f"{film}: label_1={c['label_1']} label_0={c['label_0']} "
        f"excluded={c['excluded']} finder_missed={c['finder_missed']} "
        f"label_1_from_tag={c['label_1_from_tag']} "
        f"label_1_from_gv={c['label_1_from_gv']}"
    )
    if doc["excluded"]:
        print("excluded moments:")
        for ex in doc["excluded"]:
            print(
                f"  t_ms={ex['moment_t_ms']} "
                f"nearest_make={ex.get('nearest_make_tag_t_ms')} "
                f"delta_ms={ex.get('delta_ms')}"
            )
    print(f"wrote {out} sha256={_sha256_file(out)}")
    return 0


# ---------------------------------------------------------------------------
# features F1-F15 (S3 + V3/V4)
# ---------------------------------------------------------------------------


def _series_points(series: Any) -> List[Tuple[int, float, float]]:
    out: List[Tuple[int, float, float]] = []
    if not series:
        return out
    for pt in series:
        if pt is None or len(pt) < 3:
            continue
        out.append((int(pt[0]), float(pt[1]), float(pt[2])))
    return out


def _hoop_center_width(
    hoop: Any,
) -> Optional[Tuple[float, float, float]]:
    if hoop is None:
        return None
    if isinstance(hoop, (list, tuple)) and len(hoop) >= 3:
        return float(hoop[0]), float(hoop[1]), float(hoop[2])
    return None


def find_crossing(
    points: Sequence[Tuple[int, float, float]], hy: float
) -> Optional[Tuple[int, float, float, int]]:
    """First consecutive pair with y < hy then y >= hy.

    Returns (frame, x, y, index_of_second_point) or None.
    """
    for i in range(len(points) - 1):
        _f0, _x0, y0 = points[i]
        f1, x1, y1 = points[i + 1]
        if y0 < hy and y1 >= hy:
            return int(f1), float(x1), float(y1), i + 1
    return None


def _crossing_features(
    points: Sequence[Tuple[int, float, float]],
    hx: float,
    hy: float,
    hw: float,
) -> Tuple[float, float, float, float, float]:
    """Return (F3, F4, F5, F7, F8) for one series. F6 is separate (no crossing)."""
    if hw == 0:
        hw = 1.0  # avoid div0; distances still computed — choice: treat as 1
    cross = find_crossing(points, hy)
    if cross is None:
        return 0.0, 3.0, 0.0, 0.0, 3.0
    f_cross, x_cross, _y_cross, idx = cross
    f3 = 1.0
    f4 = abs(x_cross - hx) / hw
    # F5: max depth after crossing with |x-hx| < 0.6 hw
    depths: List[float] = []
    for j in range(idx + 1, len(points)):
        _f, x, y = points[j]
        if abs(x - hx) < 0.6 * hw:
            depths.append((y - hy) / hw)
    f5 = max(depths) if depths else 0.0
    # F7: largest upward move (screen y decreases) after crossing, in hw
    ups: List[float] = []
    after = points[idx:]
    for a, b in zip(after, after[1:]):
        ups.append((a[2] - b[2]) / hw)  # positive = upward
    f7 = max(ups) if ups else 0.0
    # F8: max |x-hx|/hw over frames in (f_cross, f_cross+10]
    xs: List[float] = []
    for f, x, _y in points:
        if f_cross < f <= f_cross + 10:
            xs.append(abs(x - hx) / hw)
    f8 = max(xs) if xs else 3.0
    return f3, f4, f5, f7, f8


def _f6_column_count(
    points: Sequence[Tuple[int, float, float]],
    hx: float,
    hy: float,
    hw: float,
) -> float:
    if hw == 0:
        hw = 1.0
    n = 0
    for _f, x, y in points:
        depth = (y - hy) / hw
        if 0 < depth < 2.5 and abs(x - hx) < 0.6 * hw:
            n += 1
    return float(n)


def _clip_box(
    x0: float, y0: float, x1: float, y1: float, w: int, h: int
) -> Optional[Tuple[int, int, int, int]]:
    xa = int(max(0, min(w, round(x0))))
    xb = int(max(0, min(w, round(x1))))
    ya = int(max(0, min(h, round(y0))))
    yb = int(max(0, min(h, round(y1))))
    if xb <= xa or yb <= ya:
        return None
    return xa, ya, xb, yb


def mean_abs_gray_diff(
    frames: Sequence[np.ndarray],
    box: Tuple[int, int, int, int],
) -> float:
    """Mean absolute grayscale difference across consecutive frames in box."""
    if len(frames) < 2:
        return 0.0
    x0, y0, x1, y1 = box
    diffs: List[float] = []
    prev = None
    for fr in frames:
        if fr is None:
            prev = None
            continue
        if fr.ndim == 3:
            gray = np.mean(fr.astype(np.float64), axis=2)
        else:
            gray = fr.astype(np.float64)
        patch = gray[y0:y1, x0:x1]
        if patch.size == 0:
            prev = None
            continue
        if prev is not None and prev.shape == patch.shape:
            diffs.append(float(np.mean(np.abs(patch - prev))))
        prev = patch
    if not diffs:
        return 0.0
    return float(sum(diffs) / len(diffs))


def net_motion_ratio(
    read_frame: FrameReader,
    *,
    hx: float,
    hy: float,
    hw: float,
    center_frame: int,
    after: bool,
    n_frames: int = 12,
) -> float:
    """F12 (after=True) / F13 (after=False). Empty box or denom 0 -> 0."""
    if after:
        frame_ids = list(range(center_frame, center_frame + n_frames + 1))
    else:
        frame_ids = list(range(center_frame - n_frames, center_frame + 1))

    frames: List[Optional[np.ndarray]] = []
    h = w = None
    for fid in frame_ids:
        fr = read_frame(int(fid))
        frames.append(fr)
        if fr is not None and h is None:
            h, w = int(fr.shape[0]), int(fr.shape[1])
    if h is None or w is None:
        return 0.0

    # primary box: x hx ± 0.5 hw, y hy .. hy + 1.2 hw
    primary = _clip_box(hx - 0.5 * hw, hy, hx + 0.5 * hw, hy + 1.2 * hw, w, h)
    # side box same size at x hx + 1.5 hw (center shifted +1.5 hw)
    side = _clip_box(
        hx + 1.5 * hw - 0.5 * hw,
        hy,
        hx + 1.5 * hw + 0.5 * hw,
        hy + 1.2 * hw,
        w,
        h,
    )
    if primary is None or side is None:
        return 0.0
    # drop None frames for measure; mean_abs handles gaps by resetting prev
    valid = [f for f in frames if f is not None]
    if len(valid) < 2:
        return 0.0
    # Use aligned list (with Nones) so temporal gaps don't invent diffs
    num = mean_abs_gray_diff([f for f in frames], primary)
    den = mean_abs_gray_diff([f for f in frames], side)
    if den == 0.0:
        return 0.0
    return float(num / den)


def open_video_reader(video_path: Path) -> Tuple[float, FrameReader, Callable[[], None]]:
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise SystemExit(f"cannot open video: {video_path}")
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)

    def read_frame(frame_idx: int) -> Optional[np.ndarray]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_idx))
        ok, frame = cap.read()
        if not ok:
            return None
        return frame

    def close() -> None:
        cap.release()

    return fps, read_frame, close


def _pred_by_t(results: Any) -> Dict[int, float]:
    """Map track start t -> new_pred as 0/1 float."""
    shots = results.get("shots") if isinstance(results, dict) else results
    out: Dict[int, float] = {}
    if isinstance(shots, list):
        for row in shots:
            if not isinstance(row, dict) or "t" not in row:
                continue
            pred = row.get("new_pred")
            out[int(row["t"])] = 1.0 if pred else 0.0
    elif isinstance(shots, dict):
        for row in shots.get("shots", shots) if False else []:
            pass
    return out


def compute_features_for_track(
    track: Dict[str, Any],
    *,
    fps: float,
    read_frame: Optional[FrameReader],
    v6_pred: float,
    d2_pred: float,
) -> List[float]:
    """F1-F15 for one track. V4 no-hoop sentinels. V3 frame offsets."""
    ball = _series_points(track.get("ball"))
    bodd = _series_points(track.get("bodd"))
    f1 = float(len(ball))
    f2 = float(len(bodd))
    hoop = _hoop_center_width(track.get("hoop"))

    if hoop is None:
        # V4
        return [
            f1,
            f2,
            0.0,  # F3
            3.0,  # F4
            0.0,  # F5
            0.0,  # F6
            0.0,  # F7
            3.0,  # F8
            0.0,  # F9
            3.0,  # F10
            0.0,  # F11
            0.0,  # F12
            0.0,  # F13
            0.0,  # F14
            0.0,  # F15
        ]

    hx, hy, hw = hoop
    f3, f4, f5, f7, f8 = _crossing_features(ball, hx, hy, hw)
    f6 = _f6_column_count(ball, hx, hy, hw)
    f9, f10, f11, _f7b, _f8b = _crossing_features(bodd, hx, hy, hw)
    # F9-F11 = F3,F4,F5 on bodd only
    f9 = f9
    f10 = f10
    f11 = f11

    start_ms = int(track["t"])
    start_frame = int(round(start_ms / 1000.0 * float(fps)))
    moment_t_ms = int(track.get("moment_t_ms", start_ms))
    moment_frame = int(round(moment_t_ms / 1000.0 * float(fps)))

    cross = find_crossing(ball, hy)
    if cross is None:
        center_frame = moment_frame
    else:
        center_frame = start_frame + int(cross[0])

    if read_frame is None:
        f12 = 0.0
        f13 = 0.0
    else:
        f12 = net_motion_ratio(
            read_frame, hx=hx, hy=hy, hw=hw, center_frame=center_frame, after=True
        )
        f13 = net_motion_ratio(
            read_frame, hx=hx, hy=hy, hw=hw, center_frame=center_frame, after=False
        )

    f14 = float(v6_pred)
    f15 = float(d2_pred)
    return [f1, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12, f13, f14, f15]


def build_features_doc(
    tracks: Sequence[Dict[str, Any]],
    *,
    fps: float,
    read_frame: Optional[FrameReader],
    v6_results: Any,
    d2_results: Any,
) -> Dict[str, Any]:
    v6_by_t = _pred_by_t(v6_results)
    d2_by_t = _pred_by_t(d2_results)
    rows: List[Dict[str, Any]] = []
    for track in tracks:
        start_ms = int(track["t"])
        moment_t_ms = int(track.get("moment_t_ms", start_ms))
        hoop = _hoop_center_width(track.get("hoop"))
        if hoop is None:
            v6_p = 0.0
            d2_p = 0.0
        else:
            v6_p = v6_by_t.get(start_ms, 0.0)
            d2_p = d2_by_t.get(start_ms, 0.0)
        feats = compute_features_for_track(
            track,
            fps=fps,
            read_frame=read_frame,
            v6_pred=v6_p,
            d2_pred=d2_p,
        )
        rows.append({"moment_t_ms": moment_t_ms, "features": feats})
    return {"feature_names": list(FEATURE_NAMES), "rows": rows}


def cmd_features(args: argparse.Namespace) -> int:
    tracks = _load_json(args.tracks_json)
    if not isinstance(tracks, list):
        raise SystemExit("tracks-json must be a list")
    v6 = _load_json(args.v6_results)
    d2 = _load_json(args.d2v1_results)
    fps, read_frame, close = open_video_reader(Path(args.video))
    try:
        doc = build_features_doc(
            tracks,
            fps=fps,
            read_frame=read_frame,
            v6_results=v6,
            d2_results=d2,
        )
    finally:
        close()
    out = Path(args.out)
    _write_json(out, doc)
    print(f"wrote {out} rows={len(doc['rows'])} sha256={_sha256_file(out)}")
    return 0


# ---------------------------------------------------------------------------
# freeze / sha256 (V6)
# ---------------------------------------------------------------------------


def collect_freeze_files(dir_path: Path) -> Dict[str, str]:
    dir_path = Path(dir_path)
    out: Dict[str, str] = {}
    for path in sorted(dir_path.glob("labels_*.json")):
        out[path.name] = _sha256_file(path)
    for path in sorted(dir_path.glob("features_*.json")):
        out[path.name] = _sha256_file(path)
    return out


def cmd_freeze(args: argparse.Namespace) -> int:
    dir_path = Path(args.dir)
    frozen = collect_freeze_files(dir_path)
    out = dir_path / "frozen.json"
    _write_json(out, frozen)
    print(f"wrote {out} ({len(frozen)} files)")
    for name, digest in frozen.items():
        print(f"  {name} {digest}")
    return 0


def check_frozen(dir_path: Path) -> None:
    frozen_path = Path(dir_path) / "frozen.json"
    if not frozen_path.exists():
        raise SystemExit(f"missing frozen.json in {dir_path}")
    frozen = _load_json(frozen_path)
    current = collect_freeze_files(dir_path)
    for name, digest in frozen.items():
        if name not in current:
            raise SystemExit(f"frozen file missing: {name}")
        if current[name] != digest:
            raise SystemExit(
                f"sha256 mismatch for {name}: frozen={digest} now={current[name]}"
            )
    for name in current:
        if name not in frozen:
            raise SystemExit(f"unfrozen file present: {name}")


# ---------------------------------------------------------------------------
# band + counting (S4 / V5 / S6)
# ---------------------------------------------------------------------------


def band_call(p: float) -> str:
    """S4: p >= 0.80 make, p <= 0.20 miss, else coach. Edges inclusive."""
    if p >= P_MAKE:
        return "make"
    if p <= P_MISS:
        return "miss"
    return "coach"


def normalize_rule_call(call: str) -> str:
    """V5: no_track counted as coach for coach_load."""
    if call == "no_track":
        return "coach"
    return call


def is_real_miss_row(row: Dict[str, Any]) -> bool:
    """label 0 + matched tag/gv real shot => real miss; unmatched => non-shot."""
    if row.get("label") != 0:
        return False
    return row.get("matched_tag_t_ms") is not None


def is_non_shot_row(row: Dict[str, Any]) -> bool:
    if row.get("label") != 0:
        return False
    return row.get("matched_tag_t_ms") is None


def count_side(
    calls: Dict[int, str],
    label_rows: Sequence[Dict[str, Any]],
) -> Dict[str, int]:
    """V5 counting over scored moments (label 0 or 1 only)."""
    makes_found = 0
    real_makes = 0
    real_misses_called_make = 0
    non_shots_called_make = 0
    coach_load = 0
    silent_makes = 0
    n_scored = 0

    for row in label_rows:
        label = row.get("label")
        if label not in (0, 1):
            continue
        mt = int(row["moment_t_ms"])
        if mt not in calls:
            continue
        n_scored += 1
        call = normalize_rule_call(str(calls[mt]))
        if label == 1:
            real_makes += 1
            if call == "make":
                makes_found += 1
            elif call == "miss":
                silent_makes += 1
            elif call == "coach":
                coach_load += 1
        else:
            if call == "make":
                if is_real_miss_row(row):
                    real_misses_called_make += 1
                else:
                    non_shots_called_make += 1
            elif call == "coach":
                coach_load += 1

    false_makes = real_misses_called_make + non_shots_called_make
    return {
        "n_scored": n_scored,
        "real_makes": real_makes,
        "makes_found": makes_found,
        "real_misses_called_make": real_misses_called_make,
        "non_shots_called_make": non_shots_called_make,
        "false_makes": false_makes,
        "coach_load": coach_load,
        "silent_makes": silent_makes,
    }


def pass_bar(learned: Dict[str, int], rules: Dict[str, int]) -> bool:
    """S6: makes_found >= rules, false_makes <= rules, coach_load <= rules."""
    return (
        learned["makes_found"] >= rules["makes_found"]
        and learned["false_makes"] <= rules["false_makes"]
        and learned["coach_load"] <= rules["coach_load"]
    )


def load_rule_calls(path: Path) -> Dict[int, str]:
    doc = _load_json(path)
    rows = doc if isinstance(doc, list) else doc.get("rows") or doc.get("shots") or []
    out: Dict[int, str] = {}
    for row in rows:
        mt = int(row["moment_t_ms"])
        out[mt] = str(row["call"])
    return out


def load_scored_xy(
    labels_doc: Dict[str, Any],
    features_doc: Dict[str, Any],
) -> Tuple[np.ndarray, np.ndarray, List[int], List[Dict[str, Any]]]:
    """Scored moments = label 0/1 with a feature row. Returns X, y, times, label_rows."""
    feat_by_t = {
        int(r["moment_t_ms"]): [float(v) for v in r["features"]]
        for r in features_doc["rows"]
    }
    xs: List[List[float]] = []
    ys: List[int] = []
    times: List[int] = []
    kept: List[Dict[str, Any]] = []
    for row in labels_doc["rows"]:
        label = row.get("label")
        if label not in (0, 1):
            continue
        mt = int(row["moment_t_ms"])
        if mt not in feat_by_t:
            continue
        xs.append(feat_by_t[mt])
        ys.append(int(label))
        times.append(mt)
        kept.append(row)
    if not xs:
        return (
            np.zeros((0, len(FEATURE_NAMES)), dtype=float),
            np.zeros((0,), dtype=int),
            [],
            [],
        )
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=int), times, kept


def make_pipeline():
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    return Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "clf",
                LogisticRegression(
                    C=LR_C,
                    class_weight=LR_CLASS_WEIGHT,
                    max_iter=LR_MAX_ITER,
                ),
            ),
        ]
    )


def predict_proba_make(pipeline, X: np.ndarray) -> np.ndarray:
    """Probability of class 1 (make)."""
    if X.shape[0] == 0:
        return np.zeros((0,), dtype=float)
    proba = pipeline.predict_proba(X)
    classes = list(pipeline.named_steps["clf"].classes_)
    if 1 in classes:
        idx = classes.index(1)
        return proba[:, idx]
    # training had only one class
    if classes[0] == 1:
        return np.ones((X.shape[0],), dtype=float)
    return np.zeros((X.shape[0],), dtype=float)


# ---------------------------------------------------------------------------
# logo (S5/S6/V5/V6/V7)
# ---------------------------------------------------------------------------


def run_logo(
    *,
    data: Dict[str, Dict[str, Any]],
    rule_calls: Dict[str, Dict[int, str]],
) -> Dict[str, Any]:
    """3-fold LOGO. data[film] = {labels, features, X, y, times, label_rows}."""
    folds = []
    all_preds: Dict[str, List[Dict[str, Any]]] = {}
    all_pass = True

    for hold in FILMS:
        train_films = [f for f in FILMS if f != hold]
        X_train = np.concatenate([data[f]["X"] for f in train_films], axis=0)
        y_train = np.concatenate([data[f]["y"] for f in train_films], axis=0)
        X_test = data[hold]["X"]
        y_test = data[hold]["y"]
        times = data[hold]["times"]
        label_rows = data[hold]["label_rows"]

        pipe = make_pipeline()
        # assert-friendly: scaler fitted on training rows only
        pipe.fit(X_train, y_train)
        scaler = pipe.named_steps["scaler"]
        n_train = int(X_train.shape[0])
        p = predict_proba_make(pipe, X_test)
        learned_calls: Dict[int, str] = {}
        pred_rows: List[Dict[str, Any]] = []
        for i, mt in enumerate(times):
            prob = float(p[i]) if i < len(p) else 0.0
            call = band_call(prob)
            learned_calls[mt] = call
            pred_rows.append(
                {
                    "film": hold,
                    "moment_t_ms": mt,
                    "p": prob,
                    "call": call,
                    "label": int(y_test[i]),
                }
            )
        all_preds[hold] = pred_rows

        learned_counts = count_side(learned_calls, label_rows)
        rules_counts = count_side(rule_calls[hold], label_rows)
        ok = pass_bar(learned_counts, rules_counts)
        if not ok:
            all_pass = False
        folds.append(
            {
                "hold_out": hold,
                "train_films": train_films,
                "n_train": n_train,
                "scaler_n_samples_seen": int(getattr(scaler, "n_samples_seen_", n_train)),
                "learned": learned_counts,
                "rules": rules_counts,
                "pass": ok,
            }
        )

    return {
        "folds": folds,
        "all_pass": all_pass,
        "preds": all_preds,
    }


def _logo_report_md(report: Dict[str, Any]) -> str:
    lines = [
        "# LOGO report (spec 47)",
        "",
        f"- all_pass: {report['all_pass']}",
        "",
    ]
    for fold in report["folds"]:
        hold = fold["hold_out"]
        L = fold["learned"]
        R = fold["rules"]
        lines.extend(
            [
                f"## Hold out {hold} ({'PASS' if fold['pass'] else 'FAIL'})",
                "",
                f"- train_films: {', '.join(fold['train_films'])}",
                f"- makes_found: learned {L['makes_found']}/{L['real_makes']} vs rules {R['makes_found']}/{R['real_makes']}",
                f"- real_misses_called_make: learned {L['real_misses_called_make']} vs rules {R['real_misses_called_make']}",
                f"- non_shots_called_make: learned {L['non_shots_called_make']} vs rules {R['non_shots_called_make']}",
                f"- false_makes: learned {L['false_makes']} vs rules {R['false_makes']}",
                f"- coach_load: learned {L['coach_load']} vs rules {R['coach_load']}",
                f"- silent_makes: learned {L['silent_makes']} vs rules {R['silent_makes']}",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def cmd_logo(args: argparse.Namespace) -> int:
    dir_path = Path(args.dir)
    check_frozen(dir_path)

    data: Dict[str, Dict[str, Any]] = {}
    for film in FILMS:
        labels_path = dir_path / f"labels_{film}.json"
        features_path = dir_path / f"features_{film}.json"
        if not labels_path.exists() or not features_path.exists():
            raise SystemExit(f"missing labels/features for {film}")
        print(f"features sha256 {film}={_sha256_file(features_path)}")
        labels_doc = _load_json(labels_path)
        features_doc = _load_json(features_path)
        X, y, times, label_rows = load_scored_xy(labels_doc, features_doc)
        data[film] = {
            "labels": labels_doc,
            "features": features_doc,
            "X": X,
            "y": y,
            "times": times,
            "label_rows": label_rows,
        }

    rule_paths = {
        "adrian": Path(args.rules_adrian),
        "notus": Path(args.rules_notus),
        "gv": Path(args.rules_gv),
    }
    rule_calls = {film: load_rule_calls(path) for film, path in rule_paths.items()}

    result = run_logo(data=data, rule_calls=rule_calls)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "all_pass": result["all_pass"],
        "folds": [
            {k: v for k, v in fold.items()}
            for fold in result["folds"]
        ],
        "settings": {
            "C": LR_C,
            "class_weight": LR_CLASS_WEIGHT,
            "max_iter": LR_MAX_ITER,
            "p_make": P_MAKE,
            "p_miss": P_MISS,
            "match_label_ms": MATCH_LABEL_MS,
        },
    }
    report_path = out_dir / "logo_report.json"
    md_text = _logo_report_md(report)
    _write_json(report_path, report)
    (out_dir / "logo_report.md").write_text(md_text, encoding="utf-8")
    _write_json(out_dir / "logo_preds.json", result["preds"])
    # final --dir reads logo_report.json from --dir
    if out_dir.resolve() != dir_path.resolve():
        _write_json(dir_path / "logo_report.json", report)
        (dir_path / "logo_report.md").write_text(md_text, encoding="utf-8")
        _write_json(dir_path / "logo_preds.json", result["preds"])

    for fold in result["folds"]:
        status = "PASS" if fold["pass"] else "FAIL"
        print(
            f"LOGO hold={fold['hold_out']} {status} "
            f"makes {fold['learned']['makes_found']}/{fold['learned']['real_makes']} "
            f"(rules {fold['rules']['makes_found']}) "
            f"false {fold['learned']['false_makes']} (rules {fold['rules']['false_makes']}) "
            f"coach {fold['learned']['coach_load']} (rules {fold['rules']['coach_load']})"
        )
    print(f"wrote {report_path}")
    if not result["all_pass"]:
        print("S6 fail -> stop for Scott (V8); no second LOGO run")
        return 3
    return 0


# ---------------------------------------------------------------------------
# final (S7)
# ---------------------------------------------------------------------------


def cmd_final(args: argparse.Namespace) -> int:
    dir_path = Path(args.dir)
    report_path = dir_path / "logo_report.json"
    if not report_path.exists():
        raise SystemExit(f"missing {report_path}")
    report = _load_json(report_path)
    if not report.get("all_pass"):
        raise SystemExit("final refuses: LOGO all_pass is false")

    check_frozen(dir_path)

    Xs = []
    ys = []
    for film in FILMS:
        labels_doc = _load_json(dir_path / f"labels_{film}.json")
        features_doc = _load_json(dir_path / f"features_{film}.json")
        X, y, _times, _rows = load_scored_xy(labels_doc, features_doc)
        Xs.append(X)
        ys.append(y)
    X_all = np.concatenate(Xs, axis=0)
    y_all = np.concatenate(ys, axis=0)

    pipe = make_pipeline()
    pipe.fit(X_all, y_all)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    import joblib

    model_path = out_dir / "model.joblib"
    joblib.dump(pipe, model_path)
    feat_list_path = out_dir / "feature_list.json"
    _write_json(feat_list_path, list(FEATURE_NAMES))
    digest = _sha256_file(model_path)
    (out_dir / "sha256.txt").write_text(digest + "\n", encoding="utf-8")
    print(f"wrote {model_path} sha256={digest}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Learned make/miss (spec 47)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_lab = sub.add_parser("labels", help="Build labels_<film>.json (S2)")
    p_lab.add_argument("--film", choices=list(FILMS), required=True)
    p_lab.add_argument("--moments-json", type=Path, nargs="+", required=True)
    p_lab.add_argument("--out", type=Path, required=True)
    p_lab.add_argument("--tags", type=Path, default=None)
    p_lab.add_argument("--gv-labels", type=Path, default=None)
    p_lab.add_argument("--span-start-ms", type=int, default=None)
    p_lab.add_argument("--span-end-ms", type=int, default=None)
    p_lab.set_defaults(func=cmd_labels)

    p_feat = sub.add_parser("features", help="Build features_<film>.json (S3)")
    p_feat.add_argument("--film", choices=list(FILMS), required=True)
    p_feat.add_argument("--tracks-json", type=Path, required=True)
    p_feat.add_argument("--video", type=Path, required=True)
    p_feat.add_argument("--rules-make-miss", type=Path, required=True)
    p_feat.add_argument("--v6-results", type=Path, required=True)
    p_feat.add_argument("--d2v1-results", type=Path, required=True)
    p_feat.add_argument("--out", type=Path, required=True)
    p_feat.set_defaults(func=cmd_features)

    p_fr = sub.add_parser("freeze", help="Write frozen.json sha256 map (V6)")
    p_fr.add_argument("--dir", type=Path, required=True)
    p_fr.set_defaults(func=cmd_freeze)

    p_logo = sub.add_parser("logo", help="Leave-one-game-out (S5/S6)")
    p_logo.add_argument("--dir", type=Path, required=True)
    p_logo.add_argument("--rules-adrian", type=Path, required=True)
    p_logo.add_argument("--rules-notus", type=Path, required=True)
    p_logo.add_argument("--rules-gv", type=Path, required=True)
    p_logo.add_argument("--out", type=Path, required=True)
    p_logo.set_defaults(func=cmd_logo)

    p_final = sub.add_parser("final", help="Fit final model if LOGO passed (S7)")
    p_final.add_argument("--dir", type=Path, required=True)
    p_final.add_argument("--out-dir", type=Path, required=True)
    p_final.set_defaults(func=cmd_final)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
