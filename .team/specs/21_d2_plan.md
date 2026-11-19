VETTED by Claude Code, 2026-10-31: v2 checked - training film is only untagged games plus Notus A outside 125 frames of its holdout (ls uploads/, data/film_tags/ this session); build set, holdout and the tagged unseen check (Adrian Q4, Notus A1 Q2-Q4; specs 15 line 134, 16 line 125) excluded; no build-set frame used for labelling; new model a separate gitignored file; ball_detector.pt and ball_confidence unchanged; conf 0.28 or stricter; test = D1 rerun, one try, 0 misses called makes; three Scott gates. Two binding notes added in the body: frame count fixed by Scott at gate 1 (section 2); venv torch is CPU only, GPU training in a separate environment (section 5). Muse to check.
STAGE D2 PLAN v2 - nothing built

# Stage D2 Plan: Better Ball Detector Near the Rim

From: `.team/specs/18_makes_misses_work_plan.md` Stage D, `.team/specs/19_d1_job_spec.md` (D1), `.team/specs/20_c_job_spec.md` (Stage C), `measure_net_moved.py` FILMS, `keep_ball_detections.py` load_build_shot_list, `.team/specs/holdout_names.json`, AUTHORITY.md, AGENT_OPERATIONAL_PROTOCOL.md, `docs/agent_handoffs/ACTIVE.md`.

D1 (`.team/specs/19_d1_job_spec.md`; `C:/Users/scott/Documents/Liberty_Shot_Outputs/ball_arc/d1_report.md`) recovered 1 of 19 missed makes, 0 false makes. Diagnostic showed the ball detector misses the ball near the rim: across the 19 missed makes, 117 of 323 frames near the anchor had "ball_not_detected" (no candidate in the near-hoop zone after confidence + zone filter, before cap). Stage C (`.team/specs/20_c_job_spec.md`; `C:/Users/scott/Documents/Liberty_Shot_Outputs/scoreboard/pairs_report.md`) recovered 3 of 11 Adrian missed makes as a checker only. Scott wants the D2 framework: a better ball detector near the rim.

---

## 1. Training frames — ONLY from film NOT in the 140-shot build set, NOT in holdout, NOT in tagged unseen check shots

**Build set (EXCLUDED — 140 shots):** from `measure_net_moved.py:31-50` FILMS and `keep_ball_detections.py:628-681` load_build_shot_list (BUILD_QUARTERS = {"Q1","Q2","Q3"}):
- Notus A1 Q1: `uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4` — 31 shots
- Adrian Q1-Q3: `uploads/nfhs_gam0a66d85e12.mp4` — 109 shots

**Holdout (EXCLUDED — 20 frames, never open answer key, never use holdout frame or its neighbours):** `.team/specs/holdout_names.json` — 10 frames from Notus A1 (`notus_A1_h00_246s` through `notus_A1_h09_3881s`), 10 from Notus A (`notus_A_h00_232s` through `notus_A_h09_3603s`).

**Tagged unseen check shots (EXCLUDED — training on them burns the check):**
- Adrian Q4: 18 tagged shots (ACTIVE.md line 33: "109 in Q1–Q3 and 18 in Q4"). `.team/specs/15_net_check_plan.md` line 134 and `.team/specs/16_ball_in_net_plan.md` line 125 state: "any threshold picked from these 140 shots is build-set only and is not a result until checked on unseen shots" — Adrian Q4 is the only tagged unseen set; training on it invalidates the check.
- Notus A1 Q2–Q4: tagged shots outside Q1 (the build set uses Q1 only). Same reason — they are the unseen check for Notus A1.

**Training films (untagged game films in uploads/):**
Claude Code listed them 2026-10-31:
- `uploads/LIBERTY_A_v_HSB_H1_20260809_221334.mp4`
- `uploads/LIBERTY_A_v_HSB_H_20260809_221334.mp4`
- `uploads/LIBERTY_A_v_RIMROCK_H_20260809_221334.mp4`
- `uploads/LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334.mp4`
- `uploads/LIBERTY_H_v_IDAHO_CITY_A_20260809_221334.mp4`
- `uploads/LIBERTY_H_v_RIVERSTONE_A_20260809_221334.mp4`
- `uploads/LIBERTY_H_v_NOTUS_A_20260809_221334.mp4` — **only frames at least 5 seconds (125 frames at 25 fps) away from any of its 10 holdout timestamps** (holdout frames are at 232.3s, 606.9s, 981.5s, 1356.1s, 1730.7s, 2105.3s, 2479.9s, 2854.5s, 3229.1s, 3603.7s). No training frame within ±125 frames of any holdout timestamp.

**Notus A has no tag file in `data/film_tags/`** — only `jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334.json` and Adrian's tag file exist. The second Notus game (Liberty 38 Notus 21 per ACTIVE.md line 21) is fully untagged and therefore eligible for training frames outside the holdout distance.

