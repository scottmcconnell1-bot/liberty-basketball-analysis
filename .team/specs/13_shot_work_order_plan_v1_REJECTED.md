REJECTED by Claude Code, 2026-10-27 (v1): (1) Task 2 "birdeye make/miss" is geometrically wrong: the court homography maps the FLOOR plane; the ball and rim are 10 ft in the air, so ball-through-rim cannot be decided in court feet. Make/miss stays in image pixels at the hoop (run_saved_v6_rule, ai_bridge.py:908: hoop-width and pixel rules). Birdeye/court lines give shot LOCATION and help SHOOTER id, not make/miss. (2) Because of (1), the plan has no task that attacks the actual make/miss gap: Notus A1 Q1 24/31 (7 makes missed), Adrian 99/111 (12 makes missed). Scotts first goal is makes/misses 100%; the plan must say what fixes those missed makes (e.g. a net-movement or ball-below-rim detector measured alone in pixels near the hoop), or state plainly that court lines come first for location and why. (3) Tasks 4-5 use the 18-keypoint model as a tie-breaker; Scott dismissed that model (Stage 1: 8/20 frames). Drop it or ask Scott. (4) Task 1 and section 5 say the "same 60 frames as Stage 1" are the measurement frames; those 60 were already looked at before later settings were added, so Stage 1b needs a FRESH set of 60, picked before any tuning. (5) Outputs go to .team/shot_detectors/ inside the PUBLIC repo; game frames, overlays and maps must be written OUTSIDE the repo (e.g. C:\Users\scott\Documents\Liberty_Shot_Outputs\), only code and small summaries inside. (6) Task 1.5: "half-court Y measured once on the map" and "std across map frames <= 0.5 ft" contradict; say which. Kept: Scotts stitched-court idea, scoreboard section 4, Golden Rules table, one NEXT_TASK per gate.

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

**Approach (Scott):** Birdeye, half-court points, key points, and a mixture of detectors; find the most reliable in many situations.

---

## 2. Task Order and Rationale

| Order | Task | Why This Order |
|-------|------|----------------|
| 1 | **Court-line detection (Stage 1b)** | Per-frame homography from painted lines is the geometric backbone. Without it, no birdeye, no half-court split, no reliable shot-location or shooter assignment across pans/zooms. Stage 1b plan (spec 08) is already VETTED. |
| 1.5 | **Stitched full-court map (per game)** | No single frame shows the whole court. NFHS camera is fixed-location (pan/tilt/zoom only), so frames link via feature matching on floor markings, logos, walls (players ignored). Stitch many frames → one full-court map per game. Court points (lane corners, FT line, arcs, half court, sidelines) marked once on the map. Each frame placed by matching to the map. Per-frame line fit (Stage 1b) stays first where enough lines are visible; the stitched map is the fallback for frames with too few lines, and also the way half-court Y and court length are measured (single measurement on the map, not per-frame). |
| 2 | **Birdeye make/miss detector (primary)** | Uses per-frame homography to map ball tracks to court-space. Rim-centered coordinates + NFHS geometry = invariant make/miss logic (ball through rim, net movement in court space). Works on all gyms, all camera views. |
| 3 | **Half-court / transition detector (secondary)** | For frames where court lines are partial (zoomed on lane), use half-court Y (measured at 40.75 ft for Liberty) + key points (lane corners, FT line) to build a minimal homography. Fallback when full court not visible. |
| 4 | **Key-point / keypoint-model cross-check (tertiary)** | The existing 18-keypoint model (Stage 1) provides a sanity check on frames where it succeeds (≥4 floor points). Disagreement flags frames for review. Does not replace (2) or (3). |
| 5 | **Mixture/ensemble gate** | Combine (2), (3), (4) with a simple rule: if birdeye and half-court agree → accept; if they disagree → keypoint model breaks tie; if all three disagree → flag for Scott. Measure each detector independently first. |
| 6 | **Shooter identification** | Only after make/miss is 100% on Notus Q1 (31/31) without breaking Adrian (0 misses called makes). Uses court-space player tracks from homography + ball possession at shot moment. |
| 7 | **Other stats (rebounds, assists, steals, turnovers, fouls)** | Requires shooter ID + possession + court-space tracks. Scoreboard returns here for fouls/timeouts/possessions (see Section 4). |

