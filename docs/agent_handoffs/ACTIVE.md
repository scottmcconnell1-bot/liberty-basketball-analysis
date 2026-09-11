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
- Living docs + Cursor rule targeting `main`
- Film Review ports (CI, migrate_paths, mark_stale, opt-in precision; default **expanded**)
- **Adrian OCR lookaround** ported from `cursor/film-tool-review-layout-ac1f`:
  - `adrian_identity.py`, `adrian_quality.py`
  - `scripts/apply_adrian_jersey_lookaround.py`, `scripts/refine_adrian_events.py`
  - Tests: **16 passed**
  - Restored Adrian confirmed scorebook (Dayley #40 = Liberty away)
- **Layout tidy slice 1:** removed **380** tracked `_tmp*` / `_review*` probe artifacts; gitignore those patterns

## Next (in order)

1. Scott review/merge PR #142 (now includes Adrian OCR + layout slice 1)
2. Branch delete pass after Scott OK on inventory below
3. Layout tidy slice 2 (propose family before `git mv`): root CV modules → `src/cv/` **or** root one-off scripts → `scripts/` only
4. Measured YOLO upgrade **without** touching production `ball_detector.pt` / `ball_confidence` until Scott OK — person-model bake-off (`yolo11*` vs current) on Adrian film

## Still gated (ask Scott)

- Change production `models/ball_detector.pt` or `ball_confidence`
- Flip any feature flag False→True / unpause teach / raise auto-accept
- Mass-delete remotes
- Flip Settings `event_generator_mode` → `precision` in production

## Branch inventory (await Scott OK before deletes)

### Keep

| Branch | Why |
| --- | --- |
| `main` | Default integration line |
| `cursor/agent-os-ac1f` | Active PR #142 |
| `origin/claude/repo-branch-audit` | Donor until tools verified on main |
| `gh-pages` | Pages (if still used) |

### Likely delete

- Merged remotes (`git branch -r --merged origin/main`)
- `jason-5-may-updates` (retired name)
- `improve/precision-and-migration` (Hermes dirty)
- `cursor/active-in-progress-devin-ac1f`
- Most other unmerged historical `cursor/*` / `claude/*` after Scott scan

### Ask before touching

- `dataset-v2`
- `cursor/film-tool-review-layout-ac1f` (Adrian donor tip — keep until PR merges)

## Do not

- Schema / flags True / ball detector / unpause teach without Scott  
- Mass-delete branches without list OK  
- Treat WSL Hermes dirty tree as source of truth  
- Hermes-style mass `src/` dump in one shot  

## Report

### Proven
- Adrian lookaround + quality on this branch; 16 tests green  
- 380 temp artifacts untracked; ignore rules added  
- Production ball detector / confidence unchanged  

### Inferred
- Next biggest layout win is moving one root module family with import updates, not a full tree rewrite  

### Unknown
- Which unmerged tips Scott wants kept after PR merges  
- Whether person-model default should move to YOLO11 after a measured Adrian bake-off  