---

## 2. Who labels and how

- **Labeller:** Scott.
- **Tool:** a simple labelling page (to be built or adapted) that shows a frame, lets Scott draw a box on the ball or click "no ball visible". One label = one box (x,y,w,h) on the ball, or a "no ball" flag.
- **Frames to label:** near-rim frames found in untagged film without ground truth. Method: run the current detector (v6_ball, conf 0.28, D1 crop `hoop_x±260`, `hoop_y-200..+240`) on the untagged films; sample frames where the detector puts a ball inside the D1 near-hoop zone (horizontally `abs(x_center - hoop_x) <= 3.0 * hoop_w`, vertically `hoop_y - 4.0 * hoop_w <= y_center <= hoop_y + 300`), plus frames just after the detector loses the ball there (where the detector fails). Target: **one number, fixed by Scott at gate 1 before any labelling** (binding note, Claude Code 2026-10-31: suggested 600 frames - estimate about an hour at a few seconds per box; never changed after training starts); the split ball / no-ball falls out as sampled. Near-rim frames are favoured by picking more of them (oversampling), not by loss weights.
- **Time per frame:** estimate seconds per frame.
- **Weighting:** oversampling of near-rim frames handles class balance; loss weights are not used.

---

## 3. New model file — separate, gitignored, never committed

- **Output:** `models/ball_detector_v2.pt` (or similar name), **gitignored**, never committed (repo is PUBLIC per `.team/specs/18_makes_misses_work_plan.md` line 194).
- **Production gate:** `models/ball_detector.pt` and `ball_confidence` (0.28) are **Scott gates** (AUTHORITY.md lines 23, 17) — **not changed**.
- **Confidence threshold:** same **0.28 or stricter**; never looser (D1 spec §2, AGENT_OPERATIONAL_PROTOCOL.md Golden Rule 1: No Loosening).

---

## 4. Test — 140-shot build set stays a blind benchmark, then unseen check

- **Procedure:** rerun the D1 script (`.team/shot_detectors/keep_ball_detections.py`) with the new model swapped in for the v6 weights (`/mnt/c/Users/scott/AppData/Local/Temp/ball_net_runs/v6/weights/best.pt`), **nothing else changed**.
- **Pass criteria:** `makes_right` > 29 (D1 achieved 29, baseline target 28) **AND** `misses_called_makes == 0` (hard gate).
- **Numbers fixed before training:** the test script, the 140 shots, the confidence (0.28), the zone, the arc hyperparameters, the rule (Stage A copy all switches OFF) — all fixed in `.team/specs/19_d1_job_spec.md`. **No tuning after seeing results.**
- **One try then stop for Scott:** if the new model fails the gate, stop. No retry loops.
- **Unseen check (Scott's decision, after build-set test passes):** Adrian Q4 tracks (which must be built first) are the only tagged unseen set. Nothing is called a result before Scott runs the check on them and decides.

---

## 5. Where training runs and roughly how long

- **Hardware:** NVIDIA GeForce RTX 5060 Laptop GPU, 8 GB (Claude Code ran `nvidia-smi` 2026-10-31). The repo venv's torch is CPU only (Claude Code ran it 2026-10-31: torch 2.14.1+cpu, cuda False). Training on the GPU needs a separate CUDA build of torch in its own environment outside the repo venv (binding note, Claude Code 2026-10-31); the repo venv is not changed. Dockerfile (line 10) defaults to CPU (`TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu`). GPU is optional via override (Dockerfile line 3-4: "Override TORCH_INDEX_URL ... to build a GPU-capable image on hosts with the NVIDIA container runtime installed"). The Windows venv at `C:\Users\scott\Documents\liberty-basketball-analysis\.venv\Scripts\python.exe` (BINDING NOTE a in `.team/specs/18_makes_misses_work_plan.md`) is used for model inference; training can use the same venv or Docker.
- **Estimated time:** YOLOv8 fine-tune on estimate frames, CPU: estimate hours; GPU (if available): estimate minutes. Exact time depends on hardware.

---

## 6. What Scott decides (three gates)

Scott must explicitly say **yes** to each before proceeding:

1. **OK to label** — the labelling tool/page, the frame list, the time estimate.
2. **OK to train** — the candidate frames selected, the model config, the compute (CPU/GPU), the output path (`models/ball_detector_v2.pt` gitignored).
3. **OK to use the new model anywhere** — after the blind benchmark test passes (more makes right, 0 misses called makes), Scott decides whether to adopt it in the live detector, keep it as a candidate, or discard it.

---

**End of plan.** Nothing built. Every number above comes from a file read in this session. If a value was not found, it is marked `NOT FOUND - Claude Code to check` — none remain.