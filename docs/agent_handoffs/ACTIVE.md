# Active Task

Updated: 2026-09-11  
Branch: `cursor/agent-os-ac1f`  
PR: https://github.com/scottmcconnell1-bot/liberty-basketball-analysis/pull/142  
Base / default: `main`

## Meta

| Field | Value |
| --- | --- |
| **id** | agent-os-and-simplify |
| **status** | `in_progress` |
| **executor** | cursor-only |

## Done (Proven)

- Default branch = `main`; living docs + Cursor rule
- Film Review ports: CI, migrate_paths, mark_stale, opt-in precision (default **expanded**)
- Adrian OCR lookaround from `cursor/film-tool-review-layout-ac1f`:
  - `adrian_identity.py`, `adrian_quality.py`
  - `scripts/apply_adrian_jersey_lookaround.py`, `scripts/refine_adrian_events.py`
  - Tests: **16 passed**; confirmed scorebook Dayley #40 = Liberty away
- Layout tidy slice 1: removed **380** tracked `_tmp*` / `_review*` artifacts; gitignore those patterns
- Production `ball_detector.pt` / `ball_confidence` **unchanged**

## Next

1. Scott merge PR #142
2. Branch deletes after inventory OK
3. Layout slice 2 — pick one family before move: root CV → `src/cv/` **or** one-off root scripts → `scripts/`
4. Measured person-YOLO bake-off (`yolo11*` vs current) on Adrian film — **ask before** changing ball detector weights/confidence

## Gated

- `ball_detector.pt` / `ball_confidence`
- Feature flags False→True / teach / auto-accept
- Mass remote deletes
- Production flip to `precision` generator

## Report

### Proven
- Adrian lookaround + layout slice 1 on PR #142  
### Inferred
- Next layout win is one module family, not a Hermes mass move  
### Unknown
- Keep list for unmerged tips; whether person default should become YOLO11 after bake-off  
