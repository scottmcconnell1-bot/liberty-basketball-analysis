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
- Adrian OCR lookaround + tests (16 passed); Dayley #40 = Liberty away
- Layout tidy slice 1: removed 380 `_tmp*` / `_review*` artifacts
- Layout tidy slice 2: moved root `benchmark_*.py` + `_improve.py` → `scripts/` (not imported by app)
- Person YOLO bake-off (`scripts/benchmark_person_detectors.py` on `data/videos/Q1_snippet.mp4`, 16 frames @ conf 0.5):

| Model | people/frame | mean conf | FPS |
| --- | --- | --- | --- |
| yolov8n.pt | 6.75 | 0.694 | 4.8 |
| yolo11n.pt | 7.25 | 0.686 | 16.8 |

- Default **person** `detector_model` → **`yolo11n.pt`** (new installs / unset settings)
- Production **ball** detector / `ball_confidence` **unchanged**

## Next

1. Scott merge PR #142
2. Branch deletes after inventory OK
3. Optional: re-run bake-off with more frames / yolo11s if person recall still weak on full games
4. Layout slice 3 later: only after another explicit OK for moving imported CV modules

## Gated (still)

- `ball_detector.pt` / `ball_confidence`
- Feature flags False→True / teach / auto-accept
- Mass remote deletes
- Production flip to `precision` generator

## Report

### Proven
- yolo11n beat yolov8n on this snippet for person count + speed  
- Ball path untouched  

### Inferred
- Existing DBs that already saved `ai.detector_model=yolov8n.pt` keep that until Scott changes Settings  

### Unknown
- Whether full-game Adrian film prefers yolo11s over yolo11n  
