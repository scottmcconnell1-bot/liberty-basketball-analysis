# Liberty Basketball Analysis — Project Memory

> **Project:** Liberty Basketball Analysis
> **Memory created:** 2025-05-29
> **Repo:** https://github.com/scottmcconnell1-bot/liberty-basketball-analysis
> **Local path:** `/home/monk-admin/PROJECTS/liberty-basketball-analysis`

---

## 1. Environment & Key Paths

| What | Path / Value |
|---|---|
| Project root | `/home/monk-admin/PROJECTS/liberty-basketball-analysis` |
| Active DB | `film_analysis.db` (228 MB) — **ONLY this one has data** |
| Empty DB | `liberty_basketball.db` (0 bytes) — do NOT use |
| Uploads | `uploads/` |
| Videos | `videos/` (see list below) |
| Pipeline output | `pipeline_output/` |
| Venv | `.venv/` (Python 3.11) |
| Git branch | `jason-5-may-updates` (latest commit: `2ce20f3`) |
| App entry | `app.py` → `film_analysis.db` |
| Schema | `schema.sql` (source of truth) |
| Tests | `.venv/bin/python -m pytest tests/ -q` |
| Run app | `python app.py` (hardcoded 5000; use 8081 for web) |
| Web port | **8081** |
---

## 2. Videos Available

| File | Size | Description |
|---|---|---|
| `videos/nfhs_720p_q1.mp4` | 256 MB | NFHS Q1 footage (primary analysis target) |
| `videos/nfhs_720p_full.mp4` | 132 MB | NFHS full game 720p |
| `videos/nfhs_1080p_clip2min.mp4` | 75 MB | 2-min 1080p clip |
| `videos/nfhs_720p_clip2min.mp4` | 32 MB | 2-min 720p clip |
| `videos/liberty_vs_riverstone_4k.mp4` | 176 MB | Liberty vs Riverstone 4K |
| `videos/nfhs_4K_gam021ddbf1cf.mp4` | 3052 MB | Full 4K game |

---

## 3. Current Work — Ball Detector (ACTIVE, BROKEN)

### Status: **DETECTOR IS BROKEN — DO NOT USE**

**Latest commit:** `2ce20f3` — "v43/v44: corrected shot filter + clip extraction for human review"

**Pipeline version history:**
- v34–v44: Progressive feature engineering on trajectory data
- Shot detection pipeline: `shot_v14.py` through `shot_v44.py`
- Current pipeline entry: `shot_v43.py` / `shot_v44.py`
- Models tried: v8, v9(a-f), v13–v44

**CRITICAL FINDINGS (May 28, 2026):**
- YOLO ball detector `ball_finetune/runs/finetune2/weights/best.pt` is **BROKEN**
- mAP=0 across all 15 epochs — structured false positives locked onto center-court artifact
- Detections concentrate at 50.2% court position (two 100px cells), Y std=58px
- ALL clustering pipelines v14→v40 (incl. F1650/F1780 "perimeter manifold") = garbage built on noise
- `pipeline_output/detection_heatmap.png` shows the failure pattern
- `pipeline_output/detection_scatter.png` and `detection_distributions.png` also diagnostic

**What NOT to use:**
- `ball_finetune/runs/finetune2/weights/best.pt` — broken weights
- Any pipeline output from v14 through v40

**Required fix approach (not yet implemented):**
1. Build new detector with 50-frame human benchmark first
2. Heatmap-first diagnostic: Gaussian heatmap + scatter + histograms from detection pickle
3. Use `execute_code` with `write_file` + `terminal` using `.venv/bin/python3` (sandbox lacks cv2/PIL/matplotlib)

**Recent untracked analysis scripts:**
- `audit_detector.py`, `audit_heatmap.py`, `audit_heatmap_fast.py`
- `audit_top20.py`, `audit_top20_v2.py`
- `annotate_top20.py`
- `make_heatmap.py`, `make_top20.py`
- `pipeline_output/detector_audit/annotated_top20/` (20 annotated frames)

---

## 4. Flask App — Completed Features

### All Phases Complete:
- **Phase 1:** Data model & schema (all tables in `schema.sql`)
- **Phase 2:** Schedule & season management (CRUD, filtering, cascade delete)
- **Phase 3:** Games & film sources (CRUD, NFHS VOD links, multi-source)
- **Phase 4:** NFHS matching (confirm/reject candidates, auto-create game + source)
- **Phase 5:** Stats aggregation (box-score stats from events)
- **Phase 6:** Practices & reports (AI notes, combined summaries, date-range)

### Key app files:
- `app.py` — main Flask app, routes, DB bootstrap, resource-status API
- `config.py` — feature flags
- `schema.sql` — DB schema source of truth
- `ai_analyzer.py` — YOLO detection → detections table
- `event_generator.py` — possession, shot, rebound, assist, etc.
- `stats.py` — event → box-score aggregation
- `film_analysis.py` — shot classification, player effect
- `tracker_assigner.py` — centroid-based tracker
- `player_development.py`, `nfhs.py`

### Security fixes applied (REX-CHANGES.md):
- Debug mode off by default
- SQLite WAL + busy_timeout on all connections
- Input validation on `save_event`
- XSS prevention in templates
- Auth middleware (disabled until user system exists)

---

## 5. Key Configuration

```bash
# Environment variables
LIBERTY_DATABASE=film_analysis.db
LIBERTY_UPLOAD_FOLDER=uploads
PORT=8080
LIBERTY_DEBUG=0  # set 1 for debug mode

# DB connections always use:
#   timeout=10, PRAGMA journal_mode=WAL, PRAGMA busy_timeout=10000
```

---

## 6. Important Conventions

- **Active DB is `film_analysis.db`** — never `liberty_basketball.db` (empty)
- All DB connections must use WAL mode + busy_timeout=10000
- `execute_code` sandbox lacks cv2/PIL/matplotlib — use `write_file` + `terminal` with `.venv/bin/python3`
- Git branch: `jason-5-may-updates`
- Tests: 45 test files in `tests/`

---

## 7. Telemetry & Usage Notes

- `execute_code` sandbox: no cv2, PIL, matplotlib — write scripts to file, run via terminal
- Repo has `yolov8n.pt`, `yolov8s.pt`, `yolo11m.pt` weights at root
- `weights_ameer/` directory has 4 additional model files
- PostgreSQL is NOT installed — project uses SQLite only (no psycopg2)
- PostgreSQL apt repo not configured

---

## 8. People & Communication

- **Jason** (Scott's son, user) — works on Liberty basketball analysis
- **Scott McConnell** — project owner (trader_bot + liberty basketball)
- **Rex (Hermes)** — AI agent doing development
- **Telegram groups:**
  - `LibertyBasketball` = `-5160711355` (OLD — migrated to supergroup)
  - New supergroup ID: `-1003931170751` (bot NOT yet re-invited)
  - When sending to group, use `target=origin` (reply to current conversation)
  - Home DM: `telegram` → `8564169612` (Jason)

---

## 9. Restart Checklist

If starting a new session, do these in order:

1. **Read this file** (`PROJECT_MEMORY.md`)
2. Verify DB: `ls -la film_analysis.db liberty_basketball.db`
3. Read `PROGRESS.md` last entries (commit `2ce20f3`)
4. Read `docs/AI_AGENT_HANDOFF.md`
5. **Ball detector is broken** — do not use `ball_finetune/runs/finetune2/weights/best.pt`
6. Build new 50-frame human benchmark before retraining
7. All analysis Python scripts: run via `.venv/bin/python3` not `execute_code` sandbox
