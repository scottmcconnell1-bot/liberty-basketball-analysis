# Step 3 — Score the 111 tags again

Read `00_INDEX.md` first. Source of scope: `PROGRAM_FOR_JASON_2026-10-10.md` section 6, step 3.

**Owner:** Cursor (scoring harness) or Hermes (inside `ai_bridge.py` only).
**Depends on:** Step 1 and Step 2, both landed. **Blocks:** Step 4, and therefore everything after it.
**Offline only. No database writes.** This is the gate. Nothing is written to the ledger until this step passes.

**The gate now runs as a command.** `python scripts/shot_tag_score.py --game-id "<run 12 key>" --fixture adrian_111` prints the three numbers and exits 1 when they are below the floor in `benchmarks/shot_tags/baseline.json` (85 / 20 / 6). Report its output verbatim; a summary in prose is not a result. It needs the database and the tag file, so run it on the home laptop or on a clone with the Shared drive folder copied over it. If the floor turns out not to be reproducible from the database — the 85 was measured offline on the v6 tracks, which nobody has re-run from this repo — say so and correct the floor in the same pull request rather than scoring against a number that was never checked.

## The bar

| Metric | Current best | Required |
| --- | --- | --- |
| Right (of 111) | 85 | **more than 85** |
| Makes missed | 20 | (no separate bar, but report it) |
| Misses called makes | 6 | **not higher than 6** |

111 shot tags: 38 makes, 73 misses. "Right" means the call matched Scott's tag.

The current best came from a rule that throws out a ball sliding sideways by more than 0.45 rim-widths between 80 and 180 pixels below the hoop. **It is not turned on and no rows were written from it.**

**If the new rule loses that trade, do not ship it.** Write the numbers into `ACTIVE.md` and stop this step. A worse trade is a real result and reporting it is the job — it is not a failure to hide.

## What a score is

Three numbers, every time: **right**, **makes missed**, **misses called makes**.

A printout that only says "how many windows were called makes" is **not a score**. It cannot distinguish a rule that found 38 makes correctly from one that called 38 random windows makes.

Report them as a new row appended to the try table below, so the next agent does not re-run something that was already tried.

## Everything already tried, and its result

All offline. None written into run 12 as the make rule. Do not re-run a row from this table and present it as new.

| Try | Right | Makes missed | Misses called makes |
| --- | --- | --- | --- |
| Color tracker, line through the opening | 74 | 37 (found 1 make) | 0 |
| Gap bridge | 75 | 19 | 17 |
| Orange patch tracked through the rim | 58 | 34 | 19 |
| Orange pixels inside the net cone | about 58 | makes and misses overlap | not a separator |
| Public ball+hoop model (BODD), line through the opening | 73 | 13 | 25 |
| Ball falls in one motion to the floor | 80 | 28 (found 10 makes) | 3 |
| Line from last ball into the rim to the next ball away | 67 | 15 | 29 |
| Slight arc, same idea | worse | found up to 29 makes | up to 45 |
| Incoming speed and arc, reject a next spot arc cannot reach | 78 | 25 | 8 |
| Rim-scaled gravity, only where the ball disappears | 78 | recovered 0 of the gap makes | added 2 |
| Search every missing frame along the path | 79 | 28 | 1 new |
| "Directly under the basket", no floor required | — | 7 | 31 |
| v6 ball track, line through the opening, fall 180px | 80 | 20 | 11 |
| v6, one-frame fill between two real boxes | 80 | 20 | 11 |
| v6, ball must stay under the rim for the length of the net | 74 | 15 | 22 |
| **v6, reject sideways slide over 0.45 rim-widths from 80px to 180px below the hoop** | **85** | **20** | **6** |
| v6, same rule at **0.40** rim-widths | 85 | 21 | **5** |

The 0.40 variant is worth noting: it trades one more missed make for one fewer false make. It does **not** clear the bar either — the bar is *more than* 85 right — but it shows the knob is near a local ceiling, and that squeezing the false-make count alone will not get there.

Two more results from `ACTIVE.md` that are not in the table above:

