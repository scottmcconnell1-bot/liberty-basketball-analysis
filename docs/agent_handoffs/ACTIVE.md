# Active Task

Updated: 2026-07-05
Branch: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | stage-6b-module-gating |
| **status** | `in_progress` |
| **issued_by** | orchestrator |
| **assigned_to** | cursor-cloud-agent |

## Objective

Stage 6B: soft module gating on scouting and playbook routes per `docs/STAGE_6A_PLAN.md`.

## Checklist

- [x] `is_module_accessible` — base required; unconfigured add-ons allowed
- [x] `enforce_module_access` + blueprint `before_request` on scouting/playbook
- [x] `get_default_team_id` helper
- [x] Tests for soft gate + disabled module 404
- [x] Full pytest green
- [ ] Merge PR

## Next after merge

Stage 7A: requirements.txt / dev env fix (see QUEUE.md)
