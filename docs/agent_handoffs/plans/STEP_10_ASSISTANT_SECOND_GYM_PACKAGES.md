# Step 10 — The assistant, a second gym, then packages

Read `00_INDEX.md` first. Source of scope: `PROGRAM_FOR_JASON_2026-10-10.md` section 6, step 10 and section 4, items 7, 8, 9.

**Owner:** Cursor. **Depends on:** Step 9. **Blocks:** nothing — this is the end of the stated roadmap.

This step is three things in a required order. **Do not reorder them.**

## 10a — The assistant answers only from reviewed rows

The assistant answers from the one ledger, **not from a second database and not from guesses**. Every answer cites the clip or the event id. **It does not paper over a missing make** — if the ledger has no row, the honest answer is that there is no row, not an estimate.

| Symbol | File:line |
| --- | --- |
| `_trusted_events_for_game` | `assistant_query.py:147` |
| `_trusted_events_query` | `assistant_query.py:161` |
| `_event_citation` | `assistant_query.py:123` |
| `_clip_citation` | `assistant_query.py:135` |
| `_stat_citation` | `assistant_query.py:107` |
| `_unknown` | `assistant_query.py:33` — the path that must stay reachable |
| `assistant_workflow.py` | — |
| `tests/test_assistant.py`, `tests/test_assistant_workflow.py` | — |

Counted review statuses are **accepted, corrected, pending**. Rejected drops off. Confirm `_trusted_events_query` enforces exactly that set.

**Exit:** every answer cites a clip or an event id; a question with no reviewed row returns the unknown path, not a number.

## 10b — A second gym

**A rule that only works on this NFHS corner camera is not the product.**

Harper and Nyssa are already on the nightly full-film panel and are **not close**. As of 2026-10-09 (`docs/LEARNING_STATUS.md`) the panel fails every gate:

| Gate | Required | 2026-10-09 actual |
| --- | --- | --- |
| Final score | 100% | **0%** |
| Player points | 100% | **0%** |
| Event precision | ≥ 90% | **4.9%** |
| Event recall | ≥ 90% | **9.5%** |

That is the same disease as Adrian, measured on other films: the machine events are not the game. HUDL teach state has keys stored — that is not a box score.

Tooling: `scripts/score_full_film_panel.py`, `tests/test_full_film_panel.py`, `tests/test_accuracy_benchmark.py`, `docs/LEARNING_STATUS.md`.

**Exit:** the panel gates pass on a gym that is not the Adrian camera. Re-running the panel and reporting the same four numbers is the measurement.

## 10c — Package boundaries

Who paid for stats, film room, scouting. `module_entitlements.py` (`is_module_entitled:66`, `enforce_module_access:147`, `audit_team_entitlements:90`), `module_keys.py`, `audience_access.py`, `tests/test_audience_access.py`.

**This comes after the ledger is trustworthy.** The program file says it twice: section 4 item 9, "Package boundaries come after the ledger is trustworthy. Do not start there," and the June audit warning, "Do not start paid-package work from the June audit."

**Exit:** entitlement boundaries enforced, with the gates from 10b already passing.

## Do not, on this step

- Do not let the assistant answer from anything but reviewed rows.
- Do not let it estimate around a missing make.
- Do not claim the second gym works from the Adrian film. A second gym means a different camera.
- Do not start package work before 10a and 10b pass.
- Do not start paid-package work from the June 2026 gap audit. It is history.
- Do not grow a second database.

## Hand off with

Proven / Inferred / Unknown for each of 10a, 10b, 10c separately — they are three deliverables, not one — plus the four panel numbers, and the `ACTIVE.md` edit.
