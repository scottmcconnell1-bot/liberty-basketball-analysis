# Active Task

Updated: 2026-09-11  
Branch: `cursor/agent-os-ac1f`  
PR: https://github.com/scottmcconnell1-bot/liberty-basketball-analysis/pull/142  
Base / default: `main` (= former `jason-5-may-updates` tip `05c8475`)

## Meta

| Field | Value |
| --- | --- |
| **id** | agent-os-and-simplify |
| **status** | `in_progress` |
| **executor** | cursor-only |

## Done (Proven)

- GitHub default branch set to **`main`**
- Living docs: `AUTHORITY.md`, `AGENT_PROTOCOL.md`, `docs/BRANCH_POLICY.md`, this `ACTIVE.md`
- Cursor rule targets `main`
- Ported from `origin/claude/repo-branch-audit` (default `expanded` unchanged):
  - `.github/workflows/tests.yml`
  - `scripts/migrate_paths.py` (+ Windows-safe `/` rewrite)
  - `scripts/mark_stale_analysis_runs.py`
  - Opt-in **precision** event generator + settings catalog option
- Unit tests: migrate / stale / precision — **12 passed** locally

## Next (in order)

1. Scott review/merge PR #142  
2. Branch delete pass after Scott OK on inventory below  
3. Layout tidy only after Scott OK per step  
4. Measured YOLO/OCR upgrades later (Adrian-first)

## Branch inventory (await Scott OK before deletes)

### Keep

| Branch | Why |
| --- | --- |
| `main` | Default integration line |
| `cursor/agent-os-ac1f` | Active PR #142 |
| `origin/claude/repo-branch-audit` | Donor reference until PR merges / tools verified on main |
| `gh-pages` | GitHub Pages (if still used) |

### Likely delete (merged into `main` — ~43 remotes)

Safe candidates once Scott confirms: any `origin/cursor/*` listed by `git branch -r --merged origin/main` except none currently needed. Run after merge:

`git branch -r --merged origin/main`

### Likely delete (unmerged leftovers / superseded)

| Branch | Note |
| --- | --- |
| `jason-5-may-updates` | Tip equals old main; name retired |
| `improve/precision-and-migration` | Hermes dirty / do not merge |
| `cursor/active-in-progress-devin-ac1f` | Devin era |
| `claude/e2e-suite`, `claude/local-standup`, `claude/precision-mode` | Folded into repo-branch-audit or superseded |
| Most other unmerged `cursor/*` | Historical slices; keep only if Scott wants a specific tip |

### Ask Scott before touching

- `dataset-v2` — unknown value  
- `cursor/film-tool-review-layout-ac1f` — Adrian lookaround tip (`27b99a5` era)  
- Any branch Scott still references for film/demo work  

## Do not

- Schema / flags True / ball detector / unpause teach without Scott  
- Mass-delete branches without Scott’s list OK  
- Treat WSL Hermes dirty tree as source of truth  
- Flip `event_generator_mode` to `precision` in production without Scott (opt-in only)

## Report

### Proven
- PR #142 open with agent OS + Film Review tooling ports  
- Precision is catalog opt-in; default remains `expanded`

### Inferred
- Deleting merged remotes after Scott OK will cut noise without losing main history

### Unknown
- Which unmerged `cursor/*` tips Scott wants kept as reference
