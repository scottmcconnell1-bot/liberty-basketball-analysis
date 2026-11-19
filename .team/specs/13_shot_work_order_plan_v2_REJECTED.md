1|REJECTED by Claude Code, 2026-10-27 (v1): (1) Task 2 "birdeye make/miss" is geometrically wrong: the court homography maps the FLOOR plane; the ball and rim are 10 ft in the air, so ball-through-rim cannot be decided in court feet. Make/miss stays in image pixels at the hoop (run_saved_v6_rule, ai_bridge.py:908: hoop-width and pixel rules). Birdeye/court lines give shot LOCATION and help SHOOTER id, not make/miss. (2) Because of (1), the plan has no task that attacks the actual make/miss gap: Notus A1 Q1 24/31 (7 makes missed), Adrian 99/111 (12 makes missed). Scotts first goal is makes/misses 100%; the plan must say what fixes those missed makes (e.g. a net-movement or ball-below-rim detector measured alone in pixels near the hoop), or state plainly that court lines come first for location and why. (3) Tasks 4-5 use the 18-keypoint model as a tie-breaker; Scott dismissed that model (Stage 1: 8/20 frames). Drop it or ask Scott. (4) Task 1 and section 5 say the "same 60 frames as Stage 1" are the measurement frames; those 60 were already looked at before later settings were added, so Stage 1b needs a FRESH set of 60, picked before any tuning. (5) Outputs go to .team/shot_detectors/ inside the PUBLIC repo; game frames, overlays and maps must be written OUTSIDE the repo (e.g. C:\Users\scott\Documents\Liberty_Shot_Outputs\), only code and small summaries inside. (6) Task 1.5: "half-court Y measured once on the map" and "std across map frames <= 0.5 ft" contradict; say which. Kept: Scotts stitched-court idea, scoreboard section 4, Golden Rules table, one NEXT_TASK per gate.
2|
3|# Shot Work Order Plan — Makes/Misses First, Then Shooter, Then Other Stats
4|
5|**Author:** Hermes (Architect)  \n**Date:** 2026-10-27  \n**Status:** Plan for Vetted implementation  \n**Gate:** Must pass Vetter review before OpenCode implements  
6|
7|---
8|
9|## 1. Executive Summary & Task Order
10|
11|**Scott's directive (2026-10-27):** The Notus scoreboard reader is **SHELVED, not deleted**. It is not the make/miss detector (it never sees misses, shooter, or location, and only works when the board is on camera). The stronger coder's time goes to the court-line finder and the make/miss detectors. Scott will re-address the scoreboard later for fouls, timeouts, and possessions.
12|
13|**Scott's order of goals:**  
14|1. **Makes/misses 100% accurate**  
15|2. **Shooter identification**  
16|3. **Other stats** (rebounds, assists, steals, turnovers, fouls)
17|
18|**Approach (Scott):** Court lines, stitched map, and pixel-space make/miss detectors at the hoop; find the most reliable in many situations.
19|
20|---
21|
22|## 2. Task Order and Rationale
23|
24|| Order | Task | Why This Order |
25||-------|------|----------------|
26|| 1 | **Court-line detection (Stage 1b)** | Per-frame homography from painted lines is the geometric backbone. Without it, no birdeye, no half-court split, no reliable shot-location or shooter assignment across pans/zooms. Stage 1b plan (spec 08) is already VETTED. |
27|| 1.5 | **Stitched full-court map (per game)** | No single frame shows the whole court. NFHS camera is fixed-location (pan/tilt/zoom only), so frames link via feature matching on floor markings, logos, walls (players ignored). Stitch many frames → one full-court map per game. Court points (lane corners, FT line, arcs, half court, sidelines) marked once on the map. Each frame placed by matching to the map. Per-frame line fit (Stage 1b) stays first where enough lines are visible; the stitched map is the fallback for frames with too few lines, and also the way half-court Y and court length are measured (single measurement on the map, not per-frame). |
28|| 2 | **Pixel-space make/miss detector at the hoop (primary)** | The working rule is `run_saved_v6_rule` in `ai_bridge.py` (line 908). It decides make/miss in **image pixels at the hoop**: grouped hoop (90–110 px wide), crossing = ball above hoop_y then below within 8 samples AND within 0.55 × hoop_w horizontally; column test = stays within 0.6 × hoop_w from 80 px to 180 px below hoop; drift veto = (dist_at_180 − dist_at_80) / hoop_w > 0.40. Court lines (Task 1) and the stitched map (Task 1.5) give **shot location** and **shooter ID** — they do NOT decide make/miss. This task measures the current pixel rule on all tagged shots, then adds a **net-movement / ball-below-rim detector** measured alone in pixels near the hoop to attack the 7 Notus A1 and 12 Adrian missed makes. |
29|| 3 | **Half-court / transition detector (secondary, for LOCATION)** | For frames where court lines are partial (zoomed on lane), use half-court Y (measured at 40.75 ft for Liberty) + key points (lane corners, FT line) to build a minimal homography. Fallback when full court not visible. Output: shot location and shooter aid — NOT make/miss. |
30|| 4 | **Mixture/ensemble gate (make/miss only)** | Combine the pixel-space detectors from Task 2 (primary + net/rim supplement) with a simple rule: if they agree → accept; if they disagree → flag for Scott. Each detector is measured independently first. No keypoint model in the gate (see below). |
31|| 5 | **Shooter identification** | Only after make/miss is 100% on Notus Q1 (31/31) without breaking Adrian (0 misses called makes). Uses court-space player tracks from homography + ball possession at shot moment. |
32|| 6 | **Other stats (rebounds, assists, steals, turnovers, fouls)** | Requires shooter ID + possession + court-space tracks. Scoreboard returns here for fouls/timeouts/possessions (see Section 4). |
33|
34|**Why this order:**  
35|- Court lines (1) are the prerequisite for shot location, half-court split, and shooter assignment.  
36|- **Stitched map (1.5)** consolidates per-frame fits into a single authoritative court per game. It resolves the real-world problem that no frame shows the full court: the NFHS camera pans/tilts/zooms, so we stitch frames by feature-matching floor markings, logos, and walls (ignoring players). The map gives a single half-court Y and court length per game (measured once on the map), and provides fallback placement for frames where (1) fails.  
37|- **Make/miss is pixel-space at the hoop (2)** — `run_saved_v6_rule` proves 0 misses called makes on Adrian. The gap is missed makes (7 Notus A1, 12 Adrian). This task adds a net-movement or ball-below-rim detector measured alone in pixels near the hoop, then combines with the existing rule.  
38|- Half-court (3) is for **location** when full lines are not visible.  
39|- **No 18-keypoint model in the gate** — Scott dismissed it (Stage 1: 8/20 frames with ≥4 floor points on Notus A1). It is dropped from the plan unless Scott explicitly asks for it.  
40|- Mixture (4) is measured *after* each pixel-space detector is measured alone.  
41|- Shooter (5) and other stats (6) are blocked by make/miss accuracy — no point identifying who shot a miss that was called a make.
42|
43|---
44|
45|## 3. Pass Tests and Films for Each Task
46|
47|| Task | Pass Test | Films Used |
48||------|-----------|------------|
49|| **1. Court-line detection (Stage 1b)** | • Adrian: ≥80% frames success, half-court Y measured<br>• Notus A1: ≥70% frames success, half-court Y mean 40.75 ± 2.0 ft, median reprojection error ≤1.5 px<br>• Notus A: ≥70% frames success, half-court Y consistent with Notus A1<br>• Frame-by-frame: on frames where keypoint model got ≥4 floor points, lines method must also succeed; on frames where keypoint model got 0 points, lines method should succeed on ≥50% | Adrian (20 frames), Notus A1 (20 frames), Notus A (20 frames) — **FRESH 60 frames chosen before any tuning** (see §5) |
50|| **1.5. Stitched full-court map (per game)** | • Per game: stitched map built from ≥30 frames spanning full pan/tilt/zoom range<br>• Court points marked once on map (lane corners, FT line, arcs, half court, sidelines)<br>• Frames placed by map: on frames where Stage 1b succeeds, map-placed homography agrees with Stage 1b homography within **1.0 ft** at hoop center and **1.5 ft** at half-court Y (threshold fixed before scoring)<br>• Frames where Stage 1b fails (too few lines): map placement succeeds on ≥70%<br>• **Half-court Y measured once on the map** (single value): Liberty = 40.75 ± 0.5 ft; Adrian = measured value reported<br>• Court length derived from map half-court Y: Liberty 92.0 ± 1.0 ft; Adrian measured | Adrian (full film), Notus A1 (full film), Notus A (full film) — all frames available for stitching |
51|| **2. Pixel-space make/miss at the hoop (primary + supplement)** | **Primary (existing `run_saved_v6_rule`):**<br>• Adrian Q1–Q3 (111 shots): 0 misses called makes, ≤12 makes missed (current: 12)<br>• Notus A1 Q1 (31 shots): 31/31 right, 0 misses called makes<br>• Whole Adrian film (129 shots): 0 misses called makes, no more makes missed than current (16)<br>**Supplement (new net-movement / ball-below-rim detector):**<br>• Measured alone on the same tagged shots: recovers ≥5 of the 7 Notus A1 missed makes and ≥8 of the 12 Adrian Q1–Q3 missed makes, with 0 misses called makes<br>**Combined (Task 4 gate):** Notus A1 Q1 31/31, Adrian 0 misses called makes, ≤12 makes missed<br>`run_saved_v6_rule` prints the three numbers; `applied_to_core` stays false | Adrian full film (129 shots, tagged), Notus A1 Q1 (31 shots, tagged), Notus A (full, tagged when available) |
52|| **3. Half-court / transition detector (location only)** | • On frames where full court lines fail (zoomed on lane): recovers ≥50% of shot locations missed by Stage 1b alone<br>• Half-court Y measured at 40.75 ft (Liberty) on frames with center line visible<br>• 0 misses called makes on Adrian (this detector does not decide make/miss) | Same films as (2); focus on frames where Stage 1b court-line detection fails (partial view) |
53|| **4. Mixture/ensemble gate (make/miss only)** | • Combined detector: Notus A1 Q1 31/31, Adrian 0 misses called makes, ≤12 makes missed<br>• Each pixel-space detector's independent score reported alongside combined score<br>• No component loosens its own thresholds to chase the combined score | All three films; all tagged shots |
54|| **5. Shooter identification** | • On makes where pixel detectors agree: shooter ID matches Scott's tags ≥95%<br>• On misses: possession team matches tag ≥95%<br>• No new false makes introduced | Adrian full, Notus A1 Q1, Notus A (all tagged shots) |
55|| **6. Other stats** | • Rebounds: OREB/DREB from shooter/rebounder shirt color in court space matches tags ≥90%<br>• Assists: last pass before made FG (1-2 dribbles, no FT assists) matches tags ≥90%<br>• Steals/turnovers: defender active takeaway / offense loses ball before shot matches tags ≥90%<br>• Fouls/timeouts/possessions: scoreboard track cross-check (see Section 4) | All three films; scoreboard tracks for Adrian (proven), Notus A1, Notus A (to be built) |
56|
57|---
58|
59|## 4. Where the Scoreboard Comes Back Later
60|
61|**Per Scott (2026-10-27):** The scoreboard reader is shelved for make/miss. It returns **only** for:
62|
63|| Stat | Scoreboard Role | Condition |
64||------|----------------|-----------|
65|| **Fouls** | Scoreboard foul counts per team per period → cross-check with film-detected fouls | When scoreboard is clearly visible (readable foul digits) |
66|| **Timeouts** | Scoreboard timeout indicators (dots/remaining) → mark timeout boundaries in film | When scoreboard is clearly visible |
67|| **Possessions** | Scoreboard possession arrow + score changes → validate possession changes from film | When scoreboard is clearly visible |
68|| **Optional make cross-check** | Scoreboard score rises → confirm birdeye make **only when board is clearly visible** | Never primary; only a sanity check on frames where both exist |
69|
70|**Explicitly NOT used for:**  
71|- Primary make/miss detection (misses never appear on scoreboard)  
72|- Shooter identification (scoreboard has no shooter)  
73|- Shot location (scoreboard has no location)  
74|- Any frame where the board is not on camera or digits are unreadable
75|
76|**Implementation note:** Scoreboard tracks for Notus A1 and Notus A must be built (Adrian track exists and is proven: 43/43 makes, 51-26 final). These tracks are built by `scoreboard_clock.py` → `scripts/build_scoreboard_track.py`. They are consumed only by the fouls/timeouts/possessions module, not by the make/miss detector.
77|
78|---
79|
80|## 5. Golden Rules Respected
81|
82|| Rule | How This Plan Respects It |
83||------|---------------------------|
84|| **No looser cutoffs** | Every detector keeps its own thresholds frozen on calibration frames (60+ seconds away from measurement frames). The mixture gate does not lower any component's threshold; it only combines verdicts. If a component fails its gate, it is reported as failed — not loosened. |
85|| **No banned trials** | Linear interpolation, ByteTrack, DeepSORT, early windows — all CLOSED per `OLLAMA.md` and `DETECTOR_PROPOSAL_REJECTION.md`. This plan uses only: color segmentation + line detection + RANSAC geometric fit (Stage 1b), court-space ball tracking for location, pixel-space make/miss at the hoop (hoop-width and pixel rules), net-movement / ball-below-rim supplement in pixels. None are banned. |
86|| **`applied_to_core` stays false** | All detector experiments live in new files under `.team/stage1b_lines/` and `.team/shot_detectors/`. No changes to `ai_bridge.py`, `event_generator.py`, `net_detector.py`, `manual_tag_teach.py`, `models/ball_detector.pt`, or `ball_confidence`. The core sequence is untouched. |
87|| **Protected files untouched** | `models/ball_detector.pt`, `ball_confidence`, `schema.sql`, feature flags, production detector — none are edited. Candidate weights files (if any) are separate files validated by `validate_ball_weights.py` with the existing gate (Adrian 0 false makes, ≤12 missed; Notus <7 missed). |
88|| **Holdouts never opened** | **The 60 measurement frames for Stage 1b are FRESH:** 20 frames per film (Adrian, Notus A1, Notus A) chosen randomly from the full film BEFORE any tuning or threshold setting. They are distinct from the 60 frames used in Stage 1. Calibration frames are separate (≥60 seconds away). No peeking at measurement frames to tune thresholds. No Scott tags are copied onto AI rows. The tag files in `data/film_tags/` are read-only for scoring. |
89|
90|---
91|
92|## 6. Output Structure
93|
94|**All game frames, overlays, stitched maps, and per-frame JSON go OUTSIDE the repo:**  
95|`C:\Users\scott\Documents\Liberty_Shot_Outputs\`  
96|
97|**Only code and small summaries stay inside the repo:**  
98|```\n.team/shot_detectors/\n├── stage1b_lines/          # Task 1: per-frame court-line detection (already planned in spec 08)\n│   ├── adrian/\n│   │   ├── summary_adrian.json\n│   │   └── (no per-frame overlays or JSON — those go to Liberty_Shot_Outputs)\n│   ├── notus_a1/\n│   │   └── summary_notus_a1.json\n│   ├── notus_a/\n│   │   └── summary_notus_a.json\n│   └── measurement_report.md\n├── stitched_map/           # Task 1.5: per-game stitched full-court map\n│   ├── adrian/\n│   │   ├── summary_adrian.json\n│   │   └── (map image, court_points.json, frame_placements.json → Liberty_Shot_Outputs)\n│   ├── notus_a1/\n│   │   └── summary_notus_a1.json\n│   ├── notus_a/\n│   │   └── summary_notus_a.json\n│   └── crosscheck_vs_stage1b.md    # map-placed vs Stage 1b homography agreement per frame\n├── pixel_miss/             # Task 2: pixel-space make/miss at the hoop\n│   ├── detector.py\n│   ├── config.yaml\n│   ├── net_rim_supplement.py   # new: net-movement / ball-below-rim in pixels\n│   ├── adrian_results.json\n│   ├── notus_a1_q1_results.json\n│   ├── notus_a_results.json\n│   └── summary.md\n├── half_court/             # Task 3: half-court location fallback\n│   ├── detector.py\n│   ├── config.yaml\n│   ├── adrian_results.json\n│   ├── notus_a1_q1_results.json\n│   ├── notus_a_results.json\n│   └── summary.md\n├── ensemble/               # Task 4: mixture gate (make/miss only)\n│   ├── gate.py\n│   ├── combined_results.json\n│   └── summary.md\n└── measurement_report.md   # aggregate across all detectors, all films\n```\n99|
100|---
101|
102|## 7. Next Step
103|
104|This plan goes to `NEXT_TASK.md` **only after** the Vetter stamps it `VETTED`. The first `NEXT_TASK.md` will be **Task 1: Court-line detection (Stage 1b)** — which already has a VETTED plan in `.team/specs/08_stage1b_court_lines_plan.md`. That task is ready for OpenCode to implement.
105|
106|**Task 1.5: Stitched full-court map (per game)** will get its own `NEXT_TASK.md` after Task 1 passes its gate and the Vetter verifies the Stage 1b results. The stitched map consumes Stage 1b per-frame homographies and frame images to build the per-game map.
107|
108|Subsequent tasks (2–6) will each get their own `NEXT_TASK.md` after the previous task passes its gate and the Vetter verifies the results.
109|
110|---
111|
112|**End of Plan** — .team/specs/13_shot_work_order_plan.md