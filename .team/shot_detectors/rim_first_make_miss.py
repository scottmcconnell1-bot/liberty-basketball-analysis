"""Rim-first make/miss wrapper (spec 44/45/46). Moments in, existing track + D1 + vote out.

New file only. Does not edit collect_q4_bodd, keep_ball_detections, or the coach page.
Never opens a tags file, scoreboard, or database.
"""
from __future__ import annotations

import argparse
import copy
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# spec 44, fixed by Claude Code 2026-11-09
TRACK_LEAD_MS = 1000
# spec 45 S1, Adrian build median, fixed by Claude Code 2026-11-09.
REF_HOOP_W = 98.0


def film_scale_info(tracks: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Median hoop width / REF_HOOP_W for one film's track set (spec 45)."""
    widths: List[float] = []
    for track in tracks:
        hoop = track.get("hoop")
        if isinstance(hoop, list) and len(hoop) > 0:
            widths.append(float(hoop[2]))
    n_tracks_total = len(tracks)
    n_tracks_used = len(widths)
    if n_tracks_used == 0:
        raise SystemExit(
            "film scale: no tracks with a non-empty hoop list "
            f"(n_tracks_total={n_tracks_total})"
        )
    film_hoop_median = statistics.median(widths)
    film_scale = film_hoop_median / REF_HOOP_W
    return {
        "film_scale": film_scale,
        "film_hoop_median": film_hoop_median,
        "n_tracks_used": n_tracks_used,
        "n_tracks_total": n_tracks_total,
        "ref_hoop_w": REF_HOOP_W,
    }


def v6_ball_scaled(model, cap, fps, row, hoop, s):
    """Copy of collect_q4_bodd.v6_ball with crop/pick radius multiplied by s (spec 46)."""
    import cv2

    hx, hy = hoop[0], hoop[1]
    tag = int(round(row["t"] / 1000.0 * fps))
    cap.set(cv2.CAP_PROP_POS_FRAMES, tag)
    prev = None
    series = []
    for f in range(80):
        ok, frame = cap.read()
        if not ok:
            break
        h, w = frame.shape[:2]
        x0 = int(max(0, hx - 260 * s))
        y0 = int(max(0, hy - 200 * s))
        x1 = int(min(w, hx + 260 * s))
        y1 = int(min(h, hy + 240 * s))
        pred = model.predict(frame[y0:y1, x0:x1], conf=0.28, imgsz=640, verbose=False)[0]
        if pred.boxes is None or len(pred.boxes) == 0:
            prev = None
            continue
        picks = []
        for box in pred.boxes:
            a, b, c, d = [float(v) for v in box.xyxy[0]]
            cx, cy = x0 + (a + c) / 2, y0 + (b + d) / 2
            if abs(cx - hx) > 220 * s or abs(cy - hy) > 220 * s:
                continue
            dist = (cx - hx) ** 2 + (cy - hy) ** 2
            if prev is not None:
                dist += ((cx - prev[0]) ** 2 + (cy - prev[1]) ** 2) * 0.35
            picks.append((dist, cx, cy))
        if not picks:
            prev = None
            continue
        picks.sort()
        _d, cx, cy = picks[0]
        prev = (cx, cy)
        series.append((f, cx, cy))
    return series


def crop_scale_doc(info: Dict[str, Any]) -> Dict[str, Any]:
    """crop_scale.json payload beside tracks out-json (spec 46 V1)."""
    return {
        "crop_scale": info["film_scale"],
        "film_hoop_median": info["film_hoop_median"],
        "n_tracks_used": info["n_tracks_used"],
        "n_tracks_total": info["n_tracks_total"],
        "ref_hoop_w": REF_HOOP_W,
    }


def find_reuse_source_track(
    source_tracks: Sequence[Dict[str, Any]],
    *,
    start_ms: int,
    moment_t_ms: int,
) -> Dict[str, Any]:
    """Match source by t==start_ms, else moment_t_ms==moment (spec 46 V10)."""
    for track in source_tracks:
        if int(track["t"]) == int(start_ms):
            return track
    for track in source_tracks:
        if "moment_t_ms" in track and int(track["moment_t_ms"]) == int(moment_t_ms):
            return track
    raise SystemExit(
        f"reuse-hoops-from: no match for start_ms={start_ms} moment_t_ms={moment_t_ms}"
    )


def apply_film_scale(
    tracks: Sequence[Dict[str, Any]], scale: float
) -> List[Dict[str, Any]]:
    """Deep-copied tracks with _court_scale_x/_court_scale_y set; input unchanged."""
    scale_f = float(scale)
    out: List[Dict[str, Any]] = []
    for track in tracks:
        row = copy.deepcopy(track)
        row["_court_scale_x"] = scale_f
        row["_court_scale_y"] = scale_f
        out.append(row)
    return out


def load_moment_times_from_moments(path: Path) -> List[int]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    moments = doc.get("moments") if isinstance(doc, dict) else None
    if not isinstance(moments, list):
        raise SystemExit(f"moments json has no moments list: {path}")
    return [int(m["t_ms"]) for m in moments]


def load_moment_times_from_tag_times(path: Path) -> List[int]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit(f"tag-times json must be a list of ints: {path}")
    return [int(t) for t in data]


def start_ms_for(t_ms: int, lead_ms: int = TRACK_LEAD_MS) -> int:
    return int(t_ms) - int(lead_ms)


def start_frame_for(start_ms: int, fps: float) -> int:
    return int(round(float(start_ms) / 1000.0 * float(fps)))


def refuse_existing_file(path: Path) -> None:
    if Path(path).exists():
        raise SystemExit(f"refusing to overwrite existing file: {path}")


def refuse_existing_dir(path: Path) -> None:
    if Path(path).exists():
        raise SystemExit(f"refusing to use existing out dir: {path}")


def track_has_hoop_and_ball(track: Dict[str, Any]) -> bool:
    hoop = track.get("hoop")
    ball = track.get("ball") or []
    return hoop is not None and len(ball) > 0


def build_shot_list_from_tracks(
    tracks: Sequence[Dict[str, Any]],
    *,
    film_name: str,
    video_rel: str,
    tracks_path: Path,
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[int, Dict[str, Any]]], Dict[str, Path]]:
    """Shot rows for D1: one per track with hoop and non-empty ball. gt_make is None (V2)."""
    tracks_path = Path(tracks_path)
    tracks_by_t: Dict[int, Dict[str, Any]] = {}
    shots: List[Dict[str, Any]] = []
    for row in tracks:
        t = int(row["t"])
        tracks_by_t[t] = row
        if not track_has_hoop_and_ball(row):
            continue
        shots.append(
            {
                "film": film_name,
                "t": t,
                "quarter": None,
                "label": None,
                "player": None,
                "start": None,
                "video_rel": video_rel,
                "tracks_path_resolved": str(tracks_path.resolve()),
                "gt_make": None,
            }
        )
    return shots, {film_name: tracks_by_t}, {film_name: tracks_path.resolve()}


