# Cursor to Hermes, 2026-10-12 morning

Scott spent the evening of 2026-10-11 and the morning of 2026-10-12 pasting proposals from Gemini Code into Cursor. Gemini cannot see GitHub or this repo. Scott uploads files and pastes replies. You are taking that conversation. Measure the next proposal the same way. Write the reply so Scott can paste it back. Do not put Gemini's classes into `net_detector.py`, `event_generator.py`, or `ai_bridge.py`.

Your other job is unchanged. Read `docs/agent_handoffs/HERMES_CURSOR_2026-10-11.md`. The 6 misses still called makes are yours. No tag time inside a rule. `applied_to_core` stays false.

## How to score a hoop proposal

The hoop file on disk is raw detections, one about every 2 seconds. Stabilizing happens in memory when `load_hoop_track` calls `stabilize_hoop_track`. `save_hoop_track` does not write the median back.

- Raw track: `C:\Users\scott\LibertyData\jason-brad-share\for-drive\data\hoop_tracks\jrhigh_adrian__or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json` (1949 samples). It is not in the git repo. `data/hoop_tracks` in the repo is empty. There is no second game's hoop track.
- Tag hoops: `C:\Users\scott\AppData\Local\Temp\v6_tracks.json`. Each row has `t` and `hoop` (center x, center y, width). 111 rows. Two tag times are duplicated (2738600 and 2747200), so the answer key is 109 unique shots. Score all 111 rows anyway, the same way these numbers were produced.
- Python: `C:\Users\scott\AppData\Local\Programs\Python\Python312\python.exe`
- Film: `uploads\nfhs_gam0a66d85e12.mp4`, 1920×1080, 25 fps.
- For each tag, take the nearest raw sample within 2500 ms. The window is that sample, the 3 before it, and the 3 after it.
- The current vote sorts x and y separately and keeps the middle of each list. That is `stabilize_hoop_track` with `half = 3`.
- A hit is within 150 pixels of the grouped tag hoop. Baseline: **89 of 111**. Report closer by more than 30 pixels and farther by more than 30 pixels. A win on 00:41 or 43:06 that drops the 89 is not a win.
- Do not use a tag time or a tag result inside the rule. The 111 rows are the score only.

## What the median actually does

`scripts/build_hoop_track.py` steps every 2000 ms, calls `detect_hoop_cv`, and appends one dict if it hits. Fields stored: `timestamp_ms`, `frame`, `x`, `y`, `r`, `net_bottom`, `area`, `confidence`, `source`. There is no `net_score`. 1947 samples are `cv_rim`, one `cv_backboard`, one `cv_net`.

`stabilize_hoop_track` copies the current sample, replaces x and y with the separate medians, and sets `source` to `median_rim`. It does not read confidence. The median of x and the median of y can come from different samples, so the lock can be a point that was never detected. At 00:41 that phantom is (562, 213). The seven raw x values are 10, 562, 797, 811, 648, 311, 409. The middle x is 562. The two rim points, 797 and 811, sit at the end of the list.

Consecutive raw steps: median 100 pixels. 1227 of 1948 are longer than 50. 909 are longer than 120. 824 are longer than 150. A real rim on this sideline camera does not sit still in screen pixels.

## The three locks Gemini was trying to fix

- **00:41**, tag 41900, grouped rim (828, 260). Median lock (562, 213), 270 pixels away, on the backboard arm. The raw sample at 42000 is already the rim at (811, 230). The arm is one of the other samples in the 14-second window. Every sample in that window already scores net 1.0, so a net-score cutoff does not move it.
- **26:43**, tag 1603900, grouped rim (826, 272). Median lock about (1317, 170), about 500 pixels away, on the EXIT sign. The raw sample at the tag is the sign. Earlier samples in the window are a real rim while the camera is still panning (356, then 505, then 824). Sign confidence is about 0.52. Rim confidence is about 0.74 to 0.77.
- **43:06**, tag 2586500, grouped rim (798, 262). Median lock (1325, 159), 538 pixels away, on the EXIT sign. Four sign samples against three rim samples. The rim samples are about (748–775, 226–231) with confidence about 0.75. The sign samples are about (1325–1329, 158) with confidence about 0.53. Independent medians of x and of y land on the sign because four x values beat three.

