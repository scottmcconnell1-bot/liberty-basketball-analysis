OPTIONS v1 - Hermes - nothing built or measured

# Options for the 19 Missed Makes (12 crossing-then-veto, 7 no-crossing)

**Context from the files:** Build set = 140 tagged shots (Notus A1 Q1 31 + Adrian Q1–Q3 109). v6 rule (`run_saved_v6_rule` in `ai_bridge.py`) gets 28 makes right, 19 makes wrong (called miss), 0 of 93 real misses called makes. Rejection tally (from `Liberty_Shot_Outputs/rejection_reason_tally_2026-10-29.txt`): no_valid_crossing 7/41, column_ratio_low 4/13, short_net_depth 1/7, ball_starts_well_below 1/7, ball_box_jump 2/6, ball_went_up 2/4, short_track_left_net 0/5, ball_bounces_up 1/3, tracker_swap_bodd_ball 0/3, sideways_drift 1/1, short_combined_track 0/1, short_make_bodd_fail 0/1, x_at_180_outside_rim 0/1. Every reason rejects more real misses than makes → no cutoff can simply be loosened. Scott's observation: the tracker's boxes jump between objects (ball, heads, jersey), so one shot can look like one make and two misses in the review page.

**Tried and failed (do not propose again):** 1) 2 s earlier window (Notus 0/7), 2) drop jumps >60 px (Adrian 86/111, 3 false makes), 3) draw jumped segment through hoop (Adrian 93/111, 1 false make), 4) straight-line interpolation (Adrian 98/111, Notus 0/7) — BANNED, 5) ByteTrack (21/31, 1 false make) / DeepSORT (22/31) — BANNED, 6) wider/looser column or any looser cutoff in `ai_bridge.py` — BANNED, 7) hoop recenter — BANNED, 8) `net_moved_after_shot` rescue (recovers 6/19, fires 38/93), 9) Plan 15 colour/orange pixels in net box (8/19, 22/93), 10) Plan 16 ball detector in net box (5/19, 27–28/93; `_net_box` sits below real net), 11) Scott closed all net-region measurements 2026-10-29, 12) Notus scoreboard reader (plans 07/09) shelved by Scott.

---

## Part A — Fixes to the v6 rule's own steps

The v6 rule's step sequence (from `ai_bridge.py:908–1283`) for a shot with a crossing:
1. **Crossing detection** (lines 1014–1043): finds `cross_idx` where ball goes from above `hoop_y` to below within 8 samples and within 0.55 × `hoop_w` horizontally. Falls back to `detect_dynamic_entry_crossing` if none found.
2. **Short net depth check** (lines 1052–1063): requires ≥3 ball points with `y_rel ≤ 180×scale_y` after crossing.
3. **Downward trend check** (lines 1065–1070): `last_y > first_y` in those net-depth frames → else `ball_went_up`.
4. **Column ratio check** (lines 1072–1097): on ball track from 80px to max_y below hoop, `column_ratio = in_column / total_in_zone` (when `total_in_zone ≥ 3`). Threshold 0.5 → else `column_ratio_low`. `came_back` heuristic can override.
5. **Ball box jump check** (lines 1099–1135): from true rim crossing to end of ball track, max Euclidean jump ≤ 60×geo_mean_scale (ignores slow/through-net motion) → else `ball_box_jump`.
6. **Ball starts well below check** (lines 1137–1168): if first ball point >50px below hoop and fell ≥80px and started near rim → `ball_starts_well_below`. Also `floor_to_hoop_putback` if bodd shows floor origin.
7. **Tracker swap check** (lines 1171–1196): small frame gap (≤3) but large spatial gap (>100×geo_mean_scale) between last bodd and first ball → `tracker_swap_bodd_ball`.
8. **Provisional make** (line 1214): `pred = True`.
9. **Drift veto** (lines 1224–1240): only if both 80px and 180px measured on ball. `sideways = (dist_at_180 - dist_at_80)/hoop_w`. Veto if >0.43 → `sideways_drift`. Also `x_at_180_outside_rim` if `dist_at_180 > 0.85×hoop_w`.
10. **Bounce check** (lines 1243–1261): after max depth in `net_depth_frames`, any upward move >5×scale_y → `ball_bounces_up`.
11. **Short make bodd continuation** (lines 1263–1282): if `is_short_make` (no 180px on ball), call `short_track_stays_in_net`; if passes, check bodd after ball ends: deep bodd points (`>180px`) must have `bodd_ratio ≥ 0.95` in column → else `short_make_bodd_fail`. Also `short_track_left_net` from helper.

For the **7 no-crossing shots** (`no_valid_crossing`): the rule never reaches steps 2–11.

---

### A1. Reorder: run ball_box_jump BEFORE column_ratio_low

**What it is:** Move the ball box jump check (step 5) before the column ratio check (step 4). Currently a shot that passes column ratio but fails jump check is rejected at step 5; if jump is checked first, some shots that would fail column ratio might instead fail jump — but crucially, the jump check uses the *true crossing frame* and ignores motion after the ball is 200px down and in-column. Some of the 4 `column_ratio_low` makes may have a clean jump profile that the column test obscures because the tracker jumps *after* the net.