**Why this order:**  
- Court lines (1) are the prerequisite for birdeye (2) and half-court (3).  
- **Stitched map (1.5)** consolidates the per-frame fits from (1) into a single authoritative court per game. It resolves the real-world problem that no frame shows the full court: the NFHS camera pans/tilts/zooms, so we stitch frames by feature-matching floor markings, logos, and walls (ignoring players). The map gives a single half-court Y and court length per game (measured once, not per-frame), and provides fallback placement for frames where (1) fails.  
- Birdeye (2) is the most reliable across gyms/pans/zooms because it uses invariant NFHS geometry, not learned priors.  
- Half-court (3) handles the real-world case where the NFHS camera zooms to the lane and loses the 3-pt arc/center line.  
- Keypoint model (4) is a cross-check, not a primary — Stage 1 proved it fails on these gyms (8/20 frames with ≥4 points on Notus A1).  
- Mixture (5) is measured *after* each component is measured alone, so we know what each contributes.  
- Shooter (6) and other stats (7) are blocked by make/miss accuracy — no point identifying who shot a miss that was called a make.

---

## 3. Pass Tests and Films for Each Task

| Task | Pass Test | Films Used |
|------|-----------|------------|
| **1. Court-line detection (Stage 1b)** | • Adrian: ≥80% frames success, half-court Y measured<br>• Notus A1: ≥70% frames success, half-court Y mean 40.75 ± 2.0 ft, median reprojection error ≤1.5 px<br>• Notus A: ≥70% frames success, half-court Y consistent with Notus A1<br>• Frame-by-frame: on frames where keypoint model got ≥4 floor points, lines method must also succeed; on frames where keypoint model got 0 points, lines method should succeed on ≥50% | Adrian (20 frames), Notus A1 (20 frames), Notus A (20 frames) — **same 60 frames as Stage 1** |
| **1.5. Stitched full-court map (per game)** | • Per game: stitched map built from ≥30 frames spanning full pan/tilt/zoom range<br>• Court points marked once on map (lane corners, FT line, arcs, half court, sidelines)<br>• Frames placed by map: on frames where Stage 1b succeeds, map-placed homography agrees with Stage 1b homography within **1.0 ft** at hoop center and **1.5 ft** at half-court Y (threshold fixed before scoring)<br>• Frames where Stage 1b fails (too few lines): map placement succeeds on ≥70%<br>• Half-court Y measured on map: Liberty = 40.75 ± 0.5 ft; Adrian = measured value reported with std across map frames ≤ 0.5 ft<br>• Court length derived from map half-court Y: Liberty 92.0 ± 1.0 ft; Adrian measured | Adrian (full film), Notus A1 (full film), Notus A (full film) — all frames available for stitching |
| **2. Birdeye make/miss detector** | • Adrian Q1–Q3 (111 shots): 0 misses called makes, ≤12 makes missed (current: 12)<br>• Notus A1 Q1 (31 shots): 31/31 right, 0 misses called makes<br>• Whole Adrian film (129 shots): 0 misses called makes, no more makes missed than current (16)<br>• `run_saved_v6_rule` prints the three numbers; `applied_to_core` stays false | Adrian full film (129 shots, tagged), Notus A1 Q1 (31 shots, tagged), Notus A (full, tagged when available) |
| **3. Half-court / transition detector** | • On frames where full court lines fail (zoomed on lane): recovers ≥50% of makes missed by birdeye alone<br>• 0 misses called makes on Adrian<br>• Half-court Y measured at 40.75 ft (Liberty) on frames with center line visible | Same films as (2); focus on frames where Stage 1b court-line detection fails (partial view) |
| **4. Key-point / keypoint-model cross-check** | • On frames where keypoint model succeeds (≥4 floor points): agreement rate with birdeye ≥90%<br>• On frames where keypoint model fails (0 points): birdeye succeeds on ≥50%<br>• Disagreement frames flagged for Scott review (count reported) | Same 60 frames as Stage 1b; all tagged shots on all three films |
| **5. Mixture/ensemble gate** | • Combined detector: Notus A1 Q1 31/31, Adrian 0 misses called makes, ≤12 makes missed<br>• Each component's independent score reported alongside combined score<br>• No component loosens its own thresholds to chase the combined score | All three films; all tagged shots |
| **6. Shooter identification** | • On makes where birdeye + half-court agree: shooter ID matches Scott's tags ≥95%<br>• On misses: possession team matches tag ≥95%<br>• No new false makes introduced | Adrian full, Notus A1 Q1, Notus A (all tagged shots) |
| **7. Other stats** | • Rebounds: OREB/DREB from shooter/rebounder shirt color in court space matches tags ≥90%<br>• Assists: last pass before made FG (1-2 dribbles, no FT assists) matches tags ≥90%<br>• Steals/turnovers: defender active takeaway / offense loses ball before shot matches tags ≥90%<br>• Fouls/timeouts/possessions: scoreboard track cross-check (see Section 4) | All three films; scoreboard tracks for Adrian (proven), Notus A1, Notus A (to be built) |

---

## 4. Where the Scoreboard Comes Back Later

**Per Scott (2026-10-27):** The scoreboard reader is shelved for make/miss. It returns **only** for:

