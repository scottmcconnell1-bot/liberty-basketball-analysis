VETTED by Claude Code, 2026-10-27 09:25: v4 fixes the three v3 points (ON-segment regions only; coder saves fitting crops to .team/notus_fit_crops/ and STOPS until the Vetter writes eye_read_values.json; approved ROI file copied before any change) and keeps the v1/v2 fixes (no cutoff numbers from gate frames; fitting frames >= 60 s from all 20 gate and 20 holdout times, holdout times added to _sample_timestamps; bounded box shift; thresholds loaded once from ROOT; single holdout run after 20/20). Checked by diff --strip-trailing-cr against v3: only those changes. One edit by the Vetter in step 1: the plan wrote `_SEVEN_SEGMENT[digit]`, but scoreboard_clock.py line 47 maps pattern -> digit (and 6/7/9 have two patterns each), so that lookup would raise KeyError; replaced with the inverse rule (segments common to every pattern for the digit). Hermes edited only NEXT_TASK.md.

# NEXT_TASK.md — Notus 720p Reader Fix (v3)

## Rejection Reasons (from 09_notus_reader_fix_v2_REJECTED.md)
1. **Wrong ROI file**: `data/roi/notus_roi.json` does not exist; the ROI file is `data/roi/notus_scoreboard_rois.json` (scoreboard_clock_720p.py line 30). Say whether a corrected box replaces it or goes to a new file AND that the reader loads it.
2. **Holdout leak in fitting**: `scripts/fit_notus_segments.py` `_sample_timestamps` (line 60) excludes only GATE times; fitting frames could sit next to holdout times. The plan must have the coder add the 20 holdout times (from the plan, not from the holdout file) to the exclusion.
3. **Circular threshold rule**: "10th percentile over lit-digit pixels" needs lit pixels defined before any cutoff exists. Give a rule that does not depend on the cutoff being set, e.g. red-hue pixels inside the segment regions of segments that are ON for a digit whose value is known from the fitting frame (say how the value is known — e.g. the Vetter reads the fitting crops by eye before measuring), or another rule fixed in advance.
4. **Unbounded box re-measure**: "maximize mean V" shrinks to a few bright pixels. Keep the measured w,h and only search a bounded x,y shift, on fitting frames.
5. **_notus_red_mask loads JSON per-call with cwd-relative path**: Load once from ROOT / data/roi, like `_load_segment_geometry`.

## Rejection Reasons (from 09_notus_reader_fix_v1_REJECTED.md — keep fixed)
1. **Leak**: Mask cutoffs S>50/V>50 were picked from gate-timestamp frames; thresholds must be measured on frames ≥60 s from every gate AND holdout time, then frozen.
2. **Contradiction**: Lit tens V ≈ 10–50 (blank V ≈ 10) but fix used V>50 — a lit tens at V~10 means the tens box may not sit on the digit. Check box position before any color change.
3. **Missing holdout run**: Plan omits the single holdout run after gate passes.
4. **Scope violation**: Only NEXT_TASK.md may be created/edited; no scratch scripts.

---

