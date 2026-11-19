REJECTED by Claude Code, 2026-10-27 (v6): useful diagnosis (boards differ per game; segment g fires falsely; per-game measurement), but the fix would CREATE wrong reads: (1) Margin rule "ON only if occ >= 0.12 AND >= 2x the mean of the other 6, else None" can never read digits with many lit segments (8: every segment ~ equal to the mean of the others; also 0, 6, 9), so they always return None. Use a two-threshold dead band measured on the fitting frames by a rule fixed in advance: from the eye-read fitting crops, T_on = 10th percentile of ON-segment occupancies, T_off = 90th percentile of OFF-segment occupancies (per game); a segment is ON if occ >= T_on, OFF if occ <= T_off, otherwise the digit is None; if T_off >= T_on the segments are not separable and the coder STOPS and reports. (2) _read_notus_score sets an unreadable tens digit (None) to 0, so "15" with an unread "1" becomes 5 (exactly the A_05 wrong read). Keep BLANK (no lit pixels: "") distinct from UNREADABLE (None): blank tens + readable ones = single digit; unreadable tens = whole score None. (3) Code bug: _SEVEN_SEGMENT maps pattern string -> digit string; the plan iterates it as digit -> pattern. Import it and look up the sorted lit-segment string. (4) Fixed 0.12 is kept untested; replace with the measured T_on/T_off. (5) "core_scale may be per-game if the Vetter decides after seeing the fits" is a tuning door: remove; core_scale stays 0.46. (6) Step 0 is DONE (crops and eye-read values exist); say so instead of re-specifying it. (7) Game detection "A1" in game_id is fragile: use an explicit game_id -> A1/A map from the ROI JSON keys. Note: Hermes again created 8 scratch scripts (.team/diagnose_*.py etc.; no holdout access; moved to .team/hermes_scratch_reader9/).

## Diagnosis

**Gate result (v5): 9/20 correct, 4 WRONG reads, 7 None reads.**  
Game A1: 7/10. Game A: 2/10.

### 1. Do per-game slot boxes sit on the digits in game A (thin/dim digits)?
**No.** On Game A gate frames:
- Away tens at A_02_936s (exp=8): 0.0% red pixels — box captures dark board, not the digit.
- Away tens at A_05_2060s (exp=15): 0.0% red — same.
- Home tens at A_00_187s (exp=5): 0.0% red.
- All four Game A slots at A_00_187s: 0.0–5.2% red.
The Game A tens boxes (22×28) and ones boxes (23×29) are misaligned for the dimmer, smaller Game A digits. Game A1 boxes (25×29 / 26×30) sit better but still fail when tens is blank (score < 10).

### 2. Is one pooled geometry right for both games, or do the two boards differ?
**The two boards differ significantly.** Measured on 40 fitting frames per game:

| Metric | Game A1 | Game A |
|--------|---------|--------|
| Mean red % (frozen mask) | 20.3% | 14.1% |
| Tens crop size | 25×29 | 22×28 |
| Ones crop size | 26×30 | 23×29 |
| Tens segment b mean occupancy | 0.445 | 0.240 |
| Tens segment c mean occupancy | 0.229 | 0.203 |
| Tens segment f mean occupancy | **0.000** | **0.000** |
| Ones segment b mean occupancy | 0.742 | 0.280 |
| Ones segment g mean occupancy | 0.370 | 0.617 |

- Game A is 30% dimmer, 12–15% smaller in each dimension.
- Segment occupancy patterns are disjoint: A1 tens rely on right verticals (b,c); A tens have weak signal everywhere; A ones have strong horizontals (a,g) but weak right verticals (b,c).
- **Segment f (upper left) is NEVER lit in tens position for either game** — the pooled geometry places f in a region that is always dark for tens digits.
- One pooled `notus_segment_geometry.json` cannot serve both games.

