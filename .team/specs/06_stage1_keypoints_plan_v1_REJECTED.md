REJECTED by Claude Code, 2026-10-26 21:42: (1) Adrian video is uploads/nfhs_gam0a66d85e12.mp4, not uploads/LIBERTY_A_v_ADRIAN_H.mp4 (does not exist). (2) python -m .team.stage1_measure_keypoints is invalid (module names cannot start with a dot) and plain python is the hermes venv; use scripts/stage1_measure_keypoints.py run with ..venvScriptspython.exe. (3) Self-contradiction: no homography in Stage 1, yet half-court means and gates are required. Stage 1 is discovery only: overlays, per-index detection rates, and landmark hypotheses; no half-court numbers and no Stage 2 gates (those come after the Vetter labels the indices). (4) Do not call points floor points before indices are known; report keypoints_detected_conf_0_3. (5) Allow the GPU when available (do not force CUDA_VISIBLE_DEVICES empty); evenly spaced frames only, no vague key moments.

# Stage 1 Keypoint Measurement Plan — Coder Plan (VETTED with Corrections 3, 4, 5)

**Goal:** Quantify `models/court_keypoint_detector.pt` on ~20 frames per game (Adrian, Notus A1, Notus A). Produce overlay images and JSON per frame, plus a `measurement_report.md`. Measurement only — no changes to `ai_bridge.py` or any existing file, no interpolation, read-only use of the model.

---

## Vetter Corrections Incorporated

1. **(Correction 3)** Adrian's game (uploads/LIBERTY_A_v_ADRIAN_H.mp4) was played at **Adrian's gym**, whose length is unknown. **Remove the Adrian half-court gate [38, 44] ft**. Report Adrian's measured half-court distance instead. Only both Notus games (uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4 and uploads/LIBERTY_H_v_NOTUS_A_20260809_221334.mp4) are at Liberty (92 ft court → half court 40.75 ft from rim center).

2. **(Correction 4)** The meaning of the model's **18 keypoints is unknown**. Stage 1 must discover it: **number every point on the overlays** (index 0–17), and **report each index's likely court landmark with the frames that show it**. Do not assume the list in §1.2 of the architecture doc.

3. **(Correction 5)** Use **ONE origin: the rim center** (FT line +13.75, baseline -5.25, lane ±6), as in `ai_bridge.py` and `pick_court_points.py`. The +15/-4 values in the architecture §1.2 are backboard-face values and would shift every position by 1.25 ft. All court coordinates in this plan use the rim-center origin.

---

## Videos and Frame Selection

| Game | Video Path | Gym | Half-Court Reference |
|------|------------|-----|---------------------|
| Adrian | `uploads/LIBERTY_A_v_ADRIAN_H.mp4` | Adrian's gym (unknown length) | Report measured value only |
| Notus A1 | `uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4` | Liberty (92 ft) | 40.75 ft from rim center |
| Notus A | `uploads/LIBERTY_H_v_NOTUS_A_20260809_221334.mp4` | Liberty (92 ft) | 40.75 ft from rim center |

