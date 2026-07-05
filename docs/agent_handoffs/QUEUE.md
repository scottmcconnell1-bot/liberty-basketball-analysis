# Task Queue

Updated: 2026-07-05
Driver: orchestrator — advances without per-step Scott approval (see `docs/COMPLETION_PATH.md`)

## Active

See `ACTIVE.md`.

## Up next (ordered)

| # | Stage | Summary | Executor |
| --- | --- | --- | --- |
| 1 | 6C | Entitlements on `/status` | orchestrator |
| 2 | 6B | `require_module` decorator + scouting/playbook gating | devin or orchestrator |
| 3 | 7A | requirements.txt / dev env fix | orchestrator |
| 4 | 7D | Review counts on status/preview | orchestrator |
| 5 | 7B | Possession display in film flow | devin |
| 6 | 7C | Player minutes on stats pages | devin |
| 7 | 8B | Module state on `/preview` | orchestrator |
| 8 | 8C | Stats from accepted events only (audit + fix gaps) | orchestrator |

## Blocked on Scott

| Stage | Why |
| --- | --- |
| 6D / 9B | Auth re-enable |
| 9C | Production exposure decision |
| 10A+ | Needs real reviewed game data in DB |

## Done recently

- 6A preflight + implementation (#70, #72)
- Orchestration workflow (#68, #69, #71)
- Bootstrap verification