## Rejection Reasons (from 09_notus_reader_fix_v3_REJECTED.md)
1. Step 1 takes the UNION of all seven segment regions. For a digit like 1 (two segments on) the five OFF segments are dark board, so the 10th percentile is pulled toward unlit pixels and the cutoff comes out too low. **Use only the regions of the segments that are ON for the eye-read digit (_SEVEN_SEGMENT gives which).**
2. **No stop point**: the coder must first save the fitting crops (e.g. under `.team/notus_fit_crops/`, listed in ## Files) and STOP; the Vetter writes the eye-read values to a file (name it in ## Files); only then does the coder measure. Step 0 may use those same eye-read values to know a tens digit is lit.
3. `data/roi/notus_scoreboard_rois.json` is untracked (no git history) and holds the approved boxes: **before any in-place change the coder copies it to `data/roi/notus_scoreboard_rois_approved_2026-10-26.json` (list it in ## Files).**

---

## Fix Plan

### 0. Verify home/away TENS box positions (FIRST, before any mask change) — DONE
**Before any in-place change**, the coder copies `data/roi/notus_scoreboard_rois.json` → `data/roi/notus_scoreboard_rois_approved_2026-10-26.json`.

On **fitting frames only** (frames ≥60 s from every gate time and every holdout time):
- The coder extracts ~10 fitting-frame crops per slot (home_tens, home_ones, away_tens, away_ones) where the score is visibly changing (so tens digit is definitely lit) and saves them under `.team/notus_fit_crops/`.
- **STOP**. The coder does not measure anything yet.
- The Vetter reads the saved crops by eye and writes the ground-truth digit value for each crop to `.team/notus_fit_crops/eye_read_values.json` (one entry per crop: `{"crop_path": "...", "slot": "home_tens", "digit": 3}`).
- The coder then uses those eye-read values to know which tens boxes are on a lit-digit frame. For each of the four scoreboard slots, on a fitting frame where the Vetter-confirmed tens digit is non-blank (digit ≥ 1), crop the current `notus_scoreboard_rois.json` box and measure mean V inside the box.
- If mean V ≈ 10 (same as blank), the box is misplaced — it is not covering the tens digit.
- **If any box is wrong**: Re-measure its (x, y) on fitting frames by searching a bounded x,y shift (±8 px in x, ±6 px in y) around the current box center, keeping the measured w,h fixed, to maximize mean V when the tens digit is lit (e.g., score ≥ 10). Write corrected boxes back into `data/roi/notus_scoreboard_rois.json` (replacing the existing tens/ones boxes under `games/*/scores` and `default/scores`). The reader already loads this file via `load_rois()` — no code change needed. The coder does this re-measurement; the plan does not supply coordinates.

Gate times (s): A1 202, 606, 1010, 1413, 1817, 2221, 2625, 3028, 3432, 3836; A 187, 562, 936, 1311, 1686, 2060, 2435, 2810, 3184, 3559  
Holdout times (s): A1 246.9, 650.7, 1054.5, 1458.3, 1862.1, 2265.9, 2669.7, 3073.5, 3477.3, 3881.1; A 232.3, 606.8, 981.3, 1356.0, 1730.6, 2105.1, 2479.6, 2854.1, 3229.6, 3603.9  
**Fitting frames = any frame whose timestamp is ≥60 s away from ALL of the above 40 times.**

---

### 1. Measure Notus red-digit colour on fitting frames ONLY (no gate/holdout frames)
Using the (possibly corrected) ROI boxes from step 0 on fitting frames only:
- The coder loads the eye-read values from `.team/notus_fit_crops/eye_read_values.json` (written by the Vetter). For each crop where the Vetter-confirmed digit is non-blank, look up the **segment regions from the current `notus_segment_geometry.json`** (mapped into the slot box) **for only the segments that are ON for that digit** (the ON segments for a digit are the letters common to EVERY pattern that maps to that digit — 6 → c,d,e,f,g; 7 → a,b,c; 9 → a,b,c,f,g; every other digit has one pattern; region names are the letters a–g, as in `_SEGMENTS`). Union those ON-segment regions, and collect pixels inside that union.
- **Rule (fixed before measuring)**: From those lit-segment pixels, take the central 98% of the hue distribution (handling wrap-around at 180: map hues >165 to hue-180 so the red cluster is contiguous around 0, compute the 1st and 99th percentiles, map back to 0–179). Also take the 10th percentile of V and the 10th percentile of S over the same pixels. These four numbers become the frozen `NOTUS_H_MIN`, `NOTUS_H_MAX` (the contiguous hue interval in 0–179), `NOTUS_S_MIN`, and `NOTUS_V_MIN`.
- Write `h_min`, `h_max`, `s_min`, `v_min` to `data/roi/notus_red_thresholds.json`. The coder runs the measurement and writes the file; **this plan contains no final cutoff numbers**.

---

### 2. Add Notus-specific mask to `scoreboard_clock_720p.py`
```python
_NOTUS_THRESHOLDS: dict | None = None

def _load_notus_thresholds() -> dict:
    global _NOTUS_THRESHOLDS
    if _NOTUS_THRESHOLDS is not None:
        return _NOTUS_THRESHOLDS
    import json
    from pathlib import Path
    path = ROOT / "data" / "roi" / "notus_red_thresholds.json"
    _NOTUS_THRESHOLDS = json.loads(path.read_text(encoding="utf-8"))
    return _NOTUS_THRESHOLDS


def _notus_red_mask(crop: np.ndarray) -> np.ndarray:
    """Red mask for Notus 720p board using frozen thresholds from notus_red_thresholds.json."""
    import cv2
    thresholds = _load_notus_thresholds()
    h_min = thresholds["h_min"]
    h_max = thresholds["h_max"]
    s_min = thresholds["s_min"]
    v_min = thresholds["v_min"]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    if h_min <= h_max:
        mask = cv2.inRange(hsv, (h_min, s_min, v_min), (h_max, 255, 255))
    else:
        # wrap-around interval (should not occur after central-98% rule but handle anyway)
        low = cv2.inRange(hsv, (0, s_min, v_min), (h_max, 255, 255))
        high = cv2.inRange(hsv, (h_min, s_min, v_min), (179, 255, 255))
        mask = cv2.bitwise_or(low, high)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
```

---

### 3. Update `scripts/fit_notus_segments.py`
- Import `_notus_red_mask` from `scoreboard_clock_720p` instead of `_red_mask` from `scoreboard_clock`.
- Use `_notus_red_mask` in `_collect_masks`.
- **In `_sample_timestamps`**: add the 20 holdout times (listed in step 0 above, hardcoded in the function) to the exclusion check alongside gate times, so fitting frames stay ≥60 s from both gate AND holdout timestamps.
- Keep all other logic (frame sampling, hole detection, `core_scale=0.46`).
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
- `scoreboard_clock_720p.py` — add `_load_notus_thresholds` and `_notus_red_mask` (loads frozen thresholds once from ROOT/data/roi); use `_notus_red_mask` in `_read_score`
- `scripts/fit_notus_segments.py` — import and use `_notus_red_mask` for fitting; add 20 holdout times to `_sample_timestamps` exclusion
- `data/roi/notus_red_thresholds.json` — created by step 1 measurement (keys: `s_min`, `v_min`)
- `data/roi/notus_scoreboard_rois.json` — potentially corrected by step 0 (tens/ones boxes updated in place under `games/*/scores` and `default/scores`; reader loads it via existing `load_rois()`)
- `data/roi/notus_scoreboard_rois_approved_2026-10-26.json` — copy of original ROI file before any in-place change (step 0)
- `data/roi/notus_segment_geometry.json` — regenerated by fitting script
- `.team/notus_fit_crops/` — fitting-frame crops saved by coder in step 0 (one per slot per frame)
- `.team/notus_fit_crops/eye_read_values.json` — Vetter's eye-read digit values for each crop (step 0 → step 1 handoff)
- `tests/test_notus_digit_gate.py` — unchanged (validates the fix)
- `tests/test_notus_holdout_gate.py` — created by coder (reads holdout truth, runs once after gate passes)

---

## Constraints
- Do NOT edit `scoreboard_clock.py`.
- Do NOT create any file other than those listed above (no scratch scripts, no temp files in repo root).
- If you need numbers, run Python with code on stdin (` .venv/Scripts/python.exe - <<'PY' ... PY`).
- Never sample video within 60 s of a holdout time.