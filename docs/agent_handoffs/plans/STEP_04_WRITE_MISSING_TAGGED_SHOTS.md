# Step 4 — Write the missing tagged shots

Read `00_INDEX.md` first. Source of scope: `PROGRAM_FOR_JASON_2026-10-10.md` section 6, step 4.

**Owner:** Cursor. **Depends on:** Step 3 **passing its bar**. **Blocks:** Step 5.
**This is the first step that writes to the database.** Home database only.

## Do not start this step unless step 3 cleared the bar

More than 85 right on the 111 tags, and misses called makes not higher than 6, with the numbers written into `ACTIVE.md`. If step 3 reported a worse trade, this step does not run. Check the numbers yourself — do not take a report's word for it.

## The problem in one paragraph

Scott can reject a false row. He cannot correct a row that was never written. On this film a lot of real shots never become a row at all, because the stored ball never reaches the rim the program locked, or an arc gate drops the shot before the make rule ever runs. Nine tags were earlier copied onto corrected rows to fill the card. **Those copies are not detector results and must not be repeated.** The fix is to make the detector write the row.

## Both halves of the fix, together

The program file is explicit that these are one job, not two:

1. **Write the missing shots** — tagged shots with no row within 8 seconds get one.
2. **Do not create extras** he must reject.

A rule that adds shots he did not tag is not the answer either. His Q1 review rejected 16 extra AI shots; his Q2 review rejected all 27. Several were a pass, an inbound, a foul, a timeout, or a player who was on defense.

## Where the code is

| Symbol | File:line | Role |
| --- | --- | --- |
| `detect_shot_from_segment` | `event_generator.py:572` | Arc detection. `min_ball_rise` is a parameter, default 10. |
| `shot_min_ball_rise: 80.0` | `event_generator.py:707` | Primary shot pass gate, applied at line 832 |
| `live_shot_min_ball_rise: 170.0` | `event_generator.py:710` | Live field goal gate, applied at line 946 |
| `generate_precision_events_from_segments` | `event_generator.py:790` | The shot pass |
| `build_possession_segments` | `event_generator.py:455` | |
| `persist_events` | `event_generator.py:1498` | The write |
| `MATCH_TOLERANCE_MS = 8000` | `manual_tag_teach.py:18` | The 8-second window |
| `reconcile_makes_with_shots` | `manual_tag_teach.py:344` | No longer rejects a make he already corrected |
| `apply_saved_manual_teach` | `manual_tag_teach.py:401` | |
| `reject_shots_when_the_other_team_has_the_ball` | `manual_tag_teach.py:584` | |
| `reject_shots_when_the_ball_is_not_in_play` | `manual_tag_teach.py:708` | Between-quarters reject |

## Read this before touching "the 170"

The program file and the roadmap both say "the 170-pixel rise", as if there is one. **There are two gates**, confirmed 2026-10-11:

- `shot_min_ball_rise: 80.0` at line 707, applied in the **primary** pass at line 832
- `live_shot_min_ball_rise: 170.0` at line 710, applied to **live field goals** at line 946

A tagged shot that never becomes a row may be dropped at the 80px gate, before the 170px gate is ever reached. Diagnose which gate is actually dropping each missing shot before changing either. `adrian_quality.py:45` has a third, unrelated `MIN_SHOT_BALL_RISE = 120.0` on the quality-pass path — not this.

The standing instruction is: **do not drop the 170-pixel rise unless this same test shows the missing rows appear and new untagged shots do not.** Treat that instruction as covering both gates, and raise the two-gate discrepancy with Scott rather than deciding it alone.

## Four of the missing makes are already named

`JASON.md` names them. Do not re-derive this list — start from it and confirm it is still current.

| Video time | Team | Player | Shot | Points |
| --- | --- | --- | --- | --- |
| 8:21.9 | Adrian | Rodus | Free throw | 1 |
| 9:50.9 | Adrian | Mendoza | Free throw | 1 |
| 20:31.4 | Adrian | Alvarez | Free throw | 1 |
| 26:22.0 | Adrian | Mendoza | Two | 2 |