### 3. Why do wrong reads happen (which segments flip)?
| Failure | Expected → Got | Segments ON (occupancy ≥ 0.12) | Root cause |
|---------|----------------|--------------------------------|------------|
| A1_01_606s home_tens | 2 → None | (none, 0% red) | Tens blank (score<10), box on dark board |
| A1_05_2221s away_ones | 9 → 4 | b,c,f,g (a missing) | Segment a too weak; segment g falsely on; f geometry wrong for ones |
| A1_09_3836s home_tens | 29 → None | b,d,e,g (not a valid pattern) | Segment g falsely on; a,c,f off |
| A_00_187s all | 5,2,2,5 → None | (all < 6% red) | Boxes misaligned for Game A dim board |
| A_02_936s away_ones | 8 → 6 | a,c,d,e,f,g (b missing) | Segment b too weak in Game A ones |
| A_05_2060s away | 15 → 5 | tens: 0% red; ones: a,c,d,f,g | Tens box on dark board; ones reads 5 correctly but score=5 not 15 |
| A_07_2810s home_ones | 3 → 7 | a,b,c (d,e,f,g off) | Lower segments too weak; g falsely on for 3 |
| A_08_3184s home_tens | 25 → None | b,d,e,g (a,c,f off) | Segment g falsely on; a missing |
| A_09_3559s home_tens | 36 → None | b,c,d,g (a,e,f off) | Segment g falsely on; a,e missing |

**Pattern:** Segment g (middle horizontal) fires on digits where it should be OFF (2,3,4,5,7,9 in various cases). Segment a (top) drops out on Game A. Segment b (upper right) drops out on Game A ones. Segment f geometry is wrong for tens. Tens boxes capture background when score < 10.

---

## Fix Plan

### 0. Verify home/away TENS box positions per game (FIRST, before any mask change)
**Before any in-place change**, the coder copies `data/roi/notus_scoreboard_rois.json` → `data/roi/notus_scoreboard_rois_approved_2026-10-26.json`.

On **fitting frames only** (frames ≥60 s from every gate time and every holdout time):
- The coder extracts ~10 fitting-frame crops per slot (home_tens, home_ones, away_tens, away_ones) where the score is visibly changing (so tens digit is definitely lit) and saves them under `.team/notus_fit_crops/`.
- **STOP**. The coder does not measure anything yet.
- The Vetter reads the saved crops by eye and writes the ground-truth digit value for each crop to `.team/notus_fit_crops/eye_read_values.json` (one entry per crop: `{"crop_path": "...", "game": "A1", "slot": "home_tens", "score": 15, "digit": 1}`).
- The coder then uses those eye-read values to know which tens boxes are on a lit-digit frame. For each of the four scoreboard slots **per game**, on a fitting frame where the Vetter-confirmed tens digit is non-blank (digit ≥ 1), crop the current `notus_scoreboard_rois.json` box and measure mean V inside the box.
- If mean V ≈ 10 (same as blank), the box is misplaced — it is not covering the tens digit.
- **If any box is wrong**: Re-measure its (x, y) on fitting frames by searching a bounded x,y shift (±8 px in x, ±6 px in y) around the current box center, keeping the measured w,h fixed, to maximize mean V when the tens digit is lit (score ≥ 10). Write corrected boxes back into `data/roi/notus_scoreboard_rois.json` (replacing the existing tens/ones boxes under `games/*/scores` and `default/scores`). The reader already loads this file via `load_rois()` — no code change needed.

Gate times (s): A1 202, 606, 1010, 1413, 1817, 2221, 2625, 3028, 3432, 3836; A 187, 562, 936, 1311, 1686, 2060, 2435, 2810, 3184, 3559  
Holdout times (s): A1 246.9, 650.7, 1054.5, 1458.3, 1862.1, 2265.9, 2669.7, 3073.5, 3477.3, 3881.1; A 232.3, 606.8, 981.3, 1356.0, 1730.6, 2105.1, 2479.6, 2854.1, 3229.6, 3603.9  
**Fitting frames = any frame whose timestamp is ≥60 s away from ALL of the above 40 times.**

---

