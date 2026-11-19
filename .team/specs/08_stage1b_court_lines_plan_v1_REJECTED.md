REJECTED by Claude Code, 2026-10-26 22:12. Direction (A) first is APPROVED. Fix: (1) center line contradiction: line 87 has +40.75 for Liberty (correct: 46 - 5.25), line 134 has 81.5 ft and 35.5 (wrong); use 40.75 everywhere. (2) NFHS three-point arc is centered on the basket (0, 0), radius 19.75, not (0, -5.25). (3) Liberty center line is RED (through the logo), not blue; do not hard-code a color per court line: detect all paint colors and let the geometry assign lines. (4) Liberty floor has extra non-basketball lines (blue, likely volleyball); the fit must reject lines that do not match the basketball model. (5) No tuning on the 60 measurement frames: fix every threshold on separate frames (at least 60 s from each measured frame), then measure once; no retuning after seeing results. (6) Half court counts only when the center line is detected; a frame without it is not a failure for that reason. (7) ## Files must list the coder script scripts/stage1b_court_lines.py, its config file, and the outputs, with the .venv run command; remove the backboard Y = -4 (backboard face is 1.25 ft behind the rim center; it is not a floor line anyway). Sideline width (50 ft) is an assumption at Liberty; measure it, do not gate on it.

# Stage 1b: Court Lines Detection — Coder Plan

**Author:** Hermes (Architect)  
**Date:** 2026-10-26  
**Status:** Plan for Vetted implementation  
**Gate:** Must pass Vetter review before OpenCode implements

---

## Executive Comparison & Recommendation

### Approach (A): Direct Painted-Line Detection + NFHS Model Fit
Detect red/blue lines (Liberty) or white lines (Adrian) per frame using color segmentation + line detection (Hough / LSD / Canny + RANSAC), then fit detected line segments to the known NFHS court geometry (lane 12 ft wide, FT line 13.75 ft from rim center, baseline 5.25 ft behind rim center, lane corners at ±6 ft, 3-pt arc radius 19.75 ft, center line, sidelines at ±25 ft). Output: per-frame homography from image → court feet (rim-center origin).

**Pros:**  
- Zero training data needed; works on any gym with painted lines visible  
- Geometric constraints (parallel lane lines, perpendicular FT line, known arc radius) reject outliers automatically  
- Interpretable: Vetter can see fitted lines overlaid on frames and judge by eye  
- Adapts to camera pan/zoom per frame — no temporal smoothing required  
- Liberty 92 ft court length known; Adrian length measured from fit (baseline-to-baseline)  
- No banned trials (no interpolation, no learned model to retrain)

**Cons:**  
- Color thresholds differ by gym (red/blue vs white) — need per-gym color config  
- Glare, shadows, worn paint, or player occlusion can break line segments  
- Must handle partial views (zoomed-in on lane may not show 3-pt arc or center line)

### Approach (B): Retrain Keypoint Model on Auto-Labeled Frames
Use (A) to auto-label 60 frames per gym, Scott reviews/corrects, then fine-tune `court_keypoint_detector.pt`.

**Pros:**  
- Could generalize to frames where lines are partially occluded  
- Fast inference once trained

**Cons:**  
- Stage 1 proved the 18-keypoint model fails on these gyms (8/20 frames with ≥4 points on Notus A1) — retraining on 60 frames is insufficient for robustness across pans/zooms  
- Black box: Vetter cannot inspect "why" a keypoint was placed  
- Requires GPU training pipeline, validation set, hyperparameter search — not a small measurable task  
- Still needs (A) for the auto-labels, so (A) must work first

### Approach (C): Both, (A) Primary + Model Cross-Check
Run (A) every frame; run keypoint model as a sanity check; flag frames where they disagree > threshold.

**Pros:**  
- Defense in depth; catches (A) failures on weird frames  
- Model disagreement becomes a review signal for Scott

**Cons:**  
- Adds complexity before (A) is proven  
- Model adds compute with unproven value on these gyms