**Frame selection per game (~20 frames):**
- Uniform spacing: `total_frames // 20` stride, starting at frame 0
- Plus key moments if identifiable without tags: free-throw setups, transition wide shots, zoomed-in half-court, zoomed-in under basket
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
  "floor_points_detected": 6,
  "H_computed": true,
  "H_inliers": 6,
  "reproj_error_px": 1.23,
  "half_court_y_ft": 40.82
}
```

- `label` is always `"UNKNOWN_<id>"` — we do not assign semantic names here.
- `floor_points_detected` = count of keypoints with `conf ≥ 0.3` that, when mapped via H, project to Z=0 floor plane (lane corners, FT line corners, baseline corners, sideline intersections). Since we don't know which indices are floor points yet, **for Stage 1 count all 18 keypoints with conf ≥ 0.3**. The Vetter will review overlays to identify floor-plane indices.
- `H_computed` = true if ≥ 4 keypoints with conf ≥ 0.3 were detected (minimum for homography). Do NOT compute H in Stage 1 — just record whether it *could* be computed.
- `H_inliers`, `reproj_error_px`, `half_court_y_ft` = `null` if `H_computed` is false.

---

## Overlay Image Specification

For each frame, save an overlay image with:
- Original frame as background
- All 18 keypoints drawn as circles (radius 6 px)
- **Color by confidence**: green (conf ≥ 0.5), yellow (0.3 ≤ conf < 0.5), red (conf < 0.3)
- **Index number** (0–17) written next to each circle in white with black outline
- Top-left text: `Game: <name> | Frame: <idx> | Time: <ms>ms | Floor pts ≥0.3: <N>`

---

## Per-Game Summary JSON

```json
{
  "game": "adrian",
  "video_path": "uploads/LIBERTY_A_v_ADRIAN_H.mp4",
  "total_frames": 45000,
  "frames_analyzed": 20,
  "frame_indices": [0, 2250, 4500, ...],
  "keypoint_detection_freq": {
    "0": 18, "1": 19, ..., "17": 12
  },
  "frames_with_4plus_floor_pts": 16,
  "pct_frames_4plus_floor_pts": 80.0,
  "half_court_y_ft_measurements": [39.2, 40.1, 41.5, ...],
  "half_court_y_ft_mean": 40.3,
  "half_court_y_ft_std": 1.1,
  "half_court_y_ft_min": 38.7,
  "half_court_y_ft_max": 42.0
}
```

- `keypoint_detection_freq[id]` = number of frames (out of 20) where keypoint `id` had `conf ≥ 0.3`
- `half_court_y_ft_measurements`: for each frame where `H_computed` would be true, project the center-line keypoints (whichever indices they are) through a provisional H built from the 4 lane corners (indices TBD by Vetter review) and record the Y coordinate in feet from rim center. Since we don't know which indices are the center-line points yet, **for Stage 1 just record the raw image Y of every keypoint with conf ≥ 0.3**. The Vetter will identify center-line indices from overlays and compute half-court Y in the report.

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
3. **Half-court measurements**:
   - Adrian: mean, std, min, max (no gate — just report)
   - Notus A1: mean, std, min, max (gate: within [38, 44] ft)
   - Notus A: mean, std, min, max (gate: within [38, 44] ft)
4. **Floor-point detection rate**: % frames with ≥4 keypoints at conf ≥ 0.3 per game
5. **Pass/Fail for Stage 2 gate**:
   - Adrian: ≥ 80% frames with ≥4 floor points (no half-court gate)
   - Notus A1: ≥ 70% frames with ≥4 floor points, half-court Y in [38, 44] ft
   - Notus A: ≥ 70% frames with ≥4 floor points, half-court Y in [38, 44] ft
   - At least 10 of 18 keypoints detected ≥ 60% of frames across all games

---

## Files

Only these files are created/edited by the coder:
- `.team/specs/06_stage1_keypoints_plan.md` ← **this file**
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
python -m .team.stage1_measure_keypoints
```

The coder will implement a single module `.team/stage1_measure_keypoints/__main__.py` (and any helper modules under `.team/stage1_measure_keypoints/`) that executes the full Stage 1 measurement when invoked as above. The module must:
1. Create `.team/stage1_keypoints/{adrian,notus_a1,notus_a}/` directories
2. Load the model from `models/court_keypoint_detector.pt` (relative to repo root)
3. Open each video, select ~20 frames per the frame selection rules
4. Run inference, save overlays and JSONs
5. Write per-game summaries
6. Write `measurement_report.md`

---

## Constraints (Hard)

- **Read-only on models/**: the model file is loaded for inference only; no training, no fine-tuning, no weight modification.
- **No changes to ai_bridge.py, court_homography.py, net_detector.py, scoreboard_clock.py, pick_court_points.py, run_v8.py, or any existing repo file.**
- **No interpolation** of keypoints across frames (run_v8.py lines 85–98 do this — do not repeat).
- **No homography computation** in Stage 1 — only record whether ≥4 floor-point candidates exist.
- **Paths relative to repo root**: `uploads/...`, `models/...`, `.team/stage1_keypoints/...`
- **Headless operation**: set `CUDA_VISIBLE_DEVICES=''` and `OMP_NUM_THREADS='1'` as in run_v8.py.
- **Use ultralytics YOLO class** exactly as run_v8.py lines 25–26, 71–73.

---

## Acceptance Criteria (Vetter Will Check)

1. All 60 overlay images exist, each shows 18 numbered keypoints color-coded by confidence.
2. All 60 per-frame JSONs match the schema; `label` fields are `UNKNOWN_<id>`.
3. Three per-game summary JSONs exist with correct structure.
4. `measurement_report.md` contains the keypoint index report table and half-court measurements with gates evaluated.
5. No file outside `.team/stage1_keypoints/` and this plan file was created or modified.
6. The command `python -m .team.stage1_measure_keypoints` runs to completion without error.

---

## Next Step After Stage 1 Passes

Vetter reviews overlays and report → identifies which keypoint indices correspond to floor-plane landmarks (lane corners, FT line corners, baseline corners, center line, sideline intersections) → Architect writes Stage 2 plan using those indices and the rim-center origin.