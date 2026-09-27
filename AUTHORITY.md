# Authority — Liberty Basketball Analysis

**Executor: Cursor only.** No Hermes/Owl/Alpha split. Scott owns decisions; Cursor implements.

## Roles

| Role | Responsibility |
| --- | --- |
| **Scott** | Scope, product direction, merges to `main`, all gates below |
| **Cursor** | Implement on one active branch, verify, update `docs/agent_handoffs/ACTIVE.md`, open PRs |

## Scott gates (stop and ask)

- `schema.sql` (or equivalent DDL) changes
- Feature flags `False` → `True`
- Production ball detector (`models/ball_detector.pt`, `ball_confidence`, related settings)
- Unpausing teach / auto-accept / raising auto-accept confidence
- Deleting features or breaking existing Film Review behavior without approval
- Mass-deleting remote branches (propose a list first)

## Cursor may do without asking

- Bugfixes and refactors that do not cross the gates above
- Docs updates to ACTIVE / protocol / branch policy
- Tests, CI config, opt-in tools with defaults unchanged
- Small layout moves **only after** Scott approves that specific step

## Merge target

- Default branch: **`main`**
- Work branch: **one** `cursor/<topic>-ac1f` at a time
- Merge via PR into `main` after Scott is satisfied

## Report format

Every handoff uses **Proven / Inferred / Unknown**. Chat memory is not repository truth.