**Why it could work where tried ones failed:** The column test measures *all* ball points from 80px down, including frames where the tracker has already jumped to a head/jersey. The jump check already filters out "through" and "slow" motion. Reordering lets the jump check veto tracker-swap frames before they pollute the column ratio. No cutoff changes; same thresholds.

**Which of the 19 it could recover:** Primarily the 4 `column_ratio_low` makes (if their column failure is caused by post-net tracker jumps). Possibly some `ball_went_up` if the upward motion is a tracker artifact after a clean jump.

**Risk to zero-false-makes gate:** Low. The jump check is already in the rule and passed 0 false makes on Adrian. Reordering only changes which reason is recorded first; a shot that fails both still fails. A shot that passes jump but fails column would now be rejected at column (same outcome). A shot that fails jump but would have passed column now fails earlier (same outcome).

**How measured on the 140:** Run modified rule on the 140 build set. Count: makes recovered (of 19), new false makes (must be 0), reason tally shift. Pass = recovers ≥2 of the 4 `column_ratio_low` makes with 0 new false makes.

**Cost:** Low (code reorder only, ~30 min). No new software/training.

**Rules check:** None (no cutoff change, no banned trial, `applied_to_core=false`).

---

### A2. Use bodd track for column check when ball track has a large jump

**What it is:** When `ball_box_jump` detects a jump >60px on the ball track, fall back to the bodd track (which extends to the floor) for the column ratio check from 80px down. The bodd track is more stable after the net because it follows the body/ball-blob rather than the jumping ball box.

**Why it could work where tried ones failed:** The column test currently uses *only* the ball track (`post_cross_dense = ball[cross_idx:]`). On missed makes, the ball track often jumps to a head/jersey after the net, inflating `total_in_zone` with outliers and lowering `column_ratio`. The bodd track stays on the falling object longer. The rule already uses bodd for short-make continuation (step 11); this extends that logic to non-short makes when the ball track is visibly corrupted.

**Which of the 19 it could recover:** The 4 `column_ratio_low` makes (if their column failure is from post-net ball-track jumps). Possibly the 2 `ball_box_jump` makes (if the jump is recoverable via bodd).

**Risk to zero-false-makes gate:** Medium. The bodd track on misses can also wander (rebounder, defender). Must guard: only use bodd for column check when (a) ball track has a detected jump >60px, AND (b) bodd track exists and has ≥3 points from 80px down, AND (c) bodd column ratio ≥ 0.5. If all three hold, accept bodd column; else keep ball column result.

**How measured on the 140:** Run with this fallback. Count: makes recovered (target ≥2 of 4 `column_ratio_low`), false makes on 93 misses (must be 0), new rejection reasons logged.

**Cost:** Medium (~2 hours). New logic in existing file, no new deps.

**Rules check:** Touches Golden Rule "No looser cutoffs" — the fallback must not effectively lower the column threshold for misses. Guard conditions (a–c) keep it a *recovery*, not a *loosening*.

---

### A3. Tighten the "came_back" heuristic to save column_ratio_low makes

**What it is:** The `came_back` logic (lines 1088–1094) currently overrides a low column ratio if the ball went wide then narrowed *and* the later width ≤0.70 hoop_w. For the 4 `column_ratio_low` makes, the tracker may jump *out* wide (to a head) and never come back, so `came_back` stays false. Relax the "later ≤ 0.70" to "later ≤ 0.85" *only when* the wide point coincides with a detected ball-box jump (>60px) — i.e., the wide point is a known tracker artifact.

**Why it could work where tried ones failed:** The current `came_back` requires the track to naturally narrow. Tracker jumps don't narrow; they jump to a different object and stay there. Conditioning on a detected jump lets the rule say "this wide point is fake, ignore it for column ratio."

**Which of the 19 it could recover:** The 4 `column_ratio_low` makes where the wide point aligns with a jump.

**Risk to zero-false-makes gate:** Medium. On a real miss that happens to have a jump (e.g., ball hits rim and tracker jumps to backboard), this could incorrectly widen the "came_back" window. Guard: require the jump to be *after* 80px down (in the net), not at the rim.

**How measured on the 140:** Run modified rule. Count: `column_ratio_low` makes recovered, false makes on misses (0 required), any `came_back` activations on misses.

**Cost:** Low (~1 hour). Logic tweak only.

**Rules check:** Touches "No looser cutoffs" — the effective column threshold for jump-corrupted makes is relaxed, but only when a jump is *proven*. Must show 0 false makes on Adrian misses.

---

### A4. Use the crossing frame's horizontal position as an anchor for drift veto

**What it is:** The drift veto (step 9) compares `x_at_80` and `x_at_180` on the ball track. On the 1 `sideways_drift` make and the 1 `x_at_180_outside_rim` make, the ball track at 180px may be a tracker jump. Instead, use the crossing frame's x (`x_cross`) as the anchor: `sideways = (x_at_180 - x_cross)/hoop_w`. The crossing frame is the most reliable (ball is at the rim, 0.55×hoop_w constraint already applied).

**Why it could work where tried ones failed:** `x_at_80` is also on the ball track and can be corrupted by the same jump that corrupts `x_at_180`. The crossing frame is geometrically constrained by the 0.55×hoop_w crossing test. Anchoring to it isolates the *net-to-180px* drift from the *rim-to-80px* noise.

