# Step 7 — Shooter, team, and points

Read `00_INDEX.md` first. Source of scope: `PROGRAM_FOR_JASON_2026-10-10.md` section 6, step 7 and section 4, item 3.

**Owner:** Cursor. **Depends on:** Step 6. **Blocks:** Step 8.

## Do not start this step early

Steps 7 through 10 are the rest of the program and **they wait on a ledger that matches a book**. If step 5 did not reconcile and step 6 did not run without a tag list, this step does not start. Naming the shooter on rows that are themselves wrong produces confident wrong data, which is worse than no data.

## The target

From the film, for every shot row: **who shot it, which team, and whether it is 1, 2, or 3 points** — checked against Scott's tags where he has them.

## What is known to be wrong today

Jersey identity is wrong often enough that Scott rejected rows **for the wrong player** and **for players who were on defense**. Those rejections are already on run 12 with his notes. They are the test set for this step — fix those specific cases first, and do not re-break them.

## The naming rules — these are hard constraints

- **Dayley, Daley, and Daly are one Liberty player**, number 40, roster name **Daly**.
- **Liberty has no number 2 and no number 6.** A row claiming either is wrong.
- **Foster number 22 is Adrian**, not Liberty.
- **Liberty number 3 is Kariuki.**
- **A cluster id of 3 is not Kariuki.** This is the trap. The spatial cluster id is an index, not a jersey number. Do not join them.
- Any other close spelling is a **Scott gate** — ask before treating two spellings as one person.

## Unnamed clusters stay unnamed

`JASON.md`: cluster `7` holds 7 points and cluster `0` holds 3 on run 12, neither matching any book line. **Cluster 7 stays unnamed. Do not assign those points to a Liberty player.** Naming a cluster to close a per-player gap is the identity-step version of copying the book onto the rows.

Note how little naming achieved last time: run 12 filled in a name, jersey, or side on 52 shot rows, 25 of them in the second half (the 52 was counted when the run held 206 shot rows; it holds **229** as of 2026-10-11, 155 of them not rejected, so re-count the fraction before quoting it), and **it did not find a new shot**. Naming does not create the missing Colman, Sullivan, Peterson, Flores, Rodus, or Allison points. Identity is a correctness fix, not a recall fix — do not expect this step to move the total.

Two second-half names are known wrong against the book: Foster's two at 57:42 (his book two is already in the first-half tags) and Alvarez's two at 58:32 (the book gives him one free throw there). Both are in the test set.

## One row that does not change

The **2:55.8** row stays a **pending miss labeled tracker 7** until Scott says to change the tag. His note says that player was number 21 Colman. **Do not rename it.** This is listed under "must not be fixed the wrong way" in the program file.

## Where the code is

| Symbol | File:line | Role |
| --- | --- | --- |
| `resolve_event_identity` | `adrian_identity.py:252` | |
| `lookaround_jersey_votes` | `adrian_identity.py:110` | Votes a jersey from nearby frames |
| `match_scorebook_player` | `adrian_identity.py:157` | |
| `resolve_label_to_scorebook` | `adrian_identity.py:180` | |
| `enrich_details_with_identity` | `adrian_identity.py:232` | |
| `apply_lookaround_to_accepted` | `adrian_identity.py:307` | |
| `scorebook_roster_index` | `adrian_identity.py:33` | |
| `read_jersey_from_bbox` | `jersey_ocr.py:74` | |
| `_parse_jersey_text` | `jersey_ocr.py:34` | Where a "2" or "6" should be rejected for Liberty |
| `crop_torso` | `jersey_ocr.py:54` | |
| `jersey_shade.py` | — | Light/dark team separation |
| `_cluster_players_spatially` | `event_generator.py:394` | **Produces the cluster id. Not a jersey number.** |
| `_shooter_team` | `manual_tag_teach.py:538` | |
| `classify_shot_kind` / `scoring_event_type` | `stat_rules.py:109` / `:126` | 2 vs 3 vs free throw |
| `team_has_the_ball` | `stat_rules.py:145` | |
| `track_identity.py` | — | Also writes identity rows (named in `JASON.md`) |
| `scripts/apply_adrian_jersey_lookaround.py` | — | Existing tool, reuse |
| `tests/test_adrian_identity_lookaround.py` | — | Existing tests |

