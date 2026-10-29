# Reliable Detector Architecture
## Per-Frame Court Geometry, Independent Make/Miss Signals, and Untagged Shot Detection

**Author:** Hermes (Architect)  
**Date:** 2026-10-26  
**Status:** Proposal for Vetted plan  
**Gate:** Must pass Claude Code vet before OpenCode implements

---

## 1. Per-Frame Court Geometry

### 1.1 Problem
The NFHS camera pans and zooms. A single four-point calibration (`manual_calibration.json`) describes one camera position only. The homography from it is correct only on frames where the camera points the same way (ACTIVE.md: "no frame shows both the lane corners and the half-court line" in Notus A1). The current pipeline applies one calibration to the whole game. This breaks make/miss logic on Notus because `hoop_x`, `hoop_y`, `hoop_w` in image pixels are not comparable across gyms or across camera views within a game (BIRDS_EYE_HOMOGRAPHY_DESIGN.md §1).

### 1.2 Solution: Rebuild Homography Every Frame (or Every Few Frames)
Use the YOLO pose model at `models/court_keypoint_detector.pt` (18 court keypoints per frame; run_v8.py lines 22, 71-73) to detect floor-plane keypoints on every frame. From the detected keypoints, select the floor-plane subset (lane corners, free-throw line corners, baseline corners, sideline intersections — all Z=0 per BIRDS_EYE_HOMOGRAPHY_DESIGN.md §3.1) and compute a homography H_img2court mapping image pixels → court feet (origin = basket center, +Y toward midcourt).

**Keypoint indices from run_v8.py:** The model outputs 18 keypoints. The floor-plane subset corresponds to:
- Free-throw line left/right (lane corners at FT line): NFHS court coords (-6, +15), (+6, +15)
- Lane baseline left/right (lane corners at baseline): (-6, -4), (+6, -4)
- Baseline left/right (sideline ∩ baseline): (-25, -4), (+25, -4)
- Sideline at FT line: (-25, +15), (+25, +15)
- 3-pt arc ∩ sideline (optional, harder): approx (±22, +11.5)

Only floor-plane points (Z=0) enter the homography. Rim, backboard, and any 3D points are EXCLUDED (BIRDS_EYE_HOMOGRAPHY_DESIGN.md §3.2).

**Algorithm per frame:**
1. Run `court_keypoint_detector.pt` on frame → 18 keypoints with confidences
2. Filter keypoints with confidence ≥ 0.3 (run_v8.py uses 0.3 at line 71)
3. Map detected keypoint indices to their known NFHS floor coordinates (LANE_COURT_XY in pick_court_points.py lines 25-30; BIRDS_EYE_HOMOGRAPHY_DESIGN.md Table 3.1)
4. If ≥ 4 non-collinear floor points detected: compute H via `cv2.findHomography` with RANSAC (reprojection error ≤ 2 px; court_homography.py line 30)
5. If < 4 floor points or RANSAC inliers < 4: mark frame as **bad**, reuse last good H (with a max age of 5 frames), or fall back to pixel-space rules

### 1.3 Half Court and Lane — Automatic, No Manual Clicks
- **Lane:** The four lane corners (FT line ±6 ft, baseline ±6 ft) are the same in every NFHS gym. They come directly from the keypoint model's detections of the free-throw line and lane lines. No manual calibration needed.
- **Half court:** The keypoint model also detects the center-line keypoints. Project them through the per-frame H → court Y coordinate. The mean Y is the measured half-court distance from the hoop. This gives the gym's actual court length automatically (ai_bridge.py `half_court_y_from_image_points` lines 1491-1512). Liberty's gym is 92 ft (half court 40.75 ft from hoop; ACTIVE.md and ai_bridge.py GYM_COURT_LENGTH_FT). Notus A1 was played at Liberty.
- **Bad-frame detection:** A frame is bad if:
  - < 4 floor keypoints detected above confidence threshold
  - RANSAC inlier count < 4
  - Reprojection error > 2 px RMS
  - Homography condition number > 1e4 (near-degenerate)
  - Projected half-court Y falls outside plausible band [28, 46] ft (ai_bridge.py HALF_COURT_Y_MIN_FT/MAX_FT)

When a frame is bad, hold the last good homography for up to 5 frames. If > 5 consecutive bad frames, fall back to pixel-space rules for those frames (preserving Adrian 0-false-make guarantee).

