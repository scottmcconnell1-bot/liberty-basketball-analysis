REJECTED by Claude Code, 2026-10-26 21:05: (1) digits are red (scores) and yellow (clock), not blue/cyan; measured on Notus A1 at 300 s: 333 red, 1276 yellow, 0 blue/cyan pixels. (2) Liberty is HOME (PATRIOTS) at Notus; team mapping must come from the scorebook home/away, not "mustangs". (3) The Notus board positions must be measured on Notus frames and checked by eye on ~10 frames, not scaled from Adrian. (4) Do not copy the protected scoreboard_clock.py; import and reuse its digit functions. Also: Hermes created and deleted ~15 source files while planning; architects write only NEXT_TASK.md.

# NEXT_TASK.md

## Task: Build scoreboard tracks for both Notus games and check makes against scorebooks

**Goal:** Create scoreboard tracks for the two Notus games (720p videos with blue/cyan digits) and verify made baskets using the proven 3-sample hold rule, reporting per-team final scores and makes by value (2PT/3PT/FT) against confirmed scorebooks. Also check Notus A1 Q1 against Scott's film tags.

**Constraints:**
- Must NOT edit `scoreboard_clock.py` (protected core file)
- Must NOT tune the rule to fit — use the same rule as Adrian: "a new score counts when the new value holds for 3 one-second samples; each rise is one made basket worth the rise"
- Must be a reusable script plus tests
- Must report per team: final score and makes by value against the book
- Must check Notus A1 Q1 against Scott's tags in `data/film_tags/`

---

## Files to Create

### 1. `scoreboard_clock_720p.py` (new module)
A 720p-compatible scoreboard reader that handles blue/cyan seven-segment digits.
- Scale all coordinate boxes from 1080p by 2/3 (1280/1920 = 720/1080 = 2/3)
- Add color masks for blue/cyan digits (HSV hue ~100-130, saturation > 150, value > 50) in addition to red
- Keep the same seven-segment logic and templates
- Export `read_scoreboard_720p`, `load_scoreboard_track`, `scoreboard_at`

### 2. `scripts/build_scoreboard_track_720p.py` (new script)
Wrapper that uses `scoreboard_clock_720p.read_scoreboard_720p` to build tracks for 720p videos.
- Same interface as `build_scoreboard_track.py` but calls the 720p reader

### 3. `scripts/check_scoreboard_makes.py` (new reusable script + tests)
- Loads a scoreboard track (via `scoreboard_clock_720p.load_scoreboard_track`)
- Applies the 3-sample hold rule to detect makes for both teams
- Classifies each make by point value (1=FT, 2=2PT, 3=3PT)
- Loads confirmed scorebook from `data/stat_books/confirmed/{game_id}.json`
- Reports per team: final score, makes by value, match ✓/✗ against book
- For Notus A1: also loads `data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json`, filters Q1 makes (quarter ends at 14:43.4 = 883400 ms), matches scoreboard makes to tags within 25 s, reports matched/unmatched counts
- CLI: `python scripts/check_scoreboard_makes.py GAME_ID [GAME_ID2 ...]`

### 4. `tests/test_check_scoreboard_makes.py` (new test file)
- Unit tests for the 3-sample hold detection logic (synthetic score sequences)
- Test make value classification
- Test Q1 tag matching logic
- Integration test: run on Adrian track (already proven 43/43, 51-26) as regression guard

---

## Commands to Run

```bash
# 1. Build 720p scoreboard tracks for both Notus games
cd /mnt/c/Users/scott/Documents/liberty-basketball-analysis
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

Liberty (mustangs): N makes detected
  2PT: X, 3PT: Y, FT: Z
  Total points from makes: P (book: 29) ✓/✗

Notus (guest): N makes detected
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
- The Notus videos are 1280x720 @ 25fps. The scoreboard digits are blue/cyan (HSV hue ~100-130), not red. You must add a blue/cyan mask in `scoreboard_clock_720p.py`.
- Coordinate scaling: multiply all 1080p boxes by 2/3 and round.
- Do not modify `scoreboard_clock.py` or `scripts/build_scoreboard_track.py`.
- The 3-sample hold rule is fixed: a score is "confirmed" only after it appears in 3 consecutive 1-second samples. A rise from one confirmed score to the next confirmed score = one made basket worth the point difference.
- Q1 end for Notus A1 is at timestamp 883400 ms (14:43.4 from the EndQTR tag).
- Scorebook paths: `data/stat_books/confirmed/{game_id}.json`
- Film tags path: `data/film_tags/jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json`