(311, 158) at 46 seconds, confidence 0.726, is a real rim after the camera moved. It is not a bracket. The crop shows a red rim and a white net.

## What was measured, and the score

None of these were written into `net_detector.py`.

| Proposal | Within 150 of 111 | What it did on the named locks |
|---|---|---|
| Current separate x/y median | 89 | 00:41 phantom (562, 213) at 270px. 26:43 and 43:06 on the sign. |
| 2D medoid of the whole window | 89 | 00:41 returns the real arm sample (562, 214), still 270px. 43:06 stays on the sign. The medoid is the middle of the cloud, not the tight group. |
| Largest cluster, 50px, then medoid | 70 | 00:41 fixed, (797, 230), 43px. 43:06 stays on the sign because 4 samples beat 3. Farther by >30px on 40 tags. |
| Same idea at other distances | 70 to 85 | 50px → 70, 150px → 77, 300px → 80, 500px → 85. None beat 89. |
| Confidence-weighted distance formula | 59 | 43:06 stays on the sign. The single highest-confidence sample there is the rim, 61px away, and the formula does not pick it. 00:41 goes to (311, 158), 527px. Highest-confidence sample alone, no distance term: 48. |
| Pan chain, 120px, start at the center sample | 75 | 00:41 fixed, (804, 230), 38px. 43:06 fixed, (760, 228), 51px. 26:43 stays on the sign, 530px, because the raw sample is the sign. Raw sample alone is 76. The chain gives back the cases where the raw point is wrong and the neighbors were the correction. |
| Consensus support, 120px times the index gap, center always kept | 78 | 26:43 stays on the sign. The sign has support 3. The rim samples are spread by the pan and are not the dense group. 00:41 keeps all 7 and the phantom remains. Letting the center drop: 79. |
| Velocity hold at 150px, freeze on a longer step | 9 | Freezes 1599 of 1949 samples. 00:41 stuck at (1790, 142). |
| Smoothest 3-point run (lowest acceleration) | 84 | 00:41 fixed, 43px. 43:06 returns the sign, acceleration 3. A stationary sign is the smoothest path. |
| Highest-confidence cluster, 40px, floor 0.60 | 49 | 43:06 fixed, (760, 228), 51px. 26:43 moves to (505, 198), 329px, a rim from earlier in the pan. 00:41 goes to (311, 158), 527px. 3314200 goes from 137px (median) to 573px. Farther by >30px on 66 tags, closer on 12. |

Checks that were not a whole-game vote:

- Interior brightness spread of the box, reject if std < 5. At 00:41 the arm is 35.8 and the rim is 37.2. The arm is an open truss. The cutoff rejects neither.
- Hue and saturation. The arm is in the red mask, hue about 171, saturation about 146 ± 44. The rim is hue about 171, saturation about 156 ± 41. The orange mask (hue 8–22, saturation and value at least 90) is not what caught the arm. The one orange sample in that window is at the left edge, (10, 206), hue 12.6, saturation spread 9, which is tighter than the rim. The left edge of that frame is the wall, a yellow sheet, and folding chairs. On that frame `_red_rims` emits no candidate.
- A 30-pixel border reject. Tagged rim centers on this film sit between x=500 and x=1400. Fifteen raw samples sit on the frame border. Some are a rim sliding off as the camera pans. The arm is at x=562.
- Height penalty for y under 20% of the frame (y under 216). The only term that favors (311, 158) over the rim at (797, 230) is height, and the gap is 0.045. Both nets score 1.0, so the visual term is 0.15 for both. Neither gets the dark-above bonus. Area favors the lower rim. Tagged rim centers run from y=124 to y=277. The penalty would hit 23 of 111.
- Court box x 80–1840, y 40–450. 55 raw samples are outside. Four tags have their nearest raw sample outside, all just past the right edge (536900, 1437100, 2479100, 2508600). After the median, zero stabilized samples are outside, and zero tags receive an outside point. Those four come back 60, 50, 149, and 71 pixels from the tagged rim. `_hoop_on_court` is used only inside `_ball_at_hoop` (ball-box choice and shot peak). The precision shot loop copies `hoop_at` into `detected_hoop` and does not run that box check.
- Hardcoded sign box x 1300–1380, y 150–180, and arm box x 550–580, y 200–225. The sign box contains 61 raw samples and one real tagged rim: at 3314200 ms the grouped hoop is (1300, 156). The arm box contains 10 raw samples and no tagged rim center. The other arm samples in the 00:41 window are outside that 30-by-25 patch. Setting confidence to 0.01 would not change the median, because the median does not read confidence.
- Both neighbors within 50 pixels means "static fixture." That drops 14 of 111 tags, the ones where the camera holds on the rim. At 26:43 the sign is kept, because the step onto it is 550 pixels. At 3314200 the raw sample is (1070, 171), not the tagged coordinate, with steps of 29 and 52, so it is not rejected.

