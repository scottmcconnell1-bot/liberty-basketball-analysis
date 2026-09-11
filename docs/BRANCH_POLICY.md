# Branch Policy

Updated: 2026-09-11

## Keep it small

| Branch | Role |
| --- | --- |
| `main` | Only integration line / GitHub default |
| `cursor/<topic>-ac1f` | **One** active work branch |
| Short-lived PR branches | Merge to `main`, then delete |

## Rules

1. Do not start a second topic branch without Scott’s OK.  
2. After merge: delete remote feature branch.  
3. Park work: note in `ACTIVE.md`, then delete or leave clearly named `parked/…` only if Scott asks.  
4. Legacy name `jason-5-may-updates` may remain temporarily as a pointer; new work targets **`main`**.  
5. Propose branch deletes as a list; Scott approves before mass delete.
