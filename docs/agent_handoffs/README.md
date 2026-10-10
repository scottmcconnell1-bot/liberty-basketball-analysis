# Agent Handoffs

One active task file, not GitHub labels.

## Start here

1. `AUTHORITY.md` and `AGENT_PROTOCOL.md` at the repo root
2. **`docs/agent_handoffs/PROGRAM_FOR_JASON_2026-10-10.md`** — the whole program, then the current film count, the tries, and the order to finish
3. **`docs/agent_handoffs/COUNT_FIXES_2026-10-10.md`** and **`docs/agent_handoffs/COUNT_ROADMAP_2026-10-10.md`** — the current job only, in shorter form
4. **`docs/agent_handoffs/ACTIVE.md`** — current state, open decisions, do-nots
5. `docs/BRANCH_POLICY.md` — work on `main`

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
