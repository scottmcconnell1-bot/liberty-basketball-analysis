# Liberty Orchestration â€” Cursor-Only Workflow

Updated: 2026-07-05
Branch: `jason-5-may-updates`
Audience: Scott + Cursor Cloud Agent (orchestrator + executor)

## Purpose

Run Liberty Basketball Analysis with **Cursor Pro only**. The Cloud Agent plans, implements, tests, merges, and updates docs. The repository is the message bus.

## Parameters (locked)

- **Cursor budget:** Pro ($20/mo), **no pay-as-you-go** (on-demand disabled or $0 cap)
- **Cursor only:** Scott uses Devin for other projects; Liberty is driven entirely by the Cloud Agent
- **Autonomous mode:** orchestrator follows `docs/COMPLETION_PATH.md` and merges bounded slices after tests pass
- **Repository files are source of truth**, not chat history

## Account optimization checklist (Scott â€” do once)

Complete these in [cursor.com/dashboard](https://cursor.com/dashboard):

### Billing and usage

1. **Disable on-demand usage**, or set the monthly spend hard limit to **$0**. (Scott confirmed.)
2. **Check usage weekly** at Dashboard â†’ Billing & Invoices â†’ Included Usage.
3. **Archive stuck Cloud Agents** at [cursor.com/agents](https://cursor.com/agents) if you see false "limit reached" errors.

### Model picker (item 3 â€” nothing to install)

There is **no separate settings page** for this. When you open Cursor chat or start a Cloud Agent, use the **model dropdown** at the top of the input:

| When | Pick this |
| --- | --- |
| Normal Liberty work | **Auto** or **Composer** |
| Stuck on a hard decision | Sonnet or Opus (uses more of your $20 pool) |

That is the entire step. Default to Auto/Composer so Cursor credits last the month.

### GitHub + Cloud Agents (item 4 â€” quick verify)

If these are true, you are done â€” no further setup:

1. Go to [cursor.com/agents](https://cursor.com/agents)
2. You can start an agent on **`liberty-basketball-analysis`**
3. The agent checks out **`jason-5-may-updates`** (not `main`)

Optional check: Dashboard â†’ Settings â†’ GitHub shows the repo connected.

### Cursor Cloud Agent (sole executor)

One session reads `ACTIVE.md`, implements, tests, opens PR, merges when green.

**Start a session (optional â€” agent can also continue from queue):**

```
Read docs/COMPLETION_PATH.md and docs/agent_handoffs/ACTIVE.md. Execute the active task.
```

## Operating model

```
Scott starts one Cloud Agent session
        â†“
Orchestrator reads ACTIVE.md + PROJECT_STATUS.md
        â†“
Orchestrator plans bounded slice â†’ implements or delegates to in-session subagents
        â†“
Work lands on cursor/<task>-ac1f branch + PR
        â†“
Orchestrator updates ACTIVE.md report (Proven / Inferred / Unknown)
        â†“
Scott reviews PR + /status + /preview when product-facing
```

### Roles

| Role | Who | Does | Does not |
| --- | --- | --- | --- |
| **Owner** | Scott | Scope, schema approval, phase transitions | Review every line of code |
| **Orchestrator + executor** | Cursor Cloud Agent | Plan, implement, test, merge, update docs |

### Communication (no copy/paste)

| Artifact | Purpose |
| --- | --- |
| `docs/agent_handoffs/ACTIVE.md` | **Current task only** â€” objective, checklist, status, report |
| `docs/agent_handoffs/ARCHIVE/` | Completed tasks moved here |
| **Pull request** | Code diff, test evidence, review thread |
| `PROJECT_STATUS.md` | Long-lived Proven / Inferred / Unknown facts |

Do **not** use GitHub labels (`OWL ACTION`, etc.) for coordination. Comments on PRs are fine; labels are retired.

### Starting a session (Scott â€” one line)

```
Read docs/ORCHESTRATION.md and docs/agent_handoffs/ACTIVE.md.
Execute the active task on jason-5-may-updates. Update ACTIVE.md when done.
```

That is the only relay required.

## Orchestrator rules

1. Run git preflight before repo claims (`git fetch origin jason-5-may-updates`, compare HEAD).
2. One bounded slice per session when possible.
3. Prefer **in-session subagents** over spawning parallel Cloud Agents.
4. Run `python -m pytest tests/ -q` (or the focused subset named in ACTIVE.md) before marking done.
5. Report as **Proven / Inferred / Unknown** â€” never present inference as fact.
6. **Stop and ask Scott** before changing `schema.sql`, feature flags `False â†’ True`, or production detector settings.
7. Branch names: `cursor/<descriptive-name>-ac1f`.
8. When ACTIVE task completes: move file to `ARCHIVE/`, open next task in ACTIVE.md.

## Usage conservation

On $20 Pro, treat agent runs like a finite resource:

- Batch work: one session = one slice + tests + PR update.
- Avoid re-explaining the whole project each session; point at `ACTIVE.md` and `PROJECT_STATUS.md`.
- Do not spawn explore subagents unless the codebase search is genuinely large.
- Skip Playwright/UI audit tests unless the slice is UI-facing.
- Close the Cloud Agent session when the ACTIVE task is done.

## Legacy Alpha/Owl

`AGENT_PROTOCOL.md` and old `OWL ACTION` issues are **historical**. Do not create new Owl issues or labels. Open OWL issues on GitHub may be closed when convenient.


## Dual-machine (home + work)

Scott may switch PCs. Use **one shared feature branch** (see `ACTIVE.md`; currently `cursor/full-film-panel-ac1f`).

- Arrive: `pwsh -File scripts/sync_liberty_work.ps1` (fetch, checkout, `pull --ff-only`)
- Leave: commit safe code/docs, then `git push -u origin HEAD`
- Full protocol: `docs/DUAL_MACHINE.md`
- Never expect `.env`, `film_analysis.db`, or `uploads/` to sync via git

## Related files

- `docs/DUAL_MACHINE.md` — home + work PC pull/push protocol (code/docs only)

- `docs/agent_handoffs/ACTIVE.md` â€” current task
- `docs/agent_handoffs/ALPHA_GITHUB_SYNC_2026-07-05.md` â€” branch snapshot
- `PROJECT_STATUS.md` â€” verified project facts
- `ROADMAP.md` â€” direction
- `AUTHORITY.md` â€” who approves what
