VETTED by Claude Code, 2026-10-26 21:45: v2 fixes all five v1 errors (real Adrian video uploads/nfhs_gam0a66d85e12.mp4; scripts/stage1_measure_keypoints.py run with .venv python; discovery only, no homography, half court, or gates; keypoints_detected_conf_0_3 instead of floor points; GPU allowed, evenly spaced frames). Measurement only; read-only model; no existing file changed.

# Stage 1 Keypoint Measurement Plan — Coder Plan

**Goal:** Quantify `models/court_keypoint_detector.pt` on ~20 evenly spaced frames per game (Adrian, Notus A1, Notus A). Produce overlay images and JSON per frame, plus a `measurement_report.md`. Measurement only — no changes to `ai_bridge.py` or any existing file, no interpolation, read-only use of the model.

---

## Videos and Frame Selection

| Game | Video Path | Gym |
|------|------------|-----|
| Adrian | `uploads/nfhs_gam0a66d85e12.mp4` | Adrian's gym (unknown length) |
| Notus A1 | `uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4` | Liberty (92 ft) |
| Notus A | `uploads/LIBERTY_H_v_NOTUS_A_20260809_221334.mp4` | Liberty (92 ft) |

**Frame selection per game (~20 frames):**
- Uniform spacing only: `total_frames // 20` stride, starting at frame 0
- No key moments, no tag-based selection
- Record the exact frame indices chosen in the JSON output

---

## Model Loading

Load the model exactly as `dist/scripts/run_v8.py` does, but with paths relative to the repo root:

```python
from ultralytics import YOLO
import cv2
import numpy as np

court_model = YOLO("models/court_keypoint_detector.pt", verbose=False)
```

Run inference on a single frame:
```python
result = court_model.predict(frame, conf=0.3, verbose=False)[0]
if result.keypoints is not None and len(result.keypoints) > 0:
    kpts = result.keypoints[0].xy.cpu().numpy()[0]   # shape (18, 2)
    confs = result.keypoints[0].conf.cpu().numpy()[0] # shape (18,)
```

**GPU:** Allow GPU when available (do not force `CUDA_VISIBLE_DEVICES=''`).

---

## Output Directory

All outputs under `.team/stage1_keypoints/`:
```
.team/stage1_keypoints/
├── adrian/
│   ├── frame_0000_overlay.jpg
│   ├── frame_0000.json
│   ├── ...
│   └── summary_adrian.json
├── notus_a1/
│   ├── frame_0000_overlay.jpg
│   ├── frame_0000.json
│   ├── ...
│   └── summary_notus_a1.json
├── notus_a/
│   ├── frame_0000_overlay.jpg
│   ├── frame_0000.json
│   ├── ...
│   └── summary_notus_a.json
└── measurement_report.md
```

---

## Per-Frame JSON Schema

```json
{
  "game": "adrian|notus_a1|notus_a",
  "frame_idx": 1234,
  "timestamp_ms": 49360,
  "keypoints": [
    {"id": 0, "x": 642.3, "y": 387.1, "conf": 0.87, "label": "UNKNOWN_0"},
    {"id": 1, "x": 712.8, "y": 391.4, "conf": 0.82, "label": "UNKNOWN_1"},
    ...
    {"id": 17, "x": 598.2, "y": 512.7, "conf": 0.41, "label": "UNKNOWN_17"}
  ],
  "keypoints_detected_conf_0_3": 6,
  "H_computed": false,
  "H_inliers": null,
  "reproj_error_px": null,
  "half_court_y_ft": null
}
```

- `label` is always `"UNKNOWN_<id>"` — we do not assign semantic names here.
- `keypoints_detected_conf_0_3` = count of all 18 keypoints with `conf ≥ 0.3` (no floor-point classification in Stage 1).
- `H_computed` = always `false` in Stage 1 (no homography computation).
- `H_inliers`, `reproj_error_px`, `half_court_y_ft` = always `null` in Stage 1.

---

## Overlay Image Specification

For each frame, save an overlay image with:
- Original frame as background
- All 18 keypoints drawn as circles (radius 6 px)
- **Color by confidence**: green (conf ≥ 0.5), yellow (0.3 ≤ conf < 0.5), red (conf < 0.3)
- **Index number** (0–17) written next to each circle in white with black outline
- Top-left text: `Game: <name> | Frame: <idx> | Time: <ms>ms | Keypoints ≥0.3: <N>`

---

## Per-Game Summary JSON

```json
{
  "game": "adrian",
  "video_path": "uploads/nfhs_gam0a66d85e12.mp4",
  "total_frames": 45000,
  "frames_analyzed": 20,
  "frame_indices": [0, 2250, 4500, ...],
  "keypoint_detection_freq": {
    "0": 18, "1": 19, ..., "17": 12
  }
}
```

- `keypoint_detection_freq[id]` = number of frames (out of 20) where keypoint `id` had `conf ≥ 0.3`
- No half-court measurements, no floor-point counts, no Stage 2 gates in Stage 1 summaries.

