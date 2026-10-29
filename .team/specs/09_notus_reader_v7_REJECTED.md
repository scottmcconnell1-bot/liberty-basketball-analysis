REJECTED by Claude Code, 2026-10-27 (v7): fixes all seven v6 logic points (measured dead band T_on/T_off with STOP if not separable; BLANK vs UNREADABLE kept apart; pattern-string lookup; no core_scale door; step 0 crops done; no scratch files). Three defects remain: (1) _NOTUS_GAME_MAP is keyed "A1"/"A", but game_id is the full id (e.g. "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334"), and .get(game_id, "A1") silently reads game A with A1 settings. Key the map by the two full ids from the ROI JSON "games" keys; an unknown id must raise, never default. (2) _SEVEN_SEGMENT.get(on_str) returns a digit STRING ("5"), and "score = tens_digit * 10 + ones_digit" then repeats/concatenates strings. Convert with int() before arithmetic; blank tens -> 0 only for BLANK (""). (3) Contradiction: the Diagnosis says the Game A boxes are misaligned (A_05 away tens 0% red at score 15), but step 0 says "ROI boxes verified, no re-work". The box check was never run. Keep a per-game box check on the fitting frames: for slots whose eye-read digit is lit, measure mask coverage; if a box misses the digit, search a bounded shift (+-8 px x, +-6 px y, w,h fixed) on fitting frames only; write corrected boxes (approved copy already saved). Report the shifts to the Vetter before measuring colour.

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

### 0. Step 0 is DONE — ROI boxes verified and eye-read values exist
**No re-work needed.** The fitting-frame crops (`.team/notus_fit_crops/`) and Vetter eye-read values (`.team/notus_fit_crops/eye_read_values.json`) already exist from the previous cycle. The coder already copied `data/roi/notus_scoreboard_rois.json` → `data/roi/notus_scoreboard_rois_approved_2026-10-26.json` and verified tens/ones boxes on fitting frames where the tens digit was confirmed lit. Any box corrections have been written back to `data/roi/notus_scoreboard_rois.json`. Proceed directly to step 1.

Gate times (s): A1 202, 606, 1010, 1413, 1817, 2221, 2625, 3028, 3432, 3836; A 187, 562, 936, 1311, 1686, 2060, 2435, 2810, 3184, 3559  
Holdout times (s): A1 246.9, 650.7, 1054.5, 1458.3, 1862.1, 2265.9, 2669.7, 3073.5, 3477.3, 3881.1; A 232.3, 606.8, 981.3, 1356.0, 1730.6, 2105.1, 2479.6, 2854.1, 3229.6, 3603.9  
**Fitting frames = any frame whose timestamp is ≥60 s away from ALL of the above 40 times.**

---

### 1. Measure per-game Notus red-digit colour on fitting frames ONLY
Using the (verified) ROI boxes from step 0 on fitting frames only, **separately for Game A1 and Game A**:
- The coder loads the eye-read values from `.team/notus_fit_crops/eye_read_values.json`. For each crop where the Vetter-confirmed digit is non-blank, look up the **segment regions from the current `notus_segment_geometry.json`** (mapped into the slot box) **for only the segments that are ON for that digit** (the ON segments for a digit are the letters common to EVERY pattern that maps to that digit — 6 → c,d,e,f,g; 7 → a,b,c; 9 → a,b,c,f,g; every other digit has one pattern; region names are the letters a–g, as in `_SEGMENTS`). Union those ON-segment regions, and collect all pixels inside that union.
- **Rule (fixed before measuring)**: For each crop, compute the median V of its ON-region pixels. Keep only the pixels with V >= that crop's median V — these are the "lit pixels". Pool the lit pixels across all crops **for that game**. On that pooled set, take the central 98% of the hue distribution (handling wrap-around at 180: map hues >165 to hue-180 so the red cluster is contiguous around 0, compute the 1st and 99th percentiles, map back to 0–179). Also take the 10th percentile of V and the 10th percentile of S over the same pooled lit pixels. These four numbers become the frozen `NOTUS_H_MIN`, `NOTUS_H_MAX` (the contiguous hue interval in 0–179), `NOTUS_S_MIN`, and `NOTUS_V_MIN` **for that game**.
- Write `h_min`, `h_max`, `s_min`, `v_min` to `data/roi/notus_red_thresholds_A1.json` and `data/roi/notus_red_thresholds_A.json`. The coder runs the measurement and writes the files; **this plan contains no final cutoff numbers**.
- **REPORT-ONLY check (after freezing, no tuning)**: For each fitting frame, also collect pixels in OFF-segment regions (segments NOT lit for the eye-read digit, and blank tens slots). Using the frozen mask, compute the fraction of those OFF-region pixels that pass the mask. Report the per-game share to the Vetter; do NOT use it to adjust any threshold.

---