---

### Recommendation: **Start with (A) only. Measure it rigorously on the same 60 frames. Decide on (B)/(C) after seeing numbers.**

**Rationale:**  
- The Vetter's finding: "the zero-point frames show the lane, free-throw circle, arcs, and center line clearly. The model, not the video, is the problem."  
- Painted lines are the ground truth; the model is a noisy observer of them  
- (A) is the most reliable across gyms/pans/zooms because it uses the invariant NFHS geometry, not a learned prior  
- Scott wants "the MOST RELIABLE approach across gyms, camera pans and zooms, not the easiest"  
- (A) produces per-frame homography directly; (B) and (C) depend on (A) working first  
- If (A) achieves ≥70% valid homography on Notus A1 (matching the Stage 1 keypoint gate), it earns the right to be primary

---

## Stage 1b Goal

Measure approach (A) on the **exact same 60 frames** used in Stage 1 (20 per game: Adrian, Notus A1, Notus A), with:

1. **Overlay images:** Fitted NFHS court model drawn over each frame (lines in court-space colors, projected through the per-frame homography back to image pixels)
2. **Per-frame JSON:** Lines found, fit error in pixels, success/failure, homography matrix, half-court Y in feet
3. **Summary report:** Aggregate numbers so (A) and the keypoint model can be compared frame-by-frame

**No banned trials.** No interpolation. No existing file changed. All outputs under `.team/stage1b_lines/`.

---

## Court Geometry (NFHS, Rim-Center Origin)

| Element | Court Coordinates (ft, origin = rim center, +Y toward midcourt) |
|---------|------------------------------------------------------------------|
| Rim center | (0, 0) |
| Free-throw line | Y = +13.75 (lane corners at X = ±6) |
| Baseline | Y = -5.25 (lane corners at X = ±6, sidelines at X = ±25) |
| Lane width | 12 ft (X = -6 to +6) |
| Sidelines | X = -25 (left), X = +25 (right) |
| Center line | Y = half-court distance (Liberty: +40.75; Adrian: measured) |
| 3-pt arc | Center (0, -5.25), radius 19.75 ft (NFHS) |
| Free-throw circle | Center (0, +13.75), radius 6 ft |

**Liberty gym:** 92 ft total → half-court Y = +40.75 ft from rim center.  
**Adrian gym:** Length unknown → measure from fitted baseline-to-baseline distance.

---

## Input Frames (60 Total — Same as Stage 1)

### Adrian (20 frames)
Video: `uploads/nfhs_gam0a66d85e12.mp4`  
Indices: `[0, 4873, 9746, 14619, 19492, 24365, 29238, 34111, 38984, 43857, 48730, 53603, 58476, 63349, 68222, 73095, 77968, 82841, 87714, 92587]`

### Notus A1 (20 frames)
Video: `uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4`  
Indices: `[0, 5047, 10094, 15141, 20188, 25235, 30282, 35329, 40376, 45423, 50470, 55517, 60564, 65611, 70658, 75705, 80752, 85799, 90846, 95893]`

### Notus A (20 frames)
Video: `uploads/LIBERTY_H_v_NOTUS_A_20260809_221334.mp4`  
Indices: `[0, 4682, 9364, 14046, 18728, 23410, 28092, 32774, 37456, 42138, 46820, 51502, 56184, 60866, 65548, 70230, 74912, 79594, 84276, 88958]`

---

## Algorithm: Per-Frame Court Line Detection & Fit

### 1. Color Segmentation (Per-Gym Config)
- **Liberty (Notus A1, Notus A):** Red paint (lane, FT line, 3-pt arc) + blue paint (baselines, sidelines, center line)  
  HSV ranges: red (two bands: 0-10 and 170-180), blue (100-130)
- **Adrian:** White paint (all lines)  
  HSV range: low saturation, high value
- Output: binary mask per color class

