VETTED by Claude Code, 2026-10-29 (v2, with one binding note): all 5 rejection points are fixed - 93 real misses and 28 correct makes reported separately (sections 6, 10, 11); a before frame at peak_frame-3 with delta and largest-blob measures (3.2, 3.3); the orange 8-22 range added; no unseen set claimed and build-set thresholds are not results (6); config.yaml dropped (8). Checked by reading the plan against net_detector.py:72-77 and 459-470 and measure_net_moved.py:160-177. No protected file is edited, no cutoff changes, no banned trial, outputs outside the repo.
BINDING NOTE a (coder must follow; overrides the red1 and red2 lines in section 3.3 (file lines 67-68) and the HSV checklist item in section 11 (file line 252)): red1 and red2 use sat >= 70 and val >= 70, exactly as net_detector.py:74-75. Only the orange range (8-22) uses sat >= 90 and val >= 90 (net_detector.py:76). The plan's "sat >= 90, val >= 90" for red1/red2 is a copying error.

PLAN - NOT BUILT OR MEASURED YET

---

# Net Check Plan — Task 1 Step 3: Post-Rim Net Region Read-Only Measurement

**Author:** Hermes (Architect)  
**Date:** 2026-10-29  
**Status:** Plan for Vetted implementation  
**Gate:** Must pass Vetter review before OpenCode/Cursor implements

---

## 1. Purpose

The v6 rule (`run_saved_v6_rule` in `ai_bridge.py`) sees the ball cross the rim on 12 of 19 missed makes but then rejects them on **after-rim tests** (column_ratio_low, ball_went_up, ball_box_jump, ball_bounces_up, ball_starts_well_below, short_net_depth, sideways_drift). On the other 7 missed makes, **no_valid_crossing** is found at all (missed_make_11 has zero ball points).

The tracker is unreliable after the rim: it jumps to heads, loses the ball in the net, follows the rebound. `net_moved_after_shot` as-is (Step 1) catches 6/19 missed makes but fires on 38/93 misses.

**This step adds a separate, read-only check that looks only at the net region directly under the rim in the few frames after the ball reaches the rim, and asks: "Is the ball inside the net?"** — independent of where the tracker jumps later.

---

## 2. Scope

- **Read-only measurement only.** No edits to `ai_bridge.py`, `net_detector.py`, `models/ball_detector.pt`, `ball_confidence`, `schema.sql`, or any protected core file.
- **No cutoff changes.** The v6 rule thresholds stay exactly as they are (0 false makes must remain 0).
- **New code only** in `.team/shot_detectors/pixel_miss/` (one new file: `net_check.py` and `README.md`).
- **Measured on the same 140 tagged shots** (Notus A1 Q1: 31, Adrian Q1–Q3: 109).
- **Output** written to `C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check/` (outside repo).
- **Sandbox test run** writes to `.team/shot_outputs_test/net_check/` (never committed).
- **Reuses the review page's crops/hoop box** so Scott can see what the check saw.

---

## 3. What the Check Reads (Image Pixels)

All coordinates are **image pixels**, relative to the saved hoop track for each shot (`hoop_x`, `hoop_y`, `hoop_w` from `v6_tracks.json`).

### 3.1 Net Region (ROI)

From `net_detector.py:_net_box` (line 459):
- **x-range:** `hoop_x ± 1.1 × rim_r` where `rim_r = hoop_w / 2`
- **y-range:** `hoop_y + 0.25 × rim_r` to `hoop_y + 2.8 × rim_r`

This is a column under the rim: width ≈ `2.2 × rim_r`, height ≈ `2.55 × rim_r`.

### 3.2 Frames to Sample

Let **peak_frame** = the absolute video frame where the ball *reaches the rim*:
- For shots **with a crossing**: the crossing frame (ball goes from above to below `hoop_y` within 0.55 × `hoop_w`).
- For shots **without a crossing** (`no_valid_crossing`): the frame of the closest ball point to `(hoop_x, hoop_y)` in the saved track (same as `peak_from_track` logic in `measure_net_moved.py` line 172–176).