---

## Keypoint Index Report (in measurement_report.md)

Create a table with one row per index (0–17):

| Index | Detection Rate (all games) | Likely Landmark | Evidence Frames (game, frame_idx, image_xy) |
|-------|---------------------------|-----------------|--------------------------------------------|
| 0     | 95%                       | FT line left?   | adrian:1234 (642,387), notus_a1:5678 (712,391) |
| 1     | 92%                       | FT line right?  | ... |
| ...   | ...                       | ...             | ... |

- "Likely Landmark" is a hypothesis based on visual inspection of overlays (e.g., "left lane corner at FT line", "right baseline corner", "center line left", "3-pt arc left"). Mark as "UNCLEAR" if ambiguous.
- "Evidence Frames": list 2–3 frames per game where the keypoint is clearly visible and high-confidence, with image coordinates.

---

## Measurement Report (measurement_report.md)

Required sections:
1. **Per-game summary tables** (from summary JSONs)
2. **Keypoint index report** (table above)

**No half-court measurements, no Stage 2 gates, no pass/fail evaluation in Stage 1.** Those come after the Vetter labels the indices in Stage 2.

---

## Files

Only these files are created/edited by the coder:
- `.team/specs/06_stage1_keypoints_plan.md` ← **this file**
- `scripts/stage1_measure_keypoints.py` ← **the coder script**
- `.team/stage1_keypoints/adrian/frame_XXXX_overlay.jpg` (20 files)
- `.team/stage1_keypoints/adrian/frame_XXXX.json` (20 files)
- `.team/stage1_keypoints/adrian/summary_adrian.json`
- `.team/stage1_keypoints/notus_a1/frame_XXXX_overlay.jpg` (20 files)
- `.team/stage1_keypoints/notus_a1/frame_XXXX.json` (20 files)
- `.team/stage1_keypoints/notus_a1/summary_notus_a1.json`
- `.team/stage1_keypoints/notus_a/frame_XXXX_overlay.jpg` (20 files)
- `.team/stage1_keypoints/notus_a/frame_XXXX.json` (20 files)
- `.team/stage1_keypoints/notus_a/summary_notus_a.json`
- `.team/stage1_keypoints/measurement_report.md`

**No other files are created, edited, or deleted.**

---

## Exact Commands to Run

```bash
cd /mnt/c/Users/scott/Documents/liberty-basketball-analysis
.\.venv\Scripts\python.exe scripts/stage1_measure_keypoints.py
```

The coder will implement a single script `scripts/stage1_measure_keypoints.py` that executes the full Stage 1 measurement when invoked as above. The script must:
1. Create `.team/stage1_keypoints/{adrian,notus_a1,notus_a}/` directories
2. Load the model from `models/court_keypoint_detector.pt` (relative to repo root)
3. Open each video, select ~20 evenly spaced frames per the frame selection rules
4. Run inference, save overlays and JSONs
5. Write per-game summaries
6. Write `measurement_report.md`

---

## Constraints (Hard)

- **Read-only on models/**: the model file is loaded for inference only; no training, no fine-tuning, no weight modification.
- **No changes to ai_bridge.py, court_homography.py, net_detector.py, scoreboard_clock.py, pick_court_points.py, run_v8.py, or any existing repo file.**
- **No interpolation** of keypoints across frames (run_v8.py lines 85–98 do this — do not repeat).
- **No homography computation** in Stage 1 — only record whether ≥4 keypoints with conf ≥ 0.3 exist (as `keypoints_detected_conf_0_3`).
- **Paths relative to repo root**: `uploads/...`, `models/...`, `.team/stage1_keypoints/...`
- **Use ultralytics YOLO class** exactly as run_v8.py lines 25–26, 71–73.
- **Evenly spaced frames only** — no key moments, no tag-based selection.

---

## Acceptance Criteria (Vetter Will Check)

1. All 60 overlay images exist, each shows 18 numbered keypoints color-coded by confidence.
2. All 60 per-frame JSONs match the schema; `label` fields are `UNKNOWN_<id>`; `keypoints_detected_conf_0_3` present; `H_computed` is `false`; `H_inliers`, `reproj_error_px`, `half_court_y_ft` are `null`.
3. Three per-game summary JSONs exist with correct structure (no half-court fields, no floor-point fields).
4. `measurement_report.md` contains the keypoint index report table only (no half-court measurements, no gates).
5. No file outside `.team/stage1_keypoints/` and this plan file was created or modified.
6. The command `.\.venv\Scripts\python.exe scripts/stage1_measure_keypoints.py` runs to completion without error.

---

## Next Step After Stage 1 Passes

Vetter reviews overlays and report → identifies which keypoint indices correspond to floor-plane landmarks (lane corners, FT line corners, baseline corners, center line, sideline intersections) → Architect writes Stage 2 plan using those indices and the rim-center origin.