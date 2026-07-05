# Active Task

Updated: 2026-07-05
Branch: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | stage-10a-assistant-api |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- `POST /api/assistant/query` — read-only Q&A from trusted events, stats, clips
- `assistant_query.py` heuristic intents: player stats, team stats, turnovers, minutes, four factors, clips
- `ENABLE_ASSISTANT_READ_ONLY` feature flag + `AI_ASSIST` module gate
- Citations include event/stat/clip IDs; `review_scope=accepted_and_corrected_only`
- 360 passed, 1 skipped

### Next

Stage 10B — guided workflow: game → player → clip list
