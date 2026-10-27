# Authority — Liberty Basketball Analysis

**Roles (Scott, 2026-10-26):** Scott decides. Hermes plans. OpenCode (DeepSeek) codes. Claude Code vets the plan and the code. Every agent can see the repo and the local folder. Hermes plans and does not edit source files; nothing is ever called from the core sequence.

## Roles

| Role | Responsibility |
| --- | --- |
| **Scott** | Scope, product direction, all gates below |
| **Hermes** | Architect. Reads `ACTIVE.md` and the repo, writes one small task to `NEXT_TASK.md`. Plans only; does not edit source files. Note: `docs/agent_handoffs/HERMES.md` |
| **OpenCode (DeepSeek)** | Coder. Implements a `VETTED` plan with the smallest checkable change. `applied_to_core` stays false. Does not assign tasks or check its own work. |
| **Claude Code** | Vetter and gatekeeper (took over from Muse 2026-10-26). Vets the plan before code, checks the diff and the real tests before commit, rejects drift, records verified results. Does not plan, code, or assign tasks. Note: `CLAUDE.md` |
| **Cursor** | Not assigned. Scott has not decided whether it stays. |
| **Retired 2026-10-26** | Muse, Ollama (project manager), Gemini, Aider (builder). `MUSE.md` and `OLLAMA.md` stay as records. |

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

## The coder may do without asking

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