### 1. Measure per-game Notus red-digit colour on fitting frames ONLY
Using the (possibly corrected) ROI boxes from step 0 on fitting frames only, **separately for Game A1 and Game A**:
- The coder loads the eye-read values from `.team/notus_fit_crops/eye_read_values.json`. For each crop where the Vetter-confirmed digit is non-blank, look up the **segment regions from the current `notus_segment_geometry.json`** (mapped into the slot box) **for only the segments that are ON for that digit** (the ON segments for a digit are the letters common to EVERY pattern that maps to that digit — 6 → c,d,e,f,g; 7 → a,b,c; 9 → a,b,c,f,g; every other digit has one pattern; region names are the letters a–g, as in `_SEGMENTS`). Union those ON-segment regions, and collect all pixels inside that union.
- **Rule (fixed before measuring)**: For each crop, compute the median V of its ON-region pixels. Keep only the pixels with V >= that crop's median V — these are the "lit pixels". Pool the lit pixels across all crops **for that game**. On that pooled set, take the central 98% of the hue distribution (handling wrap-around at 180: map hues >165 to hue-180 so the red cluster is contiguous around 0, compute the 1st and 99th percentiles, map back to 0–179). Also take the 10th percentile of V and the 10th percentile of S over the same pooled lit pixels. These four numbers become the frozen `NOTUS_H_MIN`, `NOTUS_H_MAX` (the contiguous hue interval in 0–179), `NOTUS_S_MIN`, and `NOTUS_V_MIN` **for that game**.
- Write `h_min`, `h_max`, `s_min`, `v_min` to `data/roi/notus_red_thresholds_A1.json` and `data/roi/notus_red_thresholds_A.json`. The coder runs the measurement and writes the files; **this plan contains no final cutoff numbers**.
- **REPORT-ONLY check (after freezing, no tuning)**: For each fitting frame, also collect pixels in OFF-segment regions (segments NOT lit for the eye-read digit, and blank tens slots). Using the frozen mask, compute the fraction of those OFF-region pixels that pass the mask. Report the per-game share to the Vetter; do NOT use it to adjust any threshold.

---

### 2. Fit per-game segment geometry on fitting frames ONLY
- Update `scripts/fit_notus_segments.py` to produce **two geometry files**: `data/roi/notus_segment_geometry_A1.json` and `data/roi/notus_segment_geometry_A.json`.
- In `_sample_timestamps`: add the 20 holdout times (listed in step 0 above, hardcoded) to the exclusion check alongside gate times, so fitting frames stay ≥60 s from both gate AND holdout timestamps.
- Run fitting **separately per game**: filter frames by `game_id`, collect masks only from that game's frames, find hole positions, derive segment bands, write geometry for that game.
- Keep `core_scale=0.46` but allow it to be per-game if the Vetter decides after seeing the fits.
- The segment geometry JSON structure stays the same (normalized 0–1 coordinates for a–g).

---

