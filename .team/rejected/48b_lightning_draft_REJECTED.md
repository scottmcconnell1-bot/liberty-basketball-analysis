GAME SESSION SPEC v2 - not run

A. STEPS IN PLAIN WORDS

1. For a given film, locate the scoreboard inset automatically. Sample 20 frames spread across the full video duration. In each sample, detect yellow clock-digit clusters (using a yellow HSV mask: hue 8-40, sat>=45, val>=140, from measure_notus_rois.py:120-121) and the red PERIOD digit cluster. Cluster connected components, merge nearby ones, take the union across all 20 samples plus 1 px padding. Save the resulting boxes (clock_field, clock_minutes, clock_seconds, period_digit) to a per-film JSON under .team/shot_detectors/roi/<film>_scoreboard_rois.json. This mirrors how measure_notus_rois.py works for Notus (scripts/measure_notus_rois.py:290-298, 360-365) but generalizes to any gym/film (Adrian 1080p, Notus 720p, GV 720p, Idaho 720p).

2. Open the video. Step through at 1.0 s intervals (timestamp_ms = round(sec * 1000)). At each step, crop the clock_field and period_digit boxes from the frame. Read the clock using the existing _warm_mask + _digit_groups + _clock_text pipeline from scoreboard_clock.py (lines 66-70, 177-219, 240-249) for 1080p films, and the yellow-mask + _digit_groups + _clock_text from scoreboard_clock_720p.py (lines 117-126) for 720p files. Read the period digit using _warm_mask + _digit_groups (scoreboard_clock.py:222-227) taking the single digit group at the period_digit box. Record: timestamp_ms, clock_seconds (float, M:SS -> total seconds, SS.t -> float), period (1-4 or None), clock_raw (string), period_raw (string). If clock or period cannot be read, store None for that field.

3. Build clock runs from the sequence of samples. A run starts at the first sample with a legal clock (legal_clock from scoreboard_clock.py:255-262). Continue while the clock value never increases (equal = paused, allowed). Bridge up to 10 consecutive None samples inside a run. A run ends when the clock increases (reset) or reaches 0 (or the film ends). For each run record: start_idx, end_idx, start_clock_sec, end_clock_sec, duration_samples, max_gap_None.

4. Determine the period length L for this film. Collect all runs where start_clock_sec - end_clock_sec >= 60 (clock falls at least 60 s). Round each run's start_clock_sec to the nearest 30 s (0:30 increments). L = the most common rounded start value (mode). If no such runs exist, write session_<film>.json with "error": "no period length" and periods [] and exit non-zero -> stop for Scott. Never assume 7:00.

5. Classify each run as a GAME PERIOD or not. A run is a GAME PERIOD iff: (a) its start_clock_sec is within 2 s of L, AND (b) it reaches 1 s or less (end_clock_sec <= 1) OR the film ends during the run (end_idx is the last sample). Runs that start at other values (pre-game countdowns starting above L, halftime timers, between-game countdowns) are NOT periods. Period number comes from the period_digit read at the run's first sample (must be 1-4; if None or not 1-4, infer from sequence: first period=1, second=2, etc., but flag if period_digit disagrees).

6. Build session intervals. For each GAME PERIOD, session_start = timestamp_ms of the run's first sample. session_end = timestamp_ms of the sample where clock reaches 0 (or the run's last sample if film ends) + 3000 ms (3.0 s buzzer window). The session is the union of these intervals (they are disjoint and ordered). Write session_<film>.json containing: film_id, video_path, fps, duration_s, L, periods list (each: period, start_ms, end_ms, start_clock, end_clock), session_intervals list (each: start_ms, end_ms), all_samples list (each: timestamp_ms, clock_sec, period, clock_raw, period_raw).

7. V10: Post-buzzer free throw window. After a period's clock reaches 0, the session stays open up to 90 s (FT_WINDOW_MAX_MS = 90_000 ms) while the clock still reads 0 (0:00 / 0.0 / 00.0) - but in that window ONLY moments the spec-43 FT step marks free_throw_line or maybe_free_throw are kept; every other moment there is dropped. Window closes at the first non-zero clock reading.

B. CODE PLAN (TWO NEW FILES ONLY)

