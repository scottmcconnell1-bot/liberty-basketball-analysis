VETTED by Claude Code, 2026-10-29 (v1, five binding notes): the four stages follow Scott's choice and the reviewed list (.team/specs/17_missed_makes_options_REVIEWED.md); no banned trial, no looser cutoff, no net-region measurement, ai_bridge.py and protected files untouched, outputs outside the repo, D2 waits for Scott. Checked by reading the plan against ai_bridge.py run_saved_v6_rule, docs/agent_handoffs/ACTIVE.md, and the paths on disk (ls).
BINDING NOTE a (every "Run command (Windows venv ...)"): C:\Users\scott\.venv does not exist. The venv is C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe. Results file: C:\Users\scott\Documents\Liberty_Shot_Outputs\net_moved_build_results.json (the .team/shot_outputs_test copy is byte-identical; use the Liberty_Shot_Outputs one).
BINDING NOTE b (Stage A, "Plan"): inputs are C:\Users\scott\AppData\Local\Temp\v6_tracks.json and v6_tracks_notus_q1.json (the tracks_path in each results row) with truth from net_moved_build_results.json, each (film, t) once = 140. FIRST, with every switch off, the copy must give the same verdict AND the same reason as run_saved_v6_rule (imported read-only) on all 140 shots; print that check; if any shot differs, stop. Only then measure each fix alone and all together.
BINDING NOTE c (Stage B, "Window fix"): the text says +/-1 s keeps the crowd out, but the crowd feature reads +0.5 to +3 s. Use two fixed windows: onset features from peak-0.5 s to peak+1.0 s; crowd feature from peak+0.5 s to peak+3.0 s. Peak frames for no-crossing shots are guesses (peak_reason no_crossing_*): report every feature split by peak_reason as well. Decode with ffmpeg + numpy; install nothing.
BINDING NOTE d (Stage C): do NOT rebuild any scoreboard track (no build_scoreboard_track.py run). Use the existing proven track data/scoreboard_tracks/jrhigh_adrian__or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json read through scoreboard_clock.py (read only), window 25 s (ACTIVE.md "Makes from the scoreboard"). The saved tracks carry no team per shot: report the pairing two ways - by time only, and by time plus the shooting team from the tag rows - and list every rise that matches more than one shot.
BINDING NOTE e (Stage D1): before anything runs, the plan for D1 must be written into the job prompt with fixed numbers, not chosen after seeing results: the frame window per shot (the same frames the saved v6 track covers), the "near the hoop" zone (the zone the v6 rule already reads: within 3 hoop widths of the hoop centre horizontally, from above the rim down to 180 px below it - no pixel colour, no net box), the arc model (a parabola in time fitted to real detections only, with a maximum residual in px stated in advance), and that the chosen points then go through the UNCHANGED rule (the Stage A copy with every switch off). Same ball_confidence read with mode=ro. The checker runs the model with the venv.

PLAN v1 - nothing built

# Makes and Misses Work Plan

Author: Hermes (Architect)
Date: 2026-10-29
Status: PLAN v1 - nothing built
Gate: Vetter review required before any Cursor implementation. Nothing in this file is built.

## Where we stand

The missed-makes work is measured on the 140-shot build set: Notus A1 Q1 (31 shots) and Adrian Q1-Q3 (109 shots). From the files: .team/shot_outputs_test/net_moved_build_results.json, .team/shot_outputs_test/net_moved_summary.md, .team/drift_log.md, docs/agent_handoffs/ACTIVE.md, and .team/specs/16_ball_in_net_plan.md.

Numbers from the files: 47 makes, 28 right calls and 19 missed makes; 93 real misses. Hard gate for every stage: 0 misses called makes on the 140 build-set shots.

The saved v6 rule, run_saved_v6_rule in ai_bridge.py, with its net helpers short_track_stays_in_net and detect_dynamic_entry_crossing, produced the current misses.

Proven scoreboard numbers from the files: Adrian 43 of 43 makes, final 51-26; the Notus board reader failed its gate at 9 of 20 and is parked.

## Scott's words

"Scoreboard - reopen. Sound Test - Try it. Small fixes - do them. Better ball detection (this seems to be the constant error generator)."

## Stage A - small fixes inside the rule (from the reviewed options list)

### In scope

A7, A8, A4, C4, from .team/specs/17_missed_makes_options_REVIEWED.md.

### Fix definitions

A7: bodd points count toward the >=3 net-depth points, only below the rim and inside 0.6 hoop widths.

A8: ignore an upward move in the downward-trend test only where the same frame pair is a >60 px box jump.

