# Active Task

Updated: 2026-08-09 (assisted-stat sample)

Branch: `cursor/assisted-stat-sample-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | assisted-stat-sample |
| **status** | `prototype` |
| **assigned_to** | cursor-agent |

## Decision (Scott — recommendation)

**Reprioritize product** to AI-assisted manual stating (review/confirm UI). Do **not** necessarily kill overnight detection / teach-loop jobs — CV becomes a **draft generator**. Coaches Accept / Correct / Reject.

## Sample (undoable)

- Route: `/film/assisted-stat-sample`
- File: `docs/prototypes/assisted_stat_sample.html`
- Note: `docs/prototypes/ASSISTED_STAT_SAMPLE.md`
- Banner: SAMPLE / DELETE ME — easy revert of this branch

Screens: (a) game list (b) assisted workspace + quarter gate (c) correct modal.

## Prior sticky work

Previous ACTIVE was playbook dash-based pass/cut on `cursor/sticky-choreography-ac1f` (implemented). This sample branch is isolated from that product path.

## Report

### Proven

- Film tool already has AI events panel + seek (`docs/FILM_TOOL_AI_EVENTS.md`, `templates/film_tool.html`).
- Review Accept/Correct/Reject UI + `events.human_verified` exist (`docs/REVIEW_WORKFLOW_PLAN.md`, `templates/review_events.html`, clips APIs).

### Inferred

- MVP confirm UI on existing `events` is days, not weeks.
- Full review platform (queue ledger, corrections wiring, quarter gates as product rules) is weeks.

### Unknown / remaining

- Whether Scott wants MVP confirm-first or waits for fuller review_items schema.
- Keep overnight detection running vs pause GPU budget (ops choice; product rec is keep drafts flowing).
