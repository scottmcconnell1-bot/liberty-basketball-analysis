"""Build a static HTML review page for the 19 missed makes (read-only).

Task 1 step 2 — .team/specs/14_missed_makes_diagnosis_plan.md.
Imports ai_bridge / net_detector only; never edits them. Does not assign causes.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai_bridge import run_saved_v6_rule  # noqa: E402

DEFAULT_OUT_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\missed_makes_review"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/missed_makes_review"),
]

DEFAULT_RESULTS_CANDIDATES = [
    Path(r"C:\Users\scott\Documents\Liberty_Shot_Outputs\net_moved_build_results.json"),
    Path("/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/net_moved_build_results.json"),
]

CAUSE_OPTIONS = [
    "ball_never_detected_near_rim",
    "ball_detected_crossing_outside_055",
    "hoop_box_wrong_or_moved",
    "camera_panned_zoomed_during_shot",
    "ball_hidden_by_players_backboard",
    "crossing_seen_but_column_drift_test_rejected",
    "other",
]

PEAK_TYPE_MAP = {
    "crossing": "crossing",
    "no_crossing_closest_ball": "closest_ball",
    "no_crossing_tag_frame": "tag_frame",
}


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
    return DEFAULT_OUT_CANDIDATES[0]


def default_results_path() -> Path:
    found = pick_existing(*DEFAULT_RESULTS_CANDIDATES)
    if found is not None:
        return found
    return DEFAULT_RESULTS_CANDIDATES[0]


def dedupe_by_film_t(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the first row for each (film, t). Results / tracks list some t twice."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for row in rows:
        key = (row["film"], int(row["t"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def select_shots(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    build = [r for r in rows if r.get("set", "build") == "build"]
    unique = dedupe_by_film_t(build)

    missed = [r for r in unique if r.get("missed_make")]
    # Preserve plan table order: notus then adrian by ascending t within film groups
    # as listed in results (already chronological per film when concatenated).
    missed_sorted = sorted(missed, key=lambda r: (0 if r["film"] == "notus_a1" else 1, int(r["t"])))

    correct = sorted(
        [r for r in unique if r.get("gt_make") and r.get("rule_pred_make")],
        key=lambda r: int(r["t"]),
    )[:10]

    misses = sorted(
        [r for r in unique if (not r.get("gt_make")) and (not r.get("rule_pred_make"))],
        key=lambda r: int(r["t"]),
    )[:10]

    return {
        "missed_make": missed_sorted,
        "correct_make": correct,
        "miss": misses,
    }


def load_tracks(path: Path) -> Dict[int, Dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    # First occurrence wins so duplicate t rows do not overwrite unpredictably.
    by_t: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        t = int(row["t"])
        if t not in by_t:
            by_t[t] = row
    return by_t


def rule_details_by_t(timestamps: List[int], tracks_path: Path) -> Dict[int, Dict[str, Any]]:
    if not timestamps:
        return {}
    scored = run_saved_v6_rule([float(t) for t in timestamps], str(tracks_path))
    out: Dict[int, Dict[str, Any]] = {}
    for row in scored.get("results") or []:
        details = row.get("details") or {}
        if not isinstance(details, dict):
            details = {"reason": str(details)}
        out[int(row["tag_ts"])] = details
    return out


def absolute_ball_points(
    track: Dict[str, Any], t_ms: int, fps: float
) -> Dict[int, List[List[float]]]:
    """Map absolute video frame -> list of [x, y] ball points.

    Absolute frame = round(t/1000*fps) + offset (offset is track point[0]).
    """
    tag_frame = int(round(t_ms / 1000.0 * fps))
    points = list(track.get("ball") or [])
    if not points:
        points = list(track.get("bodd") or [])
    by_frame: Dict[int, List[List[float]]] = {}
    for pt in points:
        offset = int(pt[0])
        abs_f = tag_frame + offset
        by_frame.setdefault(abs_f, []).append([float(pt[1]), float(pt[2])])
    return by_frame


def crop_square(
    frame, hoop_x: float, hoop_y: float, hoop_w: float
) -> Tuple[Any, int, int, int]:
    """Return (crop_bgr, crop_x, crop_y, size)."""
    h, w = frame.shape[:2]
    size = int(max(hoop_w * 3.0, 240.0))
    cx, cy = int(round(hoop_x)), int(round(hoop_y))
    half = size // 2
    x0 = max(0, cx - half)
    y0 = max(0, cy - half)
    x1 = min(w, x0 + size)
    y1 = min(h, y0 + size)
    # Re-clamp origin if we hit the far edge
    x0 = max(0, x1 - size)
    y0 = max(0, y1 - size)
    crop = frame[y0:y1, x0:x1].copy()
    return crop, x0, y0, size


def draw_overlays(
    crop,
    crop_x: int,
    crop_y: int,
    hoop_x: float,
    hoop_y: float,
    hoop_w: float,
    ball_xy: List[List[float]],
    frame_idx: int,
    is_peak: bool,
):
    # Hoop box centered on (hoop_x, hoop_y)
    tl_x = int(round(hoop_x - hoop_w / 2.0 - crop_x))
    tl_y = int(round(hoop_y - hoop_w / 2.0 - crop_y))
    br_x = int(round(tl_x + hoop_w))
    br_y = int(round(tl_y + hoop_w))
    cv2.rectangle(crop, (tl_x, tl_y), (br_x, br_y), (0, 255, 0), 2)

    for xy in ball_xy:
        bx = int(round(xy[0] - crop_x))
        by = int(round(xy[1] - crop_y))
        cv2.circle(crop, (bx, by), 4, (0, 0, 255), -1)

    if is_peak:
        cx = int(round(hoop_x - crop_x))
        cy = int(round(hoop_y - crop_y))
        cv2.line(crop, (cx - 10, cy), (cx + 10, cy), (0, 255, 255), 2)
        cv2.line(crop, (cx, cy - 10), (cx, cy + 10), (0, 255, 255), 2)

    cv2.putText(
        crop,
        str(frame_idx),
        (4, 16),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return crop


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


def reason_badge(details: Dict[str, Any]) -> str:
    if details.get("vetoed") and details.get("veto_reason"):
        return str(details["veto_reason"])
    reason = details.get("reason") or "ok"
    if reason == "column_ratio_low" and "column_ratio" in details:
        return f"column_ratio_low: {details['column_ratio']}"
    return str(reason)


def write_shot_meta(path: Path, row: Dict[str, Any], category: str) -> None:
    meta = {
        "film": row["film"],
        "t": int(row["t"]),
        "time_str": row.get("start") or "",
        "quarter": row.get("quarter") or "",
        "label": row.get("label") or "",
        "player": row.get("player") or "",
        "gt_make": bool(row.get("gt_make")),
        "rule_pred_make": bool(row.get("rule_pred_make")),
        "missed_make": bool(row.get("missed_make")),
        "net_moved": bool(row.get("net_moved")),
        "video_path": row.get("video_path") or "",
        "tracks_path": row.get("tracks_path") or "",
        "fps": float(row.get("fps") or 25.0),
        "category": category,
    }
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def write_overlay(
    path: Path,
    row: Dict[str, Any],
    peak_frame: int,
    ball_by_frame: Dict[int, List[List[float]]],
    details: Dict[str, Any],
    crop_size: int,
) -> None:
    peak_reason = row.get("peak_reason") or ""
    peak_type = PEAK_TYPE_MAP.get(peak_reason, peak_reason or "unknown")
    # Only keep ball points in the strip window for a smaller file
    window_frames = range(peak_frame - 10, peak_frame + 26)
    trimmed = {
        str(f): ball_by_frame[f]
        for f in window_frames
        if f in ball_by_frame
    }
    payload = {
        "peak_frame": peak_frame,
        "peak_frame_type": peak_type,
        "hoop": {
            "x": float(row["hoop_x"]),
            "y": float(row["hoop_y"]),
            "w": float(row["hoop_w"]),
        },
        "rim_r": float(row.get("rim_r") or (float(row["hoop_w"]) / 2.0)),
        "crop": {
            "cx": float(row["hoop_x"]),
            "cy": float(row["hoop_y"]),
            "size": crop_size,
        },
        "ball_points_by_frame": trimmed,
        "rule_details": details,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def detail_html(
    shot_id: str,
    row: Dict[str, Any],
    details: Dict[str, Any],
    category: str,
    n_frames: int,
) -> str:
    badge = reason_badge(details)
    meta_rows = [
        ("Film", row["film"]),
        ("Time", row.get("start") or ""),
        ("t (ms)", row["t"]),
        ("Quarter", row.get("quarter") or ""),
        ("Label", row.get("label") or ""),
        ("Player", row.get("player") or ""),
        ("GT make", row.get("gt_make")),
        ("Rule pred make", row.get("rule_pred_make")),
        ("Missed make", row.get("missed_make")),
        ("net_moved_after_shot", row.get("net_moved")),
        ("Peak frame", row.get("peak_frame")),
        ("Peak reason", row.get("peak_reason")),
        ("Rule reason", badge),
    ]
    meta_html = "".join(
        f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in meta_rows
    )
    thumbs = "".join(
        f'<a href="frames/frame_{i:03d}.png" target="_blank">'
        f'<img src="frames/frame_{i:03d}.png" alt="frame {i}" class="thumb"/></a>'
        for i in range(n_frames)
    )
    cause_block = ""
    if category == "missed_make":
        opts = "".join(
            f'<option value="{c}">{c}</option>' for c in CAUSE_OPTIONS
        )
        cause_block = f"""