A4: drift measured from the crossing point's x.

C4: two bugs: in the LINE TEST ball[cross_idx:] uses an index counted on the combined track; the jump check finds its own true crossing with no hoop-width test.

### Plan

Copy the run_saved_v6_rule decision logic into a new file under .team/shot_detectors/. Proposed path: .team/shot_detectors/small_fixes_v6_copy.py.

Never edit ai_bridge.py in this stage. Each fix switchable on/off, default off. No cutoff value may change.

Run over the 140 build-set shots; per fix report missed makes recovered (list the t values), misses called makes (must be 0), and every shot whose verdict changed.

No retry loops; each stage stops for Scott if it fails.

### Stage A deliverables

Files created (exact paths):

- /mnt/c/Users/scott/Documents/liberty-basketball-analysis/.team/shot_detectors/small_fixes_v6_copy.py
- C:\Users\scott\Documents\Liberty_Shot_Outputs\small_fixes\build_results.json
- C:\Users\scott\Documents\Liberty_Shot_Outputs\small_fixes\per_fix_report.md

Run command (sandbox): python .team/shot_detectors/small_fixes_v6_copy.py with the fix switches set one at a time, over the saved build-set inputs. The copy is decision logic over saved JSON, so it can run in the Cursor sandbox without torch/ultralytics.

Run command (Windows venv and checker): the same copy with the Windows venv python (C:\Users\scott\.venv\Scripts\python.exe), over the saved build-set inputs.

Output files: the two C:\Users\scott\Documents\Liberty_Shot_Outputs\small_fixes\ files.

Numbers reported: per fix, missed makes recovered with the t values, misses called makes (must be 0), and every shot whose verdict changed.

Pass/stop rule: hard gate 0 misses called makes; stop for Scott if it fails; no retry loops.

What Scott checks by eye: the recovered t values, the verdict-change list, and the real misses.

## Stage B - sound test (measurement only)

Both build-set films have AAC stereo 48 kHz audio, Notus at 1280x720 and Adrian at 1920x1080, 25 fps.

### Window fix

The audio window is fixed before measuring: window = peak frame +/- 1 s (25 frames at 25 fps), centred on the rim moment from net_moved_build_results.json; crowd loudness feature read at +0.5 s to +3 s later.

Why: the ball-rim event is within about 0.3 s of the peak frame, and crowd loudness begins within 0.5 s, so a +/-1 s window keeps onset features inside and the crowd response outside the onset window.

### Audio library

Name the library: candidate librosa.

Check result from the files: no audio library appears in requirements.txt, requirements-dev.txt, or requirements.docker.txt, and no librosa/soundfile/pydub/moviepy/imageio/audioread/whisper/torchaudio/pyaudio entry appears in the Windows venv package list.

ffmpeg is present (WSL, Docker, CI) and backs cv2 CAP_FFMPEG.

Decision for the probe: use ffmpeg to decode AAC stereo 48 kHz to raw PCM s16le stereo, then use numpy for RMS and FFT features; if a named audio library is wanted, install it into the Windows venv.

### Features

Loudness rise after the rim moment; short high-frequency burst for a rim clang; crowd loudness 0.5-3 s later.

### Stage B deliverables

Files created (exact paths):

- .team/shot_detectors/sound_probe.py
- C:\Users\scott\Documents\Liberty_Shot_Outputs\sound\features_report.md

Run command (sandbox): python .team/shot_detectors/sound_probe.py over the build-set films and the net_moved_build_results.json.

Run command (Windows venv and checker): C:\Users\scott\.venv\Scripts\python.exe .team/shot_detectors/sound_probe.py over the build-set films and the net_moved_build_results.json.

Output files: C:\Users\scott\Documents\Liberty_Shot_Outputs\sound\features_report.md.

Numbers reported: how well each feature separates the 47 makes from the 93 misses (table), plus how many of the 19 missed makes each feature would flag at a threshold that flags 0 misses.

Pass/stop rule: measurement only; no threshold tuned on the same shots is called a result; 140 shots is a build set and an unseen set is needed before anything is used; stop for Scott before any threshold use.

What Scott checks by eye: the feature magnitudes and which missed makes the features would flag.

## Stage C - scoreboard reopened

scoreboard_clock.py is a protected core file, read only, do not edit.

Proven on Adrian: 43 of 43 makes, final 51-26.

The Notus board reader failed its gate (9 of 20) and is parked; see .team/specs/09_notus_reader_v9_SHELVED.md and .team/reader_v9_PARKED/PARKED.md.

### Step 1 - Adrian pairing

Pair each scoreboard rise with the rule's shots (team, time window; say the window and why).