### 1.4 Directional Scale Factors at Hoop (Critical for Threshold Conversion)
Per court_homography.py lines 50-65 and HOMOGRAPHY_INTEGRATION_PLAN.md §2.3: compute independent `scale_x` (ft/px horizontal) and `scale_y` (ft/px vertical) at the hoop's image position via Jacobian of H. All vertical pixel thresholds (80, 180, 200, 50, 100, 150, 20, 10, 40, 70) multiply by `scale_y`. All horizontal Euclidean distances (60 px jump, 100 px spatial gap, 12 px/frame velocity) multiply by geometric mean `√(scale_x × scale_y)`. Ratios (0.55, 0.6, 0.43, 0.40, 0.70, 0.85, 0.95, 0.5, 0.65, 1.0, 0.15, 0.20) are unitless and UNCHANGED (HOMOGRAPHY_INTEGRATION_PLAN.md §2.1, §2.5).

---

## 2. Independent Make/Miss Signals and Combination

### 2.1 Four Independent Signals

| Signal | Source | What It Detects | Current Status |
|--------|--------|-----------------|----------------|
| **S1: Scoreboard score change** | `scoreboard_clock.py` (proven 43/43 on Adrian, ACTIVE.md §5) | A team's score rises → made basket; value = rise (1, 2, or 3). Rule: new value holds for 3 one-second samples. | **Proven reliable.** 43 made baskets found, all 43 tagged makes matched within 25 s, 0 rises with no tag. Final score 51-26 matches scorebook. |
| **S2: Ball through rim** | `court_memory.py` `ball_through_rim` (core) + `run_saved_v6_rule` in `ai_bridge.py` | Ball track crosses grouped hoop (90-110 px wide) going down, stays in column (0.6 ratio) to 180 px, no drift > 0.43 hoop-widths, no bounce up. | **Proven on Adrian:** 99/111 right, 12 makes missed, 0 misses called makes (ACTIVE.md). Fails on Notus Q1: 24/31, 7 makes missed (OLLAMA.md). |
| **S3: Net motion** | `net_detector.py` `net_moved_after_shot` | Samples net ROI just before ball arrival and 6/10/16 frames after. True if net motion > 0.045 AND net motion > side ROI motion + 0.02 (camera pan rejection). | **Independent visual confirmation.** Works on swishes with no ball box in net. Not yet scored against tags. |
| **S4: Ball path in court coordinates** | New: per-frame homography + ball track transformed to court feet | Ball trajectory in court space: approaches rim from above, crosses rim plane (y=0) at x within rim radius (9 in = 0.75 ft), continues downward to net depth (~1.5 ft below rim). | **New.** Removes perspective distortion. Thresholds become constant in feet (e.g., rim radius = 0.75 ft, net depth = 1.5 ft). |

### 2.2 Combination Logic — Never Guess, Flag Disagreements

```
For each shot attempt (detected by S2 or S4):
  s1 = scoreboard shows a rise for the shooting team within 25 s?  (S1)
  s2 = ball_through_rim returns True?                              (S2)
  s3 = net_moved_after_shot returns True?                          (S3)
  s4 = court-space ball path crosses rim plane downward?           (S4)

  votes = sum([s1, s2, s3, s4])
  agree = votes >= 3
  disagree = votes == 2

  if agree:
      call = make if votes >= 3 else miss
  else:  # 2-2 split or 1-3 with one unreliable
      FLAG FOR SCOTT'S REVIEW
      record: {tag_ts, signals: {s1,s2,s3,s4}, reason: "split_vote"}

  # Reliability weighting (measured per game):
  # S1 weight = 1.0 (proven 43/43 on Adrian)
  # S2 weight = Adrian_track_record (99/111) / 111 = 0.89
  # S3 weight = TBD (measure on Adrian tags)
  # S4 weight = TBD (measure on Adrian tags after homography)
```

**Disagreement handling:** Any 2-2 split or case where S1 (scoreboard) disagrees with majority → **flag for Scott's review**. Never guess. The flagged set is the review queue.

**Reliability measurement per signal per game:**
- Run each signal independently against Scott's tags on that game
- Record: TP, FP, FN, TN
- S1 is the ground-truth anchor (scorebook-verified)
- S2, S3, S4 reliability = (TP + TN) / total on that game
- If a signal's reliability drops below 0.80 on a new gym, down-weight it and flag more aggressively

---

## 3. Shot Attempts and the Shooter Without Tags

