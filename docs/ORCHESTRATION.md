# Liberty Orchestration — Cursor + Devin Workflow

Updated: 2026-07-05
Branch: `jason-5-may-updates`
Audience: Scott + Cursor Cloud Agent (orchestrator) + Devin (optional executor)

## Purpose

Run Liberty Basketball Analysis with **Cursor Pro as orchestrator** and **Devin for heavy implementation** while Scott has a paid Devin month. The repository is the message bus. No GitHub label polling.

## Parameters (locked)

- **Cursor budget:** Pro ($20/mo), **no pay-as-you-go** (on-demand disabled or $0 cap — Scott confirmed)
- **Devin:** use for implementation slices during paid month; do not duplicate the same ACTIVE task in both agents
- **Repository files are source of truth**, not chat history

## Account optimization checklist (Scott — do once)

Complete these in [cursor.com/dashboard](https://cursor.com/dashboard):

### Billing and usage

1. **Disable on-demand usage**, or set the monthly spend hard limit to **$0**. (Scott confirmed.)
2. **Check usage weekly** at Dashboard → Billing & Invoices → Included Usage.
3. **Archive stuck Cloud Agents** at [cursor.com/agents](https://cursor.com/agents) if you see false "limit reached" errors.

### Model picker (item 3 — nothing to install)

There is **no separate settings page** for this. When you open Cursor chat or start a Cloud Agent, use the **model dropdown** at the top of the input:

| When | Pick this |
| --- | --- |
| Normal Liberty work | **Auto** or **Composer** |
| Stuck on a hard decision | Sonnet or Opus (uses more of your $20 pool) |

That is the entire step. Default to Auto/Composer so Cursor credits last the month.

### GitHub + Cloud Agents (item 4 — quick verify)

If these are true, you are done — no further setup:

1. Go to [cursor.com/agents](https://cursor.com/agents)
2. You can start an agent on **`liberty-basketball-analysis`**
3. The agent checks out **`jason-5-may-updates`** (not `main`)

Optional check: Dashboard → Settings → GitHub shows the repo connected.

### Devin (paid month — use it for heavy lifting)

| Role | Tool | When to use |
| --- | --- | --- |
| **Orchestrator** | Cursor Cloud Agent | Plan slices, review PRs, update ACTIVE.md, quick fixes |
| **Executor** | Devin | Longer implementation runs (new modules, multi-file refactors, test-heavy slices) |

**Start Devin with one line:**

```
Clone scottmcconnell1-bot/liberty-basketball-analysis, branch jason-5-may-updates.
Read docs/ORCHESTRATION.md and docs/agent_handoffs/ACTIVE.md.
Execute the active task. Open a PR when done. Update ACTIVE.md report section.
```

**Rules:**

- Only **one** agent works the ACTIVE task at a time (Cursor **or** Devin, not both).
- Devin opens a PR; Cursor orchestrator reviews it.
- Do not renew Devin after the paid month unless Cursor alone is insufficient.

## Operating model

```
Scott starts one Cloud Agent session
        ↓
Orchestrator reads ACTIVE.md + PROJECT_STATUS.md
        ↓
Orchestrator plans bounded slice → implements or delegates to in-session subagents
        ↓
Work lands on cursor/<task>-ac1f branch + PR
        ↓
Orchestrator updates ACTIVE.md report (Proven / Inferred / Unknown)
        ↓
Scott reviews PR + /status + /preview when product-facing
```

### Roles

| Role | Who | Does | Does not |
| --- | --- | --- | --- |
| **Owner** | Scott | Scope, schema approval, phase transitions | Review every line of code |
| **Orchestrator** | Cursor Cloud Agent | Plan, bounded tasks, review PRs, update ACTIVE.md | Unbounded refactors |
| **Executor** | Devin (paid month) or Cursor subagents | Multi-file implementation, tests, PR | Change scope without ACTIVE.md update |
| **Subagents** | In-session Task tool (Cursor) | Focused explore/debug when Cursor implements | Separate billed Cloud VMs |

### Communication (no copy/paste)

| Artifact | Purpose |
| --- | --- |
| `docs/agent_handoffs/ACTIVE.md` | **Current task only** — objective, checklist, status, report |
| `docs/agent_handoffs/ARCHIVE/` | Completed tasks moved here |
| **Pull request** | Code diff, test evidence, review thread |
| `PROJECT_STATUS.md` | Long-lived Proven / Inferred / Unknown facts |

Do **not** use GitHub labels (`OWL ACTION`, etc.) for coordination. Comments on PRs are fine; labels are retired.

### Starting a session (Scott — one line)

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
5. Report as **Proven / Inferred / Unknown** — never present inference as fact.
6. **Stop and ask Scott** before changing `schema.sql`, feature flags `False → True`, or production detector settings.
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

## Related files

- `docs/agent_handoffs/ACTIVE.md` — current task
- `docs/agent_handoffs/ALPHA_GITHUB_SYNC_2026-07-05.md` — branch snapshot
- `PROJECT_STATUS.md` — verified project facts
- `ROADMAP.md` — direction
- `AUTHORITY.md` — who approves what