**Which of the 19 it could recover:** The 1 `sideways_drift` make, the 1 `x_at_180_outside_rim` make. Possibly some `column_ratio_low` if their drift veto would have fired later.

**Risk to zero-false-makes gate:** Low–Medium. The crossing frame is already validated by the 0.55×hoop_w test. Using it as anchor is *stricter* for makes that truly drift (the crossing is the tightest constraint). Could only reduce false makes.

**How measured on the 140:** Run with anchor change. Count: `sideways_drift` and `x_at_180_outside_rim` makes recovered, false makes on misses (0 required), drift values on recovered makes vs misses.

**Cost:** Low (~1 hour). One variable change in drift computation.

**Rules check:** None (stricter anchor, no loosening).

---

### A5. For no_valid_crossing shots: use bodd track crossing if ball track is empty or has no above-hoop point

**What it is:** 7 makes have `no_valid_crossing`. Of these, some have a bodd track that *does* cross the hoop (bodd extends down from the rim). The rule already uses bodd for crossing detection when ball is empty (line 1007–1008), but `detect_dynamic_entry_crossing` (line 1043) may not find a crossing on bodd either. Add a dedicated bodd-only crossing search: on bodd points, find first transition from above to below `hoop_y` within 0.55×hoop_w, using the same 8-sample window.

**Why it could work where tried ones failed:** The 7 `no_valid_crossing` makes include free throws and close shots where the ball track starts *at* or *below* the rim (ball released from hand already at rim height). The bodd track, which picks up the shooter's body/arm motion, often has a cleaner above-to-below transition. The existing `detect_dynamic_entry_crossing` is generic; a bodd-specific crossing check exploits the fact that bodd tracks the shooting motion.

**Which of the 19 it could recover:** Up to 7 `no_valid_crossing` makes (depends on how many have bodd crossings).

**Risk to zero-false-makes gate:** Medium. Bodd tracks bodies, not balls. On a miss, the shooter's arm still goes up and down through the hoop plane. Must add: bodd crossing only counts if (a) ball track has no crossing, AND (b) bodd crossing frame has a ball detection within 30px of bodd point (proving ball was there), AND (c) the shot is a free throw or close-range (hoop_w ≥ threshold, or tag metadata). Without (b), a shooter's arm on a miss could trigger a false crossing.

**How measured on the 140:** Run with bodd crossing. Count: `no_valid_crossing` makes recovered, false makes on 93 misses (0 required), bodd crossing rate on makes vs misses.

**Cost:** Medium (~2 hours). New helper function, guarded activation.

**Rules check:** Touches "No looser cutoffs" — adding a new crossing path. Must prove 0 false makes on Adrian misses.

---

### A6. For no_valid_crossing shots: accept "first point at rim + next point down" without 8-sample window

**What it is:** The dynamic crossing fallback (line 890–905 in `ai_bridge.py`, called at line 1043) already has logic: if first combined point is at/just above hoop (≤10px) and within 0.55×hoop_w, and next point is lower, count it as crossing. But this only runs when `detect_dynamic_entry_crossing` returns None. Some `no_valid_crossing` shots may have a combined track where the first point is *below* hoop_y (ball starts below rim) but the *second* point is further down — the current logic requires the first point to be *above* hoop_y. Relax: if first point is within 20px below hoop_y (not above) and next point is lower and within 0.55×hoop_w, accept as crossing. This catches free throws where the ball is released at rim level.

**Why it could work where tried ones failed:** The 2 s earlier window trial (tried and failed) looked for an earlier crossing; this instead relaxes the *definition* of the crossing for shots that start at the rim. The 0.55×hoop_w horizontal constraint stays. The "next point lower" ensures downward motion.

**Which of the 19 it could recover:** Subset of 7 `no_valid_crossing` makes where ball track starts at/below rim (free throws, putbacks). From the tally: 1 `ball_starts_well_below` make is already a separate reason; this targets the other 6.

**Risk to zero-false-makes gate:** Medium. A miss where the ball bounces *up* to the rim and falls back down could have first point below rim and next point lower. Guard: require the first point to be within 0.55×hoop_w *and* the shot to be tagged as a free throw or close range (or have no bodd points above rim). Also keep the 8-sample window as primary; this is only a fallback.

**How measured on the 140:** Run with relaxed fallback. Count: `no_valid_crossing` makes recovered, false makes on 93 misses (0 required), how many misses have first point below rim + next lower within 0.55×hoop_w.

**Cost:** Low (~30 min). Logic tweak in `detect_dynamic_entry_crossing`.

**Rules check:** Touches "No looser cutoffs" — relaxing the crossing definition. Must show 0 false makes on Adrian misses.

---

### A7. Short net depth: allow bodd points to satisfy the ≥3 points requirement

**What it is:** 1 make fails `short_net_depth` (needs ≥3 ball points with `y_rel ≤ 180px`). If ball track is short but bodd track has ≥3 points in that zone, use bodd points for the depth count (already done for short makes in step 11; extend to non-short makes when ball track is short but bodd is long).

**Why it could work where tried ones failed:** The ball detector loses the ball in the net; bodd continues. The rule already uses bodd for short makes; this just says "if ball track has <3 points in net zone but bodd has ≥3, the shot *reached* the net depth — don't reject for short depth."

