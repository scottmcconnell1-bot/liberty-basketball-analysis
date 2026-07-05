# Active Task

Updated: 2026-07-05
Branch: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | stage-7b-possession-film |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- `build_possession_workflow_summary()` assigns possessions idempotently and aggregates linkage counts
- `/film?game_id=…` shows Possessions card (total, scoring, pts/poss, TO rate, linked events)
- `/analysis/<game_id>` renders possession summary panel (fixed `content` block)
- 315 passed, 1 skipped

### Next

Stage 7C — player minutes on stats pages