## Confidence, so you do not recompute it

`_red_rims` writes confidence as:

`0.22 + 0.28 * min(1, area/1400) + 0.30 * max(bright, net * 0.5) + 0.20 * height`

plus 0.05 if the dark-above fraction is over 0.4. Capped at 0.97. Dropped under 0.30.

`_net_score` does not look inside the orange box. The patch is underneath: x from `cx - 1.3r` to `cx + 1.3r`, y from just below the center to `3.2r`. A pixel counts if saturation is at most 70 and value is at least 110. Hue is ignored. Score is the fraction times 2.4, capped at 1.0, times 0.4 if the patch is shorter than `r`. About 42% of the patch saturates the score. That is why an arm, a door, and a net can all score 1.0.

The search band is the top 42% of the frame. On this film that is rows 0–453. A blob center is kept only from y=45 to y=326 inside that strip.

On the 46-second frame the split is exact:

- (311, 158), area 1280, stored 0.726: area 0.256, visual 0.15, height 0.10, dark 0.
- (797, 230), area 1385, stored 0.702: area 0.277, visual 0.15, height 0.055, dark 0.

## Where Gemini left off

The last reply Scott can paste told Gemini this: the 40-pixel highest-confidence cluster is within 150 pixels on 49 of 111, against 89 for the current median. It fixes 43:06 (51 pixels) and misses 26:43 (329 pixels) and 00:41 (527 pixels). It is farther by more than 30 pixels on 66 tags. The 0.60 floor never decides those windows, because the winning scores are all over 0.72. The next fact to use is those 66 tags: the highest confidence in the 14-second window is a different camera position, not a low-confidence sign.

Gemini's pattern has been to send a new class and ask one question about the code. Answer the question from the file, then give the whole-game count. Do not implement the class in order to answer.

## What you may tell Gemini

Gemini does not have the code. If Scott asks for a file, the useful one is still `net_detector.py` plus this note. Do not send tag times, the database, or a list of the 111 shots as something to code against.

A proposal that wins has to beat 89 of 111 within 150 pixels, on this track, with no tag times inside the rule, and it has to move 00:41, 26:43, and 43:06 toward the rim without pushing other tags off. Say the number before saying it works.

## Proven / Inferred / Unknown

**Proven:** Every score in the table was run on the raw hoop JSON and `v6_tracks.json` on 2026-10-11 night or 2026-10-12 morning. The confidence split was recomputed on the film frame and matched the stored 0.726 and 0.702. The (311, 158) crop is a rim and a net. The left-edge frame at 36 seconds shows wall, a yellow sheet, and chairs, and `_red_rims` returned no candidate.

**Inferred:** The 14-second window is the reason a pan and a sign get mixed. A vote that trusts one high-confidence sample from anywhere in that window follows the camera to the wrong moment.

**Unknown:** A rule that keeps the raw sample when it is the rim and uses the neighbors only when the raw sample is the sign or the arm, without a tag time to say which. Not found in this session.
