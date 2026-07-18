# Active Task

Updated: 2026-07-18
Branch: `cursor/fix-wilder-compare-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | fix-wilder-compare |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- PDF `No comparison available.pdf` is a Chrome print of `/videos/8/compare` (Liberty vs Wilder High School). Exact on-page error: **"AI analysis is not available on this server."**
- Compare route works: video id 8 has 3 completed analysis_runs (primary 0 events; reruns 40 and 99 events). Detections exist (190 / 2875) but compare SQL showed **0** because it queried `games.game_id` (column does not exist) and skipped rows with `relational_game_id` set.
- Wilder NFHS mp4 is **missing on disk** (`uploads/nfhs_gam30b09cbb4f_…_191311.mp4` and original `nfhs_gam30b09cbb4f.mp4`). Only Riverstone mp4 remains in `uploads/`. Cannot restore from local data.
- Port 8080 was served by `.venv` Python (no cv2/ultralytics). System Python 3.12 has AI packages, but was not the process answering `/api/ai/runtime`.

### Fixed

- `blueprints/ai.py` compare counts via `count_detections_for_analysis` / `count_events_for_analysis` keyed by `analysis_key`
- Compare template banners for missing video file + clearer AI-unavailable copy
- Tests: relational detection counts + missing-video banner

### User must do

1. Restart Liberty so code changes load (and preferably run the interpreter that has cv2/ultralytics — system Python 3.12, or install AI into `.venv`).
2. Re-download NFHS VOD `gam30b09cbb4f` (or re-upload the Wilder mp4) before new reruns / Film Tool playback.

### Compare after fix

- Count comparison of existing runs: yes (after restart).
- New "Rerun AI" comparison pass: blocked until AI runtime + video file restored.