| Stat | Scoreboard Role | Condition |
|------|----------------|-----------|
| **Fouls** | Scoreboard foul counts per team per period → cross-check with film-detected fouls | When scoreboard is clearly visible (readable foul digits) |
| **Timeouts** | Scoreboard timeout indicators (dots/remaining) → mark timeout boundaries in film | When scoreboard is clearly visible |
| **Possessions** | Scoreboard possession arrow + score changes → validate possession changes from film | When scoreboard is clearly visible |
| **Optional make cross-check** | Scoreboard score rises → confirm birdeye make **only when board is clearly visible** | Never primary; only a sanity check on frames where both exist |

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
| **No banned trials** | Linear interpolation, ByteTrack, DeepSORT, early windows — all CLOSED per `OLLAMA.md` and `DETECTOR_PROPOSAL_REJECTION.md`. This plan uses only: color segmentation + line detection + RANSAC geometric fit (Stage 1b), court-space ball tracking, half-court minimal homography, keypoint model as cross-check. None are banned. |
| **`applied_to_core` stays false** | All detector experiments live in new files under `.team/stage1b_lines/` and `.team/shot_detectors/`. No changes to `ai_bridge.py`, `event_generator.py`, `net_detector.py`, `manual_tag_teach.py`, `models/ball_detector.pt`, or `ball_confidence`. The core sequence is untouched. |
| **Protected files untouched** | `models/ball_detector.pt`, `ball_confidence`, `schema.sql`, feature flags, production detector — none are edited. Candidate weights files (if any) are separate files validated by `validate_ball_weights.py` with the existing gate (Adrian 0 false makes, ≤12 missed; Notus <7 missed). |
| **Holdouts never opened** | The 60 measurement frames (20 per game) are fixed from Stage 1. Calibration frames are separate (≥60 seconds away). No peeking at measurement frames to tune thresholds. No Scott tags are copied onto AI rows. The tag files in `data/film_tags/` are read-only for scoring. |

---

## 6. Output Structure

```
.team/shot_detectors/
├── stage1b_lines/          # Task 1: per-frame court-line detection (already planned in spec 08)
│   ├── adrian/
│   │   ├── frame_0000_overlay.png
│   │   ├── frame_0000.json
│   │   ├── ...
│   │   └── summary_adrian.json
│   ├── notus_a1/
│   │   ├── ...
│   │   └── summary_notus_a1.json
│   ├── notus_a/
│   │   ├── ...
│   │   └── summary_notus_a.json
│   └── measurement_report.md
├── stitched_map/           # Task 1.5: per-game stitched full-court map
│   ├── adrian/
│   │   ├── map_overlay.png         # full-court map with NFHS lines drawn
│   │   ├── court_points.json       # lane corners, FT line, arcs, half court, sidelines (court ft)
│   │   ├── frame_placements.json   # per-frame: frame_idx, H_img2map, placement_error_ft
│   │   ├── half_court_y_ft: 40.75  # single value measured on map
│   │   ├── court_length_ft: 92.0   # derived: 2 * (half_court_y_ft + 5.25)
│   │   └── summary_adrian.json
│   ├── notus_a1/
│   │   ├── ...
│   │   └── summary_notus_a1.json
│   ├── notus_a/
│   │   ├── ...
│   │   └── summary_notus_a.json
│   └── crosscheck_vs_stage1b.md    # map-placed vs Stage 1b homography agreement per frame
├── birdeye/
│   ├── detector.py
│   ├── config.yaml
│   ├── adrian_results.json
│   ├── notus_a1_q1_results.json
│   ├── notus_a_results.json
│   └── summary.md
├── half_court/
│   ├── detector.py
│   ├── config.yaml
│   ├── adrian_results.json
│   ├── notus_a1_q1_results.json
│   ├── notus_a_results.json
│   └── summary.md
├── keypoint_crosscheck/
│   ├── compare.py
│   ├── frame_by_frame_comparison.json
│   └── summary.md
├── ensemble/
│   ├── gate.py
│   ├── combined_results.json
│   └── summary.md
└── measurement_report.md   # aggregate across all detectors, all films
```

---

## 7. Next Step

This plan goes to `NEXT_TASK.md` **only after** the Vetter stamps it `VETTED`. The first `NEXT_TASK.md` will be **Task 1: Court-line detection (Stage 1b)** — which already has a VETTED plan in `.team/specs/08_stage1b_court_lines_plan.md`. That task is ready for OpenCode to implement.

**Task 1.5: Stitched full-court map (per game)** will get its own `NEXT_TASK.md` after Task 1 passes its gate and the Vetter verifies the Stage 1b results. The stitched map consumes Stage 1b per-frame homographies and frame images to build the per-game map.

Subsequent tasks (2–7) will each get their own `NEXT_TASK.md` after the previous task passes its gate and the Vetter verifies the results.

---

**End of Plan** — .team/specs/13_shot_work_order_plan.md