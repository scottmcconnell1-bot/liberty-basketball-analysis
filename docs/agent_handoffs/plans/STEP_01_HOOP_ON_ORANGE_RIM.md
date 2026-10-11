# Step 1 — Hoop on the orange rim

Read `00_INDEX.md` first for the rules that apply to every step. Source of scope: `PROGRAM_FOR_JASON_2026-10-10.md` section 6, step 1.

**Owner:** Cursor. **Runs in parallel with:** Step 2. **Blocks:** Step 3.
**Offline only. No database writes. No production detection pass.**

## The problem in one paragraph

Some hoop boxes on the Adrian film sit on the glass or the backboard, above the orange rim. When the locked rim is too high, a ball at the real rim is already "below" the box, so a miss reads as a make. `detect_hoop_cv` already rejects a round blob, so the ball is no longer chosen as the rim. It does **not** yet reject a box whose center is on the glass.

## The frames to open

| Timestamp | ms | What is wrong now |
| --- | --- | --- |
| 14:56.6 | 896600 | Hoop box on the backboard, above the rim |
| 29:36.5 | 1776500 | Hoop box on the top corner of the glass. A later box on this frame is a ball in a player's hands. |

Also open a handful of frames from shots that are **already called correctly**. The fix must not move those.

## The bigger target: the second-half lock

The two frames above are both in the **first half**. They are not the main event. From `JASON.md`:

| Quarter | Shot rows | Rows where a make was actually seen |
| --- | --- | --- |
| Q1 | 46 | 19 |
| Q2 | 37 | 14 |
| **Q3** | **86** | **2** |
| Q4 | 37 | 4 |

After 32:15 there are **123 shot rows: 6 called a make, 117 called a miss, and all 117 have both `through_rim` and `net_moved` false.** The first half saw 83 shots and called 33 of them makes. About 40% of first-half shots show a make; 2% in Q3.

`JASON.md` reads that as "the hoop or net lock failing on the second-half camera", and says plainly: **"That is not yet checked on frames."** Checking it on frames is this step.

Since then, `load_hoop_track` was given the ±3-sample median and the hoop track was extended to the end of the film (64:56), so Q3 is no longer stuck on the first-half rim. **Whether that actually fixed the second-half lock has not been verified on frames.** Verify it. If Q3 still reads 2 makes in 86 shots after steps 1 and 2, the rim is still wrong there and no make/miss rule will save it.

Open frames from the Q3 stretch, not only the two first-half frames. Q3 runs from 32:15.0 to 55:17.1.

`ACTIVE.md` files this as formally **Unknown**: *"Why the lock fails in Q3 and Q4. Whether the fix is a setting, a rule, or the detector."* That is the question this step answers. Q3 has **86 shot rows against about 42 real attempts Scott tagged** (32 field goals, 10 free throws) — so Q3 is over-producing shots and almost never seeing a make.

## What the round-blob reject already achieved — do not undo it

From the 2026-10-09 bullet: after `detect_hoop_cv` started rejecting a round blob, *"Checked on the frames: the mark sits on the rim while the ball is in the air, including the Alvarez miss at 4:10 where the old search had locked the ball."*

So 4:10.2 is a **solved** frame and belongs in your do-not-regress set alongside the already-correct shots. The failure mode it fixed — the ball being locked as the rim — is exactly what a loosened orange filter would bring back.

Useful existing artifacts: `tag-exports/` holds hoop probe images from earlier frame checks (`_hoop_probe_q1end.jpg`, `_hoop_probe_q2mid.jpg`, `_hoop_probe_ht.jpg`, `_hoop_probe_ft.jpg`, `_hoop_orange.jpg`, `_hoop_grid_q2.jpg` and others). Look at these before generating new ones.

**Another detection pass of this film will reprint the same baskets until the rim and net read changes.** Do not run one expecting a different answer.

## Where the code is

All in `net_detector.py`.

| Function | Line | Role |
| --- | --- | --- |
| `detect_hoop` | 31 | Entry point. CV first; falls back to court pose under 0.35 confidence. |
| `detect_hoop_cv` | 46 | Orange rim first, then `_best_backboard`, then hanging nets |
| `_rim_mask` | 70 | HSV bands: red 0–14 and 165–180, orange 8–22, all sat/val ≥ 70–90 |
| `_red_rims` | 82 | The candidate filter. **This is where the gap is.** |
| `_best_backboard` | 233 | Already finds the board. Currently only used as a fallback. |
| `_near_backboard` | 260 | Already computes board proximity. Currently unused by `_red_rims`. |
| `_hoop_from_backboard` | 270 | Derives a hoop from a board |
| `stabilize_hoop_track` | 401 | Median of ±3 samples (`_HOOP_MEDIAN_HALF = 3`), line 398 |
| `load_hoop_track` | 428 | Reads the saved track and stabilizes it |