### 2. Line Segment Extraction
- Canny edges on each mask → Probabilistic Hough (`cv2.HoughLinesP`) or LSD (`cv2.createLineSegmentDetector`)  
- Parameters tuned so lane lines (long, straight) and arcs (curved → short segments) both produce segments  
- Merge collinear segments within angle tolerance (2°) and gap tolerance (20 px)

### 3. Geometric Model Fitting (RANSAC)
**Known NFHS line set (12 infinite lines + 1 circle):**
1. Left sideline: X = -25
2. Right sideline: X = +25
3. Baseline: Y = -5.25
4. Free-throw line: Y = +13.75
5. Left lane line: X = -6
6. Right lane line: X = +6
7. Center line: Y = H/2 (H = court length; Liberty H=81.5 ft from baseline to baseline → center at Y=35.5; Adrian H unknown)
8. 3-pt arc: circle center (0, -5.25), R = 19.75
9. Free-throw circle: center (0, +13.75), R = 6
10. Left lane baseline extension (optional): X = -6, Y < -5.25
11. Right lane baseline extension (optional): X = +6, Y < -5.25
12. Backboard line (optional): Y = -4 (front face), but excluded from homography (not floor plane)

**Fitting procedure:**
- For each detected segment, compute its line equation in image coordinates
- Hypothesize correspondences: each segment votes for which NFHS line(s) it could be (by angle and approximate position)
- RANSAC over correspondences: sample minimal sets (4 lines for homography = 8 constraints), compute H_img2court via `cv2.findHomography` (src = NFHS floor points on those lines, dst = segment endpoints projected to line), score by total reprojection error of all inlier segments
- Accept H if: ≥ 4 non-collinear line correspondences, RANSAC inliers ≥ 4, median reprojection error ≤ 2 px, condition number < 1e4
- For arcs: fit circle to arc segments in court space after provisional H; refine H by including arc points

### 4. Homography Output
- H_img2court: 3×3 mapping image pixels → court feet (rim-center origin)
- hoop_img_xy: image coordinates of rim center (H⁻¹ @ [0, 0, 1])
- scale_x, scale_y at hoop: from Jacobian of H at hoop_img_xy (ft/px)
- half_court_y_ft: projected center line Y coordinate (Liberty should be ~40.75; Adrian measured)

### 5. Success/Failure Criteria Per Frame
- **SUCCESS:** Valid H computed (all criteria above met)
- **FAILURE:** < 4 line correspondences, or RANSAC inliers < 4, or reprojection error > 2 px median, or condition number ≥ 1e4, or half_court_y_ft outside plausible range [28, 46] ft

---

## Outputs (Under `.team/stage1b_lines/`)

```
.team/stage1b_lines/
├── adrian/
│   ├── frame_0000_overlay.png
│   ├── frame_0000.json
│   ├── ...
│   ├── frame_92587_overlay.png
│   ├── frame_92587.json
│   └── summary_adrian.json
├── notus_a1/
│   ├── frame_0000_overlay.png
│   ├── frame_0000.json
│   ├── ...
│   ├── frame_95893_overlay.png
│   ├── frame_95893.json
│   └── summary_notus_a1.json
├── notus_a/
│   ├── frame_0000_overlay.png
│   ├── frame_0000.json
│   ├── ...
│   ├── frame_88958_overlay.png
│   ├── frame_88958.json
│   └── summary_notus_a.json
└── measurement_report.md
```

### Per-Frame Overlay (`frame_XXXXX_overlay.png`)
- Original frame with fitted NFHS court lines drawn in image space (project court model through H back to pixels)
- Color code: lane (green), FT line/circle (blue), baseline/sidelines (red), 3-pt arc (yellow), center line (magenta)
- Draw hoop center (white +), detected line segments (thin cyan), inlier segments (thick green)
- Text overlay: frame_idx, timestamp_ms, lines_found, fit_error_px, success/fail, half_court_y_ft

