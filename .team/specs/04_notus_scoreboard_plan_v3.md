## Task: Build scoreboard tracks for both Notus games and check makes against scorebooks

**Goal:** Create scoreboard tracks for the two Notus games (720p videos) and verify made baskets using the proven 3-sample hold rule, reporting per-team final scores and makes by value (2PT/3PT/FT) against confirmed scorebooks. Also check Notus A1 Q1 against Scott's film tags.

**Constraints:**
- Must NOT edit `scoreboard_clock.py` (protected core file)
- Must NOT tune the rule to fit — use the same rule as Adrian: "a new score counts when the new value holds for 3 one-second samples; each rise is one made basket worth the rise"
- Must be a reusable script plus tests
- Must report per team: final score and makes by value against the book
- Must check Notus A1 Q1 against Scott's tags in `data/film_tags/`

---

## Files
- `scoreboard_clock_720p.py`
- `scripts/measure_notus_rois.py`
- `scripts/build_scoreboard_track_720p.py`
- `scripts/check_scoreboard_makes.py`
- `tests/test_check_scoreboard_makes.py`
- `data/roi/notus_scoreboard_rois.json`
- `data/roi/notus_crops/` (crop images)
- `data/scoreboard_tracks/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json`
- `data/scoreboard_tracks/jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334.json`

## Details

### 1. `scoreboard_clock_720p.py` (new module)
A 720p-compatible scoreboard reader that imports and reuses digit-reading functions from `scoreboard_clock.py`.
- Import only real functions from `scoreboard_clock` by name: `_red_mask`, `_warm_mask`, `_segment_digit`, `_digit_groups`, `_score_value`, `_load_templates`, `read_scoreboard`
- Never import `read_digits` or `seven_segment_templates` — they do not exist in `scoreboard_clock.py`
- Never copy or edit `scoreboard_clock.py`
- Define Notus-specific ROI boxes for score digits (red) and clock digits (yellow) — **measured on Notus frames, not scaled from Adrian**
- Use the imported `_red_mask` for RED score digits and `_warm_mask` for YELLOW clock digits
- OpenCV loads BGR; the imported masks handle color order
- Export `read_scoreboard_720p`, `load_scoreboard_track`, `scoreboard_at`

### 2. `scripts/measure_notus_rois.py` (new script — **run first**)
Measures Notus scoreboard digit boxes on actual Notus frames non-interactively and saves crops for Vetter eye-check.
- **Non-interactive** — no human prompts, no GUI windows
- For **each Notus game**, sample the board position at **10 times spread across the game** (the camera pans; the board appears to be a fixed overlay)
- At each of the 10 times per game, extract one crop showing the digit boxes overlaid
- Save **20 crops total** (10 per game) to `data/roi/notus_crops/` for Vetter visual verification
- Save the measured ROI coordinates (x, y, w, h for each digit box: home score tens/ones, away score tens/ones, clock minutes/seconds) to `data/roi/notus_scoreboard_rois.json`
- **This script runs before any track building; the coder stops after this step and reports the crops for approval before building tracks.**

### 3. `scripts/build_scoreboard_track_720p.py` (new script)
Wrapper that uses `scoreboard_clock_720p.read_scoreboard_720p` to build tracks for 720p videos.
- Reads ROI config from `data/roi/notus_scoreboard_rois.json`
- Same interface as `build_scoreboard_track.py` but calls the 720p reader with Notus ROIs

### 4. `scripts/check_scoreboard_makes.py` (new reusable script + tests)
- Loads a scoreboard track (via `scoreboard_clock_720p.load_scoreboard_track`)
- Applies the 3-sample hold rule to detect makes for both teams
- Classifies each make by point value (1=FT, 2=2PT, 3=3PT)
- Loads confirmed scorebook from `data/stat_books/confirmed/{game_id}.json`
- **Team mapping comes from scorebook `home_team` / `away_team` fields** — Liberty is HOME (PATRIOTS) in both Notus games
- Reports per team (using scorebook team names): final score, makes by value, match ✓/✗ against book
- For Notus A1: also loads `data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json`, filters Q1 makes (quarter ends at 14:43.4 = 883400 ms), matches scoreboard makes to tags within 25 s, reports matched/unmatched counts
- CLI: `python scripts/check_scoreboard_makes.py GAME_ID [GAME_ID2 ...]`