## The work

1. **Build the test set — it is already on disk.** Do not reconstruct it from the database. `tag-exports/` holds Scott's reviews and the before-states:

   | File | What it is |
   | --- | --- |
   | `tag-exports/adrian_q1_ai_shot_review.csv` | His Q1 review: 16 extra AI shots rejected, with notes |
   | `tag-exports/adrian_q2_ai_shot_review.csv` | His Q2 review: all 27 rows rejected, with notes |
   | `tag-exports/q1_ai_shots_before_review_20261008.json` | Before-state for Q1 |
   | `tag-exports/q2_ai_shots_before_review_20261008.json` | Before-state for Q2 |
   | `tag-exports/jrhigh_adrian_q1_manual_tags.json` | His Q1 manual tags |
   | `tag-exports/compare_adrian_q1.json` / `.py` | An existing Q1 comparison |

   **One file `ACTIVE.md` names is not in the repo:** `tag-exports/rejected_makes_before_restore_20261007.json`, the before-state of the seven wrongly rejected makes. Checked 2026-10-11 — `tag-exports/` holds only the four files above plus the hoop probe images. It is probably on the home machine like the database. Do not plan around having it; ask Scott if you need it.

   His notes name the reason per row: a pass, an inbound, a foul being called, a timeout, a player on defense, or a player not in the game. The defense cases are the identity test set. One row to know: **31:55.4 is a real shot — #22 missed a 3, and the AI row is the wrong one.**
2. **Add the roster constraints as hard filters.** Liberty has no 2 and no 6 — an OCR result of 2 or 6 on a Liberty player is a misread, not a player. Foster 22 is Adrian. Encode these, do not rely on a model learning them.
3. **Separate cluster id from jersey number** everywhere they are currently conflated. Audit for any place a cluster id is used as a number. Cluster 3 is not Kariuki.
4. **Team before player.** Which team has the ball is a cheaper and more reliable signal than which player. `team_has_the_ball` (`stat_rules.py:145`) already exists and `reject_shots_when_the_other_team_has_the_ball` (`manual_tag_teach.py:584`) already uses tags for it. Get team right first; a shot credited to the right team and an unknown player is more useful than a confident wrong name.
5. **Points.** 2, 3, or free throw, from court position and the free-throw formation detector (`detect_ft_formation`, `court_memory.py:258`). A shot row by itself is 0 points.
6. **Re-check against his tags** where he has them, and report accuracy as a number.

## Exit test

- The rows Scott rejected for the wrong player are now right, or are reported as still wrong with a reason.
- The rows he rejected for a player on defense are no longer written for that player.
- No row names a Liberty 2 or Liberty 6. No row joins cluster id 3 to Kariuki.
- The 2:55.8 row is unchanged.
- Shooter and team accuracy against his tags is reported as right / wrong / unknown counts.

## Do not, on this step

- Do not treat a close spelling as a known name without asking Scott.
- Do not rename the 2:55.8 row.
- Do not copy his tags onto rows to make identity look better.
- Do not ask Scott to accept or reject his own tags.
- **Do not open `GET /api/analysis/<game_id>`** (`blueprints/ai.py:809`). **That request rewrites identity rows** — on this step of all steps, that silently destroys the thing you are fixing. Read `events` directly, or the HTML results page.
- Do not assign cluster 7's or cluster 0's points to a named player.
- Do not reorganize the core sequence.

## Hand off with

Proven / Inferred / Unknown, the test-set results, the accuracy counts, and the `ACTIVE.md` edit.
