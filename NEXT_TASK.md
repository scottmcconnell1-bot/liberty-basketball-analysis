VETTED by Claude Code, 2026-10-26 21:58: v2 fixes all four v1 errors (fitting frames separate from the 20 gate frames with no retuning; fixed slot boxes; _SEGMENT_ON 0.12 verified; complete ## Files matching acceptance). Cosmetic: line "scoreboard_clock_720p.py — edit only this file" means the only EXISTING file edited; the acceptance list governs.

## Task: Fix Notus score reader — segment occupancy, no templates

**Goal:** Replace the template-based digit reader in `scoreboard_clock_720p.py` with a seven-segment occupancy reader measured on Notus digits. The reader must decode each digit from which of its seven segments are lit inside the measured tens/ones boxes, treat a blank tens slot as "no digit" (not zero), and use **no templates from another board**. Gate: on the 20 Notus crops (re-sampled from the videos at the same timestamps using the ROI JSON), the reader returns exactly the answer key in `.team/specs/04_notus_crop_truth.json` for both scores, 20 of 20. Only after the gate passes: build both full tracks and run `scripts/check_scoreboard_makes.py` as in v3. The clock is not needed for makes; do not spend effort on it.

## Files
- `scoreboard_clock_720p.py` — edit only this file
- `scripts/fit_notus_segments.py` — new script to fit segment geometry on non-gate frames
- `data/roi/notus_segment_geometry.json` — measured segment regions (relative coords within slot box), produced by fit script
- `data/roi/notus_scoreboard_rois.json` — read-only, provides the measured tens/ones boxes per game
- `data/roi/notus_crops/` — 20 existing crops for reference; the gate re-samples from the videos at the same timestamps
- `.team/specs/04_notus_crop_truth.json` — answer key (ground truth scores for each crop)
- `scripts/build_scoreboard_track_720p.py` — unchanged, will be run after gate passes
- `scripts/check_scoreboard_makes.py` — unchanged, will be run after gate passes
- `tests/test_notus_digit_gate.py` — new gate test file

## Plan

### 1. Measure Notus seven-segment geometry on NON-gate frames (one-time, offline)
- Select fitting frames: at least 10 timestamps per Notus game, each at least 60 seconds away from every answer-key timestamp in `.team/specs/04_notus_crop_truth.json`.
- From the fitting frames, extract the red-mask pixels inside each tens/ones slot box (the fixed boxes from the ROI JSON — do NOT normalize to a tight digit bounding box).
- For each slot box, cluster the lit pixels into the seven standard segments (a,b,c,d,e,f,g) using the same relative layout as `_SEGMENTS` in `scoreboard_clock.py` but **fitted to Notus digit proportions inside the fixed slot box**.
- Save the fitted segment regions (as relative coordinates within the slot box) to `data/roi/notus_segment_geometry.json`. This is measured once; the reader loads it at runtime.

### 2. Replace `_slot_text` in `scoreboard_clock_720p.py` with a segment-occupancy reader
- **Delete** the current `_slot_text` that calls `_segment_digit` (template matching).
- **Add** `_read_notus_digit(mask: np.ndarray) -> str | None` that:
  1. Loads the Notus segment geometry JSON (cached).
  2. For each of the 7 segments, computes the fraction of pixels lit in that segment region within the fixed slot box.
  3. A segment is "on" if its lit fraction ≥ `_SEGMENT_ON` (imported from `scoreboard_clock.py`; value is **0.12**).
  4. Builds the lit-segment string (e.g., "abcdg") and looks it up in `_SEVEN_SEGMENT` (imported from `scoreboard_clock.py`).
  5. Returns the digit string, or `""` if no segments lit (blank slot), or `None` if the pattern is not a known digit.
- **Update** `_read_score` to use `_read_notus_digit` on the red-masked tens and ones boxes.
- Keep `_score_value` logic unchanged: blank tens + blank ones = no score; blank ones = single-digit score; leading zero in tens = no score; any unread slot (`None`) = no score.

### 3. Gate test (must pass before any track building)
- Create `tests/test_notus_digit_gate.py` that:
  1. Loads the ROI JSON and the answer key.
  2. For each of the 20 entries in the answer key:
     - Opens the corresponding video at the exact timestamp.
     - Crops the home and away tens/ones boxes from the ROI config (fixed slot boxes).
     - Runs the new `_read_notus_digit` on each box via `_read_score`.
     - Asserts the returned `(home, away)` tuple exactly matches the answer key.
  3. Prints a 20-row table: crop name | expected home | expected away | got home | got away | ✓/✗.
  4. Fails if any row is ✗.
- Run: `.venv/Scripts/python.exe -m pytest tests/test_notus_digit_gate.py -q`
- **Do not proceed** until all 20 pass. If any fail, report the failures; do not retune the fitting or threshold to make the gate pass.

### 4. After gate passes (separate step, not in this task)
- Run `scripts/build_scoreboard_track_720p.py` for both Notus games.
- Run `scripts/check_scoreboard_makes.py` for both games.
- Run `pytest tests/test_check_scoreboard_makes.py -q` (Adrian regression must still yield 43 makes, 51-26).

## Constraints
- **Never edit `scoreboard_clock.py`**. Import `_red_mask`, `_warm_mask`, `_score_value`, `_SEVEN_SEGMENT`, `_SEGMENTS`, `_SEGMENT_ON` by name only.
- **Never copy code from `scoreboard_clock.py`** — import and reuse.
- The segment geometry JSON is measured data, not code; it lives in `data/roi/`.
- The clock reader (`_clock_text`, clock boxes) is untouched; it stays as-is (may read `None`; makes don't need it).
- No template matching (`_segment_digit`, `_load_templates`, `scoreboard_digits.npz`) in the score path.
- Fitting frames must be disjoint from gate frames (≥ 60 s separation); the gate runs on the answer-key frames with zero retuning.

## Acceptance
- `tests/test_notus_digit_gate.py` passes (20/20 crops match answer key exactly).
- Created/edited files exactly: `scoreboard_clock_720p.py`, `scripts/fit_notus_segments.py`, `data/roi/notus_segment_geometry.json`, `tests/test_notus_digit_gate.py`.
- No other files changed.
- No new dependencies.