def _pred_index(results_doc: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    shots = results_doc.get("shots") if isinstance(results_doc, dict) else None
    if not isinstance(shots, list):
        raise SystemExit("results json has no shots list")
    return {int(s["t"]): s for s in shots}


def vote_one(
    *,
    has_track: bool,
    v6_pred: Optional[bool],
    d2v1_pred: Optional[bool],
) -> str:
    if not has_track:
        return "no_track"
    p1 = bool(v6_pred)
    p2 = bool(d2v1_pred)
    if p1 and p2:
        return "make"
    if p1 or p2:
        return "coach"
    return "miss"


def build_vote_rows(
    tracks: Sequence[Dict[str, Any]],
    v6_results: Dict[str, Any],
    d2v1_results: Dict[str, Any],
) -> List[Dict[str, Any]]:
    v6_by_t = _pred_index(v6_results)
    d2_by_t = _pred_index(d2v1_results)
    rows: List[Dict[str, Any]] = []
    for track in tracks:
        start_ms = int(track["t"])
        moment_t_ms = int(track.get("moment_t_ms", start_ms))
        hoop = track.get("hoop")
        if isinstance(hoop, tuple):
            hoop = list(hoop)
        has_track = track_has_hoop_and_ball(track)
        if not has_track:
            rows.append(
                {
                    "moment_t_ms": moment_t_ms,
                    "start_ms": start_ms,
                    "hoop": hoop,
                    "v6_pred": None,
                    "v6_reason": None,
                    "d2v1_pred": None,
                    "d2v1_reason": None,
                    "call": "no_track",
                }
            )
            continue
        if start_ms not in v6_by_t:
            raise SystemExit(f"missing v6 result for t={start_ms}")
        if start_ms not in d2_by_t:
            raise SystemExit(f"missing d2v1 result for t={start_ms}")
        v6 = v6_by_t[start_ms]
        d2 = d2_by_t[start_ms]
        p1 = bool(v6["new_pred"])
        p2 = bool(d2["new_pred"])
        rows.append(
            {
                "moment_t_ms": moment_t_ms,
                "start_ms": start_ms,
                "hoop": hoop,
                "v6_pred": p1,
                "v6_reason": v6.get("new_reason"),
                "d2v1_pred": p2,
                "d2v1_reason": d2.get("new_reason"),
                "call": vote_one(has_track=True, v6_pred=p1, d2v1_pred=p2),
            }
        )
    return rows


def write_vote_outputs(
    rows: List[Dict[str, Any]],
    out_dir: Path,
    *,
    film_scale_doc: Optional[Dict[str, Any]] = None,
) -> None:
    out_dir = Path(out_dir)
    refuse_existing_dir(out_dir)
    out_dir.mkdir(parents=True)
    (out_dir / "make_miss.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )
    counts: Dict[str, int] = {"make": 0, "coach": 0, "miss": 0, "no_track": 0}
    for row in rows:
        call = str(row["call"])
        counts[call] = counts.get(call, 0) + 1
    lines = [
        "# rim-first make/miss vote",
        "",
        f"- make: {counts.get('make', 0)}",
        f"- coach: {counts.get('coach', 0)}",
        f"- miss: {counts.get('miss', 0)}",
        f"- no_track: {counts.get('no_track', 0)}",
        f"- total: {len(rows)}",
    ]
    if film_scale_doc is not None:
        lines.append(
            "- Film scale: "
            f"film_scale={film_scale_doc['film_scale']} "
            f"film_hoop_median={film_scale_doc['film_hoop_median']} "
            f"n_tracks_used={film_scale_doc['n_tracks_used']}"
        )
    lines.append("")
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def _write_tracks_json(out_json: Path, tracks: List[Dict[str, Any]]) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(tracks), encoding="utf-8")
    print(f"wrote {out_json} ({len(tracks)} tracks)")


def _write_crop_scale_beside(out_json: Path, info: Dict[str, Any]) -> None:
    crop_path = Path(out_json).parent / "crop_scale.json"
    refuse_existing_file(crop_path)
    crop_path.write_text(json.dumps(crop_scale_doc(info), indent=2), encoding="utf-8")
    print(f"wrote {crop_path} crop_scale={info['film_scale']}")


def _fill_balls_scaled(
    tracks: List[Dict[str, Any]],
    *,
    video: Path,
    s: float,
    v6_model: Any,
) -> None:
    import cv2

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    for row in tracks:
        hoop = row.get("hoop")
        start_ms = int(row["t"])
        if hoop is not None:
            row["ball"] = v6_ball_scaled(
                v6_model, cap, fps, {"t": start_ms}, hoop, s
            )
        else:
            row["ball"] = []
    cap.release()


def cmd_tracks(args: argparse.Namespace) -> int:
    import cv2
    from ultralytics import YOLO

    import collect_q4_bodd as q4

    if args.moments_json:
        times = load_moment_times_from_moments(Path(args.moments_json))
    else:
        times = load_moment_times_from_tag_times(Path(args.tag_times_json))

    lead_ms = int(args.lead_ms)
    out_json = Path(args.out_json)
    refuse_existing_file(out_json)

    scaled_crop = bool(getattr(args, "scaled_crop", False))
    reuse_from = getattr(args, "reuse_hoops_from", None)
    if reuse_from is not None and not scaled_crop:
        raise SystemExit("--reuse-hoops-from requires --scaled-crop")

    video = Path(args.video)

    # Spec 46 V10: reuse hoops/bodd from an existing track file; pass 2 only.
    if scaled_crop and reuse_from is not None:
        source = json.loads(Path(reuse_from).read_text(encoding="utf-8"))
        if not isinstance(source, list):
            raise SystemExit("reuse-hoops-from json must be a list")
        tracks: List[Dict[str, Any]] = []
        for t_ms in times:
            start_ms = start_ms_for(t_ms, lead_ms)
            src = find_reuse_source_track(
                source, start_ms=start_ms, moment_t_ms=int(t_ms)
            )
            row = copy.deepcopy(src)
            row.pop("result", None)
            row["t"] = start_ms
            tracks.append(row)
        info = film_scale_info(tracks)
        s = info["film_scale"]
        v6_model = YOLO(str(q4.V6))
        _fill_balls_scaled(tracks, video=video, s=s, v6_model=v6_model)
        _write_tracks_json(out_json, tracks)
        _write_crop_scale_beside(out_json, info)
        return 0

    bodd_model = YOLO(str(q4.BODD))
    if "hoop" not in bodd_model.names.values():
        raise SystemExit("BODD model has no hoop class")

    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    sample_rows: List[Dict[str, Any]] = []
    for t_ms in times:
        start_ms = start_ms_for(t_ms, lead_ms)
        start = start_frame_for(start_ms, fps)
        samples = q4.collect_samples(bodd_model, cap, start)
        sample_rows.append(
            {
                "t": start_ms,
                "moment_t_ms": int(t_ms),
                "samples": samples,
            }
        )
    cap.release()

    # Spec 46 V4: pass 1 = BODD/hoop only; pass 2 = v6_ball_scaled.
    # Flags off: same as spec 44 (v6_ball in the second capture).
    if scaled_crop:
        tracks = []
        for row in sample_rows:
            start_ms = int(row["t"])
            cands = q4.groups(row["samples"])
            bodd = []
            for sample in row["samples"]:
                if not sample["balls"]:
                    continue
                ball = max(sample["balls"], key=lambda item: item["c"])
                if ball["c"] >= 0.28:
                    bodd.append((sample["f"], ball["x"], ball["y"]))
            hoop = None
            if cands and bodd:
                hoop = min(
                    cands,
                    key=lambda h: min(
                        (x - h[0]) ** 2 + (y - h[1]) ** 2 for _f, x, y in bodd
                    ),
                )
            tracks.append(
                {
                    "t": start_ms,
                    "moment_t_ms": int(row["moment_t_ms"]),
                    "hoop": list(hoop) if hoop is not None else None,
                    "ball": [],
                    "bodd": bodd,
                }
            )
        info = film_scale_info(tracks)
        s = info["film_scale"]
        v6_model = YOLO(str(q4.V6))
        _fill_balls_scaled(tracks, video=video, s=s, v6_model=v6_model)
        _write_tracks_json(out_json, tracks)
        _write_crop_scale_beside(out_json, info)
        return 0

    v6_model = YOLO(str(q4.V6))
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    tracks = []
    for row in sample_rows:
        start_ms = int(row["t"])
        cands = q4.groups(row["samples"])
        bodd = []
        for sample in row["samples"]:
            if not sample["balls"]:
                continue
            ball = max(sample["balls"], key=lambda item: item["c"])
            if ball["c"] >= 0.28:
                bodd.append((sample["f"], ball["x"], ball["y"]))
        hoop = None
        if cands and bodd:
            hoop = min(
                cands,
                key=lambda h: min((x - h[0]) ** 2 + (y - h[1]) ** 2 for _f, x, y in bodd),
            )
        series = (
            q4.v6_ball(v6_model, cap, fps, {"t": start_ms}, hoop)
            if hoop is not None
            else []
        )
        tracks.append(
            {
                "t": start_ms,
                "moment_t_ms": int(row["moment_t_ms"]),
                "hoop": list(hoop) if hoop is not None else None,
                "ball": series,
                "bodd": bodd,
            }
        )
    cap.release()

    _write_tracks_json(out_json, tracks)
    return 0


def _system_exit_message(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if code is None:
        return ""
    return str(code)


def cmd_d1(args: argparse.Namespace) -> int:
    import keep_ball_detections as kbd

    scaled_crop = bool(getattr(args, "scaled_crop", False))
    film_scale = bool(getattr(args, "film_scale", False))
    if scaled_crop and not film_scale:
        raise SystemExit("d1 --scaled-crop requires --film-scale")

    tracks_path = Path(args.tracks_json).resolve()
    out_dir = Path(args.out_dir)
    refuse_existing_dir(out_dir)
    out_dir.mkdir(parents=True)

    tracks = json.loads(tracks_path.read_text(encoding="utf-8"))
    if not isinstance(tracks, list):
        raise SystemExit("tracks json must be a list")

    film_doc: Optional[Dict[str, Any]] = None
    s: Optional[float] = None
    # Spec 45 V9: with --film-scale, write scaled copy under out_dir and point
    # build_shot_list + kbd.FILMS at that path so NO-OP PROOF compares like with like.
    if film_scale:
        info = film_scale_info(tracks)
        s = info["film_scale"]
        scaled = apply_film_scale(tracks, s)
        scaled_path = out_dir / "tracks_scaled.json"
        refuse_existing_file(scaled_path)
        scaled_path.write_text(json.dumps(scaled), encoding="utf-8")
        film_doc = dict(info)
        film_doc["tracks_json"] = str(tracks_path)
        print(
            f"film_scale={info['film_scale']} "
            f"film_hoop_median={info['film_hoop_median']} "
            f"n_tracks_used={info['n_tracks_used']}"
        )
        tracks = scaled
        tracks_path = scaled_path.resolve()

        crop_scale_json = getattr(args, "crop_scale_json", None)
        if crop_scale_json is not None:
            crop_doc = json.loads(Path(crop_scale_json).read_text(encoding="utf-8"))
            if not isinstance(crop_doc, dict) or "crop_scale" not in crop_doc:
                raise SystemExit(
                    f"crop-scale-json missing crop_scale: {crop_scale_json}"
                )
            if crop_doc["crop_scale"] != s:
                raise SystemExit(
                    f"crop_scale {crop_doc['crop_scale']!r} != film_scale {s!r}"
                )

    film_name = str(args.film_name)
    video_rel = str(args.video_rel)
    shots, tracks_by_film, path_by_film = build_shot_list_from_tracks(
        tracks,
        film_name=film_name,
        video_rel=video_rel,
        tracks_path=tracks_path,
    )

    # V2: truth_is_make (keep_ball_detections.py:562-563) accepts gt_make None via
    # bool(None) == False; summarize_results likewise. No crash -> keep None, no note.
    kbd.FILMS = [
        {
            "name": film_name,
            "video_rel": video_rel,
            "tags_rel": None,
            "track_candidates": [str(tracks_path)],
        }
    ]

    def _load_build_shot_list(tracks_dir=None):
        return shots, tracks_by_film, path_by_film

    kbd.load_build_shot_list = _load_build_shot_list  # type: ignore[assignment]

    candidates = out_dir / "candidates.json"
    results = out_dir / "results.json"
    report = out_dir / "report.md"
    weights = Path(args.weights)

    extract_argv = [
        "--step",
        "extract",
        "--v6-weights",
        str(weights),
        "--out-json",
        str(candidates),
    ]
    report_argv = [
        "--step",
        "arc-rule-report",
        "--candidates-json",
        str(candidates),
        "--out-json",
        str(results),
        "--out-md",
        str(report),
    ]
    if args.mapping_proof_json is not None:
        report_argv.extend(["--mapping-proof-json", str(args.mapping_proof_json)])

    orig_crop: Optional[Tuple[Any, Any, Any, Any]] = None
    if scaled_crop:
        assert s is not None
        orig_crop = (
            kbd.CROP_LEFT_RIGHT,
            kbd.CROP_ABOVE,
            kbd.CROP_BELOW,
            kbd.ZONE_BELOW_PX,
        )
        kbd.CROP_LEFT_RIGHT = 260 * s
        kbd.CROP_ABOVE = 200 * s
        kbd.CROP_BELOW = 240 * s
        kbd.ZONE_BELOW_PX = 300 * s
        kbd_crop = {
            "CROP_LEFT_RIGHT": kbd.CROP_LEFT_RIGHT,
            "CROP_ABOVE": kbd.CROP_ABOVE,
            "CROP_BELOW": kbd.CROP_BELOW,
            "ZONE_BELOW_PX": kbd.ZONE_BELOW_PX,
        }
        if film_doc is not None:
            film_doc["kbd_crop"] = kbd_crop

    if film_doc is not None:
        (out_dir / "film_scale.json").write_text(
            json.dumps(film_doc, indent=2), encoding="utf-8"
        )

    try:
        # Extract: d2v1 always trips the 0.90 mapping gate after writing candidates.json.
        # With --mapping-proof-json, continue to arc-rule-report (spec 23 v3).
        try:
            rc = kbd.main(extract_argv)
            if rc:
                return int(rc)
        except SystemExit as e:
            msg = _system_exit_message(e)
            if (
                args.mapping_proof_json is not None
                and msg.startswith("MAPPING CHECK GATE FAILED")
                and candidates.exists()
            ):
                print(
                    "extract mapping gate stop "
                    "(expected for d2v1; proof file used, spec 23 v3)"
                )
            else:
                raise

        # Report: HARD GATE / LOST MAKES are truth-based; gt_make is None here (spec 44 V2).
        try:
            return int(kbd.main(report_argv) or 0)
        except SystemExit as e:
            msg = _system_exit_message(e)
            if results.exists() and (
                msg.startswith("HARD GATE FAILED") or msg.startswith("LOST MAKES")
            ):
                print("truth-based gate ignored: truth absent (spec 44 V2)")
                note = {"truth_absent": True, "ignored_exit": msg}
                (out_dir / "wrapper_note.json").write_text(
                    json.dumps(note, indent=2), encoding="utf-8"
                )
                return 0
            raise
    finally:
        if orig_crop is not None:
            (
                kbd.CROP_LEFT_RIGHT,
                kbd.CROP_ABOVE,
                kbd.CROP_BELOW,
                kbd.ZONE_BELOW_PX,
            ) = orig_crop


def _load_side_film_scale(results_path: Path) -> Optional[Dict[str, Any]]:
    path = Path(results_path).resolve().parent / "film_scale.json"
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise SystemExit(f"film_scale.json must be an object: {path}")
    return doc


def cmd_vote(args: argparse.Namespace) -> int:
    tracks = json.loads(Path(args.tracks_json).read_text(encoding="utf-8"))
    v6 = json.loads(Path(args.v6_results).read_text(encoding="utf-8"))
    d2 = json.loads(Path(args.d2v1_results).read_text(encoding="utf-8"))
    if not isinstance(tracks, list):
        raise SystemExit("tracks json must be a list")

    v6_scale = _load_side_film_scale(Path(args.v6_results))
    d2_scale = _load_side_film_scale(Path(args.d2v1_results))
    film_scale_doc: Optional[Dict[str, Any]] = None
    if v6_scale is None and d2_scale is None:
        film_scale_doc = None
    elif v6_scale is None or d2_scale is None:
        missing = "v6" if v6_scale is None else "d2v1"
        raise SystemExit(
            f"film_scale.json missing beside {missing} results "
            "(need both identical, or neither)"
        )
    elif v6_scale != d2_scale:
        raise SystemExit(
            "film_scale.json beside v6 and d2v1 results differ "
            "(must be identical)"
        )
    else:
        film_scale_doc = v6_scale

    rows = build_vote_rows(tracks, v6, d2)
    if film_scale_doc is not None:
        for row in rows:
            row["film_scale"] = film_scale_doc["film_scale"]
            row["film_hoop_median"] = film_scale_doc["film_hoop_median"]
            row["n_tracks_used"] = film_scale_doc["n_tracks_used"]
    write_vote_outputs(rows, Path(args.out_dir), film_scale_doc=film_scale_doc)
    print(f"wrote {args.out_dir}/make_miss.json ({len(rows)} rows)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rim-first make/miss (spec 44)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_tracks = sub.add_parser("tracks", help="Build tracks from moments via collect_q4_bodd")
    src = p_tracks.add_mutually_exclusive_group(required=True)
    src.add_argument("--moments-json", type=Path, default=None)
    src.add_argument("--tag-times-json", type=Path, default=None)
    p_tracks.add_argument("--video", type=Path, required=True)
    p_tracks.add_argument("--out-json", type=Path, required=True)
    p_tracks.add_argument(
        "--lead-ms",
        type=int,
        default=TRACK_LEAD_MS,
        help='default TRACK_LEAD_MS = 1000 (spec 44, fixed by Claude Code 2026-11-09)',
    )
    p_tracks.add_argument(
        "--scaled-crop",
        action="store_true",
        default=False,
        help="spec 46: pass-2 ball series via v6_ball_scaled; write crop_scale.json",
    )
    p_tracks.add_argument(
        "--reuse-hoops-from",
        type=Path,
        default=None,
        help="spec 46 V10: with --scaled-crop, take hoop/bodd from PATH (no BODD pass)",
    )
    p_tracks.set_defaults(func=cmd_tracks)

    p_d1 = sub.add_parser("d1", help="Run D1 extract + arc-rule-report on a track file")
    p_d1.add_argument("--tracks-json", type=Path, required=True)
    p_d1.add_argument("--video-rel", type=str, required=True)
    p_d1.add_argument("--film-name", type=str, required=True)
    p_d1.add_argument("--weights", type=Path, required=True)
    p_d1.add_argument("--out-dir", type=Path, required=True)
    p_d1.add_argument("--mapping-proof-json", type=Path, default=None)
    p_d1.add_argument(
        "--film-scale",
        action="store_true",
        default=False,
        help="spec 45: set _court_scale_x/_y from median hoop width / REF_HOOP_W",
    )
    p_d1.add_argument(
        "--scaled-crop",
        action="store_true",
        default=False,
        help="spec 46: scale kbd crop constants by film_scale (requires --film-scale)",
    )
    p_d1.add_argument(
        "--crop-scale-json",
        type=Path,
        default=None,
        help="spec 46: optional crop_scale.json; crop_scale must equal film_scale",
    )
    p_d1.set_defaults(func=cmd_d1)

    p_vote = sub.add_parser("vote", help="Vote v6 + d2v1 new_pred into make/coach/miss/no_track")
    p_vote.add_argument("--tracks-json", type=Path, required=True)
    p_vote.add_argument("--v6-results", type=Path, required=True)
    p_vote.add_argument("--d2v1-results", type=Path, required=True)
    p_vote.add_argument("--out-dir", type=Path, required=True)
    p_vote.set_defaults(func=cmd_vote)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
