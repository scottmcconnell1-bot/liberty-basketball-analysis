# Active Task

Updated: 2026-09-14  
Branch: `cursor/e2e-port-ac1f`  
Base / default: `main` (PR #142 merged)

## Meta

| Field | Value |
| --- | --- |
| **id** | e2e-port-from-jason |
| **status** | `in_progress` |
| **executor** | cursor-only |

## Done (Proven)

- PR #142 merged to `main` (agent OS, Film tools, Adrian OCR, layout, person YOLO)
- PR #140 closed as superseded by #142
- Porting from Jason #141 onto main: E2E suite, seeder, notification INSERT fix, admin-reset FK order, video_trim cross-worker/collision fixes, E2E + quality docs

## Next

1. Finish/verify this E2E port PR
2. Close or park #141 after port lands
3. Branch cleanup inventory for Scott OK
4. Revisit Jason P0 TODO (GitHub Pages exposure, auth) as Scott decisions

## Gated

- `ball_detector.pt` / `ball_confidence`
- Feature flags False→True / teach / auto-accept
- Mass remote deletes
- Production flip to `precision` generator

## Report

### Proven
- `main` now carries Cursor agent OS + Film tooling from #142  
### Inferred
- #141 unique value is E2E/seeder/bugfixes, not the jason-5 merge stack  
### Unknown
- Whether every e2e scenario passes against current main without scenario edits  
