# Active Task

Updated: 2026-07-05
Branch: `jason-5-may-updates`

## Meta

| Field | Value |
| --- | --- |
| **id** | stage-6c-status-entitlements |
| **status** | `in_progress` |
| **issued_by** | orchestrator |
| **assigned_to** | cursor-cloud-agent |

## Objective

Show module entitlement audit on `/status` per Stage 6C in `docs/STAGE_6A_PLAN.md` and `docs/COMPLETION_PATH.md`.

## Checklist

- [x] Call `audit_team_entitlements()` from status_page
- [x] Render enabled/disabled/missing keys per team on `status.html`
- [x] Add API test asserting Module Entitlements + base_platform visible
- [x] Run full pytest
- [ ] Merge PR (orchestrator)

## Report

_See PR after merge._