**The diagnosed cause is already written down**, and it points straight back at step 1:

> "For these four, no stored ball box reaches the hoop the program had locked, and the nylon under that locked point does not move in the video around his tag. He says the real net did move, so that locked point is not the rim he watched."

So these four are **not** expected to be fixed by loosening a rise gate. They are expected to be fixed by step 1 finding the rim Scott actually saw. **Re-measure them after step 1 lands, before changing anything in this file.** If step 1 worked, some of these appear on their own.

Three others from the original seven — Colman's free throw at 19:41.7, Dayley's two at 26:43.9, and Colman's three at 30:36.7 — **were** written, by the change that keeps the ball box at the locked hoop instead of the highest-confidence box. Those three makes are the points that took the card from 43 to 49. That is the shape of a real fix: change what the detector sees, and the rows appear.

## Free throws are over half the problem

Four of the six makes that were never stored as a shot are **free throws**. `JASON.md` also scores free throws as a category failure: 11 of 21 tags matched, 10 missed, 4 extra rows. Only 2 of Scott's 9 tagged free-throw makes are on the live card.

A free throw has no drive, a short arc, and a stationary shooter — the possession and arc logic built for live field goals is the wrong shape for it. `detect_ft_formation` (`court_memory.py:258`) and `_is_lane_ft` (`court_memory.py:334`) already exist. Check whether the free-throw path is even reaching the shot pass before tuning a rise gate that may never apply to it.

Note the gate asymmetry: `live_shot_min_ball_rise: 170.0` applies to **live field goals**. The comment at `event_generator.py:708` says "Lane FTs keep the 80px floor." So a missing free throw is dying somewhere other than the 170.

## The gap is already counted: 22 tags

From the 2026-10-09 pickup bullet in `ACTIVE.md` — this is the measurement of record:

**22 of 111 shot tags have no AI row within 8 seconds: 6 makes and 16 misses. Nine of them are in Q3.**

The nine Q3 ones had no rim at all, because the hoop track stopped at 32:14. The track now runs to the end of the film (64:56, 1,949 raw samples) with the ±3 median rule. After that, **a ball within 280 pixels of the median rim is true for 17 of the 22.**

The five still beyond 280 pixels are named:

| Video time | Player | Shot |
| --- | --- | --- |
| 4:10.2 | Alvarez | Free throw miss |
| 8:21.9 | Rodus | Free throw (make) |
| 9:50.9 | Mendoza | Free throw (make) |
| 13:52.4 | Linkhart | Free throw miss |
| 32:09.8 | Foster | 3 miss |

**Four of these five are free throws.** Note this list is *not* the same as the four tagged makes above — that list is "tagged makes with no row", this one is "tags beyond the 280px rim gate". Rodus 8:21.9 and Mendoza 9:50.9 are on both.

## A shot-detection signal that already works — read before inventing one

Also from the 2026-10-09 bullet. This is the most promising result in the record and it is easy to miss:

> "A round red blob within 110 pixels of that rim, read every frame, reaches **all nine** of those shots (Rodus at 40 pixels, Mendoza's 9:50 free throw at 67, Linkhart at 81). Every fifth frame, through the end of the third quarter, that signal matches **91 of 111 shot tags and 8 moments with no tag.** Those eight were looked at: the ball is at the rim in each one. They are shots that were not tagged, not the old teleport rows."

That is exactly this step's exit test in miniature: it finds the missing shots **and** its extras are real shots a person can see, not noise. Start here. Do not start from a rise-gate change.

**The matching caution, same bullet:** "Calling make or miss from whether the ball is seen below the rim was right on 15 of 24 tagged shots and wrong on 9, so that rule was not used to write results."

So the 110-pixel signal is a **shot detector, not a make/miss rule.** Use it to decide *that a shot happened* (this step). Use step 3's rule to decide *whether it went in*. Keeping those two jobs separate is the point.

