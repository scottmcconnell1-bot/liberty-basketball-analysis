# Assisted stating — product note (SAMPLE)

Updated: 2026-08-09  
Branch: `cursor/assisted-stat-sample-ac1f`  
Status: **prototype only — delete/revert when product direction is decided**

## Recommendation

**Do not kill overnight detection jobs.** Reprioritize the product surface to a **review / confirm UI**. CV / teach-loop becomes a **draft event generator**; coaches Accept / Correct / Reject.

## Sample

- Static (open in browser): [`assisted_stat_sample.html`](assisted_stat_sample.html)
- App route (when Flask is running): `/film/assisted-stat-sample`
- Banner: **SAMPLE / DELETE ME**

## Screens in the sample

1. Game list — pick a game to stat  
2. Assisted workspace — video placeholder + candidate timeline + Accept / Correct / Reject + running score + quarter gate  
3. Correct modal — event type / jersey / points  

## Feasibility (brief)

| Path | Effort | Reuse |
| --- | --- | --- |
| MVP confirm UI on existing `events` (`human_verified`, clip update APIs) | **~2–4 days** | `film_tool.html`, `review_events.html`, `docs/REVIEW_WORKFLOW_PLAN.md`, `docs/FILM_TOOL_AI_EVENTS.md`, `blueprints/clips.py` |
| Full product (review_items, corrections ledger, quarter gates, training export) | **1–2+ weeks** | schema + workflow plan gaps |

“Without much trouble” ≈ MVP confirm UI, not the full review platform.