### 3.1 Shot Attempt Detection (No Score Change = Miss)
- Scoreboard (S1) gives makes with team and points.
- Video must find **all shot attempts** (makes + misses).
- A shot attempt = ball leaves a player toward the rim (upward then downward trajectory crossing rim plane).
- Detection: track ball in court coordinates (S4). A shot attempt is a ball track that:
  1. Starts in a player's possession (ball within 3 ft of player centroid, moving with player)
  2. Leaves player upward (positive court Y velocity toward midcourt + upward Z component inferred from image Y decreasing)
  3. Crosses rim plane (court Y ≈ 0, court X within ±0.75 ft) going downward
  4. Ends below rim (court Y < -1 ft) or is rebounded

Every attempt with no matching S1 score rise within 25 s = **miss**. Every S1 rise with no matching attempt = **flag** (should not happen; S1 is 43/43).

### 3.2 Shooter Identification
- At shot attempt start frame: ball is with a player.
- Use `BasketballStatsAdapter.synchronize_tracker_ids` (ai_bridge.py lines 173-228) for stable tracker IDs across occlusions (HOG + spatial proximity).
- The player whose tracker ID is closest to ball at release frame = shooter.
- **Team:** Jersey color clustering (Liberty vs opponent) on the shooter's detection crops. Liberty wears light, opponents dark (or vice versa per game). Cluster HSV hue/saturation of torso region.
- **Jersey number:** OCR on the shooter's detection crop at release frame. `detection.jersey_read` / `jersey_confidence` in ai_bridge.py DetectionData (lines 36-38). If OCR confidence < 0.7, leave jersey unknown — do not guess.

### 3.3 Output per Shot Attempt
```json
{
  "timestamp_ms": 123456,
  "court_x_ft": -1.2,
  "court_y_ft": 0.0,
  "is_make": true,
  "make_signals": {"scoreboard": true, "ball_through_rim": true, "net_motion": true, "court_path": true},
  "shooter": {"tracker_id": 7, "team": "liberty", "jersey": "22", "jersey_conf": 0.85},
  "shot_type": "2pt",  // from court zone at release: paint/perimeter/three
  "points": 2,
  "flagged_for_review": false
}
```

---

## 4. Staged Order of Small, Testable Tasks

### Stage 1: Measure Court Keypoint Model (MUST COMPLETE FIRST)
**Goal:** Quantify the 18-keypoint model on ~20 frames spread across each game (Adrian, Notus A1, Notus A). Save overlay crops for Vetter to check by eye.

**Tasks:**
1. Extract ~20 frames per game: uniformly spaced (e.g., every 3000 frames ≈ every 2 min at 25 fps), plus key moments (free throws, transitions, zoomed-in, zoomed-out).
2. Run `court_keypoint_detector.pt` on each frame.
3. For each frame, save:
   - Original frame with 18 keypoints drawn (color-coded by confidence: green ≥0.5, yellow 0.3-0.5, red <0.3)
   - JSON: `{frame_idx, timestamp_ms, keypoints: [{id, name, x, y, conf}, ...], floor_points_detected: N, H_computed: bool, H_inliers: int, reproj_error_px: float, half_court_y_ft: float}`
4. Aggregate per game:
   - % frames with ≥4 floor points
   - % frames with valid H (inliers ≥4, reproj ≤2 px)
   - Mean/median reprojection error
   - Half-court Y measurements: mean, std, min, max
   - Which of the 18 keypoints are detected how often (frequency table)

**Deliverable:** `.team/specs/stage1_keypoint_measurement/` with overlay crops and `measurement_report.md`.

**Pass Gate for Stage 2:**
- Adrian: ≥ 80% frames valid H, half-court Y in [38, 44] ft (Liberty 92 ft → 40.75 ft)
- Notus A1: ≥ 70% frames valid H (different camera angles), half-court Y consistent with Liberty gym
- At least 10 of 18 keypoints detected ≥ 60% of frames

### Stage 2: Per-Frame Homography Pipeline
**Goal:** Integrate per-frame H into `run_saved_v6_rule` via `court_homography.py` (vetted, frozen).

**Tasks:**
1. Add `build_per_frame_homographies(video_path, keypoint_model)` → list of (frame_idx, H_or_None, hoop_img_xy, scale_x, scale_y, half_court_y_ft)
2. Modify `run_saved_v6_rule` to accept optional per-frame homography list (HOMOGRAPHY_INTEGRATION_PLAN.md §3-§7)
3. Transform tracks to court space per frame using per-track hoop position for scale (court_homography.py `apply_homography_to_tracks`)
4. Run identity test: H=I on Adrian → exact dict equality + score 99/111/0 (HOMOGRAPHY_INTEGRATION_PLAN.md §8)