Sample **5 frames after the peak frame**: `peak_frame + 1, +2, +3, +4, +5`.

**Also sample 1 BEFORE frame:** `peak_frame - 3` (same as `net_moved_after_shot` uses). This gives a baseline before the ball arrives, to subtract rim/hands/jersey orange that exists on misses too.

**Rationale:** The ball passes through the rim and enters the net in ~1–3 frames at 25 fps. Sampling 5 frames after peak captures the ball in the net before the tracker loses it or jumps away. The before frame gives a per-shot baseline to compute the **change** in orange pixels (delta = after - before).

### 3.3 What to Measure Per Frame

For each of the 5 after-frames, within the net ROI:
1. **Orange pixel count** — HSV range matching `net_detector.py:74-76`:
   - red1: hue 0–14, sat >= 90, val >= 90
   - red2: hue 165–180, sat >= 90, val >= 90
   - orange: hue 8–22, sat >= 90, val >= 90
   Count pixels in the ROI matching any of these three ranges.
2. **White/gray pixel count** — HSV range for the net (white: sat < 60, val > 155; gray: sat < 55, val 70–190). Count pixels in the ROI matching this.
3. **Largest single orange blob area** — connected-component area (in pixels) of the largest contiguous orange region in the ROI. The ball is one round blob; the rim is a wide band.
4. **Orange/white ratio** — `orange_px / max(1, white_px + gray_px)`.

**Also measure the BEFORE frame** (`peak_frame - 3`) with the same four metrics to get `before_orange_px`, `before_white_px`, `before_max_blob`, `before_ratio`.

**Output per shot:** a JSON object with:
```json
{
  "t": 342800,
  "film": "adrian",
  "peak_frame": 8573,
  "has_crossing": true,
  "before": {"frame": 8570, "orange_px": 45, "white_px": 480, "gray_px": 350, "max_blob": 12, "orange_ratio": 0.05},
  "frames": [
    {"frame": 8574, "orange_px": 120, "white_px": 450, "gray_px": 320, "max_blob": 85, "orange_ratio": 0.16, "delta_orange": 75, "delta_ratio": 0.11},
    {"frame": 8575, "orange_px": 95,  "white_px": 480, "gray_px": 350, "max_blob": 70, "orange_ratio": 0.12, "delta_orange": 50, "delta_ratio": 0.07},
    {"frame": 8576, "orange_px": 60,  "white_px": 500, "gray_px": 380, "max_blob": 40, "orange_ratio": 0.07, "delta_orange": 15, "delta_ratio": 0.02},
    {"frame": 8577, "orange_px": 15,  "white_px": 520, "gray_px": 400, "max_blob": 8,  "orange_ratio": 0.02, "delta_orange": -30, "delta_ratio": -0.03},
    {"frame": 8578, "orange_px": 5,   "white_px": 530, "gray_px": 410, "max_blob": 3,  "orange_ratio": 0.01, "delta_orange": -40, "delta_ratio": -0.04}
  ],
  "max_orange_ratio": 0.16,
  "max_delta_ratio": 0.11,
  "max_orange_frame": 8574,
  "max_delta_frame": 8574
}
```

---

## 4. Decision Rule (for measurement reporting only)

**A shot is flagged as "net check caught this missed make" if:**
- `max_delta_ratio` across the 5 frames ≥ **0.08** (tunable threshold for reporting; the measurement reports the raw numbers, this threshold is only for the summary table).

**Why delta_ratio:** The rim is the same color as the ball (`net_detector.py:99` "The ball and this rim land in the same orange hue on this camera"). A raw orange count in the net box will also count rim, hands, skin and jerseys under the rim on rebounds, so it will fire on misses. The **change** from the before-frame (same box, before the ball arrives) removes the static rim/hands/jersey contribution. The largest single orange blob (the ball is one round blob; the rim is a wide band) is an additional discriminator.

---

## 5. How to Find the "Ball Reached the Rim" Frame (No Crossing Case)

Reuse the existing logic from `measure_net_moved.py:peak_from_track` (lines 171–177):