<section class="cause">
  <h2>Cause (human assignment)</h2>
  <p>Select exactly one cause. The build script never guesses.</p>
  <label>Cause
    <select id="cause-select" data-shot-id="{shot_id}" data-t="{row['t']}" data-film="{row['film']}">
      <option value="">— select —</option>
      {opts}
    </select>
  </label>
  <label class="other-note" style="display:none">Other description
    <input type="text" id="other-text" maxlength="200" placeholder="one sentence"/>
  </label>
  <p class="hint">Use Export Causes on the index page after filling all 19.</p>
</section>
<script>
const sel = document.getElementById('cause-select');
const other = document.querySelector('.other-note');
sel.addEventListener('change', () => {{
  other.style.display = sel.value === 'other' ? 'block' : 'none';
  const key = 'mm_cause_' + sel.dataset.shotId;
  const payload = {{
    shot_id: sel.dataset.shotId,
    t: Number(sel.dataset.t),
    film: sel.dataset.film,
    cause: sel.value || null,
    other_text: document.getElementById('other-text').value || null
  }};
  localStorage.setItem(key, JSON.stringify(payload));
}});
document.getElementById('other-text').addEventListener('input', () => sel.dispatchEvent(new Event('change')));
(function restore() {{
  const raw = localStorage.getItem('mm_cause_' + sel.dataset.shotId);
  if (!raw) return;
  try {{
    const p = JSON.parse(raw);
    if (p.cause) sel.value = p.cause;
    if (p.other_text) document.getElementById('other-text').value = p.other_text;
    other.style.display = sel.value === 'other' ? 'block' : 'none';
  }} catch (e) {{}}
}})();
</script>
"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{shot_id} — Missed Makes Review</title>
<style>
body {{ font-family: Georgia, 'Times New Roman', serif; margin: 1.5rem; background: #1a1a1a; color: #eee; }}
a {{ color: #9cf; }}
.thumbs {{ display: flex; flex-wrap: nowrap; overflow-x: auto; gap: 4px; padding: 8px 0; }}
.thumb {{ height: 96px; border: 1px solid #444; }}
table {{ border-collapse: collapse; margin: 1rem 0; }}
th, td {{ border: 1px solid #555; padding: 4px 8px; text-align: left; }}
th {{ background: #333; }}
.cause label {{ display: block; margin: 0.5rem 0; }}
</style>
</head>
<body>
<p><a href="../../index.html">&larr; Back to index</a></p>
<h1>{shot_id}</h1>
<p>{row['film']} · {row.get('start') or ''} · {row.get('quarter') or ''} · {row.get('label') or ''} · {row.get('player') or ''}</p>
<section>
  <h2>Frame strip (peak = frame_010)</h2>
  <div class="thumbs">{thumbs}</div>
</section>
<section>
  <h2>Metadata</h2>
  <table>{meta_html}</table>
</section>
{cause_block}
</body>
</html>
"""


def index_html(cards: List[Dict[str, Any]]) -> str:
    def section(title: str, cat: str) -> str:
        items = [c for c in cards if c["category"] == cat]
        blocks = []
        for c in items:
            blocks.append(
                f"""
<article class="card">
  <a href="shots/{c['shot_id']}/detail.html">
    <img src="shots/{c['shot_id']}/frames/frame_010.png" alt="{c['shot_id']} peak"/>
  </a>
  <h3>{c['shot_id']}</h3>
  <p>{c['film']} · {c['time_str']} · {c['quarter']}</p>
  <p>{c['label']} · {c['player']}</p>
  <p class="badge">{c['badge']}</p>
  <p>net_moved={c['net_moved']}</p>
  <p><a href="shots/{c['shot_id']}/detail.html">Open detail</a></p>
</article>
"""
            )
        return f"<section><h2>{title} ({len(items)})</h2><div class='grid'>{''.join(blocks)}</div></section>"

    body = (
        section("Missed Makes", "missed_make")
        + section("Correct Makes", "correct_make")
        + section("Misses", "miss")
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Missed Makes Diagnosis Review — 2026-10-28</title>
<style>
body {{ font-family: Georgia, 'Times New Roman', serif; margin: 0; padding: 1.5rem; background: #121212; color: #eee; }}
h1 {{ font-weight: normal; }}
a {{ color: #9cf; }}
.grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; }}
@media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
.card {{ background: #1e1e1e; padding: 0.75rem; border: 1px solid #333; }}
.card img {{ width: 100%; height: auto; display: block; background: #000; }}
.badge {{ display: inline-block; background: #333; padding: 2px 6px; font-size: 0.9rem; }}
.toolbar {{ margin: 1rem 0; padding: 0.75rem; background: #1e1e1e; border: 1px solid #333; }}
button {{ font: inherit; padding: 0.4rem 0.8rem; cursor: pointer; }}
</style>
</head>
<body>
<h1>Missed Makes Diagnosis Review — 2026-10-28</h1>
<p>Causes are assigned by a human on each missed-make detail page. This page does not guess.</p>
<div class="toolbar">
  <button type="button" id="export-causes">Export Causes</button>
  <span id="export-status"></span>
</div>
{body}
<script>
const MISSED_IDS = {json.dumps([c['shot_id'] for c in cards if c['category']=='missed_make'])};
document.getElementById('export-causes').addEventListener('click', () => {{
  const rows = MISSED_IDS.map(id => {{
    const raw = localStorage.getItem('mm_cause_' + id);
    if (!raw) return {{ shot_id: id, t: null, film: null, cause: null }};
    try {{ return JSON.parse(raw); }} catch (e) {{ return {{ shot_id: id, cause: null }}; }}
  }});
  const blob = new Blob([JSON.stringify(rows, null, 2)], {{ type: 'application/json' }});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'causes.json';
  a.click();
  URL.revokeObjectURL(a.href);
  document.getElementById('export-status').textContent =
    'Downloaded causes.json (' + rows.filter(r => r.cause).length + ' of ' + rows.length + ' filled)';
}});
</script>
</body>
</html>
"""


def process_shot(
    shot_id: str,
    category: str,
    row: Dict[str, Any],
    track: Dict[str, Any],
    details: Dict[str, Any],
    reader: FrameReader,
    out_root: Path,
) -> Tuple[int, Dict[str, Any]]:
    shot_dir = out_root / "shots" / shot_id
    frames_dir = shot_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    peak_frame = int(row["peak_frame"])
    fps = float(row.get("fps") or reader.fps or 25.0)
    hoop_x = float(row["hoop_x"])
    hoop_y = float(row["hoop_y"])
    hoop_w = float(row["hoop_w"])
    t_ms = int(row["t"])

    ball_by_frame = absolute_ball_points(track, t_ms, fps)
    total = reader.total_frames
    lo = peak_frame - 10
    hi = peak_frame + 25
    if total > 0:
        lo = max(0, lo)
        hi = min(total - 1, hi)
    else:
        lo = max(0, lo)

    png_count = 0
    crop_size = int(max(hoop_w * 3.0, 240.0))
    # Always write 36 slots; clamp missing ends by repeating edge if needed
    for slot in range(36):
        frame_idx = peak_frame - 10 + slot
        if total > 0:
            frame_idx = min(max(0, frame_idx), total - 1)
        else:
            frame_idx = max(0, frame_idx)
        frame = reader.read(frame_idx)
        if frame is None:
            crop = np.zeros((crop_size, crop_size, 3), dtype=np.uint8)
            crop_x = crop_y = 0
        else:
            crop, crop_x, crop_y, crop_size = crop_square(frame, hoop_x, hoop_y, hoop_w)
            ball_xy = ball_by_frame.get(frame_idx, [])
            crop = draw_overlays(
                crop,
                crop_x,
                crop_y,
                hoop_x,
                hoop_y,
                hoop_w,
                ball_xy,
                frame_idx,
                is_peak=(frame_idx == peak_frame),
            )
        out_png = frames_dir / f"frame_{slot:03d}.png"
        cv2.imwrite(str(out_png), crop)
        png_count += 1

    write_shot_meta(shot_dir / "shot_meta.json", row, category)
    write_overlay(
        shot_dir / "overlay_data.json",
        row,
        peak_frame,
        ball_by_frame,
        details,
        crop_size,
    )
    (shot_dir / "detail.html").write_text(
        detail_html(shot_id, row, details, category, png_count),
        encoding="utf-8",
    )

    card = {
        "shot_id": shot_id,
        "category": category,
        "film": row["film"],
        "time_str": row.get("start") or "",
        "quarter": row.get("quarter") or "",
        "label": row.get("label") or "",
        "player": row.get("player") or "",
        "badge": reason_badge(details),
        "net_moved": bool(row.get("net_moved")),
    }
    return png_count, card


def write_cause_template(out_root: Path, missed: List[Tuple[str, Dict[str, Any]]]) -> None:
    rows = [
        {
            "shot_id": shot_id,
            "t": int(row["t"]),
            "film": row["film"],
            "cause": None,
        }
        for shot_id, row in missed
    ]
    (out_root / "cause_template.json").write_text(
        json.dumps(rows, indent=2), encoding="utf-8"
    )


def write_cause_counts_stub(out_root: Path) -> None:
    lines = [
        "# Cause Counts (filled after review)",
        "",
        "| Cause | Count |",
        "|-------|-------|",
    ]
    for c in CAUSE_OPTIONS:
        lines.append(f"| {c} | N |")
    lines.append("| **Total** | **19** |")
    lines.append("")
    lines.append(
        "Regenerate after saving `causes.json` (Export Causes from index.html)."
    )
    (out_root / "cause_counts.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Review page output folder (default: Liberty_Shot_Outputs/missed_makes_review)",
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=None,
        help="Step-1 results JSON (default: Liberty_Shot_Outputs/net_moved_build_results.json)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out) if args.out is not None else default_out_dir()
    results_arg = Path(args.results) if args.results is not None else default_results_path()
    results_path = resolve_path(str(results_arg))
    if not results_path.exists():
        print(f"ERROR: results file not found: {results_arg} (resolved {results_path})")
        return 1

    rows = json.loads(results_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        print("ERROR: results JSON must be a list of shot rows")
        return 1

    selected = select_shots(rows)
    if len(selected["missed_make"]) != 19:
        print(
            f"WARNING: expected 19 missed makes, got {len(selected['missed_make'])}"
        )
    if len(selected["correct_make"]) != 10:
        print(
            f"WARNING: expected 10 correct makes, got {len(selected['correct_make'])}"
        )
    if len(selected["miss"]) != 10:
        print(f"WARNING: expected 10 misses, got {len(selected['miss'])}")

    out_dir.mkdir(parents=True, exist_ok=True)

    # Cache tracks + rule details per tracks file
    track_cache: Dict[str, Dict[int, Dict[str, Any]]] = {}
    details_cache: Dict[str, Dict[int, Dict[str, Any]]] = {}
    reader_cache: Dict[str, FrameReader] = {}

    def tracks_for(row: Dict[str, Any]) -> Tuple[Path, Dict[int, Dict[str, Any]]]:
        key = row["tracks_path"]
        tp = resolve_path(key)
        if key not in track_cache:
            if not tp.exists():
                raise FileNotFoundError(f"tracks not found: {key} -> {tp}")
            track_cache[key] = load_tracks(tp)
        return tp, track_cache[key]

    def details_for(row: Dict[str, Any], all_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        key = row["tracks_path"]
        if key not in details_cache:
            tp = resolve_path(key)
            ts = sorted({int(r["t"]) for r in all_rows if r["tracks_path"] == key})
            details_cache[key] = rule_details_by_t(ts, tp)
        return details_cache[key].get(int(row["t"])) or {"reason": "unknown"}

    def reader_for(row: Dict[str, Any]) -> FrameReader:
        key = row["video_path"]
        if key not in reader_cache:
            vp = resolve_path(key)
            if not vp.exists():
                raise FileNotFoundError(f"video not found: {key} -> {vp}")
            reader_cache[key] = FrameReader(vp)
        return reader_cache[key]

    try:
        all_selected = (
            selected["missed_make"] + selected["correct_make"] + selected["miss"]
        )
        # Preload rule details per tracks file
        for row in all_selected:
            details_for(row, all_selected)

        cards: List[Dict[str, Any]] = []
        png_total = 0
        missed_pairs: List[Tuple[str, Dict[str, Any]]] = []

        for i, row in enumerate(selected["missed_make"], start=1):
            shot_id = f"missed_make_{i:02d}"
            _tp, tracks = tracks_for(row)
            track = tracks.get(int(row["t"]))
            if track is None:
                raise KeyError(f"No track for {row['film']} t={row['t']}")
            details = details_for(row, all_selected)
            reader = reader_for(row)
            n, card = process_shot(
                shot_id, "missed_make", row, track, details, reader, out_dir
            )
            png_total += n
            cards.append(card)
            missed_pairs.append((shot_id, row))
            print(
                f"[{shot_id}] {row['film']} t={row['t']} peak={row['peak_frame']} "
                f"reason={reason_badge(details)}",
                flush=True,
            )

        for i, row in enumerate(selected["correct_make"], start=1):
            shot_id = f"correct_make_{i:02d}"
            _tp, tracks = tracks_for(row)
            track = tracks.get(int(row["t"]))
            if track is None:
                raise KeyError(f"No track for {row['film']} t={row['t']}")
            details = details_for(row, all_selected)
            reader = reader_for(row)
            n, card = process_shot(
                shot_id, "correct_make", row, track, details, reader, out_dir
            )
            png_total += n
            cards.append(card)
            print(
                f"[{shot_id}] {row['film']} t={row['t']} peak={row['peak_frame']} "
                f"reason={reason_badge(details)}",
                flush=True,
            )

        for i, row in enumerate(selected["miss"], start=1):
            shot_id = f"miss_{i:02d}"
            _tp, tracks = tracks_for(row)
            track = tracks.get(int(row["t"]))
            if track is None:
                raise KeyError(f"No track for {row['film']} t={row['t']}")
            details = details_for(row, all_selected)
            reader = reader_for(row)
            n, card = process_shot(
                shot_id, "miss", row, track, details, reader, out_dir
            )
            png_total += n
            cards.append(card)
            print(
                f"[{shot_id}] {row['film']} t={row['t']} peak={row['peak_frame']} "
                f"reason={reason_badge(details)}",
                flush=True,
            )

        (out_dir / "index.html").write_text(index_html(cards), encoding="utf-8")
        write_cause_template(out_dir, missed_pairs)
        write_cause_counts_stub(out_dir)

        n_mm = len(selected["missed_make"])
        n_cm = len(selected["correct_make"])
        n_ms = len(selected["miss"])
        n_shots = n_mm + n_cm + n_ms
        print("")
        print(f"Built review page at {out_dir}")
        print(
            f"Shots processed: {n_shots} ({n_mm} missed makes, {n_cm} correct makes, {n_ms} misses)"
        )
        print(f"Frames extracted: {n_shots} × 36 = {png_total} PNGs")
        print(
            f"Cause template written: cause_template.json ({n_mm} entries, all null)"
        )
        print("Open index.html in a browser to assign causes.")
        print("STOP — page built, causes assigned by human")
        return 0
    finally:
        for r in reader_cache.values():
            r.close()


if __name__ == "__main__":
    raise SystemExit(main())