### 2. Fit per-game segment geometry on fitting frames ONLY
- Update `scripts/fit_notus_segments.py` to produce **two geometry files**: `data/roi/notus_segment_geometry_A1.json` and `data/roi/notus_segment_geometry_A.json`.
- In `_sample_timestamps`: add the 20 holdout times (listed above, hardcoded) to the exclusion check alongside gate times, so fitting frames stay ≥60 s from both gate AND holdout timestamps.
- Run fitting **separately per game**: filter frames by `game_id`, collect masks only from that game's frames, find hole positions, derive segment bands, write geometry for that game.
- **core_scale stays 0.46** (no per-game tuning).
- The segment geometry JSON structure stays the same (normalized 0–1 coordinates for a–g).

---

### 3. Add per-game Notus mask and digit reader to `scoreboard_clock_720p.py`

```python
_NOTUS_THRESHOLDS_A1: dict | None = None
_NOTUS_THRESHOLDS_A: dict | None = None
_NOTUS_GEOMETRY_A1: dict | None = None
_NOTUS_GEOMETRY_A: dict | None = None

# Explicit game_id -> game_key map from ROI JSON keys
_NOTUS_GAME_MAP: dict[str, str] = {
    "A1": "A1",
    "A": "A",
    # add others if ROI keys differ
}

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

def _notus_red_mask(crop: np.ndarray, game_key: str) -> np.ndarray:
    """Red mask for Notus 720p board using frozen thresholds for the specific game."""
    import cv2
    if game_key == "A1":
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

def _read_notus_digit(crop: np.ndarray, game_key: str, T_on: float, T_off: float) -> int | None:
    """Read one Notus digit with per-game geometry and MEASURED dead-band thresholds."""
    if crop is None or crop.size == 0:
        return None
    h, w = crop.shape[:2]
    mask = _notus_red_mask(crop, game_key)
    if np.count_nonzero(mask) == 0:
        return ""  # BLANK: no lit pixels (blank tens slot)

    # Load per-game geometry
    if game_key == "A1":
        geometry = _load_notus_geometry_A1()
    else:
        geometry = _load_notus_geometry_A()

    segments_px = {}
    for seg, (x1, y1, x2, y2) in geometry["segments"].items():
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)
        segments_px[seg] = (px1, py1, px2, py2)

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

    # DEAD-BAND RULE (measured on fitting frames by rule fixed in advance):
    # T_on = 10th percentile of ON-segment occupancies (per game)
    # T_off = 90th percentile of OFF-segment occupancies (per game)
    # Segment is ON if occ >= T_on, OFF if occ <= T_off, otherwise digit is UNREADABLE (None)
    on_segs = []
    for seg in 'abcdefg':
        occ = occupancies[seg]
        if occ >= T_on:
            on_segs.append(seg)
        elif occ > T_off:
            return None  # ambiguously lit — UNREADABLE

    if T_off >= T_on:
        # Segments not separable — coder STOPS and reports to Vetter
        raise RuntimeError(f"Dead band not separable: T_off={T_off:.3f} >= T_on={T_on:.3f} for {game_key}")

    on_str = ''.join(sorted(on_segs))
    # _SEVEN_SEGMENT maps pattern_string -> digit_string (e.g., "abcedf" -> "0")
    # Look up the sorted lit-segment string directly
    from scoreboard_clock_720p import _SEVEN_SEGMENT  # or import at module top
    return _SEVEN_SEGMENT.get(on_str)  # returns int or None if no valid pattern

def _read_notus_score(frame: np.ndarray, cells: dict, game_id: str) -> int | None:
    """Read home or away score (two digits). BLANK tens + readable ones = single digit.
    UNREADABLE tens (None) = whole score None."""
    tens_box = cells.get("tens")
    ones_box = cells.get("ones")
    if not tens_box or not ones_box:
        return None
    x_t, y_t, w_t, h_t = tens_box
    x_o, y_o, w_o, h_o = ones_box
    tens_crop = frame[y_t:y_t+h_t, x_t:x_t+w_t]
    ones_crop = frame[y_o:y_o+h_o, x_o:x_o+w_o]

    # Load per-game dead-band thresholds (written by measurement step)
    game_key = _NOTUS_GAME_MAP.get(game_id, "A1")  # default to A1 if unknown
    if game_key == "A1":
        thresholds = _load_notus_thresholds_A1()
    else:
        thresholds = _load_notus_thresholds_A()
    T_on = thresholds["T_on"]
    T_off = thresholds["T_off"]

    tens_digit = _read_notus_digit(tens_crop, game_key, T_on, T_off)
    ones_digit = _read_notus_digit(ones_crop, game_key, T_on, T_off)

    if tens_digit is None or ones_digit is None:
        return None  # UNREADABLE → whole score None
    if tens_digit == "":
        tens_digit = 0  # BLANK → leading zero (score < 10)
    if ones_digit == "":
        return None  # ones must be readable

    score = tens_digit * 10 + ones_digit
    return score
```

- Replace `_read_score` calls for Notus games with `_read_notus_score` (pass `game_id` from the config).
- Keep `_SEVEN_SEGMENT` unchanged (pattern string → digit string mapping).
- **Score-continuity cross-check** (for the makes script later): In the caller that tracks score over time, if a new score does not follow the previous held score by +1, +2, +3, or 0 (stay equal), treat the new score as unread (return None / do not update). This is a cross-check the makes script can use; the reader itself just returns the score or None.

