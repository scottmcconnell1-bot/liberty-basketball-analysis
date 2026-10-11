# Step 5 — Compare the card to the book

Read `00_INDEX.md` first. Source of scope: `PROGRAM_FOR_JASON_2026-10-10.md` section 6, step 5.

**Owner:** Cursor. **Depends on:** Step 4. **Blocks:** Step 6.
**Read-only on the home database.** This step explains a gap. It does not close one.

## The numbers

| Thing | Value |
| --- | --- |
| Book | Liberty 51, Adrian 26 — 77 points |
| Scott's tags through three quarters | Liberty 43, Adrian 24 — **matches the book** |
| Q3 alone, from tags | Liberty 16, Adrian 9 |
| Q4 remainder | Liberty 8, Adrian 2 — **Q4 is not tagged** |
| Run 12 non-rejected make points, measured 2026-10-11 | **55** (15 twos, 5 threes, 10 free throws) |
| Run 12 distinct baskets, measured 2026-10-11 | **53** — one `made_two` is stored twice |
| Run 12 shot rows, measured 2026-10-11 | **229**, of which **155** are not rejected |
| Quarter ends | Q1 16:00.7, Q2 32:15.0, Q3 55:17.1 |
| Q4 Start QTR tag | 56:26.7 — this is the inbound, not a tagged quarter |

Neither 55 nor 53 is an accuracy claim; they are what the card held on 2026-10-11. The 49 from 2026-10-08 and the 64 / 76 / 59 / 43 before it are older nights, not contradictions. Re-measure before quoting.

## The duplicate basket at 0:48.2 — find this before comparing anything

One `made_two` at **0:48.2** is stored **twice**, and both rows are taught Dayley rows. That is why non-rejected makes add to 55 points but distinct baskets are 53.

This is a data defect, not a detector error and not a rounding difference. Two points sit on the card that the film shows once. Before you explain any gap against the book, establish which it is:

- **one basket written twice** — the same event persisted on two passes, in which case look for others and ask how `persist_events` let it through; or
- **two rows taught from one tag** — the teach pass graded two nearby AI rows against a single tag, in which case the 8-second window matched twice and the second row should have stayed pending.

Either way it changes the arithmetic of this step, and **neither is fixed by writing more rows.** Report which one it is. Do not delete a row to make the total come out: deleting data without an archive plan is a Scott gate, and a card that reads 53 for the right reason is worth more than one that reads 53 because a row was removed.

A whole-card check for the same shape: `scripts/shot_tag_score.py` reports `unmatched_stored_makes`, the stored makes that graded no tag at all. Two rows on one tag show up as one of them going unmatched.

## The per-player gap is already written down

`JASON.md` has the full-game comparison on run 12 (pending plus corrected), from the 2026-10-06/08 era. Re-measure it after step 4 — do not quote these as current — but use it as the expected shape of the answer.

| Player | Run 12 | Book |
| --- | --- | --- |
| Dayley | 14 | 26 |
| Colman | 4 | 15 |
| Peterson | 2 | 4 |
| Sullivan | 0 | 4 |
| Flores | 0 | 2 |
| Mendoza | 15 | 13 |
| Alvarez | 7 | 5 |
| Foster | 9 | 2 |
| Rodus | 3 | 4 |
| Allison | 0 | 2 |
| Unnamed cluster `7` | 7 | — |
| Unnamed cluster `0` | 3 | — |

Read the shape, not just the total: Liberty's scorers are **under** (Dayley 14 of 26, Colman 4 of 15, Sullivan and Flores at zero), while Adrian's are **over** (Foster 9 against 2, Mendoza 15 against 13) and ten points sit on two unnamed clusters. A card that reaches 77 by piling points onto the wrong players is not a pass. Report by player and by team, not only the total.

**Cluster 7 and cluster 0 stay unnamed.** Do not assign their points to a Liberty player to make a line match.

Second half specifically: the book has 35 points there, run 12 scored 14, and **zero second-half scoring rows carry `film_tool_teach`** because the tags stop at 32:15. Colman, Sullivan, Peterson, Flores, Rodus, and Allison have no second-half scoring row at all.

## Scoring rules to apply

- Made two is 2. Made three is 3. Made free throw is 1. A shot row by itself is 0.
- Counted review statuses: **accepted, corrected, pending**. Rejected drops off the card.
- A make is `ball_through_rim` or `net_moved_after_shot`. Both false is a miss.

## The work

1. **Recount the card.** Non-rejected make points on run 12, by quarter and by team, after step 4's writes. State the total.
2. **Flag the nine tag-copy rows.** Nine shots with no detector row had Scott's tag copied onto a corrected row earlier. They are on the card and they are **not** detector results. Identify them, and report the card total both with and without them. A total that silently includes them overstates what the detector did.
3. **Reconcile shot by shot.** For every point of difference between the card and 77, attribute it to exactly one of:
   - an **untagged Q4 possession** (expected — Q4 has no tags, and the remainder is Liberty 8, Adrian 2), or
   - a **row the detector still did not write**, or
   - a **row the detector wrote wrong** (wrong result, wrong points, wrong team).
4. **Report the three-quarter comparison separately** from the Q4 comparison. Through Q3 the tags match the book exactly, so that stretch is a clean test of the detector. Q4 is not — nothing there is graded by a tag.

## Exit test

The gap is explained **shot by shot**. Every missing or extra point is attributed to one of the three causes above. No point is left as "unexplained" without saying so explicitly and counting it.

## Do not, on this step

- **Do not close the gap by copying 51–26 onto the rows.** This is the single most important do-not on this step. The number matching is worthless if the rows were edited to make it match.
- Do not add more tag-copy rows.
- Do not ask Scott to accept or reject his own tags.
- Do not treat the bottom of `HERMES.md` ("Where the Adrian count stands") as the counting run. That is the September 30 rerun.
- Do not use the September 28 rerun key that `check_adrian_rerun_score` (`ai_bridge.py:875`) defaults to. The counting run is `...__rerun_20261006_033941`.
- Do not write to the database on this step.
- **Do not open `GET /api/analysis/<game_id>`** (`blueprints/ai.py:809`) to read the card. That request **rewrites identity rows** — it would change the thing you are measuring. Read the `events` table directly, or the HTML results page.

## A likely outcome worth planning for

Through Q3 the tags are 43–24 and the book agrees. If the card after step 4 still falls well short of 67 points through Q3, the detector is still not writing the game, and the honest report says so. Steps 6 through 10 all assume a ledger that matches a book. If this step shows it does not, say that plainly rather than moving on.

## Hand off with

Proven / Inferred / Unknown, the recounted card (by quarter, by team, with and without the nine copies), the shot-by-shot attribution table, and the `ACTIVE.md` edit.