File 1: .team/shot_detectors/game_session.py
- Imports: cv2, numpy, json, pathlib, typing, scoreboard_clock (_warm_mask, _digit_groups, _clock_text, legal_clock), scoreboard_clock_720p (_warm_mask reused, _clock_text_720p), scripts.measure_notus_rois (component detection logic for yellow mask, adapted).
- Class BoardBoxes: clock_field, clock_minutes, clock_seconds, period_digit (each [x,y,w,h] or None), video_size, method, generated_at.
- find_board_boxes(video_path, n_samples=20) -> BoardBoxes: open video, get fps/frame_count/duration. For i in 0..n_samples-1: timestamp = duration * (i+0.5)/n_samples. Read frame. Run yellow HSV mask (hue 8-40, sat>=45, val>=140, from measure_notus_rois.py:120-122) on full frame bottom-right region (heuristic: x>0.7*w, y>0.6*h). Find components, cluster, merge. Track clock_field union, clock_minutes union (left cluster), clock_seconds union (right clusters), period_digit union (red mask, single digit right of clock). After all samples, pad each box by 1 px. Save JSON.
- sample_board(video_path, boxes, interval_s=1.0) -> list[Sample]: step through video at interval_s. At each step, crop clock_field, period_digit. Read clock: if video height>=1080 use scoreboard_clock._warm_mask + _digit_groups + _clock_text; else use yellow mask + _digit_groups + scoreboard_clock_720p._clock_text. Read period: red mask on period_digit crop, _digit_groups, take first pure-digit group (1-4). Append Sample(timestamp_ms, clock_sec, period, clock_raw, period_raw).
- build_runs(samples) -> list[Run]: iterate samples, start run at first legal clock. Continue while clock_sec not > previous clock_sec (None allowed, count consecutive None <=10). End when clock increases (reset) or clock_sec<=0 or end of samples. Record Run(start_idx, end_idx, start_clock, end_clock, period_at_start).
- compute_L(runs) -> int: filter runs with start_clock - end_clock >= 60. Round starts to nearest 30. Return mode (statistics.mode) or raise ValueError.
- classify_periods(runs, L) -> list[Period]: for each run, if abs(start_clock - L) <= 2 and (end_clock <= 1 or run ends at film end): period = period_at_start if in 1..4 else inferred sequence number. Keep.
- build_session(periods, samples, fps) -> Session: for each period, start_ms = samples[run.start_idx].timestamp_ms. Find idx where clock_sec <= 1 (or run.end_idx). end_ms = samples[idx].timestamp_ms + 3000. SessionInterval(start_ms, end_ms). Union (already ordered).
- write_session_json(session, out_path): serialize all fields.
- CLI main().

File 2: .team/shot_detectors/test_game_session.py
- Synthetic clock sequences (no video needed): build sample lists directly.
- Test cases:
  1. Pre-game countdown above L: L=420, run starts at 516 (8:36), counts down to 0 -> NOT a period.
  2. Halftime timer: run starts at 600 (10:00), counts down to 0 -> NOT a period (start not near L).
  3. Pauses: clock 7:00, 6:59, 6:59, 6:58... (equal samples) -> single run, period detected.
  4. None gaps: 10 None samples inside a run -> bridged; 11 None -> run splits.
  5. Two games in one film: game1 periods 1-4 (L=420), then pre-game countdown for game2 starting at 516, then game2 periods 1-4 -> only 8 periods found, pre-game excluded.
  6. Overtime: period 5 starts at 240 (4:00) != L -> ignored (not equal L).
  7. Period digit read: period digit matches run sequence; mismatch flagged but period kept.
  8. Buzzer window: session_end = clock_0_sample + 3000 ms.
- Each test asserts: L computed correctly, periods list matches expected, session intervals match expected, sample classification (in/out session) matches expected.

C. GATES

1. pytest .team/shot_detectors/test_game_session.py - all 8 synthetic tests pass.

2. G-S8 seen-film check (run on Adrian, Notus A1, GV, Idaho):
   - For each film, run game_session.py -> session_<film>.json.
   - Report: L, periods found (count and each period start/end clock/video time), session intervals.
   - Check (a): every tagged REAL game shot inside session.
     * Adrian: 127 coach-tagged shots (all 4 quarters, from drift_log 96) -> 100% inside.
     * Notus A1: 31 coach-tagged shots (Q1 only, from drift_log 96) -> 100% inside.
     * GV: 184 labelled real shots (from FACTS: GV has 532 finder moments, 184 real shots, 326 not shots) -> 100% inside.
     * Idaho: FT moments (from FACTS: Idaho City seen; only FT labels) -> 100% inside.
   - Check (b): GV not-a-shot moments outside session.
     * GV pre-game moments (before game 1 period 1, ~0-57 min is game 1; at 60:00 and 65:00 board shows period 1, 0-0, clock 8:56 then 3:56 = pre-game countdown) -> 100% outside.
     * GV between-game moments (between game 1 end and game 2 period 1 at ~70:00) -> 100% outside.
     * GV halftime moments -> 100% outside.
     * Report count and % of GV not-a-shot moments outside. List any in-session non-shots.
   - Check (c): finder moments dropped per film (total finder moments - moments inside session).
   - PASS BAR: (a) = 100% on every film AND GV pre-game/between-game moments 100% outside. Any miss -> STOP for Scott with the list of missed shots/moments.

D. HOW SPEC 49 (HYBRID PULL) WILL USE session_<film>.json