---

### 4. Update `scripts/fit_notus_segments.py`
- Import `_notus_red_mask` from `scoreboard_clock_720p`.
- Use `_notus_red_mask(crop, game_key)` in `_collect_masks` (pass the game_key from the explicit map).
- In `_sample_timestamps`: add the 20 holdout times (hardcoded) to the exclusion check.
- Run fitting **per game_id**: group frames by game, fit geometry separately, write two files.
- Re-run to produce `data/roi/notus_segment_geometry_A1.json` and `data/roi/notus_segment_geometry_A.json`.

---

### 5. Compute per-game dead-band thresholds (T_on, T_off) and add to threshold JSONs
After step 1 (red thresholds) and step 4 (geometry) are done, the coder runs a **one-time measurement script** on the fitting-frame crops with eye-read values:
- For each game, using the per-game geometry and red mask, collect ON-segment occupancies (segments lit for the eye-read digit) and OFF-segment occupancies (segments not lit for that digit, plus all segments in blank tens slots).
- Compute T_on = 10th percentile of ON-segment occupancies; T_off = 90th percentile of OFF-segment occupancies.
- If T_off >= T_on for either game: **STOP and report to Vetter** (segments not separable).
- Append `T_on` and `T_off` to `data/roi/notus_red_thresholds_A1.json` and `data/roi/notus_red_thresholds_A.json` (keys: `T_on`, `T_off` alongside existing `h_min`, `h_max`, `s_min`, `v_min`).

---

### 6. Re-run the 20-crop gate ONCE (no retuning)
```bash
.venv/Scripts/python.exe scripts/fit_notus_segments.py
.venv/Scripts/python.exe -m pytest tests/test_notus_digit_gate.py -q
```
**Expected**: 20/20 pass. If not, stop — do not retune.

---

### 7. Single holdout run (only if gate passes 20/20)
- Coder writes `tests/test_notus_holdout_gate.py` that reads `.team/specs/04_notus_holdout_truth.json` (Architect must NOT open that file or the holdout_*.png crops).
- Run once:
```bash
.venv/Scripts/python.exe -m pytest tests/test_notus_holdout_gate.py -q
```
**Expected**: holdout passes. No further changes after this run.

---

## Files
- `scoreboard_clock_720p.py` — add per-game `_load_notus_thresholds_A1/A`, `_load_notus_geometry_A1/A`, `_notus_red_mask(crop, game_key)`, `_read_notus_digit(crop, game_key, T_on, T_off)` with dead-band rule, `_read_notus_score(frame, cells, game_id)`; use `_read_notus_score` for Notus games.
- `scripts/fit_notus_segments.py` — import `_notus_red_mask`; add 20 holdout times to `_sample_timestamps` exclusion; fit per game; write `notus_segment_geometry_A1.json` and `notus_segment_geometry_A.json`.
- `data/roi/notus_red_thresholds_A1.json` — created by step 1 measurement (keys: `h_min`, `h_max`, `s_min`, `v_min`, `T_on`, `T_off`).
- `data/roi/notus_red_thresholds_A.json` — created by step 1 measurement (keys: `h_min`, `h_max`, `s_min`, `v_min`, `T_on`, `T_off`).
- `data/roi/notus_scoreboard_rois.json` — corrected boxes from step 0 (tens/ones boxes updated in place under `games/*/scores` and `default/scores`).
- `data/roi/notus_scoreboard_rois_approved_2026-10-26.json` — copy of original ROI file before any in-place change (step 0, already done).
- `data/roi/notus_segment_geometry_A1.json` — regenerated by fitting script for Game A1.
- `data/roi/notus_segment_geometry_A.json` — regenerated by fitting script for Game A.
- `.team/notus_fit_crops/` — fitting-frame crops (already exist from step 0).
- `.team/notus_fit_crops/eye_read_values.json` — Vetter's eye-read digit values for each crop (already exist).
- `tests/test_notus_digit_gate.py` — unchanged (validates the fix).
- `tests/test_notus_holdout_gate.py` — created by coder (reads holdout truth, runs once after gate passes).

---

## Constraints
- Do NOT edit `scoreboard_clock.py`.
- Do NOT create any file other than those listed above (no scratch scripts, no temp files in repo root).
- If you need numbers, run Python with code on stdin (` .venv/Scripts/python.exe - <<'PY' ... PY`).
- Never sample video within 60 s of a holdout time.
- **WRONG reads must become impossible or near-impossible** — the dead-band rule (ON if occ >= T_on, OFF if occ <= T_off, else None) prefers None over a wrong digit. T_on/T_off measured on fitting frames by a rule written before measuring.
- core_scale stays 0.46 (no tuning).
- Game detection uses explicit `_NOTUS_GAME_MAP` from ROI JSON keys.
- Gate on the same 20 once; holdout once only after a 20/20 gate.