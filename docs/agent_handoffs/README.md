# Agent Handoffs

One active task file, not GitHub labels.

## Start here

1. `AUTHORITY.md` and `AGENT_PROTOCOL.md` at the repo root
2. **`docs/agent_handoffs/COUNT_FIXES_2026-10-10.md`** and **`docs/agent_handoffs/COUNT_ROADMAP_2026-10-10.md`** — what is broken, and the order to fix it
3. **`docs/agent_handoffs/ACTIVE.md`** — current state, open decisions, do-nots
4. `docs/BRANCH_POLICY.md` — work on `main`

## Workflow

1. Update `ACTIVE.md` when a task actually completes. Replace the paragraph it changes. Move old text to `ARCHIVE/`.
2. Code changes go to `main`. Open a pull request for Jason when asked, and the same one for Brad on `Brad/Claude`.
3. Jason's note is `JASON.md`. Brad's note is `BRAD.md`. Hermes' note is `HERMES.md`.

## Legacy (retired)

Alpha/Owl GitHub label polling is historical. The old issue and queue notes are in `ARCHIVE/legacy-alpha-owl/`. Do not create new Owl-labeled issues.

## Report format

```markdown
### Proven
(directly verified, say what was checked)

### Inferred
(reasonable conclusions)

### Unknown
(not yet verified)
```