### 3. Add per-game Notus mask and digit reader to `scoreboard_clock_720p.py`
```python
_NOTUS_THRESHOLDS_A1: dict | None = None
_NOTUS_THRESHOLDS_A: dict | None = None
_NOTUS_GEOMETRY_A1: dict | None = None
_NOTUS_GEOMETRY_A: dict | None = None

def _load_notus_thresholds_A1() -> dict:
    global _NOTUS_THRESHOLDS_A1
    if _NOTUS_THRESHOLDS_A1 is not None:
        return _NOTUS_THRESHOLDS_A1
    import json
    from pathlib import Path
    path = ROOT / "data" / "roi" / "notus_red_thresholds_A1.json"
    _NOTUS_THRESHOLDS_A1 = json.loads(path.read_text(encoding="utf-8"))
    return _NOTUS_THRESHOLDS_A1

def _load_notus_thresholds_A() -> dict:
    global _NOTUS_THRESHOLDS_A
    if _NOTUS_THRESHOLDS_A is not None:
        return _NOTUS_THRESHOLDS_A
    import json
    from pathlib import Path
    path = ROOT / "data" / "roi" / "notus_red_thresholds_A.json"
    _NOTUS_THRESHOLDS_A = json.loads(path.read_text(encoding="utf-8"))
    return _NOTUS_THRESHOLDS_A

def _load_notus_geometry_A1() -> dict:
    global _NOTUS_GEOMETRY_A1
    if _NOTUS_GEOMETRY_A1 is not None:
        return _NOTUS_GEOMETRY_A1
    import json
    from pathlib import Path
    path = ROOT / "data" / "roi" / "notus_segment_geometry_A1.json"
    _NOTUS_GEOMETRY_A1 = json.loads(path.read_text(encoding="utf-8"))
    return _NOTUS_GEOMETRY_A1

def _load_notus_geometry_A() -> dict:
    global _NOTUS_GEOMETRY_A
    if _NOTUS_GEOMETRY_A is not None:
        return _NOTUS_GEOMETRY_A
    import json
    from pathlib import Path
    path = ROOT / "data" / "roi" / "notus_segment_geometry_A.json"
    _NOTUS_GEOMETRY_A = json.loads(path.read_text(encoding="utf-8"))
    return _NOTUS_GEOMETRY_A

def _notus_red_mask(crop: np.ndarray, game_id: str) -> np.ndarray:
    """Red mask for Notus 720p board using frozen thresholds for the specific game."""
    import cv2
    if "A1" in game_id:
        thresholds = _load_notus_thresholds_A1()
    else:
        thresholds = _load_notus_thresholds_A()
    h_min = thresholds["h_min"]
    h_max = thresholds["h_max"]
    s_min = thresholds["s_min"]
    v_min = thresholds["v_min"]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    if h_min <= h_max:
        mask = cv2.inRange(hsv, (h_min, s_min, v_min), (h_max, 255, 255))
    else:
        low = cv2.inRange(hsv, (0, s_min, v_min), (h_max, 255, 255))
        high = cv2.inRange(hsv, (h_min, s_min, v_min), (179, 255, 255))
        mask = cv2.bitwise_or(low, high)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))

def _read_notus_digit(crop: np.ndarray, game_id: str) -> int | None:
    """Read one Notus digit with per-game geometry and MARGIN RULE."""
    if crop is None or crop.size == 0:
        return None
    h, w = crop.shape[:2]
    mask = _notus_red_mask(crop, game_id)
    if np.count_nonzero(mask) == 0:
        return None  # blank tens slot
    
    # Load per-game geometry
    if "A1" in game_id:
        geometry = _load_notus_geometry_A1()
    else:
        geometry = _load_notus_geometry_A()
    
    segments_px = {}
    for seg, (x1, y1, x2, y2) in geometry["segments"].items():
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)
        segments_px[seg] = (px1, py1, px2, py2)
    
    # MARGIN RULE: a segment is ON only if occupancy >= 0.12 AND 
    #               occupancy >= 2.0 * (mean occupancy of the other 6 segments)
    #               otherwise the digit is UNREADABLE (return None)
    occupancies = {}
    for seg in 'abcdefg':
        px1, py1, px2, py2 = segments_px[seg]
        if px1 >= px2 or py1 >= py2:
            occupancies[seg] = 0.0
            continue
        seg_mask = mask[py1:py2, px1:px2]
        seg_total = seg_mask.size
        seg_red = np.count_nonzero(seg_mask)
        occupancies[seg] = seg_red / seg_total if seg_total > 0 else 0.0
    
    mean_other = {seg: np.mean([v for k, v in occupancies.items() if k != seg]) for seg in 'abcdefg'}
    on_segs = []
    for seg in 'abcdefg':
        occ = occupancies[seg]
        if occ >= 0.12 and occ >= 2.0 * mean_other[seg]:
            on_segs.append(seg)
        elif occ >= 0.12:
            # Segment is ambiguously lit — digit is unreadable
            return None
    
    on_str = ''.join(sorted(on_segs))
    for d, pattern in _SEVEN_SEGMENT.items():
        if ''.join(sorted(pattern)) == on_str:
            return d
    return None  # no valid pattern matched

def _read_notus_score(frame: np.ndarray, cells: dict, game_id: str) -> int | None:
    """Read home or away score (two digits) with score-continuity check."""
    tens_box = cells.get("tens")
    ones_box = cells.get("ones")
    if not tens_box or not ones_box:
        return None
    x_t, y_t, w_t, h_t = tens_box
    x_o, y_o, w_o, h_o = ones_box
    tens_crop = frame[y_t:y_t+h_t, x_t:x_t+w_t]
    ones_crop = frame[y_o:y_o+h_o, x_o:x_o+w_o]
    tens_digit = _read_notus_digit(tens_crop, game_id)
    ones_digit = _read_notus_digit(ones_crop, game_id)
    if tens_digit is None and ones_digit is None:
        return None
    if tens_digit is None:
        tens_digit = 0
    if ones_digit is None:
        return None  # ones must be readable
    score = tens_digit * 10 + ones_digit
    return score
```

