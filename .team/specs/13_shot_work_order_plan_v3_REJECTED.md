REJECTED by Claude Code, 2026-10-27 (v2): v1 reasons 1, 3 (gate), 4, 5, 6 fixed in content, but: (A) FILE FORMAT broken: every line starts with a line number and "|" (copied from the read tool), and 56 places contain a literal "\n" instead of a new line (header, output tree). Rewrite the file as clean Markdown. (B) Reason 2 not fixed: make/miss is Scotts first goal and does not depend on court lines, yet Task 2 still waits behind Tasks 1 and 1.5. Put the pixel make/miss task FIRST (court lines may run after it or alongside), or give a real reason it must wait. (C) Overfitting: the supplement is scored on the same 7 Notus and 12 Adrian missed makes it is built to recover. State BEFORE tuning which tagged shots are used to build it and which are kept unseen to score it (e.g. Adrian Q4 and any Notus A1 shots after Q1, if tagged; check data/film_tags), and score the pass test on the unseen ones. (D) net_moved_after_shot already exists (net_detector.py, protected). Say whether the supplement reuses net_detector.py read-only or is new code, and why new code is needed. (E) Task 2 "primary" pass test requires Notus 31/31 from run_saved_v6_rule, which is known to score 24/31: make it a baseline MEASUREMENT, not a pass test. (F) Leftovers: Task 1 pass test still compares to "frames where keypoint model got >=4 floor points" (the keypoint model is dropped, and the fresh frames have no keypoint results); section 4 still says "confirm birdeye make". Previous stamp: REJECTED by Claude Code, 2026-10-27 (v1): (1) Task 2 "birdeye make/miss" is geometrically wrong: the court homography maps the FLOOR plane; the ball and rim are 10 ft in the air, so ball-through-rim cannot be decided in court feet. Make/miss stays in image pixels at the hoop (run_saved_v6_rule, ai_bridge.py:908: hoop-width and pixel rules). Birdeye/court lines give shot LOCATION and help SHOOTER id, not make/miss. (2) Because of (1), the plan has no task that attacks the actual make/miss gap: Notus A1 Q1 24/31 (7 make...

# Shot Work Order Plan — Makes/Misses First, Then Shooter, Then Other Stats

**Author:** Hermes (Architect)  
**Date:** 2026-10-27  
**Status:** Plan for Vetted implementation  
**Gate:** Must pass Vetter review before OpenCode implements  

---

## 1. Executive Summary & Task Order

**Scott's directive (2026-10-27):** The Notus scoreboard reader is **SHELVED, not deleted**. It is not the make/miss detector (it never sees misses, shooter, or location, and only works when the board is on camera). The stronger coder's time goes to the court-line finder and the make/miss detectors. Scott will re-address the scoreboard later for fouls, timeouts, and possessions.

**Scott's order of goals:**  
1. **Makes/misses 100% accurate**  
2. **Shooter identification**  
3. **Other stats** (rebounds, assists, steals, turnovers, fouls)

**Approach (Scott):** Court lines, stitched map, and pixel-space make/miss detectors at the hoop; find the most reliable in many situations.

---

## 2. Task Order and Rationale

| Order | Task | Why This Order |
|-------|------|----------------|
| 1 | **Pixel-space make/miss detector at the hoop (primary + supplement)** | The working rule is `run_saved_v6_rule` in `ai_bridge.py` (line 908). It decides make/miss in **image pixels at the hoop**: grouped hoop (90–110 px wide), crossing = ball above hoop_y then below within 8 samples AND within 0.55 × hoop_w horizontally; column test = stays within 0.6 × hoop_w from 80 px to 180 px below hoop; drift veto = (dist_at_180 − dist_at_80) / hoop_w > 0.40. Court lines and stitched map give **shot location** and **shooter ID** — they do NOT decide make/miss. This task measures the current pixel rule on all tagged shots as a BASELINE, then adds a **net-movement / ball-below-rim detector** measured alone in pixels near the hoop to attack the 7 Notus A1 and 12 Adrian missed makes. Court-line detection (Task 2) and stitched map (Task 3) may run after or alongside — make/miss does not depend on them. |
| 2 | **Court-line detection (Stage 1b)** | Per-frame homography from painted lines is the geometric backbone for shot location, half-court split, and shooter assignment across pans/zooms. Stage 1b plan (spec 08) is already VETTED. |
| 3 | **Stitched full-court map (per game)** | No single frame shows the whole court. NFHS camera is fixed-location (pan/tilt/zoom only), so frames link via feature matching on floor markings, logos, walls (players ignored). Stitch many frames → one full-court map per game. Court points (lane corners, FT line, arcs, half court, sidelines) marked once on the map. Each frame placed by matching to the map. Per-frame line fit (Task 2) stays first where enough lines are visible; the stitched map is the fallback for frames with too few lines, and also the way half-court Y and court length are measured (single measurement on the map, not per-frame). |
| 4 | **Half-court / transition detector (location only)** | For frames where court lines are partial (zoomed on lane), use half-court Y (measured at 40.75 ft for Liberty) + key points (lane corners, FT line) to build a minimal homography. Fallback when full court not visible. Output: shot location and shooter aid — NOT make/miss. |
| 5 | **Mixture/ensemble gate (make/miss only)** | Combine the pixel-space detectors from Task 1 (primary + net/rim supplement) with a simple rule: if they agree → accept; if they disagree → flag for Scott. Each detector is measured independently first. No keypoint model in the gate. |
| 6 | **Shooter identification** | Only after make/miss is 100% on Notus Q1 (31/31) without breaking Adrian (0 misses called makes). Uses court-space player tracks from homography + ball possession at shot moment. |
| 7 | **Other stats (rebounds, assists, steals, turnovers, fouls)** | Requires shooter ID + possession + court-space tracks. Scoreboard returns here for fouls/timeouts/possessions (see Section 4). |

**Why this order:**  
- **Make/miss is pixel-space at the hoop (Task 1)** — `run_saved_v6_rule` proves 0 misses called makes on Adrian. The gap is missed makes (7 Notus A1 Q1, 12 Adrian Q1–Q3). This task adds a net-movement or ball-below-rim detector measured alone in pixels near the hoop, then combines with the existing rule.  
- Court lines (Task 2) are the prerequisite for shot location, half-court split, and shooter assignment.  
- **Stitched map (Task 3)** consolidates per-frame fits into a single authoritative court per game. It resolves the real-world problem that no frame shows the full court: the NFHS camera pans/tilts/zooms, so we stitch frames by feature-matching floor markings, logos, and walls (ignoring players). The map gives a single half-court Y and court length per game (measured once on the map), and provides fallback placement for frames where Task 2 fails.  
- Half-court (Task 4) is for **location** when full lines are not visible.  
- **No 18-keypoint model in the gate** — Scott dismissed it (Stage 1: 8/20 frames with ≥4 floor points on Notus A1). It is dropped from the plan unless Scott explicitly asks for it.  
- Mixture (Task 5) is measured *after* each pixel-space detector is measured alone.  
- Shooter (Task 6) and other stats (Task 7) are blocked by make/miss accuracy — no point identifying who shot a miss that was called a make.

---

## 3. Pass Tests and Films for Each Task

| Task | Pass Test | Films Used |
|------|-----------|------------|
| **1. Pixel-space make/miss at the hoop (primary + supplement)** | **Primary (existing `run_saved_v6_rule`) — BASELINE MEASUREMENT:**<br>• Adrian Q1–Q3 (111 shots): 0 misses called makes, ≤12 makes missed (current: 12)<br>• Notus A1 Q1 (31 shots): reports current score (known: 24/31), 0 misses called makes<br>• Whole Adrian film (129 shots): 0 misses called makes, no more makes missed than current (16)<br><br>**Supplement (new net-movement / ball-below-rim detector):**<br>• **Build set (tagged, used for tuning):** Notus A1 Q1 (31 shots, all tagged) + Adrian Q1–Q3 (tagged shots, 111 total). These are the shots the supplement is designed to recover.<br>• **Unseen test set (tagged, held out):** Adrian Q4–end (tagged shots after Q3). Notus A1 has no shots after Q1 in the tag file, so no unseen Notus set exists.<br>• Measured alone on **unseen** Adrian Q4+ shots: recovers ≥50% of missed makes in that quarter, with 0 misses called makes.<br><br>**Combined (Task 5 gate):** Notus A1 Q1 31/31, Adrian 0 misses called makes, ≤12 makes missed<br>`run_saved_v6_rule` prints the three numbers; `applied_to_core` stays false | Adrian full film (129 shots, tagged Q1–end), Notus A1 Q1 (31 shots, tagged), Notus A (full, tagged when available) |
| **2. Court-line detection (Stage 1b)** | • Adrian: ≥80% frames success, half-court Y measured<br>• Notus A1: ≥70% frames success, half-court Y mean 40.75 ± 2.0 ft, median reprojection error ≤1.5 px<br>• Notus A: ≥70% frames success, half-court Y consistent with Notus A1<br>• Frame-by-frame: on frames where Stage 1b succeeds, record half-court Y; on frames where it fails, note failure reason | Adrian (20 frames), Notus A1 (20 frames), Notus A (20 frames) — **FRESH 60 frames chosen before any tuning** (see §5) |
| **3. Stitched full-court map (per game)** | • Per game: stitched map built from ≥30 frames spanning full pan/tilt/zoom range<br>• Court points marked once on map (lane corners, FT line, arcs, half court, sidelines)<br>• Frames placed by map: on frames where Stage 1b succeeds, map-placed homography agrees with Stage 1b homography within **1.0 ft** at hoop center and **1.5 ft** at half-court Y (threshold fixed before scoring)<br>• Frames where Stage 1b fails (too few lines): map placement succeeds on ≥70%<br>• **Half-court Y measured once on the map** (single value): Liberty = 40.75 ± 0.5 ft; Adrian = measured value reported<br>• Court length derived from map half-court Y: Liberty 92.0 ± 1.0 ft; Adrian measured | Adrian (full film), Notus A1 (full film), Notus A (full film) — all frames available for stitching |
| **4. Half-court / transition detector (location only)** | • On frames where full court lines fail (zoomed on lane): recovers ≥50% of shot locations missed by Stage 1b alone<br>• Half-court Y measured at 40.75 ft (Liberty) on frames with center line visible<br>• 0 misses called makes on Adrian (this detector does not decide make/miss) | Same films as Task 1; focus on frames where Stage 1b court-line detection fails (partial view) |
| **5. Mixture/ensemble gate (make/miss only)** | • Combined detector: Notus A1 Q1 31/31, Adrian 0 misses called makes, ≤12 makes missed<br>• Each pixel-space detector's independent score reported alongside combined score<br>• No component loosens its own thresholds to chase the combined score | All three films; all tagged shots |
| **6. Shooter identification** | • On makes where pixel detectors agree: shooter ID matches Scott's tags ≥95%<br>• On misses: possession team matches tag ≥95%<br>• No new false makes introduced | Adrian full, Notus A1 Q1, Notus A (all tagged shots) |
| **7. Other stats** | • Rebounds: OREB/DREB from shooter/rebounder shirt color in court space matches tags ≥90%<br>• Assists: last pass before made FG (1-2 dribbles, no FT assists) matches tags ≥90%<br>• Steals/turnovers: defender active takeaway / offense loses ball before shot matches tags ≥90%<br>• Fouls/timeouts/possessions: scoreboard track cross-check (see Section 4) | All three films; scoreboard tracks for Adrian (proven), Notus A1, Notus A (to be built) |

---

## 4. Where the Scoreboard Comes Back Later

**Per Scott (2026-10-27):** The scoreboard reader is shelved for make/miss. It returns **only** for:

| Stat | Scoreboard Role | Condition |
|------|----------------|-----------|
| **Fouls** | Scoreboard foul counts per team per period → cross-check with film-detected fouls | When scoreboard is clearly visible (readable foul digits) |
| **Timeouts** | Scoreboard timeout indicators (dots/remaining) → mark timeout boundaries in film | When scoreboard is clearly visible |
| **Possessions** | Scoreboard possession arrow + score changes → validate possession changes from film | When scoreboard is clearly visible |
| **Optional make cross-check** | Scoreboard score rises → confirm make **only when board is clearly visible** | Never primary; only a sanity check on frames where both exist |

**Explicitly NOT used for:**  
- Primary make/miss detection (misses never appear on scoreboard)  
- Shooter identification (scoreboard has no shooter)  
- Shot location (scoreboard has no location)  
- Any frame where the board is not on camera or digits are unreadable

**Implementation note:** Scoreboard tracks for Notus A1 and Notus A must be built (Adrian track exists and is proven: 43/43 makes, 51-26 final). These tracks are built by `scoreboard_clock.py` → `scripts/build_scoreboard_track.py`. They are consumed only by the fouls/timeouts/possessions module, not by the make/miss detector.

---

## 5. Golden Rules Respected

| Rule | How This Plan Respects It |
|------|---------------------------|
| **No looser cutoffs** | Every detector keeps its own thresholds frozen on calibration frames (60+ seconds away from measurement frames). The mixture gate does not lower any component's threshold; it only combines verdicts. If a component fails its gate, it is reported as failed — not loosened. |
| **No banned trials** | Linear interpolation, ByteTrack, DeepSORT, early windows — all CLOSED per `OLLAMA.md` and `DETECTOR_PROPOSAL_REJECTION.md`. This plan uses only: color segmentation + line detection + RANSAC geometric fit (Stage 1b), court-space ball tracking for location, pixel-space make/miss at the hoop (hoop-width and pixel rules), net-movement / ball-below-rim supplement in pixels. None are banned. |
| **`applied_to_core` stays false** | All detector experiments live in new files under `.team/stage1b_lines/` and `.team/shot_detectors/`. No changes to `ai_bridge.py`, `event_generator.py`, `net_detector.py`, `manual_tag_teach.py`, `models/ball_detector.pt`, or `ball_confidence`. The core sequence is untouched. |
| **Protected files untouched** | `models/ball_detector.pt`, `ball_confidence`, `schema.sql`, feature flags, production detector — none are edited. Candidate weights files (if any) are separate files validated by `validate_ball_weights.py` with the existing gate (Adrian 0 false makes, ≤12 missed; Notus <7 missed). |
| **Holdouts never opened** | **The 60 measurement frames for Stage 1b are FRESH:** 20 frames per film (Adrian, Notus A1, Notus A) chosen randomly from the full film BEFORE any tuning or threshold setting. They are distinct from the 60 frames used in Stage 1. Calibration frames are separate (≥60 seconds away). No peeking at measurement frames to tune thresholds. No Scott tags are copied onto AI rows. The tag files in `data/film_tags/` are read-only for scoring. |

---

## 6. Net Detector Reuse Decision

The supplement in Task 1 uses **new code** (`net_rim_supplement.py`), not `net_detector.py` read-only.  
**Reason:** `net_detector.py` (`net_moved_after_shot`) was designed for a different signal (full-net motion over a window) and is protected — it cannot be modified. The supplement needs a lightweight, hoop-local detector: ball-below-rim in the column (80–180 px below hoop) and net-pixel displacement in a tight ROI around the rim, both measured in the same pixel space as `run_saved_v6_rule`. Reusing `net_detector.py` would require changing its thresholds or input window, which violates the protected-file rule. A new, focused module keeps the existing net detector intact and lets the supplement evolve independently.

---

## 7. Output Structure

**All game frames, overlays, stitched maps, and per-frame JSON go OUTSIDE the repo:**  
`C:\Users\scott\Documents\Liberty_Shot_Outputs\`

**Only code and small summaries stay inside the repo:**
```
.team/shot_detectors/
├── pixel_miss/             # Task 1: pixel-space make/miss at the hoop
│   ├── detector.py
│   ├── config.yaml
│   ├── net_rim_supplement.py   # new: net-movement / ball-below-rim in pixels
│   ├── adrian_results.json
│   ├── notus_a1_q1_results.json
│   ├── notus_a_results.json
│   └── summary.md
├── stage1b_lines/          # Task 2: per-frame court-line detection (already planned in spec 08)
│   ├── adrian/
│   │   ├── summary_adrian.json
│   │   └── (no per-frame overlays or JSON — those go to Liberty_Shot_Outputs)
│   ├── notus_a1/
│   │   └── summary_notus_a1.json
│   ├── notus_a/
│   │   └── summary_notus_a.json
│   └── measurement_report.md
├── stitched_map/           # Task 3: per-game stitched full-court map
│   ├── adrian/
│   │   ├── summary_adrian.json
│   │   └── (map image, court_points.json, frame_placements.json → Liberty_Shot_Outputs)
│   ├── notus_a1/
│   │   └── summary_notus_a1.json
│   ├── notus_a/
│   │   └── summary_notus_a.json
│   └── crosscheck_vs_stage1b.md    # map-placed vs Stage 1b homography agreement per frame
├── half_court/             # Task 4: half-court location fallback
│   ├── detector.py
│   ├── config.yaml
│   ├── adrian_results.json
│   ├── notus_a1_q1_results.json
│   ├── notus_a_results.json
│   └── summary.md
├── ensemble/               # Task 5: mixture gate (make/miss only)
│   ├── gate.py
│   ├── combined_results.json
│   └── summary.md
└── measurement_report.md   # aggregate across all detectors, all films
```

---

## 8. Next Step

This plan goes to `NEXT_TASK.md` **only after** the Vetter stamps it `VETTED`. The first `NEXT_TASK.md` will be **Task 1: Pixel-space make/miss at the hoop (primary + supplement)** — court lines and stitched map run after or alongside.

**Task 2: Court-line detection (Stage 1b)** already has a VETTED plan in `.team/specs/08_stage1b_court_lines_plan.md`. That task is ready for OpenCode to implement once Task 1 passes its gate.

**Task 3: Stitched full-court map (per game)** will get its own `NEXT_TASK.md` after Task 2 passes its gate and the Vetter verifies the Stage 1b results. The stitched map consumes Stage 1b per-frame homographies and frame images to build the per-game map.

Subsequent tasks (4–7) will each get their own `NEXT_TASK.md` after the previous task passes its gate and the Vetter verifies the results.

---

**End of Plan** — .team/specs/13_shot_work_order_plan.md
