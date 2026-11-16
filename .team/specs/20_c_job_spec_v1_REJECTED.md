REJECTED by Claude Code, 2026-10-31: (1) section 5 window is backwards ("rise time -> rise time + 25 s") and contradicts section 4; (2) section 4 calls rise-after-shot a "finding" but no file records the direction (ACTIVE.md, spec 04 v3, spec 05 say only "within 25 s"); (3) section 6 counts wrong: d1_results.json has 109 Adrian shots, 38 makes, 71 misses, 27 makes already right (Hermes wrote 43 / 66 / 29); (4) 1-point rises (free throws) are not separated, so a foul-shot rise after a missed field goal could make a false make.

STAGE C JOB SPEC v1 - nothing built

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

**Finding**: The recorded 25 s pairing was **rise-after-shot only** (rise within 25 s *after* the tag). The text says "matched to a rise within 25 s of the tag" and the rise rule is "each rise is one made basket" — the scoreboard shows the score *after* the basket. The pairing direction is rise-after-shot. **Use exactly that; never wider.**

## 5. Pairing — no guessing

For each rise, list every Adrian shot inside the 25 s window (rise time → rise time + 25 s).

A pair is **CLEAN** only when:
- The rise has exactly one shot in its window, AND
- That shot has exactly one rise in its window.

Anything else is **AMBIGUOUS** and is **never counted as a recovered make**.

Report the pairing **two ways** (BINDING NOTE d):
1. **By time only** — rise timestamp vs shot timestamp.
2. **By time plus shooting team from the tag rows** — say plainly: "a new game has no tag rows, so the time-only count is the one that matters."

List every rise that matches more than one shot (ambiguous rises).

## 6. Numbers reported (fixed before anything runs)

Adrian shots in the 140 build set: 109 shots (43 makes, 66 misses — from ACTIVE.md pickup: 109 Q1–Q3 shots, 43 makes, final 51-26).

From D1 results (user: "Makes right went 28 -> 29 of 47; 18 makes are still called misses: 11 Adrian, 7 Notus"):

**Of the 11 Adrian makes still called misses:**
- CLEAN rises (one rise, one shot in window)
- AMBIGUOUS rises (multiple shots or multiple rises)
- NO RISE

**Of the Adrian real misses (66):**
- CLEAN rises (a real miss with a CLEAN rise = **false make**; hard gate, must be 0 — report every one by time)
- AMBIGUOUS rises
- NO RISE

**Of the Adrian makes already right (29 after D1, 28 baseline):**
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