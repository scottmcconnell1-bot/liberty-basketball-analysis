# Step 6 — A film with no shot-by-shot list

Read `00_INDEX.md` first. Source of scope: `PROGRAM_FOR_JASON_2026-10-10.md` section 6, step 6.

**Owner:** Cursor. **Depends on:** Step 5. **Blocks:** Step 7, and the whole rest of the program.
**This is the step that turns a graded experiment into a product.**

## Why this step exists

Everything up to here used Scott's 111 tags as a list of times to grade. Tag windows are how a rule is graded. **They are not how a future game gets counted.** A rule that only works when someone hands it 111 timestamps is not a product — the next gym has no tags.

`run_ball_hoop_experiment` (`ai_bridge.py:856`) **cannot do this step.** It only grades timestamps you hand it. It does not watch a film, name the shooter, or write the ledger. Do not use it here, and do not let a passing step-3 number stand in for this.

## The target

The ledger has to notice, from the film and with no hand-built list of times:

- that a shot happened
- the shooter
- the team
- 1, 2, or 3 points

Run it on **Q4 of Adrian** (the first untagged stretch, remainder Liberty 8, Adrian 2) or on **one other Liberty film**.

Q4 is the cheaper test and has a known point total to check against. Another film is the stronger test. Prefer Q4 first, then a second film if Q4 passes.

## The work

1. Run the step-3 make/miss rule on the untagged stretch, with no timestamp list.
2. Produce the shot list the program found: time, shooter, team, points, make or miss.
3. **Have a person look at the extras.** Every shot the program found that Scott did not tag must be one a person can see on the film. That is the test — not a count, a look.
4. For Q4, compare the resulting points to the remainder: Liberty 8, Adrian 2.
5. Confirm the other modules read these events and **do not grow a second database**. One ledger is the product.

## Exit test

- The same make/miss rule from step 3 runs **without a tag list**.
- The extra shots it finds are ones a person can see on the film.
- The other modules read those events. No second database.

## Do not, on this step

- Do not build a timestamp list for Q4 and call that "no list". If a list is built, this step did not happen.
- Do not use `run_ball_hoop_experiment` as the runner.
- Do not copy the book's Q4 remainder (8 and 2) onto the rows.
- Do not turn on `rim_arc_shots`.
- Do not change `models/ball_detector.pt` or `ball_confidence`.
- Do not reorganize the core sequence.

## Note on what "shooter and team" means here

Step 7 is where shooter and team get fixed properly against Scott's tags. This step needs them *attempted* so the untagged run produces a real ledger row, not a bare shot event. Expect them to be wrong often — jersey identity is known to be unreliable (see step 7). Report how often, as the input to step 7. Do not stop this step because identity is poor; do not claim identity works because this step ran.

## Hand off with

Proven / Inferred / Unknown, the found shot list for the untagged stretch, the human check on the extras, the Q4 point comparison, and the `ACTIVE.md` edit.