```python
if ball_points_exist:
    hx, hy = float(hoop_x), float(hoop_y)
    best = min(ball_points, key=lambda pt: (pt[1] - hx)**2 + (pt[2] - hy)**2)
    peak_frame = tag_frame + int(best[0])   # absolute video frame
    has_crossing = False
else:
    peak_frame = tag_frame                  # fallback: tag frame
    has_crossing = False
```

This is exactly what the review page already uses for `peak_reason = "no_crossing_closest_ball"` or `"no_crossing_tag_frame"`.

---

## 6. Measurement Protocol

| Set | Shots | Purpose |
|-----|-------|---------|
| **Build (tagged, used for tuning)** | Notus A1 Q1 (31) + Adrian Q1–Q3 (109) = 140 | Measure the check on all 19 missed makes + 28 correct makes + 93 real misses |
| **Unseen** | **None** — Adrian Q4 has no tracks built | Not scored in this step; any threshold picked from these 140 shots is build-set only and is not a result until checked on unseen shots (Plan 13's open question to Scott) |

Run the check on **every shot in the build set** (140 shots). Report:

### For the 19 missed makes:
- How many have `max_delta_ratio ≥ 0.08` (caught)
- Per-shot: `max_delta_ratio`, `max_delta_frame`, `has_crossing`

### For the 28 correct makes (sanity check — the check should catch these too):
- How many have `max_delta_ratio ≥ 0.08`
- Per-shot: `max_delta_ratio`, `max_delta_frame`, `has_crossing`

### For the real misses (93 shots):
- How many have `max_delta_ratio ≥ 0.08` (**must be 0 to even consider this check**)
- Count of false fires at each threshold (0.05, 0.08, 0.10, 0.12)

**Success bar for even considering this check:** fires on **0 real misses** at the chosen threshold.

---

## 7. Output Files

All written to `C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check\`:

```
net_check/
├── build_results.json          # Per-shot raw measurements (140 objects)
├── summary.md                  # Table: missed makes caught, correct makes caught, misses fired on
├── missed_makes_detail.md      # 19 rows with max_delta_ratio, frames
├── correct_makes_detail.md     # 28 rows (sanity check)
├── misses_fired_on.md          # Any misses with ratio > 0 (should be empty at threshold)
└── crops/                      # Reuse review page crops: one PNG per shot showing
    ├── missed_make_01/         # the net ROI with orange pixel overlay on the
    │   └── net_check_010.png   # peak+1 frame (frame where max_delta_ratio occurs)
    └── ...
```

**Crops:** For each of the 39 review-page shots (19 missed makes, 10 correct makes, 10 misses), save one PNG: the frame at `max_delta_frame` (or `peak_frame + 2` if no delta found), cropped to the review page's square crop (centered on hoop, size `max(hoop_w * 3, 240)`), with the net ROI box drawn in blue and orange pixels highlighted in red.

---

## 8. Files the Coder May Create (Only New Files)

```
.team/shot_detectors/pixel_miss/
├── net_check.py                # Main measurement script (reads v6_tracks, tags, videos; writes outputs)
└── README.md                   # One-paragraph description + run command
```

**No config.yaml.** All constants (thresholds, HSV ranges, frame offsets) stay at the top of `net_check.py` (no new dependency).

**No edits to existing files.** `applied_to_core` stays `false`.

---

## 9. Exact Run Command

```cmd
# Windows (Claude Code runs this with the venv)
.venv\Scripts\python.exe .team/shot_detectors/pixel_miss/net_check.py --out C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check

# WSL sandbox (Cursor tests here)
python3 .team/shot_detectors/pixel_miss/net_check.py --out .team/shot_outputs_test/net_check
```

The script must:
1. Load tag files and track files (read-only).
2. For each build-set shot, compute `peak_frame` and `has_crossing` per §5.
3. Read 1 before frame (`peak_frame - 3`) and 5 after frames (`peak_frame + 1` through `+5`) from the video.
4. For each frame, crop the net ROI (§3.1), count orange/white/gray pixels, find largest orange blob (§3.3).
5. Compute deltas (after - before) for orange_px and orange_ratio.
6. Write `build_results.json`, `summary.md`, `missed_makes_detail.md`, `correct_makes_detail.md`, `misses_fired_on.md`.
7. Generate crops for the 39 review-page shots (§7).
8. Print console summary with counts.
9. **Exit. No further steps.**

---

## 10. Console Output Format

```
=== NET CHECK SUMMARY ===
Build shots: 140
Missed makes: 19
  Caught (delta_ratio ≥ 0.08): X
  By crossing status:
    Has crossing: Y caught / 12
    No crossing:  Z caught / 7
Correct makes: 28
  Caught (delta_ratio ≥ 0.08): W   <-- sanity check
Real misses: 93
  Fired on (delta_ratio ≥ 0.08): 0   <-- MUST BE 0
  Fired on (delta_ratio ≥ 0.05): N
  Fired on (delta_ratio ≥ 0.10): N
  Fired on (delta_ratio ≥ 0.12): N

Per missed make:
  missed_make_01 (notus_a1 t=64200):  max_delta=0.XX at frame NNNNN  crossing=True
  ...
  missed_make_19 (adrian t=3095700):  max_delta=0.XX at frame NNNNN  crossing=False

Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check\build_results.json
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check\summary.md
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check\missed_makes_detail.md
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check\correct_makes_detail.md
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check\misses_fired_on.md
Crops: 39 PNGs in crops/
STOP — measurement complete, no detector changes
```

---

## 11. Verification Checklist (Coder Confirms Before Done)

- [ ] Reads `v6_tracks.json` / `v6_tracks_notus_q1.json` and tag files (read-only).
- [ ] Computes `peak_frame` per §5 (crossing frame or closest-ball frame).
- [ ] Samples exactly 1 before frame (`peak_frame - 3`) and 5 after frames (`peak_frame + 1` through `peak_frame + 5`).
- [ ] Net ROI matches `net_detector.py:_net_box` (x ± 1.1×rim_r, y + 0.25×rim_r to +2.8×rim_r).
- [ ] HSV ranges match `net_detector.py:74-76`: red1 (0–14, sat>=90, val>=90), red2 (165–180, sat>=90, val>=90), orange (8–22, sat>=90, val>=90).
- [ ] Measures largest single orange blob area per frame (connected components).
- [ ] Computes deltas (after - before) for orange_px and orange_ratio.
- [ ] Outputs per-shot JSON with all frames' counts, ratios, blobs, and deltas.
- [ ] Reports: 19 missed makes caught count, 28 correct makes caught count, 93 misses fired-on count at 0.05/0.08/0.10/0.12.
- [ ] **Asserts 0 real misses fired at threshold 0.08** (prints FAIL if not 0).
- [ ] Generates 39 crop PNGs with net ROI box and orange highlight.
- [ ] All outputs to `C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check\`.
- [ ] No edits to `ai_bridge.py`, `net_detector.py`, any protected file.
- [ ] `applied_to_core` stays `false`.
- [ ] No `config.yaml` created; constants at top of `net_check.py`.

---

## 12. Golden Rules Compliance

| Rule | How This Plan Respects It |
|------|---------------------------|
| **No looser cutoffs** | v6 rule thresholds untouched. This check only measures; its threshold is reported, not applied to any detector. |
| **No banned trials** | No interpolation, ByteTrack, DeepSORT, early windows, wider column, hoop recenter. Pure pixel measurement in a fixed ROI. |
| **No hard-coded results** | Measures real video frames; outputs raw counts. |
| **`applied_to_core` = false** | New file only in `.team/shot_detectors/pixel_miss/`. Core untouched. |
| **Holdouts never opened** | No unseen set in this step (Adrian Q4 has no tracks). |
| **Output outside repo** | All images/JSON to `Liberty_Shot_Outputs/`. Sandbox uses `.team/shot_outputs_test/`. |

---

## 13. Next Step (After VETTED)

This plan goes to `NEXT_TASK.md` only after the Vetter stamps it `VETTED`. The Coder (Cursor sandbox) implements `net_check.py`. Results inform whether a `net_rim_supplement.py` detector (Task 1 Step 4 in work order) is viable.

---

**End of Plan** — `.team/specs/15_net_check_plan.md`