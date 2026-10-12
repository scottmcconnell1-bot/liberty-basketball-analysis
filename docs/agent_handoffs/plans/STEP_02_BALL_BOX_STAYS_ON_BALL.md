# Step 2 — Ball box stays on the ball

Read `00_INDEX.md` first for the rules that apply to every step. Source of scope: `PROGRAM_FOR_JASON_2026-10-10.md` section 6, step 2.

**Owner:** Cursor. **Runs in parallel with:** Step 1. **Blocks:** Step 3.
**Offline only. No database writes.**

## The problem in one paragraph

The kept ball box leaves the ball. It jumps to the wall, or to a ball in a player's hands well below the rim, while the ball in the air is still visible. Two separate things also knock the box out for a run of frames: the white net cords cross the ball and change how it looks, and at production image size 320 a ball in a 1920-wide frame is about 7 pixels, so a clean ball in the air blinks for a frame or two anyway. Those two are different problems — do not treat the blink as a net problem.

## The frames to open

| Timestamp | ms | What is wrong now |
| --- | --- | --- |
| 25:15.7 | 1515700 | The box leaves the ball and sits on the wall left of the backboard |
| 40:55.6 | 2455600 | Hoop is on the rim, then the box is on a ball in a player's hands well below the rim, then a box is back at the rim |
| 29:36.5 | 1776500 | A later box is a ball in a player's hands (this frame is also a step-1 frame) |
| 12:35.4 | 755400 | **Control case.** The ball hits short and falls in the lane in front of the basket. This is a **miss**. From this camera, image-down looks like a make if "below the rim" is the test. It must stay a miss. |
| 14:56.6 | 896600 | Step-1 frame. Check the ball box here too. |

## Where the code is

All in `event_generator.py`.

| Symbol | Line | Role |
| --- | --- | --- |
| `build_ball_track` | 290 | Picks one ball box per frame. **This is where the gap is.** |
| `_ball_on_carried_player` | 261 | Rejects a box on a player present just before and just after |
| `_people_near` | 244 | Finds people in the surrounding frames |
| `_ball_at_hoop` | 191 | Box is above the locked rim and within `_RIM_MAX_DIST` |
| `_hoop_on_court` | 183 | Sanity box: x 80–1840, y 40–450 |
| `_PLAYER_GAP_FRAMES = 20` | 216 | 0.8s at 25fps |
| `_PLAYER_SAME_SPOT = 160.0` | 218 | Same player, not one across the court |
| `_PLAYER_BOX_PAD = 24.0` | 219 | |
| `_RIM_MAX_DIST = 280.0` | 179 | |
| `_RIM_CONF_FLOOR = 0.35` | 180 | |

Read `build_ball_track` (290–328) before changing it. Today it does, per frame: sort candidates by confidence; if more than one, drop the ones on a carried player; then if any candidate is at the hoop, take the one nearest the rim; otherwise take the highest-confidence box.

**What is missing:** there is no continuity check at all. Nothing compares this frame's chosen box to the last accepted one. A box on the wall is accepted as readily as a box on the ball, as long as nothing else that frame outranks it. That is the direct cause of 1515700.

## The 28 missed makes are already broken down by cause

From the 2026-10-09 bullet in `ACTIVE.md`, on the rule that scored 80 of 111. The 28 makes it missed were **four different failures**, not one:

| Cause | Count |
| --- | --- |
| The ball box drops out for 14–22 frames **at the rim** | 8 |
| The box drops out **on the way to the floor** | 7 |
| The tracked fall **stops short of 300 pixels** | 4 |
| **No ball above the rim** in the tag window at all | 7 |
| The box jumps back up | 2 |

The first two are this step's problem. The fourth is step 1's (no rim means no "above the rim"). Report which bucket each frame you fix belongs to — a fix that only addresses one bucket should say so rather than claiming the ball track is fixed.

Two mechanisms are already distinguished in the record and should not be conflated:
- **The net**: on a trip through the rim the box drops while the white cords cross the ball and returns when the ball is a whole circle again — **39 trips**.
- **The blink**: the same detector drops a clean ball in open air for a frame or two — **116 blinks**.

"Those missed frames stay unmarked even at a very low score, so it is not a cutoff sitting just under the box." Lowering confidence does not reach them, and `ball_confidence` is a Scott gate anyway.

Also already tried and failed: searching every frame between sightings, cropped along the path, found **2 new ball boxes in 576 gaps**. A round orange blob on those frames filled 529 frames and added **one false make (280200) with no new make**. Projecting a straight line across gaps of up to 15 frames does not recover the rest.

## The work

1. **Measure before you change.** On each frame above, dump every ball candidate with its box, confidence, and which branch of `build_ball_track` selected the winner. Say where the winner sits in plain words ("on the wall left of the backboard", "on the ball in flight", "in a player's hands").
2. **Add continuity, not another model.** The ball in flight moves a bounded distance between frames. A candidate whose displacement from the last accepted ball cannot be reached in the elapsed frames is not that ball — reject it when a consistent candidate exists, and prefer a short gap over a teleport when one does not. Tune the bound from the measured frames, not from a guess.
3. **Keep the ball off the walls.** 1515700 puts the box outside the playing surface. `_hoop_on_court` (line 183) already shows the shape of a coordinate sanity gate for the rim; the ball needs its own, and it is not the same box.
4. **Do not fill gaps by inventing positions.** A one-frame fill between two real boxes was already tried — it scored 80 right, 20 missed, 11 false, no better than the plain v6 line rule. Searching every missing frame along the path scored 79. Both are in the try table in the program file. Re-running them is not this step.
5. **Re-dump the same frames** and state the outcome per frame.

## What is explicitly not this step

**Another weights file of the same kind.** v1 through v6 were trained off to the side. v6 already improved boxes on the ball in the net — held-out, a box landed on the path under the rim on 16 of 19 frames, up from 6 of 19, and quiet empty nets stayed quiet on about 7 or 8 of 305. The make/miss count did not move past 80 until the sideways check. Another file of that kind will not fix the count on this camera. Template-matching the ball across the white net was also tried and gained nothing — the net changes the ball's look.

**Lowering the confidence cutoff.** It does not mark the frames where the cords cross the ball. And `ball_confidence` is a Scott gate regardless.

## Exit test

On the five frames listed above, say where the box sits — per frame, in plain words, with the coordinates. For each one, either:

- the box is **on the ball**, or
- the jump is **rejected** and the shot is **not called a make**.

755400 must still come out a **miss**. If a continuity fix turns that short miss into a make, the fix is wrong, not the control case.

Also confirm no regression: the shots that are already called correctly are still called correctly. Run the existing event-generator tests:
```
pytest tests/test_event_generator_precision.py tests/test_event_pipeline.py
```

Specifically, these two must keep passing — they encode behaviour already won:
```
pytest tests/test_event_generator_precision.py::test_a_ball_on_a_player_loses_to_the_ball_in_the_air \
       tests/test_event_generator_precision.py::test_a_lower_confidence_ball_at_the_hoop_is_the_shot
```

## Do not, on this step

- Do not write database rows.
- Do not change `models/ball_detector.pt` or `ball_confidence`.
- Do not train v7.
- Do not start a production detection pass of this film expecting new baskets.
- Do not turn on `rim_arc_shots` (`event_generator.py:1071`).
- Do not reorganize the core sequence.

## Hand off with

Proven / Inferred / Unknown, the per-frame before-and-after dump for all five frames, and the pytest output. Then update the paragraph in `ACTIVE.md` that this changes.
