# Liberty Orchestration — Cursor-Only Workflow

Updated: 2026-07-05
Branch: `jason-5-may-updates`
Audience: Scott + Cursor Cloud Agent (orchestrator)

## Purpose

Run Liberty Basketball Analysis with **one subscription** (Cursor Pro), **no pay-as-you-go**, and **no second agent product** (Devin). The Cursor Cloud Agent orchestrates work; subagents inside the same session do focused execution. The repository is the message bus.

This replaces the legacy Alpha/Owl label-and-poller workaround.

## Parameters (locked)

- **Budget:** Cursor Pro ($20/mo) only
- **No on-demand / pay-as-you-go billing**
- **No Devin subscription** for this project
- **No 24/7 autonomous pollers** until usage is proven sustainable
- **Repository files are source of truth**, not chat history

## Account optimization checklist (Scott — do once)

Complete these in [cursor.com/dashboard](https://cursor.com/dashboard):

### Billing and usage

1. **Do not subscribe to Devin** for Liberty work. Cursor covers orchestration + implementation.
2. **Disable on-demand usage**, or set the monthly spend hard limit to **$0**.
   - Cloud Agents may require on-demand to be *configured*; a $0 cap prevents surprise charges.
   - When the included ~$20 API pool is exhausted, agents stop. That is acceptable.
3. **Check usage weekly** at Dashboard → Billing & Invoices → Included Usage.
4. **Archive stuck Cloud Agents** at [cursor.com/agents](https://cursor.com/agents) if you see false "limit reached" errors.

### Model strategy (stretch the $20 pool)

| Use case | Model | Why |
| --- | --- | --- |
| Routine implementation, tests, docs | **Composer** or **Auto** | Lower cost; included generously |
| Orchestrator planning and review | **Composer** default; upgrade only for hard decisions | Reserve expensive models |
| Deep architecture / ambiguous tradeoffs | **Sonnet** or **Opus** | Use sparingly — burns pool fast |
| Parallel `/orchestrate` cloud workers | **Avoid by default** | Each worker is a separate billed VM run |

### What not to enable yet

- **Cursor Automations** on a cron (burns usage while idle)
- **`/orchestrate` parallel cloud-agent trees** for routine slices
- **Multiple simultaneous Cloud Agent sessions** on the same task

### GitHub connection

1. Connect `scottmcconnell1-bot/liberty-basketball-analysis` in Cloud Agents settings.
2. Working branch: **`jason-5-may-updates`** (not `main`).
3. Optional later: trigger Cloud Agent from a GitHub comment (`@cursor`) on a PR — only after the manual workflow is stable.

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
| **Orchestrator** | Cursor Cloud Agent | Plan, bounded tasks, implement or subagent, test, PR, docs truth | Drift from repo; unbounded refactors |
| **Subagents** | In-session Task tool | Focused explore/debug/implementation | Run as separate billed Cloud VMs |

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