**Which of the 19 it could recover:** The 1 `short_net_depth` make.

**Risk to zero-false-makes gate:** Low. Bodd points in the net zone on a miss would mean the tracker followed the ball down — but on a miss, the ball doesn't go through the net. The bodd track on a miss typically goes to the rebounder, not down through the net. Guard: only use bodd depth points if they are *below* the rim and *in column* (≤0.6×hoop_w).

**How measured on the 140:** Run with bodd depth fallback. Count: `short_net_depth` make recovered, false makes on misses (0 required), bodd depth points on makes vs misses.

**Cost:** Low (~1 hour). Reuse existing bodd logic.

**Rules check:** None (reuse of existing short-make logic, no new threshold).

---

### A8. Ball_went_up: ignore upward moves that coincide with a ball_box_jump

**What it is:** 2 makes fail `ball_went_up` (last_y ≤ first_y in net_depth_frames). If the upward move happens at the same frame where `ball_box_jump` detects a jump >60px, treat it as a tracker artifact, not a real bounce. Specifically: when computing downward trend, skip any frame pair where the jump >60px *and* the next point is higher.

**Why it could work where tried ones failed:** The ball track jumps to a head/jersey (which is higher than the net), creating an apparent "upward" motion. The jump check already detects this; the downward trend check doesn't know about it. Linking them lets the rule discount tracker-jump-induced upward moves.

**Which of the 19 it could recover:** The 2 `ball_went_up` makes (if their upward move aligns with a jump).

**Risk to zero-false-makes gate:** Low. A real bounce (ball hits rim and pops up) would not have a 60px box jump — the ball box would stay on the ball. This only ignores upward moves *proven* to be tracker jumps.

**How measured on the 140:** Run with linked check. Count: `ball_went_up` makes recovered, false makes on misses (0 required), jump/upward coincidence on makes vs misses.

**Cost:** Low (~1 hour). Cross-reference existing jump and trend checks.

**Rules check:** None (uses existing jump detection, no new threshold).

---

### A9. Short_track_left_net: use bodd to confirm net exit on short makes

**What it is:** 0 makes fail this currently, but the helper `short_track_stays_in_net` (not shown in the read) may be too strict. For short makes (no 180px on ball), the rule checks bodd continuation. If bodd shows the object *leaving* the net column (going sideways to rebounder), veto. But on a made short shot, bodd may briefly leave column due to tracker noise. Relax: require bodd to leave column *and stay out* for ≥3 consecutive frames before vetoing.

**Why it could work where tried ones failed:** Prevents a single noisy bodd frame from vetoing a real short make. The 0 current failures means this is preventive for future Notus shots.

**Which of the 19 it could recover:** 0 currently, but protects against future `short_track_left_net` on Notus.

**Risk to zero-false-makes gate:** Low. Making the veto *stricter* (requiring sustained exit) can only reduce false makes.

**How measured on the 140:** Run with sustained-exit requirement. Count: any `short_track_left_net` activations on makes vs misses (should be 0 on makes, possibly some on misses).

**Cost:** Low (~30 min). Change in helper function.

**Rules check:** None (stricter veto).

---

### A10. Ball_bounces_up: require upward move to exceed 10px (not 5px) AND persist for 2 frames

**What it is:** 1 make fails `ball_bounces_up` (upward move >5×scale_y after max depth). Raise the threshold to 10×scale_y and require it on 2 consecutive frames. A tracker jump to a head is a single-frame large jump; a real bounce is a smaller but sustained upward motion.

**Why it could work where tried ones failed:** The current 5px threshold catches tracker noise. A real bounce is a parabolic arc — upward for multiple frames. The 1 `ball_bounces_up` make likely has a single-frame tracker jump.

**Which of the 19 it could recover:** The 1 `ball_bounces_up` make.

**Risk to zero-false-makes gate:** Low. Stricter bounce detection reduces false makes.

**How measured on the 140:** Run with raised threshold. Count: `ball_bounces_up` make recovered, false makes on misses (0 required), bounce events on makes vs misses.

**Cost:** Low (~30 min). Threshold change in existing check.

**Rules check:** None (stricter, not looser).

---

## Part B — Other possibilities (not on tried-and-failed list)

---

### B1. Candidate ball detector weights file (Scott gate 2026-10-20)

**What it is:** Train or fine-tune a new `ball_detector.pt` (saved as a separate candidate file, e.g., `candidate_notus_rim.pt`) that holds the ball through the net on the 19 missed makes. Score it with `validate_ball_weights.py` (Adrian: 0 false makes, ≤12 makes missed; Notus: <7 makes missed). This is explicitly allowed by Scott (2026-10-20) and the protocol.

**Why it could work where tried ones failed:** The current `models/ball_detector.pt` loses the ball in the net (tracker jumps to heads/jerseys). A model trained on net-region crops from the 19 missed makes + correct makes could learn to keep the ball box on the ball through the net. This attacks the *root cause* (ball detection failure) rather than patching the rule's reaction to bad tracks.

**Which of the 19 it could recover:** Potentially all 19 (7 no-crossing + 12 crossing-then-veto) if the ball track stays clean through the net. The 12 crossing-then-veto shots *have* a crossing; the vetoes are caused by post-crossing track corruption. The 7 no-crossing shots may get a crossing if the ball is detected earlier.

