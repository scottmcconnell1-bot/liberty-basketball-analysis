# Active Task

Updated: 2026-09-14  
Branch: `cursor/close-public-register-ac1f`  
Base / default: `main`

## Meta

| Field | Value |
| --- | --- |
| **id** | close-public-register |
| **status** | `in_progress` |
| **executor** | cursor-only |

## Done (Proven)

- Public self-signup closed: anonymous `/register` redirects to login; no account created
- Existing accounts unchanged (login still works)
- Admins create users via `/register` (linked from Users page)
- Register/Login nav copy updated; e2e seeds users in DB instead of public register

## Next

1. Verify tests / open PR → merge
2. Scott: create accounts while signed in as admin (Users → Create user)
3. Later (when ready): invite codes / email / SMS brainstorm → build

## Gated

- `ball_detector.pt` / `ball_confidence`
- Feature flags False→True / teach / auto-accept
- Production flip to `precision` generator
- Re-publicizing repo or Pages without Scott OK

## Remotes

`main`, `jason-5-may-updates`, `gh-pages`, `dataset-v2`, `improve/precision-and-migration`, `fix/game-id-analysis-key`, this branch
