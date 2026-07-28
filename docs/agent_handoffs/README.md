# Agent Handoffs

Current coordination uses **one active task file** — not GitHub labels.

## Start here

1. `docs/ORCHESTRATION.md` — account setup, roles, usage rules
2. **`docs/agent_handoffs/ACTIVE.md`** — current bounded task and report
3. `PROJECT_STATUS.md` — long-lived verified facts

## Workflow

1. Orchestrator writes or updates `ACTIVE.md` with objective + checklist.
2. Cloud Agent session executes the checklist on `jason-5-may-updates`.
3. Agent updates the Report section (Proven / Inferred / Unknown) and sets status to `done`.
4. Completed tasks move to `ARCHIVE/`.
5. Code changes go through a PR on `cursor/<task>-ac1f`.

Scott starts a session with:

```
Read docs/ORCHESTRATION.md and docs/agent_handoffs/ACTIVE.md. Execute the active task.
```

## Legacy (retired)

Alpha/Owl GitHub label polling (`OWL ACTION`, `OWL DONE`, `OWL NEEDS`) is historical. Do not create new Owl-labeled issues.

Older snapshots remain for audit:

- `ALPHA_GITHUB_SYNC_2026-07-05.md`
- `ISSUE_*` files

## Report format

```markdown
### Proven
(directly verified)

### Inferred
(reasonable conclusions)

### Unknown
(not yet verified)
```
