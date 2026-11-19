REJECTED by Claude Code, 2026-10-27: v2 fixes the leak (no cutoff numbers; measured on fitting frames; holdout run added) but: (1) Wrong file: data/roi/notus_roi.json does not exist; the ROI file is data/roi/notus_scoreboard_rois.json (scoreboard_clock_720p.py line 30). Say whether a corrected box replaces it or goes to a new file AND that the reader loads it. (2) Holdout leak: scripts/fit_notus_segments.py _sample_timestamps (line 60) excludes only GATE times; the plan says keep that sampling, so fitting frames could sit next to holdout times. The plan must have the coder add the 20 holdout times (from the plan, not from the holdout file) to the exclusion. (3) Circular rule: "10th percentile over lit-digit pixels" needs lit pixels defined before any cutoff exists. Give a rule that does not depend on the cutoff being set, e.g. red-hue pixels inside the segment regions of segments that are ON for a digit whose value is known from the fitting frame (say how the value is known — e.g. the Vetter reads the fitting crops by eye before measuring), or another rule that is fixed in advance. (4) Box re-measure "maximize mean V" is unbounded (shrinks to a few bright pixels): keep the measured w,h and only search a bounded x,y shift, on fitting frames. (5) _notus_red_mask reads the JSON on every call with a cwd-relative path: load once from ROOT / data/roi, like _load_segment_geometry.

# NEXT_TASK.md — Notus 720p Reader Fix (v2)

## Rejection Reasons (from 09_notus_reader_fix_v1_REJECTED.md)
1. **Leak**: Mask cutoffs S>50/V>50 were picked from gate-timestamp frames; thresholds must be measured on frames ≥60 s from every gate AND holdout time, then frozen.
2. **Contradiction**: Lit tens V ≈ 10–50 (blank V ≈ 10) but fix used V>50 — a lit tens at V~10 means the tens box may not sit on the digit. Check box position before any color change.
3. **Missing holdout run**: Plan omits the single holdout run after gate passes.
4. **Scope violation**: Only NEXT_TASK.md may be created/edited; no scratch scripts.

---

## Fix Plan

### 0. Verify home/away TENS box positions (FIRST, before any mask change)
On **fitting frames only** (frames ≥60 s from every gate time and every holdout time):
- For each of the four scoreboard slots (home_tens, home_ones, away_tens, away_ones), crop the current `notus_roi.json` box on a fitting frame where the score is visibly changing (so tens digit is definitely lit).
- Measure mean V inside the box. If mean V ≈ 10 (same as blank), the box is misplaced — it is not covering the tens digit.
- **If any box is wrong**: Re-measure its (x, y, w, h) on fitting frames by finding the rectangle that maximizes mean V when the tens digit is lit (e.g., score ≥ 10). Write corrected boxes to a new `data/roi/notus_roi.json` (do not edit the original until verified). The coder does this re-measurement; the plan does not supply coordinates.

Gate times (s): A1 202, 606, 1010, 1413, 1817, 2221, 2625, 3028, 3432, 3836; A 187, 562, 936, 1311, 1686, 2060, 2435, 2810, 3184, 3559  
Holdout times (s): A1 246.9, 650.7, 1054.5, 1458.3, 1862.1, 2265.9, 2669.7, 3073.5, 3477.3, 3881.1; A 232.3, 606.8, 981.3, 1356.0, 1730.6, 2105.1, 2479.6, 2854.1, 3229.6, 3603.9  
**Fitting frames = any frame whose timestamp is ≥60 s away from ALL of the above 40 times.**

---