## Turning the writer on has already failed once

Do not repeat this. From the same bullet:

> "He then said to turn the writer on. It inserted **39 pending misses (14 next to a tag, 25 with no tag). The 25 were deleted.** The kept ball jumps hundreds of pixels between samples on the tagged shots and on the extras, so rise, distance, and confidence do not separate them."

That is the failure mode this step exists to avoid: 25 extras for 14 real rows. The cause named is the ball jumping hundreds of pixels between samples — **which is step 2's job.** If step 2 did not fix the jumping, this step will reproduce that result.

A net-motion scan was also tried and rejected: "every 4 seconds, fired on 79 samples near a tag and 72 samples with no tag." Roughly one false for every true. Not usable.

## The work

1. **List the gap.** Every one of Scott's shot tags with no detector row within 8 seconds. This is the target set. Record it before changing anything.
2. **Diagnose each one.** For each missing tag, say *where* it died: no ball track near the rim, possession segment never formed, 80px primary gate, 170px live gate, between-quarters reject, or defensive-team reject. Group them. The groups tell you what to fix; a single global loosening does not.
3. **Fix the cause, not the symptom.** Steps 1 and 2 may already have moved some of these — re-measure after they land before assuming a gate is at fault.
4. **Write the rows the detector found.** His tag within 8 seconds grades the row. An unmatched tag stays unmatched; it is **not** inserted as a make.
5. **Count the extras.** Run a pass over the film and count shots with no tag within 8 seconds. Compare against the pre-change count. A pile of new untagged shots fails this step even if every missing row appeared.

## Regression tests that must keep passing

```
pytest tests/test_event_generator_precision.py::test_a_lower_confidence_ball_at_the_hoop_is_the_shot \
       tests/test_event_generator_precision.py::test_a_ball_on_a_player_loses_to_the_ball_in_the_air \
       tests/test_manual_tag_teach.py::test_a_tagged_make_is_never_rejected_by_the_ai_shot
```

## Exit test

Both halves, reported as numbers:

1. Tagged shots that had no row within 8 seconds **now have one** — the baseline is **22 of 111**. Give the after count and list any still missing with the reason.
   - Of the 22, 17 are already within 280px of the median rim. Those should be the cheap ones. The five named above are the hard ones, and four of them are free throws.
2. A pass over the film **does not add a pile of shots with no tag** — give the before and after untagged-shot counts. The failed attempt produced **25 untagged rows for 14 tagged ones**; the 110-pixel signal produced **8 untagged for 91 tagged**, and all 8 were real shots on the film. Anything near the first ratio fails.

Both-false stays a miss until Scott changes that.

## Do not, on this step

- Do not copy his tags or the book onto the rows. Nine such copies already exist — do not add a tenth.
- Do not insert an unmatched tag as a make.
- Do not turn on `rim_arc_shots` (`event_generator.py:1071`). On this film the same rise appears on tagged shots and on moments with no tag.
- Do not widen `MATCH_TOLERANCE_MS` past 8000.
- Do not change `models/ball_detector.pt` or `ball_confidence`.
- Do not change both-false-is-a-miss.
- Do not ask Scott to accept or reject his own tags.
- Do not rename the 2:55.8 row to Colman. It stays a pending miss labeled tracker 7 until he says to change the tag, even though his note says that player was number 21 Colman.
- Do not write to anything but the home database. School uses Funnel only.

## Before you write

Deleting or replacing run data is a Scott gate and needs an archive plan. Five older reruns were removed on 2026-10-08 only after an encrypted archive (`encrypted-archive/liberty_adrian_detections_20261007.enc`, commit `df83b66`) — the passphrase is not in the repo. If this step would overwrite run 12 rather than add to it, stop and ask.

Never commit `scottmcconnell1-bot-liberty-basketball-analysis-*.txt`.

## Hand off with

Proven / Inferred / Unknown, the gap list with a cause per missing tag, the four counts (missing before/after, untagged before/after), and the `ACTIVE.md` edit.