**Risk to zero-false-makes gate:** Medium. A model that "sees the ball in the net" on makes might also "see a ball in the net" on misses (front-of-rim rebounds, net flicker). The validation gate (Adrian 0 false makes) is the filter. Must not overwrite `models/ball_detector.pt` or change `ball_confidence`.

**How measured on the 140:** Run `validate_ball_weights.py` on candidate file. Pass = Adrian 0 false makes, ≤12 makes missed; Notus <7 makes missed. The 140 build set is the validation set.

**Cost:** High (training: hours to days, GPU, labeled net-region crops). New software: training pipeline, but inference uses existing YOLO/ultralytics.

**Rules check:** Candidate weights protocol (AUTHORITY.md §4, AGENT_OPERATIONAL_PROTOCOL.md §4). Production `models/ball_detector.pt` and `ball_confidence` are Scott gates — candidate is separate file, never overwrites production.

---

### B2. Ball track interpolation in *court space* (not pixel space) — per reliable detector architecture

**What it is:** The reliable detector architecture (spec 05) proposes per-frame homography from court keypoints. Transform ball tracks to court feet (where the rim is a fixed 0.75 ft radius, net depth 1.5 ft). Interpolate gaps ≤15 frames in *court space* (where ball motion is parabolic and uniform), not pixel space (where perspective distorts). Then run the v6 rule logic in court space with constant thresholds (rim radius 0.75 ft, net depth 1.5 ft, drift in ft).

**Why it could work where tried ones failed:** Pixel-space interpolation (tried, banned) fails because the ball's pixel trajectory curves wildly with camera zoom/pan. In court space, a shot is a clean parabola. The 12 crossing-then-veto shots have gaps/jumps in *pixel* space that may be smooth in court space. The 7 no-crossing shots may get a crossing in court space if the ball's court-space path crosses the rim plane.

**Which of the 19 it could recover:** All 19 potentially. Court-space thresholds are constant across gyms and camera views.

**Risk to zero-false-makes gate:** Medium. Requires per-frame homography (Stage 1b/2 of work order). If homography fails on a frame, fall back to pixel rule (preserving Adrian 0 false makes). The court-space rule must pass the Adrian identity test (exact equality when H=I).

**How measured on the 140:** Stage 1b (keypoint measurement) must pass first (≥70% frames valid H on Notus). Then Stage 2 (court-space rule) on 140: target >24 right on Notus Q1, 0 false makes, ≤6 makes missed. Adrian identity test must pass exactly.

**Cost:** High (Stage 1b + 2 of work order: weeks, court keypoint model, homography pipeline). But this is the *architected path* (spec 05, work order plan 13).

**Rules check:** This is the approved architecture (spec 05 VETTED, plan 13 VETTED). No banned trials. `applied_to_core=false` until Scott accepts contract.

---

### B3. Scoreboard score change as a make signal (S1 in spec 05)

**What it is:** The scoreboard reader (`scoreboard_clock.py`) is proven 43/43 on Adrian (every made basket = score rise, 0 rises without tag). On Notus, build the scoreboard track for the full game. For the 19 missed makes, check if the scoreboard shows a score rise for the shooting team within 25 s of the shot tag. If yes, that is independent confirmation of a make — even if the ball track is corrupted.