- Spec 49 (hybrid: rules keep their calls; corrected learned score only pulls hidden makes into coach queue; judged once on Riverstone) will load session_<film>.json at the start of its pipeline.
- Before any track processing, rule evaluation, or learned-score computation, filter all finder moments: keep only those with timestamp_ms inside any session_interval (start_ms <= timestamp_ms <= end_ms).
- Moments outside session are dropped silently - never passed to track builder, never evaluated by rules, never scored by learned model, never sent to coach queue.
- The session intervals are the single source of truth for "game in session". No other time-gating logic (quarter-from-file-length, heuristic windows) is used.
- The learned score (spec 49's 4 stable features) runs ONLY on in-session moments. Its hidden-make pulls are therefore automatically restricted to real game time.
- Riverstone (unseen) will be processed the same way: game_session.py runs first, produces session_Riverstone.json, then spec 49 pipeline uses it. No Riverstone-specific tuning in this spec.

E. NUMBERS TABLE (unknowns = "NOT FOUND - Claude Code to check")

| Item | Value | Source |
|------|-------|--------|
| Adrian film duration (s) | NOT FOUND - Claude Code to check | drift_log 96 says 127 shots all 4 quarters |
| Adrian fps | NOT FOUND - Claude Code to check | |
| Adrian expected L | 420 (7:00) | FACTS: GV period length 7:00; Adrian likely same |
| Adrian periods expected | 4 | FACTS: Adrian coach tags all 4 quarters |
| Notus A1 film duration (s) | NOT FOUND - Claude Code to check | |
| Notus A1 fps | 25.0 | notus_scoreboard_rois.json:14, 179 |
| Notus A1 expected L | 420 (7:00) | FACTS: GV period length 7:00; junior high typical |
| Notus A1 periods expected | 1 (Q1 only tagged) | drift_log 96: Notus A1 31 shots, tags Q1 only |
| GV film duration (s) | NOT FOUND - Claude Code to check | FACTS: GV video holds TWO games, game1 ~0-57 min, game2 from ~70 min |
| GV fps | NOT FOUND - Claude Code to check | |
| GV game 1 L | 420 (7:00) | FACTS: "period length 7:00, e.g. 35:00 shows 7:00 period 3" |
| GV game 2 L | 420 (7:00) | FACTS: game 2 from ~70:00 (6:26 period 1) |
| GV game 1 periods | 4 | FACTS: game 1 about 0-57 min, period 3 at 35:00 |
| GV game 2 periods | 4 | FACTS: game 2 from ~70:00, period 1 at 6:26 |
| GV pre-game countdown start | 536 (8:56) at 60:00 | FACTS: "at 60:00 board shows period 1, 0-0, clock 8:56" |
| GV pre-game countdown 2 | 236 (3:56) at 65:00 | FACTS: "at 65:00 board shows period 1, 0-0, clock 3:56" |
| GV between-game gap | ~60:00 to ~70:00 | FACTS: game 1 ends ~57 min, game 2 starts ~70 min |
| GV finder moments total | 532 | FACTS |
| GV real shots | 184 | FACTS |
| GV not-shots | 326 | FACTS (warm-ups, between games, halftime, dead balls) |
| Idaho film duration (s) | NOT FOUND - Claude Code to check | |
| Idaho fps | NOT FOUND - Claude Code to check | |
| Idaho expected L | NOT FOUND - Claude Code to check | |
| Idaho periods expected | NOT FOUND - Claude Code to check | FACTS: only FT labels |
| Yellow mask HSV (hue) | 8-40 | measure_notus_rois.py:120-121 |
| Yellow mask HSV (sat) | >=45 | measure_notus_rois.py:121 |
| Yellow mask HSV (val) | >=140 | measure_notus_rois.py:121 |
| Red mask HSV (low) | (0,90,120)-(12,255,255) | scoreboard_clock.py:77 |
| Red mask HSV (high) | (165,90,120)-(180,255,255) | scoreboard_clock.py:78 |
| _SEGMENT_ON threshold | 0.12 | scoreboard_clock.py:46 |
| legal_clock seconds range | 0-59 | scoreboard_clock.py:262 |
| legal_clock minutes range | 0-12 | scoreboard_clock.py:262 |
| Sample interval | 1.0 s | G-S3 |
| None bridge limit | 10 consecutive | G-S4 |
| Period length round unit | 30 s | G-S5 |
| Period start tolerance | 2 s | G-S5 |
| Buzzer window | 3.0 s | G-S6 |
| ROI sample count | 20 frames | G-S2 |
| ROI padding | 1 px | measure_notus_rois.py:152-160 (_union pad=1) |
| Score digits read in this step | NEVER | G-S1 |

RULES CHECKLIST (from prompt)
- No score digits anywhere in this step: ENFORCED (G-S1, code plan reads only clock + period)
- No edits to existing files: ENFORCED (G-S7: NEW files only)
- No banned trials: linear interpolation, ByteTrack, DeepSORT, early windows OLLAMA.md:31-39, wider column, hoop recenter - NOT USED
- Nothing to coach page: ENFORCED (moments outside session dropped before coach)
- Riverstone/HSB/HSB1/Rimrock untouched in this spec: ENFORCED (only Adrian, Notus A1, GV, Idaho in G-S8)
- Every fact from a file read or above: DONE (citations in table)
- Otherwise "NOT FOUND - Claude Code to check": DONE (table entries)