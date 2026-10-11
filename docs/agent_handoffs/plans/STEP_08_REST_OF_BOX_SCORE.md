# Step 8 — The rest of the box score from the film

Read `00_INDEX.md` first. Source of scope: `PROGRAM_FOR_JASON_2026-10-10.md` section 6, step 8 and section 4, item 4.

**Owner:** Cursor. **Depends on:** Step 7. **Blocks:** Step 9.

## Do not start this step early

Steps 7 through 10 wait on a ledger that matches a book. Rebounds and turnovers built on wrong shots are wrong.

## The target

**Rebounds, turnovers, steals, fouls, blocks — and assists** written from the film, under the rules Scott set on **2026-09-15**.

## The 2026-09-15 rules, verbatim

They are not in a separate document. They are the NFHS counting-rules bullet in `docs/agent_handoffs/ACTIVE.md`, under **Standing facts**:

> **FT** is the lane lined up around the key with the camera locked on it.
> **Assist** is the last pass before a made field goal, 1-2 dribbles, no FT assists.
> **Turnover** is the offense losing the ball before a shot.
> **Steal** is the defender's active play causing that turnover.
> **OREB or DREB** comes from shooter and rebounder shirt color.
> **Block** is a deflection near the shooter's hand; if it still goes in, it is a field goal.
> **Starters** are the five the coach picks per game.

That is the whole specification. Three things follow directly from it and are easy to get wrong:

- **A steal is a subset of a turnover**, not a parallel event. If `credit_steal` fires where no turnover was credited, one of the two is wrong.
- **Assists depend on a made field goal**, so assists cannot be better than the make/miss rule underneath them. There are **no free-throw assists**.
- **Rebound side comes from shirt color**, not from team assignment or cluster id. `jersey_shade.py` is the relevant module, not the identity path.

## What is already on run 12, and where it came from

Steals and fouls on Adrian were written **from Scott's film-tool tags, not from the film and not from the heuristic**:

- 14 accepted manual steals
- 18 fouls
- 5 personal fouls
- 14 steal-linked turnovers

That is the current state. This step is about producing the same categories **from the film**. Do not mistake the tag-derived rows for detector output.

## The full baseline, from `JASON.md`

This is the per-stat measurement against Scott's **first-half** tags. A match is one live row of the same stat within 8 seconds; live means pending, corrected, or accepted. **This is your grader.** Re-measure it first — it predates steps 1 through 7 — then beat it.

| Stat | Verdict | Tags matched | Tags missed | Extra live rows |
| --- | --- | --- | --- | --- |
| Field-goal attempts | Partly | 31 of 48 | 17 | 46 |
| Free throws | Fails | 11 of 21 | 10 | 4 |
| Rebounds | Fails | 13 of 29 | 16 | 39 |
| Turnovers | Fails | 3 of 16 | 13 | 17 |
| **Assists** | Fails | **0 of 6** | 6 | 8 |
| Steals | Not written | 0 of 8 | 8 | 0 |
| Fouls | Not written | 0 of 18 | 18 | 0 |
| Blocks | Unchecked | no tags | — | 4, all after 32:15 |

The book columns for attempts, rebounds, assists, steals, blocks, turnovers, and fouls are **empty on all 28 players**, so the second half can only be checked for points and free throws. The first-half tags are the only ground truth this step has.

What that table is really saying: **the only rows that agree with the tags are rows Scott already corrected from the film tool.** All 13 rebound matches carry a film-tool teach mark; no pending rebound is within 8 seconds of a tag. The 3 turnover matches are the only corrected turnovers. All 10 assists miss every tag — the closest is 34 seconds away. Field-goal attempts are the single count that lands on tags without a prior correction.

Two specific defects to fix, not just measure:
- One matched rebound pair names **Peterson's** offensive rebound at 5:41 as **Dayley**.
- On **9 of the 13** taught rebound rows, the detail flag says the **opposite** of the event type.

**132 of 170 rebounds are written within 6 seconds after an unseen miss** — a shot row with both flags false. Rebounds are currently a shadow of the shot-detection failure. If step 1 through 4 worked, this number should move on its own before you write any rebound logic. Measure it before and after.

**804 of the 1,452 events are `possession_change`**, which the box score ignores.

## Assists are a sixth category

The program file's step 8 lists rebounds, turnovers, steals, fouls, and blocks — **it omits assists**. The tag file has 6 assist tags (Peterson 1, Sullivan 2, Colman 2, Foster 1) and run 12 has 10 pending assists matching none of them. `credit_assist` already exists at `stat_rules.py:21`.

Treat assists as in scope and say so in the report. If Scott wants them deferred, that is his call to make with the number in front of him.

## The steals numbers, reconciled

