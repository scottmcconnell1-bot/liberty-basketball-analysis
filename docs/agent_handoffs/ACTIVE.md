# Active Task

Updated: 2026-09-14  
Branch: `main`  
Base / default: `main`

## Meta

| Field | Value |
| --- | --- |
| **id** | p0-pages-done-auth-explain |
| **status** | `awaiting_scott` (auth decision only) |
| **executor** | cursor-only |

## Done (Proven)

- PR #142 / #143 on `main`; stale jason-5 PRs closed; 72 remote tips deleted
- PR #144 merged (ACTIVE handoff)
- Repo set **private**; GitHub Pages set **`public: false`** (site still exists but not world-readable). Pages cannot be fully deactivated (org/API 422).

## Next (await Scott)

1. **Auth / `/register`** — decide whether strangers should be able to create accounts (see chat explanation). No code change until you pick an option.
2. Optional: keep/delete `dataset-v2`, `improve/precision-and-migration`, `fix/game-id-analysis-key`, `jason-5-may-updates`

## Gated

- `ball_detector.pt` / `ball_confidence`
- Feature flags False→True / teach / auto-accept
- Production flip to `precision` generator
- Re-publicizing repo or Pages without Scott OK

## Remotes

`main`, `jason-5-may-updates`, `gh-pages`, `dataset-v2`, `improve/precision-and-migration`, `fix/game-id-analysis-key`
