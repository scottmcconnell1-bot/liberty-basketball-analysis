REJECTED by Claude Code, 2026-10-29: the plan's idea (look only at the net column under the rim just after the ball arrives) is right, but 5 things must change. Checked by reading net_detector.py 459-470 and 53-99, measure_net_moved.py 160-177, and the step-1 counts.
1. Count error (sections 6, 10, 11): real misses are 93, not 121. 140 shots = 47 real makes (28 correct + 19 missed) + 93 real misses. 121 wrongly includes the 28 correct makes. Report the 28 correct makes as their own line (the check should catch them too - a sanity check).
2. Rim is the same color as the ball (net_detector.py:99 "The ball and this rim land in the same orange hue on this camera"). A raw orange count in the net box will also count rim, hands, skin and jerseys under the rim on rebounds, so it will fire on misses. Add a per-shot BEFORE frame (same box, a frame before the ball arrives, e.g. peak-3 as in net_moved_after_shot) and report the CHANGE in orange pixels, plus the size of the largest single orange blob (the ball is one round blob; the rim is a wide band).
3. Color range must match net_detector.py:74-76: red1 (0-14), red2 (165-180) AND orange (8-22, sat>=90, val>=90). The plan leaves out the orange range.
4. Section 6 "Unseen: Adrian Q4+ (tagged, held out)" is wrong: Adrian Q4 has no tracks built. Say only: no unseen set in this step; any threshold picked from these 140 shots is build-set only and is not a result until checked on unseen shots (plan 13's open question to Scott).
5. Drop config.yaml; keep the constants at the top of net_check.py (no new dependency). Files allowed: net_check.py and README.md.

PLAN - NOT BUILT OR MEASURED YET

---

# Net Check Plan â€” Task 1 Step 3: Post-Rim Net Region Read-Only Measurement

**Author:** Hermes (Architect)  
**Date:** 2026-10-29  
**Status:** Plan for Vetted implementation  
**Gate:** Must pass Vetter review before OpenCode/Cursor implements

---

## 1. Purpose

The v6 rule (`run_saved_v6_rule` in `ai_bridge.py`) sees the ball cross the rim on 12 of 19 missed makes but then rejects them on **after-rim tests** (column_ratio_low, ball_went_up, ball_box_jump, ball_bounces_up, ball_starts_well_below, short_net_depth, sideways_drift). On the other 7 missed makes, **no_valid_crossing** is found at all (missed_make_11 has zero ball points).

The tracker is unreliable after the rim: it jumps to heads, loses the ball in the net, follows the rebound. `net_moved_after_shot` as-is (Step 1) catches 6/19 missed makes but fires on 38/93 misses.

**This step adds a separate, read-only check that looks only at the net region directly under the rim in the few frames after the ball reaches the rim, and asks: "Is the ball inside the net?"** â€” independent of where the tracker jumps later.

---

## 2. Scope

- **Read-only measurement only.** No edits to `ai_bridge.py`, `net_detector.py`, `models/ball_detector.pt`, `ball_confidence`, `schema.sql`, or any protected core file.
- **No cutoff changes.** The v6 rule thresholds stay exactly as they are (0 false makes must remain 0).
- **New code only** in `.team/shot_detectors/pixel_miss/` (one new file).
- **Measured on the same 140 tagged shots** (Notus A1 Q1: 31, Adrian Q1â€“Q3: 109).
- **Output** written to `C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check/` (outside repo).
- **Sandbox test run** writes to `.team/shot_outputs_test/net_check/` (never committed).
- **Reuses the review page's crops/hoop box** so Scott can see what the check saw.

---

## 3. What the Check Reads (Image Pixels)

All coordinates are **image pixels**, relative to the saved hoop track for each shot (`hoop_x`, `hoop_y`, `hoop_w` from `v6_tracks.json`).

### 3.1 Net Region (ROI)

From `net_detector.py:_net_box` (line 459):
- **x-range:** `hoop_x Â± 1.1 Ã— rim_r` where `rim_r = hoop_w / 2`
- **y-range:** `hoop_y + 0.25 Ã— rim_r` to `hoop_y + 2.8 Ã— rim_r`

This is a column under the rim: width â‰ˆ `2.2 Ã— rim_r`, height â‰ˆ `2.55 Ã— rim_r`.

### 3.2 Frames to Sample

Let **peak_frame** = the absolute video frame where the ball *reaches the rim*:
- For shots **with a crossing**: the crossing frame (ball goes from above to below `hoop_y` within 0.55 Ã— `hoop_w`).
- For shots **without a crossing** (`no_valid_crossing`): the frame of the closest ball point to `(hoop_x, hoop_y)` in the saved track (same as `peak_from_track` logic in `measure_net_moved.py` line 172â€“176).

Sample **5 frames after the peak frame**: `peak_frame + 1, +2, +3, +4, +5`.

**Rationale:** The ball passes through the rim and enters the net in ~1â€“3 frames at 25 fps. Sampling 5 frames after peak captures the ball in the net before the tracker loses it or jumps away.

### 3.3 What to Measure Per Frame

For each of the 5 frames, within the net ROI:
1. **Orange pixel count** â€” HSV range for the ball (red/orange: hue 0â€“14 or 165â€“180, sat > 70, val > 70). Count pixels in the ROI matching this.
2. **White/gray pixel count** â€” HSV range for the net (white: sat < 60, val > 155; gray: sat < 55, val 70â€“190). Count pixels in the ROI matching this.
3. **Orange/white ratio** â€” `orange_px / max(1, white_px + gray_px)`.

**Output per shot:** a JSON object with:
```json
{
  "t": 342800,
  "film": "adrian",
  "peak_frame": 8573,
  "has_crossing": true,
  "frames": [
    {"frame": 8574, "orange_px": 120, "white_px": 450, "gray_px": 320, "orange_ratio": 0.16},
    {"frame": 8575, "orange_px": 95,  "white_px": 480, "gray_px": 350, "orange_ratio": 0.12},
    {"frame": 8576, "orange_px": 60,  "white_px": 500, "gray_px": 380, "orange_ratio": 0.07},
    {"frame": 8577, "orange_px": 15,  "white_px": 520, "gray_px": 400, "orange_ratio": 0.02},
    {"frame": 8578, "orange_px": 5,   "white_px": 530, "gray_px": 410, "orange_ratio": 0.01}
  ],
  "max_orange_ratio": 0.16,
  "max_orange_frame": 8574
}
```

---

## 4. Decision Rule (for measurement reporting only)

**A shot is flagged as "net check caught this missed make" if:**
- `max_orange_ratio` across the 5 frames â‰¥ **0.08** (tunable threshold for reporting; the measurement reports the raw numbers, this threshold is only for the summary table).

**Why 0.08:** The net is mostly white/gray. An orange ball in the net should show a measurable orange pixel cluster. On misses, the net shows only white/gray. The exact threshold is reported but not baked into any detector yet â€” this step only measures.

---

## 5. How to Find the "Ball Reached the Rim" Frame (No Crossing Case)

Reuse the existing logic from `measure_net_moved.py:peak_from_track` (lines 171â€“177):

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
| **Build (tagged, used for tuning)** | Notus A1 Q1 (31) + Adrian Q1â€“Q3 (109) = 140 | Measure the check on all 19 missed makes + all real misses |
| **Unseen** | Adrian Q4+ (tagged, held out) | Not scored in this step; reported as "n/a" |

Run the check on **every shot in the build set** (140 shots). Report:

### For the 19 missed makes:
- How many have `max_orange_ratio â‰¥ 0.08` (caught)
- Per-shot: `max_orange_ratio`, `max_orange_frame`, `has_crossing`

### For the real misses (121 shots):
- How many have `max_orange_ratio â‰¥ 0.08` (**must be 0 to even consider this check**)
- Count of false fires at each threshold (0.05, 0.08, 0.10, 0.12)

**Success bar for even considering this check:** fires on **0 real misses** at the chosen threshold.

---

## 7. Output Files

All written to `C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check\`:

```
net_check/
â”œâ”€â”€ build_results.json          # Per-shot raw measurements (140 objects)
â”œâ”€â”€ summary.md                  # Table: missed makes caught, misses fired on
â”œâ”€â”€ missed_makes_detail.md      # 19 rows with max_orange_ratio, frames
â”œâ”€â”€ misses_fired_on.md          # Any misses with ratio > 0 (should be empty at threshold)
â””â”€â”€ crops/                      # Reuse review page crops: one PNG per shot showing
    â”œâ”€â”€ missed_make_01/         # the net ROI with orange pixel overlay on the
    â”‚   â””â”€â”€ net_check_010.png   # peak+1 frame (frame where max_orange_ratio occurs)
    â””â”€â”€ ...
```

**Crops:** For each of the 39 review-page shots (19 missed makes, 10 correct makes, 10 misses), save one PNG: the frame at `max_orange_frame` (or `peak_frame + 2` if no orange found), cropped to the review page's square crop (centered on hoop, size `max(hoop_w * 3, 240)`), with the net ROI box drawn in blue and orange pixels highlighted in red.

---

## 8. Files the Coder May Create (Only New Files)

```
.team/shot_detectors/pixel_miss/
â”œâ”€â”€ net_check.py                # Main measurement script (reads v6_tracks, tags, videos; writes outputs)
â”œâ”€â”€ config.yaml                 # Thresholds (orange_ratio â‰¥ 0.08, HSV ranges, 5 post-peak frames)
â””â”€â”€ README.md                   # One-paragraph description + run command
```

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
2. For each build-set shot, compute `peak_frame` and `has_crossing` per Â§5.
3. Read 5 frames after `peak_frame` from the video.
4. For each frame, crop the net ROI (Â§3.1), count orange/white/gray pixels (Â§3.3).
5. Write `build_results.json`, `summary.md`, `missed_makes_detail.md`, `misses_fired_on.md`.
6. Generate crops for the 39 review-page shots (Â§7).
7. Print console summary with counts.
8. **Exit. No further steps.**

---

## 10. Console Output Format

```
=== NET CHECK SUMMARY ===
Build shots: 140
Missed makes: 19
  Caught (orange_ratio â‰¥ 0.08): X
  By crossing status:
    Has crossing: Y caught / 12
    No crossing:  Z caught / 7
Real misses: 121
  Fired on (orange_ratio â‰¥ 0.08): 0   <-- MUST BE 0
  Fired on (orange_ratio â‰¥ 0.05): N
  Fired on (orange_ratio â‰¥ 0.10): N
  Fired on (orange_ratio â‰¥ 0.12): N

Per missed make:
  missed_make_01 (notus_a1 t=64200):  max_orange=0.XX at frame NNNNN  crossing=True
  ...
  missed_make_19 (adrian t=3095700):  max_orange=0.XX at frame NNNNN  crossing=False

Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check\build_results.json
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check\summary.md
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check\missed_makes_detail.md
Wrote: C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check\misses_fired_on.md
Crops: 39 PNGs in crops/
STOP â€” measurement complete, no detector changes
```

---

## 11. Verification Checklist (Coder Confirms Before Done)

- [ ] Reads `v6_tracks.json` / `v6_tracks_notus_q1.json` and tag files (read-only).
- [ ] Computes `peak_frame` per Â§5 (crossing frame or closest-ball frame).
- [ ] Samples exactly 5 frames: `peak_frame + 1` through `peak_frame + 5`.
- [ ] Net ROI matches `net_detector.py:_net_box` (x Â± 1.1Ã—rim_r, y + 0.25Ã—rim_r to +2.8Ã—rim_r).
- [ ] HSV ranges: orange (hue 0â€“14,165â€“180; sat>70; val>70), white (sat<60; val>155), gray (sat<55; val 70â€“190).
- [ ] Outputs per-shot JSON with all 5 frames' counts and ratios.
- [ ] Reports: 19 missed makes caught count, 121 misses fired-on count at 0.05/0.08/0.10/0.12.
- [ ] **Asserts 0 real misses fired at threshold 0.08** (prints FAIL if not 0).
- [ ] Generates 39 crop PNGs with net ROI box and orange highlight.
- [ ] All outputs to `C:\Users\scott\Documents\Liberty_Shot_Outputs\net_check\`.
- [ ] No edits to `ai_bridge.py`, `net_detector.py`, any protected file.
- [ ] `applied_to_core` stays `false`.

---

## 12. Golden Rules Compliance

| Rule | How This Plan Respects It |
|------|---------------------------|
| **No looser cutoffs** | v6 rule thresholds untouched. This check only measures; its threshold is reported, not applied to any detector. |
| **No banned trials** | No interpolation, ByteTrack, DeepSORT, early windows, wider column, hoop recenter. Pure pixel measurement in a fixed ROI. |
| **No hard-coded results** | Measures real video frames; outputs raw counts. |
| **`applied_to_core` = false** | New file only in `.team/shot_detectors/pixel_miss/`. Core untouched. |
| **Holdouts never opened** | Adrian Q4+ not scored; reported as n/a. |
| **Output outside repo** | All images/JSON to `Liberty_Shot_Outputs/`. Sandbox uses `.team/shot_outputs_test/`. |

---

## 13. Next Step (After VETTED)

This plan goes to `NEXT_TASK.md` only after the Vetter stamps it `VETTED`. The Coder (Cursor sandbox) implements `net_check.py`. Results inform whether a `net_rim_supplement.py` detector (Task 1 Step 4 in work order) is viable.

---

**End of Plan** â€” `.team/specs/15_net_check_plan.md`