**Why it could work where tried ones failed:** The scoreboard sees *makes only* (misses don't change score). It is completely independent of ball tracking, camera angle, net detection. The 19 missed makes are all real makes; most should have a scoreboard rise. This doesn't fix the ball track; it provides a *parallel verdict* that can override the track-based miss.

**Which of the 19 it could recover:** All 19 that have a scoreboard rise (likely most; free throws and field goals in Q1). The 7 no-crossing and 12 crossing-then-veto are all tagged makes.

**Risk to zero-false-makes gate:** None for the scoreboard itself (0 false rises on Adrian). Risk is in *combining* it: the mixture gate (plan 13 Task 5) must not auto-accept scoreboard on frames where the board is not visible. Spec 05 says: scoreboard is S1 (weight 1.0), combine with S2/S3/S4 by voting; 2-2 split → flag for Scott. Never guess.

**How measured on the 140:** Build Notus A1 scoreboard track (plan 13 Task 1). Run scoreboard rise detection on the 31 Notus Q1 shots + 109 Adrian Q1–Q3. Count: scoreboard rises on the 19 missed makes (should be high), scoreboard rises on 93 real misses (must be 0). Then test mixture gate: S1+S2+S3+S4 voting on 140.

**Cost:** Medium (build scoreboard track for Notus A1: ~1 day; mixture gate: ~1 day). Scoreboard reader exists and is proven.

**Rules check:** Scoreboard is shelved for *primary* make/miss (plan 13 §4), but returns as *cross-check* (S1 in spec 05). This is allowed.

---

### B4. Human-in-the-loop: flag only the 19 missed makes for Scott review (auto-accept the other 121)

**What it is:** The v6 rule gets 121 of 140 right (28 makes + 93 misses). Instead of fixing the rule to catch the 19, build a review queue that shows Scott *only* the 19 shots the rule calls "miss" but are tagged "make" (using the tag file as ground truth for queue building). Scott clicks "make" or "miss" on each. Once reviewed, the rule's output for those 19 is replaced with Scott's verdict. Future games: any shot the rule calls "miss" but has high make-probability signals (scoreboard rise, net motion, court-space cross) goes to the queue.

**Why it could work where tried ones failed:** Scott's goal is "never tags a game by hand." Tagging 19 shots per game (vs 140) is an 86% reduction. The 19 are the *hard* shots; the 121 easy ones are auto-correct. This accepts that the rule has a "hard set" and offloads it to the human, while automating the easy majority.

**Which of the 19 it could recover:** All 19 (Scott's verdict is ground truth).

**Risk to zero-false-makes gate:** None — Scott's review *is* the gate. The rule's 0 false makes on the 93 real misses stands.

**How measured on the 140:** Build the review queue for the 19 missed makes. Time Scott to review 19 shots. Measure: review time per shot, accuracy of Scott's clicks (should be 100%), total tagging time per game vs 140 manual tags.

**Cost:** Low–Medium (review UI: ~2 days; queue logic: ~1 day). No ML training.

**Rules check:** None. `applied_to_core=false`. The rule stays unchanged; the review layer wraps it.

---

### B5. Ensemble of multiple ball trackers (nearest-box, ByteTrack, DeepSORT, SORT) with agreement gate

**What it is:** Run 4 trackers on each shot. Each produces a ball track. Run the v6 rule on each track independently. If ≥3 trackers agree "make", call make. If ≥3 agree "miss", call miss. If 2-2 split, flag for Scott. ByteTrack/DeepSORT alone failed (21/31, 22/31, 1 false make), but they *differ* in *which* makes they catch. An ensemble exploits diversity.

**Why it could work where tried ones failed:** ByteTrack caught 21/31 (lost 2 makes nearest-box got), DeepSORT caught 22/31 (same 2 lost). Nearest-box (v6 tracks) catches 24/31. The union of all trackers may cover all 31. The 1 false make from ByteTrack was at 9:51.1 (591100) — if nearest-box and DeepSORT say "miss" there, the 2-2 split flags it for Scott instead of auto-accepting the false make.

**Which of the 19 it could recover:** Up to 19 (union of tracker coverages). The 2 makes nearest-box got right but ByteTrack/DeepSORT lost are already in the 24. The 7 nearest-box missed may be caught by ByteTrack/DeepSORT.

**Risk to zero-false-makes gate:** Medium. ByteTrack had 1 false make. The agreement gate (≥3) suppresses single-tracker false makes. But if 2 trackers false-make the same miss, it could pass. Must measure pairwise false-make correlation on Adrian misses.

**How measured on the 140:** Run all 4 trackers on the 140 shots (or at least the 31 Notus + 109 Adrian tracks). Run v6 rule on each tracker's output. Build agreement table. Pass = ensemble gets 31/31 Notus, 0 false makes on Adrian, ≤12 makes missed.

**Cost:** High (run 4 trackers on full films, store tracks, build ensemble logic). ByteTrack/DeepSORT already implemented in repo (plan 15/16 context).

**Rules check:** ByteTrack/DeepSORT are BANNED as *primary* detectors (OLLAMA.md). Using them as *ensemble members* with a voting gate that flags disagreements is not banned — it's a mixture (plan 13 Task 5). Must not lower any tracker's internal thresholds.

---

### B6. Use the review page's "ball detected at rim, at net, after net" as three independent make signals

**What it is:** Scott observes: "the ball is detected on its way up, at the rim and after the rim, and the pictures can look like one make and two misses for one shot." The review page already shows crops at three phases. Build a detector that says: if ball detected in *all three phases* (up, at rim, down) within one shot window → make. The tracker jumping between objects creates *multiple* detections; a real make has detections in all three zones; a miss typically has only up + rim (ball hits rim and bounces out) or only rim + down (putback).

**Why it could work where tried ones failed:** This uses the *multiplicity* of detections (which Scott sees as noise) as a *signal*. The current rule tries to stitch one clean track; this says "three noisy tracks in the right places = make."

**Which of the 19 it could recover:** The 12 crossing-then-veto shots (they have rim crossing + some net detections). The 7 no-crossing may have up + rim detections but no clean crossing.

**Risk to zero-false-makes gate:** Medium. A miss with a putback could have up (shot) + rim (hit) + down (rebound) detections. Guard: require the "down" detection to be *in the net column* (x within 0.55×hoop_w, y > hoop_y + 80px) and the "up" detection to be *above* the rim (y < hoop_y - 50px).

**How measured on the 140:** Implement three-zone detector on the 140 shots using existing review-page crops/detections. Count: makes caught, false makes on 93 misses (0 required).

**Cost:** Medium (~2 days). New detector using existing detection data.

**Rules check:** None (new detector, no cutoff changes to v6 rule).

---

### B7. Free-throw specific rule (all 7 no-crossing + several crossing-then-veto are free throws)

**What it is:** From the tally and OLLAMA.md, the 7 Notus missed makes include 3 free throws (2:22.6, 2:39.3, 5:57.5) and the Adrian missed makes include free throws. Free throws have: fixed shooter position, no defender, ball released from ~same height, predictable arc. Build a free-throw-specific rule: detect the free-throw line (court lines), find the shooter at the line, track ball from release to rim. Use a simpler crossing test: ball center crosses a fixed hoop-width window at the rim. No column test needed (ball goes straight down).

**Why it could work where tried ones failed:** The general rule handles jump shots, layups, putbacks, free throws with one logic. Free throws are a distinct, simpler case. The 3 Notus free-throw misses are `column_ratio_low` (2) and `short_make_bodd_fail` (1) — the column test is too strict for a straight-down trajectory.

**Which of the 19 it could recover:** The 3 Notus free-throw makes + any Adrian free-throw makes in the 19.

**Risk to zero-false-makes gate:** Low. Free-throw rule only activates on detected free-throw situations (shooter at FT line, no players in lane). On a missed free throw, the ball hits rim and bounces out — the crossing test (ball center through hoop window) fails.

**How measured on the 140:** Tag free throws in the 140 (from tag file or scoreboard). Run FT rule on FT shots only. Count: FT makes recovered, false makes on FT misses (0 required).

**Cost:** Medium (~3 days: FT detection + simplified rule). Court line detection needed (Stage 1b).

**Rules check:** None (specialized rule for a subclass, no loosening of general rule).

---

### B8. Rim-contact detection (ball hits rim → changes trajectory)

**What it is:** On a made shot, the ball passes through the rim with minimal deflection (clean crossing). On a missed shot that hits the rim, the ball's trajectory changes abruptly (bounce). Detect this in the ball track: at the crossing frame, compute the angle before and after. Large angle change (>30°) = rim contact = likely miss. Small angle change = clean pass = likely make. This is a *new signal* (S5) for the mixture gate.

**Why it could work where tried ones failed:** The v6 rule's drift/bounce checks are post-hoc. Rim-contact detection uses the *crossing frame itself* — the moment of truth. The 12 crossing-then-veto makes have a clean crossing (that's why they have a crossing); their vetoes come later. A clean crossing + no rim contact = strong make signal.

**Which of the 19 it could recover:** The 12 crossing-then-veto makes (they have clean crossings). The 7 no-crossing makes don't have a crossing to analyze.

**Risk to zero-false-makes gate:** Low. A clean pass through the net has minimal angle change. A rim hit has a sharp angle change. This signal is independent of post-rim tracker corruption.

**How measured on the 140:** Compute angle change at crossing for all 140 shots. Build ROC: angle threshold vs make/miss. Target: threshold that catches ≥10 of 12 crossing makes with 0 false makes on 93 misses.

**Cost:** Medium (~2 days). New signal computation, needs reliable crossing frame (already have).

**Rules check:** None (new signal for mixture gate, not a v6 rule change).

---

### B9. Opponent basket detection (mirror the hoop logic for the other end)

**What it is:** The current rule only tracks the "grouped hoop" at one end (Liberty's basket). The opponent's basket is never calibrated. On Notus, some of the 19 missed makes may be at the opponent's basket (Notus scoring). Add opponent hoop detection: use the court keypoint model (Stage 1b) to find both baskets per frame. Run the same v6 logic on both hoops. A make is a crossing at *either* hoop with the shooting team's color.

**Why it could work where tried ones failed:** If the 19 missed makes include Notus makes at their own basket, the current rule (calibrated to Liberty's hoop) would never see a crossing. The grouped hoop detection may only find Liberty's hoop.

**Which of the 19 it could recover:** Any missed makes at the opponent basket (unknown how many of the 19).

**Risk to zero-false-makes gate:** Low. Same rule applied to second hoop. Must correctly assign shooting team (jersey color) to avoid calling opponent's make as Liberty's.

**How measured on the 140:** Requires Stage 1b (court keypoints) to locate both hoops. Then run dual-hoop v6 on 140. Count: makes recovered, false makes.

**Cost:** High (requires Stage 1b + dual-hoop logic). Part of the architected path.

**Rules check:** Part of spec 05 / plan 13 architecture.

---

### B10. Learn a "track quality" classifier to weight the v6 rule's steps

**What it is:** Train a small classifier (logistic regression / random forest) on the 140 shots using the v6 rule's intermediate values as features: `column_ratio`, `max_jump`, `sideways`, `x_at_180/hoop_w`, `net_depth_frames_count`, `has_crossing`, `ball_went_up`, `ball_bounces_up`, `bodd_ratio`, etc. Target = ground truth make/miss. The classifier learns which combinations of "failed steps" still indicate a make (e.g., high column_ratio + high jump = tracker jump, not miss). Use the classifier's probability as a *supplement* to the rule: if rule says miss but classifier P(make) > 0.9 → flag for review (don't auto-flip).

**Why it could work where tried ones failed:** The rule uses hard thresholds in sequence. A classifier sees the *joint distribution*: a shot with `column_ratio_low` (0.45) but `max_jump`=80px and `sideways`=0.1 is likely a make with a tracker jump. The rule sees "column_ratio < 0.5 → miss" and stops.

**Which of the 19 it could recover:** All 19 potentially, by learning the joint pattern of the 12 crossing-then-veto makes vs the misses that fail the same steps.

**Risk to zero-false-makes gate:** Medium. A classifier can overfit the 140 build set. Must validate on unseen (Adrian Q4, or cross-validation). The gate: classifier only *flags*, never *overrides*. Auto-accept only when rule + classifier agree.

**How measured on the 140:** Train on 140 (or leave-one-out CV). Report: CV accuracy, precision/recall on makes, false make rate on misses at P(make)>0.9 threshold. Pass = 0 false makes at high-confidence threshold, recalls ≥10 of 19 missed makes.

**Cost:** Medium (~2 days: feature extraction, training, validation). No new deps (scikit-learn).

**Rules check:** None (classifier is a supplement, not a rule change. `applied_to_core=false`. Holdout not opened if using CV).

---

---

## Ranked Summary Table

| Option | Expected Gain (of 19 missed makes) | Risk to 0 False Makes | Cost | Notes |
|--------|-----------------------------------|----------------------|------|-------|
| **A1: Reorder jump before column** | 2–4 (column_ratio_low) | Very Low | 30 min | Try first: trivial, safe, uses existing logic |
| **A4: Crossing-anchored drift veto** | 1–2 (sideways_drift, x_at_180) | Low | 1 hr | Try second: stricter anchor, no loosening |
| **A8: Link ball_went_up to jump check** | 1–2 (ball_went_up) | Low | 1 hr | Try third: connects two existing checks |
| **A7: Bodd depth fallback for short_net_depth** | 1 (short_net_depth) | Low | 1 hr | Try fourth: reuses short-make logic |
| **A3: Jump-conditioned came_back** | 2–4 (column_ratio_low) | Medium | 1 hr | Guarded; must show 0 false makes |
| **A2: Bodd column fallback on jump** | 2–4 (column_ratio_low, ball_box_jump) | Medium | 2 hrs | Guarded; must show 0 false makes |
| **A6: Relaxed crossing for rim-level starts** | 2–6 (no_valid_crossing subset) | Medium | 30 min | Guarded; free-throw focused |
| **A5: Bodd crossing for no_valid_crossing** | 3–7 (no_valid_crossing) | Medium | 2 hrs | Needs ball-bodd proximity guard |
| **A10: Stricter ball_bounces_up** | 1 (ball_bounces_up) | Very Low | 30 min | Preventive, stricter |
| **A9: Sustained exit for short_track_left_net** | 0 (preventive) | Very Low | 30 min | Preventive for future |
| **B3: Scoreboard as S1 signal** | Up to 19 (all with score rise) | None (independent) | Medium | Architected path (spec 05); needs Notus scoreboard track |
| **B2: Court-space interpolation + rule** | Up to 19 (all) | Medium | High (weeks) | Architected path (spec 05, plan 13); requires Stage 1b pass |
| **B1: Candidate ball weights** | Up to 19 (all) | Medium | High (training) | Scott gate allowed; must pass validate_ball_weights.py |
| **B4: Human-in-loop review queue** | 19 (Scott verifies) | None | Low–Med | 86% auto; Scott tags only hard 19 |
| **B6: Three-zone detection (up/rim/down)** | 10–12 (crossing makes) | Medium | 2 days | Uses tracker multiplicity as signal |
| **B7: Free-throw specific rule** | 3–5 (FT makes) | Low | 3 days | Needs court lines (Stage 1b) |
| **B8: Rim-contact angle change** | 10–12 (crossing makes) | Low | 2 days | New signal for mixture gate |
| **B5: Multi-tracker ensemble** | Up to 19 (union) | Medium | High | ByteTrack/DeepSORT banned as primary; allowed as ensemble members |
| **B9: Opponent basket detection** | Unknown (depends on how many Notus makes) | Low | High | Requires Stage 1b |
| **B10: Track-quality classifier** | 10–19 (joint patterns) | Medium | 2 days | Flags only; no auto-override |

**What I would try first and why:**

1. **A1 (reorder jump before column)** — 30 min, zero risk, uses existing code, targets the 4 `column_ratio_low` makes which are the largest single reason group among crossing-then-veto shots. If it recovers ≥2 with 0 false makes, it's a free win.

2. **A4 (crossing-anchored drift)** — 1 hr, low risk, targets the 1 `sideways_drift` and 1 `x_at_180_outside_rim` makes. The crossing frame is the most geometrically constrained point in the rule; using it as anchor is logically sound and can only tighten drift detection.

3. **A8 (link ball_went_up to jump)** — 1 hr, low risk, targets 2 `ball_went_up` makes. The jump check already exists; this just shares its finding with the trend check.

These three are pure logic rearrangements in `ai_bridge.py` with no new thresholds, no new data, no net-region measurements, and no banned trials. They can be tested sequentially on the 140 build set in one afternoon.

**Numbers marked "from the files":** All rejection tallies (7/41, 4/13, etc.) from `Liberty_Shot_Outputs/rejection_reason_tally_2026-10-29.txt`. Baseline scores (28/47 makes right, 19 missed, 0 false makes) from `OLLAMA.md`, `MUSE.md`, `AGENT_OPERATIONAL_PROTOCOL.md`, `DETECTOR_PROPOSAL_REJECTION.md`. Tried-and-failed results from same files. Step names and reasons quoted from `ai_bridge.py:908–1283`. Spec 05, plan 13, plan 15, plan 16, pixel_miss README from their respective files in `.team/specs/` and `.team/shot_detectors/pixel_miss/`.