The sources look contradictory and are not. `ACTIVE.md` (2026-10-08) settles it:

> "His film-tool tags are written on the counting run: **14 accepted manual steals, 18 fouls, 5 personal fouls, and 14 steal-linked turnovers.** The counting card shows **Liberty 8 steals and 18 fouls, Adrian 6 steals and 5 fouls.** Existing AI turnovers were left in place, so team turnovers on the card rose with the 14 linked rows (Liberty 20 to 26, Adrian 19 to 27). Point totals did not change."

So **Liberty 8 + Adrian 6 = the 14**. `JASON.md`'s "8 of 8 steal tags missed" is the earlier, first-half-only measurement taken *before* the steal-and-foul write, by the now-finished agent `5cb51e6b-92f6-4927-8332-2bbc4dae58c3` (**do not resume it**).

Residual uncertainty worth one query: `JASON.md` lists its 8 first-half steal tags as Liberty 4 (Colman 2, Sullivan 1, Dayley 1) and Adrian 4 (Foster 2, Linkhart 1, Mendoza 1) — a 4/4 split, where the card shows 8/6. Confirm the split against run 12 before using either as a denominator.

**These 14 steals and 18 fouls came from Scott's tags, not from the film.** They are your labelled set, not detector output. Producing them from the film is the job.

## The two settings that do not change

**`emit_fouls` stays false** (`event_generator.py:725`, used at line 1062). That heuristic credits the shooter after a long dead ball — the current gate is `next_segment is None or next_gap >= 90`. **A long gap after a shot is not a foul.** Turning this on is a feature-flag flip, which is a Scott gate, and the program file says it stays off.

**`credit_steal` stays the defender's active takeaway** (`stat_rules.py:69`, used at `event_generator.py:882`). Not every change of possession is a steal.

## Where the code is

| Symbol | File:line | Role |
| --- | --- | --- |
| `credit_assist` | `stat_rules.py:21` | |
| `classify_rebound` | `stat_rules.py:46` | |
| `credit_steal` | `stat_rules.py:69` | Defender's active takeaway |
| `classify_turnover_kind` | `stat_rules.py:85` | dead_ball / after_shot |
| `credit_block` | `stat_rules.py:92` | |
| `second_chance_make` | `stat_rules.py:135` | |
| `points_off_turnover` | `stat_rules.py:141` | |
| `generate_expanded_events_from_segments` | `event_generator.py:1125` | Where the non-shot events are built |
| `generate_precision_events_from_segments` | `event_generator.py:790` | |
| `_ball_deflected_away` | `event_generator.py:771` | |
| `emit_fouls: False` | `event_generator.py:725` | **Stays false** |
| `credit_assist` | `stat_rules.py:21` | **Assists — omitted from the program file's step 8** |
| `teach_from_film_tool_rows` | `manual_tag_teach.py:194` | How the tag-derived rows got there |
| `jersey_shade.py` | — | **Shirt color — this is what decides OREB vs DREB** |
| `game_boxscore.py` | — | Core sequence, do not reorganize |
| `boxscore_constraints.py` | — | |
| `tests/test_game_boxscore.py`, `tests/test_film_critical_stats.py` | — | Existing tests |

## The work

1. Re-read the 2026-09-15 rules above. They are the spec.
2. For each category — rebound, turnover, steal, foul, block — state what the film signal actually is before writing the rule, and what distinguishes it from the thing it is most often confused with (a rebound from a loose ball, a steal from a bad pass, a block from a miss).
3. Grade against Scott's first-half tags using the baseline table above, after re-measuring it. Report right / missed / false per category in the same shape as step 3.
4. Report right / missed / false per category. One number per category, the same shape as step 3.
5. A category that does not beat its tag-derived baseline does not ship. Say so and move on; do not ship all five because three worked.

## Exit test

- Each of the **six** categories — rebounds, turnovers, steals, fouls, blocks, assists — is produced from the film and graded against Scott's tags, with right / missed / false reported per category.
- The rebound-after-unseen-miss count (was 132 of 170) is reported before and after.
- Peterson's 5:41 rebound is no longer named Dayley, and the 9 taught rows whose detail flag contradicts the event type are fixed.
- `emit_fouls` is still false.
- `credit_steal` still requires the defender's active takeaway.
- No category ships that scores worse than what is already on run 12 from the tags.

## Do not, on this step

- Do not turn on `emit_fouls`. It is a Scott gate and the answer is already no.
- Do not loosen `credit_steal` to every change of possession.
- Do not copy the tag-derived rows and call them detector output.
- Do not change `schema.sql` — Scott gate. If a category needs a column that does not exist, stop and ask.
- Do not reorganize the core sequence.

## Hand off with

Proven / Inferred / Unknown, the six per-category score lines, and the `ACTIVE.md` edit.