- **Make/miss from "the ball is seen below the rim"**: right on 15 of 24 tagged shots, wrong on 9. Not used to write results. Image-down is not "through the net" — this is the same camera-geometry problem stated as a number.
- **A net-motion scan of Q1–Q3**, every 4 seconds: fired on 79 samples near a tag and 72 samples with no tag. Roughly one false for every true. Not turned on.

Also already established as dead ends, with the reason:

- **Loosening** the pair window, the fall gap, or the drop each added more false makes than makes.
- **Starting 1.6 seconds before the tag** picked up the previous play.
- **Template-matching the ball across the white net** gained nothing. The net changes the ball's look.
- **Physics from the incoming arc** rejects some front-rim misses and also rejects real makes that rattle, because the rim changes the speed.
- **Gravity in inches**, using the 18-inch rim and the camera tilt, was off by feet. This camera mixes height and depth, and dividing by the cosine of the tilt does not separate them.

## Why the line rule cannot finish the job alone

The camera looks down from the side. A ball through the white net and a ball off the front of the orange rim **draw the same line**, and both can fall to the floor in front of the basket. Image-down is not "through the net". That is why 755400 (a short miss falling in the lane) reads as a make under a naive below-the-rim test.

This is the reason step 1 and step 2 come first: a correct rim and a ball box that stays on the ball change the inputs the rule sees. Score the rule **with** those two fixes in place. That is the new thing being measured — not a new rule invented from scratch.

## The work

1. Confirm step 1 and step 2 are actually landed, by running their exit tests, not by reading their reports.
2. Re-score the existing best rule (sideways slide, 0.45 rim-widths, 80–180px below the hoop) on the 111 tags **with the step 1 and step 2 fixes in place**. This is the primary measurement. It may move on its own.
3. Report right / makes missed / misses called makes. Append the row to the table above.
4. Only if that does not clear the bar, try a variant — and say in the report why that variant is not one of the rows already in the table.
5. Write the final numbers into `ACTIVE.md` either way.

## The harness

`run_ball_hoop_experiment` (`ai_bridge.py:856`) grades timestamps you hand it. For **this** step that is acceptable, because the 111 tags are exactly such a list. It is **not** acceptable for step 6, which has no list — do not let its convenience here turn into a dependency later.

If Hermes runs it: `ai_bridge.py` only, nothing in the core calls it, and the result leaves as JSON with `applied_to_core: false` until Scott accepts it.

Two live bugs in that file, confirmed 2026-10-11 — fix or route around them before trusting any number it prints:

- `find_hoop_on_orange_rim` (`ai_bridge.py:662`) filters detections for `class_name in ('hoop','rim','basket')`. **v6 emits one class, `basketball`.** The list is always empty, so the function returns `None` and every window is called a miss.
- `classify_make_miss` sets `hoop_on_rim = True` in the source (`ai_bridge.py:757`) and uses it at line 759. It never looks at the picture, so a box on the glass is never rejected.
- `check_adrian_rerun_score` (`ai_bridge.py:875`) defaults to a hardcoded Windows path and the debug query uses the **September 28** rerun key. That is not run 12.

A number produced by that file without fixing those is not a score.

## Exit test

- More than 85 right, **and** misses called makes not higher than 6.
- The three numbers are reported, and the try table has a new row.
- The numbers are in `ACTIVE.md`.

If the bar is not met: stop. Do not proceed to step 4. Report the numbers.

## Do not, on this step

- Do not write database rows from a rule that has not beaten 85 right without more false makes. This is the whole point of the gate.
- Do not change `models/ball_detector.pt` or `ball_confidence`.
- Do not train another ball-weights file of the same kind.
- Do not drop both-false-is-a-miss. Scott kept it on 2026-10-07 and it does not change until he says so, and not before a tested rule beats 85 / 6.
- Do not report "windows called makes" as a score.
- Do not copy Scott's tags or the book onto rows to improve the number.

## Hand off with

Proven / Inferred / Unknown, the three numbers, the new try-table row, and the `ACTIVE.md` edit.
