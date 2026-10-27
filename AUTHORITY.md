# Authority — Liberty Basketball Analysis

**Executor: Cursor.** Scott owns decisions; Cursor implements. Hermes may edit `ai_bridge.py` only (see `docs/agent_handoffs/HERMES.md`). Hermes never edits or is called from the core sequence.

## Roles

| Role | Responsibility |
| --- | --- |
| **Scott** | Scope, product direction, all gates below |
| **Cursor** | Builder, not orchestrator. Smallest checkable change. `applied_to_core` stays false. Sync `main`, `jason-5-may-updates`, and `Brad/Claude`. Does not assign tasks or manage the other agents. |
| **Claude Code** | Auditor and gatekeeper (took over from Muse 2026-10-26). Read `CLAUDE.md` and `ACTIVE.md` on `main`. Vets proposals, checks diffs and test results before commit, rejects drift. Same gates as Cursor. Does not assign tasks. No separate branch |
| **Ollama** | Read `OLLAMA.md` on this PC. Local model `gemma4:cloud`. Keep `SESSION_STATE.md`. Does not build, assign tasks, or manage the other agents. |

Scott (2026-10-20) allowed a candidate ball weights file. It is not `models/ball_detector.pt`. That production file and `ball_confidence` stay behind the gate above.

## Scott gates (stop and ask)

- `schema.sql` (or equivalent DDL) changes
- Feature flags `False` → `True`
- Production ball detector (`models/ball_detector.pt`, `ball_confidence`, related settings)
- Unpausing teach / auto-accept / raising auto-accept confidence
- Deleting features or breaking existing Film Review behavior without approval
- Deleting data (old analysis reruns, detections, tags) without an archive plan
- Mass-deleting remote branches (propose a list first)
- A name that might be a misspelling of a roster or scorebook name
- Changes to the protected core files in `.cursorrules` beyond a bug Scott has asked to fix

## Cursor may do without asking

- Bugfixes and refactors that do not cross the gates above
- Docs updates to ACTIVE / protocol / branch policy
- Tests, CI config, opt-in tools with defaults unchanged
- Speed fixes in the film tool, helpers, and templates that keep the same results

## Merge target

See `docs/BRANCH_POLICY.md`. Work and merge on `main`.

## Report format

Every handoff uses **Proven / Inferred / Unknown**. Chat memory is not repository truth.

- **Proven** means a command, a query, a file, or a screenshot was checked in this session. Say which one.
- A fix is not Proven until it was run against the real thing it fixes (the live film, the live page, the real database read-only), not only a test.