- Replace `_read_score` calls for Notus games with `_read_notus_score` (pass `game_id` from the config).
- Keep `_SEVEN_SEGMENT` unchanged.
- **Score-continuity cross-check** (for the makes script later): In the caller that tracks score over time, if a new score does not follow the previous held score by +1, +2, +3, or 0 (stay equal), treat the new score as unread (return None / do not update). This is a cross-check the makes script can use; the reader itself just returns the score or None.

---

### 4. Update `scripts/fit_notus_segments.py`
- Import `_notus_red_mask` from `scoreboard_clock_720p`.
- Use `_notus_red_mask(crop, game_id)` in `_collect_masks`.
- In `_sample_timestamps`: add the 20 holdout times (hardcoded) to the exclusion check.
- Run fitting **per game_id**: group frames by game, fit geometry separately, write two files.
- Re-run to produce `data/roi/notus_segment_geometry_A1.json` and `data/roi/notus_segment_geometry_A.json`.

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
- `scoreboard_clock_720p.py` — add per-game `_load_notus_thresholds_A1/A`, `_load_notus_geometry_A1/A`, `_notus_red_mask(crop, game_id)`, `_read_notus_digit(crop, game_id)` with margin rule, `_read_notus_score(frame, cells, game_id)`; use `_read_notus_score` for Notus games.
- `scripts/fit_notus_segments.py` — import `_notus_red_mask`; add 20 holdout times to `_sample_timestamps` exclusion; fit per game; write `notus_segment_geometry_A1.json` and `notus_segment_geometry_A.json`.
- `data/roi/notus_red_thresholds_A1.json` — created by step 1 measurement (keys: `h_min`, `h_max`, `s_min`, `v_min`).
- `data/roi/notus_red_thresholds_A.json` — created by step 1 measurement.
- `data/roi/notus_scoreboard_rois.json` — potentially corrected by step 0 (tens/ones boxes updated in place under `games/*/scores` and `default/scores`).
- `data/roi/notus_scoreboard_rois_approved_2026-10-26.json` — copy of original ROI file before any in-place change (step 0).
- `data/roi/notus_segment_geometry_A1.json` — regenerated by fitting script for Game A1.
- `data/roi/notus_segment_geometry_A.json` — regenerated by fitting script for Game A.
- `.team/notus_fit_crops/` — fitting-frame crops saved by coder in step 0 (one per slot per frame).
- `.team/notus_fit_crops/eye_read_values.json` — Vetter's eye-read digit values for each crop (step 0 → step 1 handoff).
- `tests/test_notus_digit_gate.py` — unchanged (validates the fix).
- `tests/test_notus_holdout_gate.py` — created by coder (reads holdout truth, runs once after gate passes).

---

## Constraints
- Do NOT edit `scoreboard_clock.py`.
- Do NOT create any file other than those listed above (no scratch scripts, no temp files in repo root).
- If you need numbers, run Python with code on stdin (` .venv/Scripts/python.exe - <<'PY' ... PY`).
- Never sample video within 60 s of a holdout time.
- **WRONG reads must become impossible or near-impossible** — the margin rule (segment ON only if occupancy ≥ 0.12 AND ≥ 2× mean of other 6 segments) prefers None over a wrong digit.
- Any threshold or geometry still measured on fitting frames by a rule written before measuring.
- Gate on the same 20 once; holdout once only after a 20/20 gate.