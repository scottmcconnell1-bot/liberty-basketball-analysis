# Dual-machine protocol (home + work PC)

Updated: 2026-08-03  
Shared branch: `cursor/full-film-panel-ac1f`  
Audience: Scott (and any Cursor agent on either machine)

## Goal

Work interchangeably on home and work PCs. **Git is the handoff.** Same branch, pull on arrive, push on leave.

## Shared branch

- Prefer **`cursor/full-film-panel-ac1f`** (confirm in `docs/agent_handoffs/ACTIVE.md`).
- Local branch must track `origin/cursor/full-film-panel-ac1f`.

## Arrive (either machine)

```powershell
powershell -File scripts/sync_liberty_work.ps1
```

That script: ensure `origin` fetches all branches → `fetch` → checkout shared branch → `pull --ff-only` → print status → remind to push before leaving.

Manual equivalent:

```powershell
git config remote.origin.fetch "+refs/heads/*:refs/remotes/origin/*"
git fetch origin
git checkout cursor/full-film-panel-ac1f
git pull --ff-only origin cursor/full-film-panel-ac1f
git branch --set-upstream-to=origin/cursor/full-film-panel-ac1f
git status -sb
```

## Leave (either machine)

1. Commit **code/docs** that belong on the shared branch (no secrets).
2. Push:

```powershell
git push -u origin HEAD
```

Optional overnight/home snapshot (already skips unsafe paths):

```powershell
powershell -File scripts/daily_git_save.ps1
```

## Source of truth

| Syncs via git | Stays machine-local (do NOT sync) |
| --- | --- |
| App code, templates, tests | `.env` / credentials |
| `docs/agent_handoffs/ACTIVE.md` | `film_analysis.db` (~GB) and other `*.db` |
| Playbook sheet-align cache (small JSON) | `uploads/` |
| Safe scripts under `scripts/` | Teach/panel runtime logs under `data/hoopsalytics/*.log`, detached PIDs, teach_loop_state |

**ACTIVE.md is agent truth.** Chat is not.

## Do not

- Force-push `main` / `master` / shared feature history.
- Kill `analysis_launcher` / `hoops_teach_loop` when restarting Flask (home teach loop).
- Expect film DB or uploads to appear after `git pull` — they will not.

## Agent session-start blurb (paste-ready)

```
Read docs/ORCHESTRATION.md, docs/DUAL_MACHINE.md, and docs/agent_handoffs/ACTIVE.md.
Shared branch: cursor/full-film-panel-ac1f. Pull --ff-only before claiming repo state; push before ending if you changed code/docs.
ACTIVE.md is truth. Do not sync or commit .env, film_analysis.db, uploads/, or teach runtime logs.
One bounded slice. Cursor Pro only. Report Proven / Inferred / Unknown.
Do not kill analysis_launcher / hoops_teach_loop.
```
