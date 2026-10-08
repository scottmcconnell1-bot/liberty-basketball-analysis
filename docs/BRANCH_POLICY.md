# Branch Policy

Updated: 2026-10-07

## Keep it small

| Branch | Role |
| --- | --- |
| `main` | Working branch and GitHub default. Finished work is merged here and pushed. |
| `jason-5-may-updates`, `Brad/Claude` | Mirrors. They stay even with `main`. |
| Short-lived PR branches | Merge to `main`, then delete |

## Rules

1. Work on `main`. A side branch or a write-up is not the current code.
2. Do not start a second topic branch without Scott's OK.
3. When a pull request is opened for Jason, push the same commits to `Brad/Claude` and open the matching pull request there.
4. After a merge, delete the short-lived remote branch.
5. Park work in a note in `ACTIVE.md`. Do not leave unnamed branches behind.
6. Propose branch deletes as a list. Scott approves before any mass delete.
7. Never force-push and never amend a pushed commit.