Window: 25 s, the window used for the saved-v6 scoreboard pairing, per the recorded spec; why: it is the established pairing window, with the rule's shot tolerance at 8 s.

Report how many of the 12 Adrian missed makes get a rise and whether any of the real misses get one.

### Step 2 - Notus

Say plainly what would have to change for the parked reader to pass, which parked plan to restart, and that Scott decides before any Notus reader work starts.

### Stage C deliverables

Files created (exact paths): no new file required for the read-only pairing; any new pairing code goes to .team/shot_detectors/scoreboard_pair_rises.py.

Run command (sandbox): python scripts/build_scoreboard_track.py GAME VIDEO and python .team/shot_detectors/scoreboard_pair_rises.py.

Run command (Windows venv and checker): C:\Users\scott\.venv\Scripts\python.exe scripts/build_scoreboard_track.py GAME VIDEO and C:\Users\scott\.venv\Scripts\python.exe .team/shot_detectors/scoreboard_pair_rises.py.

Output files: pairing report outside the repo at C:\Users\scott\Documents\Liberty_Shot_Outputs\scoreboard\pairs_report.md.

Numbers reported: how many of the 12 Adrian missed makes get a rise, and whether any real miss gets one.

Pass/stop rule: measurement only; stop for Scott; Scott decides on any Notus reader work.

What Scott checks by eye: the pairing list and the missed makes that get rises.

## Stage D - better ball detection near the rim (Scott: "the constant error generator")

### Proven facts

From the files: in the 7 no-crossing makes the tracked object starts 1 to 2.6 hoop widths off centre or well below the rim, and 2 (t=801800, t=3095700) have no point near the hoop at all; 3 column-ratio makes read 0.0.

### D1

Keep every ball detection near the hoop per frame (today only the nearest box is kept) at the same ball_confidence (read from the DB with mode=ro; never lower it), and choose among REAL detections the ones that fit one falling arc - no made-up points (interpolation is banned), not ByteTrack or DeepSORT (banned); report what fraction of the 19 then get a valid crossing and a clean line test, and the misses.

### D2

Candidate ball weights file trained on Liberty film.

Where labelled frames come from: Scott's tags give times, not boxes - state how boxes are made and how much of Scott's time it costs.

Saved as a separate file, scored by C:\Users\scott\AppData\Local\Temp\validate_ball_weights.py, never copied over models/ball_detector.pt; tighten the pass bar as the reviewed list says.

D2 is planned only; it needs Scott's yes before training starts.

### Stage D deliverables

Files created (exact paths): D1 - .team/shot_detectors/keep_ball_detections.py; D2 - none yet, planned only.

Run command (sandbox): python .team/shot_detectors/keep_ball_detections.py with the saved build-set inputs. The Cursor sandbox has no torch/ultralytics, so Cursor writes and tests what it can; the checker runs the model with the Windows venv.

Run command (Windows venv and checker): C:\Users\scott\.venv\Scripts\python.exe .team/shot_detectors/keep_ball_detections.py with the same ball_confidence from the DB read with mode=ro.

Output files: D1 results outside the repo at C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_arc\d1_results.json and C:\Users\scott\Documents\Liberty_Shot_Outputs\ball_arc\d1_report.md.

Numbers reported: what fraction of the 19 then get a valid crossing and a clean line test, and the misses.

Pass/stop rule: hard gate 0 misses called makes; stop for Scott if it fails; no retry loops; D2 planned only and needs Scott's yes before training starts.

What Scott checks by eye: the detections kept, the arc choices, the misses.

## Rules for every stage

No looser cutoffs; no banned trial (linear interpolation, ByteTrack, DeepSORT, early windows, wider column, hoop recenter); no net-region measurement of any kind (Scott closed it); no hard-coded results; applied_to_core stays false; ai_bridge.py, protected core files, models/ball_detector.pt and ball_confidence untouched; film_analysis.db opened read-only (mode=ro) only; images, crops and audio clips written outside the repo (C:\Users\scott\Documents\Liberty_Shot_Outputs\<stage>) because the repo is public; Cursor runs in a sandbox without torch/ultralytics, so for any model step Cursor writes and tests what it can and the checker runs the model with the Windows venv.

## Per-stage deliverable checklist

For each stage give: files created (exact paths), the run command (Windows venv and sandbox), the output files, the numbers reported, the pass/stop rule, and what Scott checks by eye.

Covered above per stage: Stage A, Stage B, Stage C, Stage D.

## End

Nothing is built. No scratch scripts and no runs that write files beyond the stage outputs listed above were created for this plan.