### 1. Measure Notus red-digit colour on fitting frames ONLY (no gate/holdout frames)
Using the (possibly corrected) ROI boxes from step 0 on fitting frames only:
- For each lit digit crop (score visibly non-zero), compute HSV of pixels inside the digit region.
- **Rule (fixed before measuring)**: Take the 10th percentile of V and the 10th percentile of S over all lit-digit pixels across all four slots and all fitting frames. These two numbers become the frozen `NOTUS_S_MIN` and `NOTUS_V_MIN`.
- Write `NOTUS_S_MIN` and `NOTUS_V_MIN` to `data/roi/notus_red_thresholds.json` (keys: `s_min`, `v_min`). The coder runs the measurement and writes the file; **this plan contains no final cutoff numbers**.
- Hue ranges stay the standard red wrap: [0, 12] ∪ [165, 180] (H in 0–179 OpenCV scale).

---

### 2. Add Notus-specific mask to `scoreboard_clock_720p.py`
```python
def _notus_red_mask(crop: np.ndarray) -> np.ndarray:
    """Red mask for Notus 720p board using frozen thresholds from notus_red_thresholds.json."""
    import cv2, json
    from pathlib import Path
    thresholds = json.loads(Path("data/roi/notus_red_thresholds.json").read_text())
    s_min = thresholds["s_min"]
    v_min = thresholds["v_min"]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    low = cv2.inRange(hsv, (0, s_min, v_min), (12, 255, 255))
    high = cv2.inRange(hsv, (165, s_min, v_min), (180, 255, 255))
    mask = cv2.bitwise_or(low, high)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
```

---

### 3. Update `scripts/fit_notus_segments.py`
- Import `_notus_red_mask` from `scoreboard_clock_720p` instead of `_red_mask` from `scoreboard_clock`.
- Use `_notus_red_mask` in `_collect_masks`.
- Keep all other logic (frame sampling ≥60 s from gate, hole detection, `core_scale=0.46`).
- Re-run to produce new `data/roi/notus_segment_geometry.json`.

---

### 4. Update `scoreboard_clock_720p.py` (do NOT edit `scoreboard_clock.py`)
- Replace `_red_mask` calls in `_read_score` with `_notus_red_mask`.
- Keep `_read_notus_digit`, `_read_score`, `_SEGMENT_ON=0.12`, `_SEVEN_SEGMENT` unchanged.
- The new geometry + new mask will yield correct segment occupancy.

---

### 5. Re-run the 20-crop gate ONCE (no retuning)
```bash
.venv/Scripts/python.exe scripts/fit_notus_segments.py
.venv/Scripts/python.exe -m pytest tests/test_notus_digit_gate.py -q
```
**Expected**: 20/20 pass. If not, stop — do not retune.

---

### 6. Single holdout run (only if gate passes 20/20)
- Coder writes `tests/test_notus_holdout_gate.py` that reads `.team/specs/04_notus_holdout_truth.json` (Architect must NOT open that file or the holdout_*.png crops).
- Run once:
```bash
.venv/Scripts/python.exe -m pytest tests/test_notus_holdout_gate.py -q
```
**Expected**: holdout passes. No further changes after this run.

---

## Files
- `scoreboard_clock_720p.py` — add `_notus_red_mask` (reads frozen thresholds); use it in `_read_score`
- `scripts/fit_notus_segments.py` — import and use `_notus_red_mask` for fitting
- `data/roi/notus_red_thresholds.json` — created by step 1 measurement (keys: `s_min`, `v_min`)
- `data/roi/notus_roi.json` — potentially corrected by step 0 (if any tens box was misplaced)
- `data/roi/notus_segment_geometry.json` — regenerated by fitting script
- `tests/test_notus_digit_gate.py` — unchanged (validates the fix)
- `tests/test_notus_holdout_gate.py` — created by coder (reads holdout truth, runs once after gate passes)

---

## Constraints
- Do NOT edit `scoreboard_clock.py`.
- Do NOT create any file other than those listed above (no scratch scripts, no temp files in repo root).
- If you need numbers, run Python with code on stdin (` .venv/Scripts/python.exe - <<'PY' ... PY`).
- Never sample video within 60 s of a holdout time.