Helper scripts that already exist and should be reused rather than rewritten:
`scripts/build_hoop_track.py`, `scripts/_probe_hoop_frame.py`.

## What `_red_rims` already rejects

Read lines 82–137 before changing anything. The existing gates are:

- area outside 80–8000
- width outside 12–160, height outside 4–70
- `bh > bw * 1.5` (too tall)
- `bw < bh * 1.45` — the round-blob reject. The ball is about 44 by 46, the rim about 65 by 30.
- center above 10% or below 72% of the ROI height
- the two top corners (exit sign territory)
- `bright < 0.08 and cy > 52%` of ROI height — wall cans sit lower than a backboard
- final confidence under 0.30

Confidence is `0.22 + 0.28*area_bonus + 0.30*max(bright, net*0.5) + 0.20*height_bonus`, plus 0.05 when `dark_above > 0.4`.

Note what this means: `height_bonus` **rewards being higher in the frame**. A box on the glass scores better than the rim under it on that term. That is a plausible reason the glass wins on 896600 and 1776500, but it is a hypothesis — confirm it on the actual frames before acting on it.

## The work

1. **Measure before you change.** On 896600 and 1776500, dump every candidate `_red_rims` returns, with its box, its area, its `bright`, `net`, `dark_above`, `height_bonus`, and its final confidence. Record which one wins and by how much. Without this, any fix is a guess.
2. **Add a glass reject.** A candidate whose center sits inside the backboard quad, above the rim band, is not the rim. `_best_backboard` (line 233) already returns the board and `_near_backboard` (line 260) already scores proximity — both exist and are not wired into `_red_rims`. Prefer wiring these in over inventing a new detector.
3. **Prefer the band under the board.** When a board is found, the rim is the orange band at the bottom edge of it, not the top corner. `_hoop_from_backboard` (line 270) already encodes that geometry.
4. **Re-dump the same candidates** and show the winner changed on the two bad frames and did not change on the good ones.

Options allowed by the roadmap, in preference order: the orange-band finder already in `net_detector.py`; or a model that genuinely emits a hoop class.

**v6 does not emit a hoop class.** It has one class, `basketball`, loaded and checked 2026-10-10. Any approach that filters detections for a class named `hoop`, `rim`, or `basket` against v6 gets an empty list. That is exactly the bug in `Scott_Hermes` `6143e83` and still in `cbeb0ed` — `ai_bridge.py:662` `find_hoop_on_orange_rim` filters on those three names and `ai_bridge.py:757` then hardcodes `hoop_on_rim = True`. Do not repeat it, and do not build on it.

## Exit test

All three must hold. Report the evidence for each.

1. On 896600 and 1776500 the chosen box sits on the **orange rim band**, not the glass and not the backboard. Show the box coordinates and a crop or an overlay for each frame.
2. A one-sample jump onto the glass does not move the locked rim. The `±3` median in `stabilize_hoop_track` is the mechanism; show it holds with the new candidate filter in place.
3. These still pass:
   ```
   pytest tests/test_net_detector.py::test_a_round_ball_does_not_become_the_rim \
          tests/test_net_detector.py::test_a_one_sample_jump_does_not_move_the_rim
   ```
   (`tests/test_net_detector.py:45` and `:66`.)

A passing test alone is not verification. The frames are the verification.

## Do not, on this step

- Do not write database rows. Nothing from this step reaches the ledger.
- Do not touch `models/ball_detector.pt` or `ball_confidence`. That is a Scott gate.
- Do not start a production detection pass of this film expecting new baskets.
- Do not call the rim red paint. The hue bins in older notes are camera numbers.
- Do not treat `Scott_Hermes` `6143e83` or PR #168 `cbeb0ed` as this step. Neither looks at the picture.
- Do not reorganize the core sequence.

## Hand off with

The Proven / Inferred / Unknown block from `00_INDEX.md`, plus the before-and-after candidate dump for both frames, and the pytest output. Then update the paragraph in `ACTIVE.md` that this changes.
