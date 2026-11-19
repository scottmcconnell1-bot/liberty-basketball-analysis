VETTED by Claude Code, 2026-10-31: v2 checked against 18_makes_misses_work_plan.md BINDING NOTE d, ACTIVE.md lines 9-11, specs 04 v3 / 05 (no direction recorded - after-shot only is the stricter reading), d1_results.json counts (109 / 38 / 71 / 27 / 11, venv python count this session), measure_net_moved.py line 22 (FT in SHOT_KINDS, loaded by keep_ball_detections.py load_build_shot_list). Measurement only, applied_to_core false, no protected file edited, no rebuild, outputs outside the repo. One binding note added in the body of section 5 (rise time). Muse to check.
STAGE C JOB SPEC v2 - nothing built

# Stage C Job Spec: Scoreboard Pair Rises (Measurement Only)

Plan: `.team/specs/18_makes_misses_work_plan.md` Stage C (BINDING NOTE d), `docs/agent_handoffs/ACTIVE.md` ("Makes from the scoreboard"), `scoreboard_clock.py` (read only, protected), `.team/shot_detectors/keep_ball_detections.py` (how D1 builds its 140-shot list), `AGENT_OPERATIONAL_PROTOCOL.md` (Golden Rules).

## 1. Script path (MEASUREMENT ONLY — like D1)

`.team/shot_detectors/scoreboard_pair_rises.py` + tests `.team/shot_detectors/test_scoreboard_pair_rises.py`

- Changes nothing in the program. `applied_to_core` stays `false`.
- A make is still `ball_through_rim` or `net_moved_after_shot`; the scoreboard is a **checker only**. Putting it into the program is Scott's decision later.

## 2. Inputs (read only)

- **Scoreboard track**: existing Adrian track at `data/scoreboard_tracks/jrhigh_adrian__or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json`, read through `scoreboard_clock.py` functions (`load_scoreboard_track`, `scoreboard_at`). **No edits, no rebuild** — do NOT list `scripts/build_scoreboard_track.py` in any run command; the work plan's run command that does is wrong (BINDING NOTE d).
- **Shots**: the same 140-shot list D1 used (same loader logic from `keep_ball_detections.py::load_build_shot_list`); stop unless exactly 140. Adrian shots only for pairing; per-shot old/new verdicts from `d1_results.json`.
- **Live DB**: `film_analysis.db` only with `mode=ro` if needed at all.

## 3. Rise rule (exactly as recorded)

From `ACTIVE.md` lines 9–10:

> **Rule (set once, not tuned):** a team's score counts when the new value holds for 3 one-second samples; each rise is one made basket worth the rise.

Quoted verbatim from `docs/agent_handoffs/ACTIVE.md` (updated 2026-10-26, "Makes from the scoreboard" section).

## 4. Window: 25 s (BINDING NOTE d)

BINDING NOTE d states: "window 25 s (ACTIVE.md 'Makes from the scoreboard')".

From `ACTIVE.md` line 11: "43 made baskets found; all 43 tagged makes matched to a rise **within 25 s of the tag**".

**Direction NOT recorded in the files.** The files `ACTIVE.md` (line 11), `.team/specs/04_notus_scoreboard_plan_v3.md` (line 58), and `.team/specs/05_reliable_detector_architecture.md` (line 67) all say only "within 25 s" and do NOT record a direction. Fixed in advance as the stricter reading: the rise must come at or after the shot, no more than 25 s after it (shot t <= rise t <= shot t + 25 s). This is narrower than either-side, never wider.

## 5. Pairing — no guessing

For each Adrian shot, the window is **shot t .. shot t + 25 s** (as section 4). A rise's candidate shots are the shots whose window contains the rise.

**Rise time (binding note, Claude Code 2026-10-31):** a rise's time is the time of the FIRST one-second sample that shows the new value (the value that then holds for 3 samples). A shot counts toward the "exactly one rise" test with rises of any value (1, 2 or 3), so a make followed by an and-one free throw is AMBIGUOUS, never CLEAN.

A pair is **CLEAN** only when:
- The rise has exactly one shot in its window, AND
- That shot has exactly one rise in its window.

Anything else is **AMBIGUOUS** and is **never counted as a recovered make**.

**Fixed rule (stated in advance):** a 1-point rise is a free throw and is **never paired as a recovered field-goal make**; 1-point rises are listed in their own table with any shots in their windows. Only 2- and 3-point rises can make a CLEAN pair.

The 140-shot list **INCLUDES free throws** (from `measure_net_moved.py::load_shot_tags` where `SHOT_KINDS = {"2PT", "3PT", "FT"}`).

Report the pairing **two ways** (BINDING NOTE d):
1. **By time only** — rise timestamp vs shot timestamp.
2. **By time plus shooting team from the tag rows** — say plainly: "a new game has no tag rows, so the time-only count is the one that matters."

List every rise that matches more than one shot (ambiguous rises).

## 6. Numbers reported (fixed before anything runs)

Adrian shots in the 140 build set = 109 (from `d1_results.json`, counted by Claude Code 2026-10-31).
Adrian makes = 38.
Adrian real misses = 71.
Adrian makes already right after D1 = 27.
Adrian makes still called misses = 11.

The script must compute these counts itself and stop if they differ.

**Of the 11 Adrian makes still called misses:**
- CLEAN rises (one rise, one shot in window; rise value 2 or 3)
- AMBIGUOUS rises (multiple shots or multiple rises)
- NO RISE

**Of the Adrian real misses (71):**
- CLEAN rises with rise value 2 or 3 (a real miss with a CLEAN 2/3-point rise = **false make**; hard gate, must be 0 — report every one by time)
- CLEAN rises with rise value 1 (free throw; listed separately, not a false make)
- AMBIGUOUS rises
- NO RISE

**Of the Adrian makes already right (27 after D1):**
- How many get a CLEAN rise (cross-check)

**Rises with no shot at all** (unpaired rises)

**Points by rise value (1/2/3)** next to each pair (from ACTIVE.md: "Points by value match the tags exactly: Liberty 17 twos, 5 threes, 2 free throws; Adrian 5 twos, 1 three, 13 free throws")

## 7. Outputs (outside the repo — repo is PUBLIC)

- `C:/Users/scott/Documents/Liberty_Shot_Outputs/scoreboard/pairs_results.json`
- `C:/Users/scott/Documents/Liberty_Shot_Outputs/scoreboard/pairs_report.md`

**Run command with repo venv:**
```
.venv/Scripts/python.exe .team/shot_detectors/scoreboard_pair_rises.py
```

(No `scripts/build_scoreboard_track.py` — BINDING NOTE d)

## 8. Stop rules

- No tuning after results.
- No second window.
- No retry.
- After the report, stop for Scott.

**Notus**: one paragraph only saying its reader is parked (`.team/specs/09_notus_reader_v9_SHELVED.md`) and Scott decides any Notus work.

---

Every fact above comes from a file read in this session. If a value was not found, it is marked `NOT FOUND - Claude Code to check` — none remain in this spec.