### 5. `tests/test_check_scoreboard_makes.py` (new test file)
- Unit tests for the 3-sample hold detection logic (synthetic score sequences)
- Test make value classification
- Test Q1 tag matching logic
- Integration test: run on Adrian track (`jrhigh_adrian__or_LIBERTY_A_v_ADRIAN_H_20260809_221334`) as regression guard — must still yield 43 makes, 51-26

---

## Commands to Run

```bash
# 0. Measure Notus ROIs and save crops for Vetter approval (RUN FIRST)
cd /mnt/c/Users/scott/Documents/liberty-basketball-analysis
.venv/Scripts/python.exe scripts/measure_notus_rois.py

# Coder STOPS HERE and reports the 20 crops in data/roi/notus_crops/ for Vetter approval.
# Vetter reviews crops and approves the ROI config before proceeding.

# 1. Build 720p scoreboard tracks for both Notus games (after ROI approval)
.venv/Scripts/python.exe scripts/build_scoreboard_track_720p.py "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334" "uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4"
.venv/Scripts/python.exe scripts/build_scoreboard_track_720p.py "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334" "uploads/LIBERTY_H_v_NOTUS_A_20260809_221334.mp4"

# 2. Run the check script on both games
.venv/Scripts/python.exe scripts/check_scoreboard_makes.py "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334" "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334"

# 3. Run tests (including Adrian regression)
.venv/Scripts/python.exe -m pytest tests/test_check_scoreboard_makes.py -q
```

---

## Expected Outputs (from commands above)

The check script should print for each game:

```
=== jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334 ===
Scorebook: Liberty 29 - Notus 48

Liberty (PATRIOTS): N makes detected
  2PT: X, 3PT: Y, FT: Z
  Total points from makes: P (book: 29) ✓/✗

Notus (guest team name from book): N makes detected
  2PT: X, 3PT: Y, FT: Z
  Total points from makes: P (book: 48) ✓/✗

--- Notus A1 Q1 Check Against Scott's Tags ---
Q1 tagged makes: T
Q1 scoreboard makes: S
Matched (within 25s): M
Unmatched tags: U
Unmatched scoreboard makes: V
```

---

## Notes for OpenCode

- The Adrian track (`jrhigh_adrian__or_LIBERTY_A_v_ADRIAN_H_20260809_221334`) uses the original `scoreboard_clock.py` and is the regression baseline. The test must confirm it still yields 43 makes, 51-26.
- The Notus videos are 1280x720 @ 25fps. The scoreboard digits are **RED (scores)** and **YELLOW (clock)** — not blue/cyan. OpenCV loads BGR; the imported `_red_mask` and `_warm_mask` handle this.
- **Notus ROI positions must be measured on Notus frames** via `measure_notus_rois.py` and verified by eye on 20 crops (10 per game) before building tracks. Do NOT scale from Adrian.
- **Do not modify `scoreboard_clock.py` or `scripts/build_scoreboard_track.py`.** Import and reuse digit functions from `scoreboard_clock.py` by the seven names above only.
- The 3-sample hold rule is fixed: a score is "confirmed" only after it appears in 3 consecutive 1-second samples. A rise from one confirmed score to the next confirmed score = one made basket worth the point difference.
- Q1 end for Notus A1 is at timestamp 883400 ms (14:43.4 from the EndQTR tag).
- Scorebook paths: `data/stat_books/confirmed/{game_id}.json`
- Film tags path: `data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json`
- Team names for reporting come from the scorebook's `home_team` and `away_team` fields (Liberty = PATRIOTS = home in both Notus games).