**Pass Gate:**
- Adrian identity test: exact equality on all track keys + score 99 right, 12 makes missed, 0 misses called makes
- Notus Q1 in court space: > 24 right, 0 false makes, ≤ 6 makes missed (BIRDS_EYE_HOMOGRAPHY_DESIGN.md §7.1)

### Stage 3: Independent Signal Scoring
**Goal:** Measure S2, S3, S4 independently on Adrian tags.

**Tasks:**
1. Score S2 (`ball_through_rim` via `run_saved_v6_rule`) — already known: 99/111, 12 missed, 0 false
2. Score S3 (`net_moved_after_shot`) on all 111 Adrian tags
3. Score S4 (court-space ball path) on all 111 Adrian tags using Stage 2 homographies
4. Build 2×2 agreement tables for each pair (S1 vs S2, S1 vs S3, S1 vs S4, S2 vs S3, etc.)

**Pass Gate:**
- S3 reliability ≥ 0.85 on Adrian
- S4 reliability ≥ 0.85 on Adrian
- S1-S2-S3-S4 4-way agreement on ≥ 90 of 111 Adrian tags

### Stage 4: Notus Q1 Validation
**Goal:** Confirm the full pipeline on Notus Q1 against scorebook.

**Tasks:**
1. Build scoreboard track for Notus A1 (ACTIVE.md §5 step 1)
2. Run full pipeline (Stages 1-3) on Notus Q1
3. Compare makes from S1 (scoreboard) vs video-detected attempts (S2+S3+S4)
4. Score shooter identification on the 31 Notus Q1 tags (player + team + jersey)

**Pass Gate (TEAM_RECOVERY.md §1):**
- Notus A1 Q1: 31 of 31 right (make/miss)
- Adrian: 0 misses called makes, no more makes missed than today (12)

### Stage 5: Shooter Identification Structure
**Goal:** Hermes structures how to identify the shooter (ACTIVE.md §5 step 2).

**Tasks:**
1. Stable tracker IDs across game (ai_bridge.py `synchronize_tracker_ids`)
2. Jersey color clustering for team
3. OCR for jersey number at release frame
4. Output schema as in §3.3

---

## 5. Risks and Proof Criteria

| Risk | Likelihood | Impact | Mitigation | Proof of Stage Success (Measured Numbers) |
|------|------------|--------|------------|------------------------------------------|
| **Keypoint model misses floor points on zoomed-in frames** | High | High | Fallback to last good H (max 5 frames); pixel-space fallback after that | Stage 1: ≥ 70% frames valid H on Notus; ≤ 5 consecutive bad frames |
| **Homography jitter frame-to-frame** | Medium | Medium | Temporal smoothing: median H over 3-frame window; reject if condition number spikes | Stage 2: Homography translation < 0.5 ft, rotation < 0.5° between adjacent good frames |
| **Scale factors wrong at hoop (perspective varies across court)** | Medium | High | Use local scale at hoop only (court_homography.py); all rules operate at hoop | Stage 2: Identity test passes exact float equality on all track keys |
| **S3 (net motion) false positives on camera pan** | Medium | Medium | Side ROI subtraction (net_detector.py line 511: `net >= beside + 0.02`) | Stage 3: S3 FP rate ≤ 5% on Adrian non-shot frames |
| **S4 (court path) fails when ball track has gaps** | High | High | Interpolate gaps ≤ 15 frames in court space (not pixel space) | Stage 3: S4 recall ≥ 85% on Adrian makes |
| **Shooter ID wrong on crossing/occlusion** | High | Medium | Tracker ID stability (HOG + spatial); flag low-confidence jerseys | Stage 5: Shooter tracker ID matches tagged shooter on ≥ 80% of Adrian tagged shots |
| **Notus court-space ≤ pixel-space** | Medium | Medium | Abandon court-space for Notus; pixel baseline remains | Stage 4: Notus Q1 court-space > 24 right, 0 false makes |
| **Adrian regression** | Low | Critical | Identity test enforces exact equality; Adrian never transformed in production | Stage 2: Identity test passes every run; baseline anchor test (99/111/0) runs in CI |

### Measured Numbers That Prove Each Stage Worked

**Stage 1 (Keypoint Measurement):**
- Adrian: 20 frames → ≥ 16 valid H (80%), half_court_y_ft mean 40.75 ± 2.0, reproj error median ≤ 1.5 px
- Notus A1: 20 frames → ≥ 14 valid H (70%), half_court_y_ft consistent with Liberty gym
- Notus A: 20 frames → ≥ 14 valid H (70%)
- Keypoint detection frequency table: ≥ 10 keypoints detected ≥ 60% of frames

