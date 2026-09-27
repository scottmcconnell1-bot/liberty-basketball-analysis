# Analysis speed: validation log (2026-09-27)

## What was seen on the live server

A live read-only check showed the Adrian Jr High rerun on the home PC at about
**1 frame/second**:

- It went from frame 2,000 at 23:00 to frame 30,000 at about 06:11 MDT.
- The RTX 5060 GPU sat at **1% utilisation**.
- At that rate the 97,475-frame game takes about 27 hours.

## Cause, measured in Docker

The real `ai_analyzer.run_ai_analysis` was run on a 20 s cut of
`data/videos/Q1_snippet.mp4` (602 frames) in the `liberty-analysis:cpu` image,
using `scripts/bench/bench_analysis_loop.py`. The database was padded with other
games' detections to mimic the live table.

| Detections already in DB | No index (before) | Index added | Fixed code (index created automatically) |
|---|---:|---:|---:|
| 0 | 11.2 fps | — | — |
| 1,000,000 | 7.7 fps | 10.6 fps | — |
| 3,000,000 | 5.0 fps | 10.1 fps | **11.4 fps** |

- **The slow query:** with the tracker wrapper on (the default), each frame runs
  `SELECT … FROM detections WHERE game_id=? AND frame_number=?`. The table had no
  index at all, so every frame scanned every row.
- **Cost:** about **0.034 s per frame per million rows**. The live table held 55.6M rows
  before the 2026-09-15 wipe and refills with every run (about 10 rows per frame). At about
  25M rows that is about 0.85 s per frame, which matches the ~1 fps seen live.
- **Why the GPU sat idle:** on the GPU, YOLO takes only a few milliseconds per frame, so
  this query was nearly all of the frame time.

Jersey OCR (EasyOCR, hard-coded `gpu=False`):

- **Speed:** 10.2 fps without it, 7.8 fps with it.
- **Cost:** 869 `readtext` calls took 19.5 s of the 77 s loop.
- **Payoff:** those calls produced **6 jersey reads in 602 frames**.

## Fixes, each validated → fixed → revalidated

Every test in the table fails on `origin/cursor/playbook-jason-clean-slate-ac1f`
(28ad1d5) and passes after the fix. The tests are in `tests/test_analysis_speed.py`
unless another file is named.

| # | Problem | Fix | Regression test |
|---|---|---|---|
| 1 | No index for the per-frame detection lookup | `idx_detections_game_frame` on `detections(game_id, frame_number)`, in `schema.sql` for new DBs | test_new_database_indexes_the_per_frame_detection_lookup |
| 2 | The live DB never gets a new schema index | `helpers.ensure_detection_indexes()` runs from `_ensure_migration_columns` at app start | test_existing_database_gets_the_index_at_startup, test_detection_index_helper_is_shared_and_idempotent |
| 3 | Analyses started by the teach loop run before any app restart | `ai_analyzer.run_ai_analysis` calls `ensure_detection_indexes` before its frame loop | test_analyzer_adds_the_index_before_its_frame_loop |
| 4 | Jersey OCR always on the CPU | `jersey_ocr._get_ocr_engine` uses `gpu=torch.cuda.is_available()` | test_jersey_ocr_uses_the_gpu_when_cuda_is_available |
| 5 | `docker build` failed: `requirements.docker.txt` includes `-r requirements-dev.txt`, which the Dockerfile never copied | The Dockerfile copies both files | test_dockerfile_copies_every_requirements_file_it_installs |
| 6 | `/sw.js` returned 404 live: the route was defined after `app.run()` in `app.py`, so `python app.py` never registered it | The route moved above the `__main__` block | test_service_worker_is_served_when_app_runs_as_a_script (starts `python app.py` and requests `/sw.js`) |
| 7 | `load_all_settings` raised on a DB without `app_settings` (fixed in closed PR #139 but never ported) | A missing table is treated as "no overrides" | tests/test_ai_analyzer.py::test_run_ai_analysis_raises_when_video_missing |
| 8 | The analyzer loaded about 170 MB of weights before checking the video exists | The video is checked first | same test as #7 |

**A test that was wrong, not the code:**
`tests/test_nfhs_download.py::test_start_video_analysis_requires_ai_packages` assumed
OpenCV/YOLO were *not* installed, so it failed wherever they are. It now forces the
"packages unavailable" condition itself.

## Results

| Environment | Result |
|---|---|
| Full CV image (`bash scripts/docker_test.sh`) | **989 passed, 38 skipped** |
| CI-like `python:3.12-slim` + `requirements.txt` (`bash scripts/docker_test.sh --ci`) | **976 passed, 25 skipped** |
| `ruff --select F821,F811,F823,E9` | clean |
| Benchmark, fixed code, 3M-row DB | **11.4 fps (was 5.0)** |

## What to expect on the home PC

**First start after deploy:** `CREATE INDEX` on the large live table runs once. It can
take a minute or two and blocks writes while it runs. Do it while no analysis is
running, or let the next analysis create it.

**Speed after that:** the frame loop should be limited by YOLO and decoding on the GPU,
not by SQLite. That is expected to be many times faster than the ~1 fps seen live. This
was not measured on the home PC: this machine has no NVIDIA GPU.

**Further speed-ups, which are Scott's decisions because they change accuracy/behaviour:**
- `ai.jersey_ocr_stride` 5 → 15 or 30, or turn jersey OCR off until it reads more than
  about 1% of boxes.
- `ai.detection_stride` 1 → 2, which halves YOLO work.
