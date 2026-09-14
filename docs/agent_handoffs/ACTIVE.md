# Active Task

Updated: 2026-09-14  
Branch: `cursor/handoff-post-e2e-ac1f` (docs only)  
Base / default: `main` (PR #143 merged)

## Meta

| Field | Value |
| --- | --- |
| **id** | post-e2e-cleanup-and-p0-pause |
| **status** | `awaiting_scott` (P0 only) |
| **executor** | cursor-only |

## Done (Proven)

- PR #142 / #143 on `main`; #140 / #141 closed superseded
- Closed 19 stale open PRs targeting `jason-5-may-updates` (#139, #134–#123, #112, #93–#90, #67) — commits recoverable from closed PRs
- Deleted **72** stale remote tips (`claude/*` + old `cursor/*`)
- Remotes now: `main`, `jason-5-may-updates`, `gh-pages`, `dataset-v2`, `improve/precision-and-migration`, `fix/game-id-analysis-key`, `cursor/handoff-post-e2e-ac1f` (#144)

## Next (await Scott — P0)

1. GitHub Pages / `gh-pages` exposure  
2. Auth model and `/register`  
3. Optional later: decide keep/delete for `dataset-v2`, `improve/precision-and-migration`, `fix/game-id-analysis-key`; merge/close #144

## Gated

- `ball_detector.pt` / `ball_confidence`
- Feature flags False→True / teach / auto-accept
- Production flip to `precision` generator
- Touching / deleting `gh-pages` without Scott OK

## Remaining remotes

| Branch | Role |
| --- | --- |
| `main` | Integration line |
| `jason-5-may-updates` | Historical pointer (temp) |
| `gh-pages` | Deploy — P0 review before any change |
| `dataset-v2` | Decide later |
| `improve/precision-and-migration` | Decide later |
| `fix/game-id-analysis-key` | Decide later |
| `cursor/handoff-post-e2e-ac1f` | This handoff PR (#144) |

## Report

### Proven
- Open PRs against jason-5 cleared; remote tip count reduced to 7  
### Inferred
- Unique WIP from closed #134 (Recruiting) / #133 (playbook digitize) still recoverable via those PR commit SHAs if needed later  
### Unknown
- Whether `gh-pages` still publishes anything sensitive  