**Stage 2 (Per-Frame Homography + Court-Space Rules):**
- Adrian identity test: PASS (exact dict equality on all 111 tracks + score 99/111/0)
- Notus Q1 court-space: right > 24, makes_missed ≤ 6, misses_called_makes = 0
- Homography stability: frame-to-frame Δtranslation < 0.5 ft, Δrotation < 0.5° on 90% of adjacent good frames

**Stage 3 (Independent Signals):**
- S3 (net motion) on Adrian: TP ≥ 35, FP ≤ 5, FN ≤ 5, TN ≥ 66 (reliability ≥ 0.85)
- S4 (court path) on Adrian: TP ≥ 35, FP ≤ 5, FN ≤ 5, TN ≥ 66 (reliability ≥ 0.85)
- 4-way agreement (S1∧S2∧S3∧S4) on ≥ 90 of 111 Adrian tags

**Stage 4 (Notus Q1 Full Pipeline):**
- Scoreboard track built for Notus A1: final score matches book (Liberty 29, Notus 48)
- Make/miss on 31 Q1 tags: 31 right, 0 missed makes, 0 false makes
- Adrian unchanged: 99/111/0

**Stage 5 (Shooter ID):**
- Shooter tracker ID matches tagged shooter on ≥ 80% of Adrian 111 shots
- Team classification accuracy ≥ 95% on Adrian
- Jersey OCR confidence ≥ 0.7 on ≥ 70% of shots; when confident, accuracy ≥ 90%

---

## Appendix: Key Constants from Repository (Quoted from Files)

- **Adrian baseline:** 99 right, 12 makes missed, 0 misses called makes (ACTIVE.md, OLLAMA.md, ai_bridge.py line 1305)
- **Notus Q1 baseline:** 24 right, 7 makes missed, 0 misses called makes (ACTIVE.md, OLLAMA.md)
- **Liberty court length:** 92 ft → half court 40.75 ft from hoop (ACTIVE.md, ai_bridge.py GYM_COURT_LENGTH_FT)
- **NFHS lane:** 12 ft wide, FT line 15 ft from basket, baseline 4 ft behind basket (BIRDS_EYE_HOMOGRAPHY_DESIGN.md Table 3.1, pick_court_points.py LANE_COURT_XY)
- **Hoop diameter:** 18 in = 1.5 ft → radius 0.75 ft
- **Net depth:** ~1.5 ft below rim
- **Court keypoint model:** `models/court_keypoint_detector.pt`, 18 keypoints, conf ≥ 0.3 (run_v8.py)
- **Scoreboard rule:** score holds 3 one-second samples; rise = made basket (ACTIVE.md, scoreboard_clock.py)
- **Make definition:** `ball_through_rim` OR `net_moved_after_shot` (ACTIVE.md, TEAM_RECOVERY.md)
- **Banned trials (OLLAMA.md):** Linear interpolation, ByteTrack, DeepSORT, early windows — DO NOT REPEAT
- **Golden Rules (AGENT_OPERATIONAL_PROTOCOL.md):** No loosening cutoffs, no banned trials, no theater, audit filter, protected files

---

## File Structure for Implementation

```
liberty-basketball-analysis/
├── court_homography.py              # VETTED, frozen — import only
├── ai_bridge.py                     # Hermes section: _prepare_tracks_for_rule, threshold injection
├── net_detector.py                  # S3: net_moved_after_shot (proven)
├── scoreboard_clock.py              # S1: scoreboard score change (proven 43/43)
├── pick_court_points.py             # Manual calibration (reference only)
├── dist/scripts/run_v8.py           # Court keypoint model usage reference
├── .team/specs/
│   ├── 05_reliable_detector_architecture.md   # THIS FILE
│   └── stage1_keypoint_measurement/           # Stage 1 deliverables
├── calibrations/
│   ├── adrian_gym_homography.json   # Identity H for testing
│   └── notus_gym_homography.json    # Per-frame H cache (optional)
└── gemini-upload/
    └── court_homography.py          # Copy for Gemini prototyping
```

---

**END OF PROPOSAL**

*This architecture returns to the bird's-eye work, half-court and court keypoints, and a mixture of independent detectors as directed by Scott (2026-10-26). No manual tagging. Make/miss 100% accurate. Most reliable approach across gyms, pans, zooms, occlusion, lighting — not the easiest.*