### Per-Frame JSON (`frame_XXXXX.json`)
```json
{
  "game": "notus_a1",
  "frame_idx": 20188,
  "timestamp_ms": 807520,
  "lines_detected": {
    "left_sideline": true,
    "right_sideline": false,
    "baseline": true,
    "ft_line": true,
    "left_lane": true,
    "right_lane": true,
    "center_line": false,
    "three_pt_arc": true,
    "ft_circle": false
  },
  "line_segments_found": 14,
  "inlier_segments": 9,
  "reprojection_error_px": 1.3,
  "homography_valid": true,
  "H_img2court": [[...], [...], [...]],
  "hoop_img_xy": [640, 360],
  "scale_x_ft_per_px": 0.012,
  "scale_y_ft_per_px": 0.011,
  "half_court_y_ft": 40.8,
  "court_length_ft": 81.6,
  "success": true
}
```

### Per-Game Summary (`summary_<game>.json`)
```json
{
  "game": "notus_a1",
  "video_path": "uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4",
  "total_frames": 100950,
  "frames_analyzed": 20,
  "frame_indices": [...],
  "success_count": 15,
  "failure_count": 5,
  "success_rate": 0.75,
  "lines_found_per_frame": {"mean": 6.2, "median": 7, "min": 2, "max": 9},
  "reprojection_error_px": {"mean": 1.4, "median": 1.2, "p90": 2.1},
  "half_court_y_ft": {"mean": 40.7, "std": 0.8, "min": 39.1, "max": 42.3},
  "court_length_ft": {"mean": 81.4, "std": 1.2},
  "keypoint_model_comparison": {
    "frames_both_succeed": 8,
    "lines_succeeds_keypoints_fails": 5,
    "keypoints_succeeds_lines_fails": 0,
    "both_fail": 7
  }
}
```

### Measurement Report (`measurement_report.md`)
- Table: 60 rows (one per frame) with frame_idx, game, lines_found, fit_error_px, success, half_court_y_ft, keypoint_model_floor_points (from Stage 1), keypoint_model_H_valid (from Stage 1)
- Aggregate comparison: (A) vs keypoint model on success rate, half-court consistency, frames where (A) works and keypoints don't (and vice versa)
- Visual summary: 3-panel figure per game (best overlay, median overlay, worst failure overlay) — like Vetter's `vetter_sheet_best_median_zero.png`
- Verdict: Does (A) meet the Stage 1 keypoint gate (≥70% valid H on Notus A1, half-court Y consistent with 40.75 ft)?

---

## Pass Gate for Stage 2 (Per-Frame Homography Pipeline)

- **Adrian:** ≥ 80% frames success, half-court Y measured and reported (no gate on value — gym length unknown)
- **Notus A1:** ≥ 70% frames success, half-court Y mean within 40.75 ± 2.0 ft, median reprojection error ≤ 1.5 px
- **Notus A:** ≥ 70% frames success, half-court Y consistent with Notus A1 (same gym)
- **Frame-by-frame comparison:** On frames where keypoint model got ≥4 floor points, (A) must also succeed; on frames where keypoint model got 0 points, (A) should succeed on ≥ 50%

---

## Implementation Constraints

- **No changes to existing files.** New code only.
- **No interpolation, no temporal smoothing.** Each frame independent.
- **Output directory:** `.team/stage1b_lines/` (create it)
- **Dependencies:** OpenCV, NumPy, Ultralytics (for reference only — not used in (A))
- **Config:** Per-gym HSV ranges in a small YAML/JSON (Liberty vs Adrian)
- **Reference code:** `dist/scripts/run_v8.py` (keypoint model usage), `court_homography.py` (homography math, Jacobian scale), `pick_court_points.py` (NFHS coordinates), `ai_bridge.py` (rim-center origin constants)

---

## Files

```
.team/specs/08_stage1b_court_lines_plan.md
```

(Only this file is created/edited. All Stage 1b outputs go to `.team/stage1b_lines/` — created by the Coder at runtime.)