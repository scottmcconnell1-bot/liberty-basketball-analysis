# Active Task

Updated: 2026-07-19
Branch: `cursor/fix-app-context-postprocess-ac1f`

## Meta

| Field | Value |
| --- | --- |
| **id** | fix-app-context-postprocess |
| **status** | `done` |
| **assigned_to** | cursor-cloud-agent |

## Report

### Proven

- **Root cause (215754):** After event generation, `auto_accept_high_confidence_events` → `refresh_game_stats` → `feature_enabled()` → Flask `current_app` with no app context in the AI worker subprocess. Log: `logs/ai-*215754*.log` ends with events written then `Working outside of application context` (no stack in log because post-process raises outside the detection `try/except`).
- **Fix:** `helpers.refresh_game_stats` uses `has_app_context()` / DB settings; `event_generator.persist_events` best-effort wraps auto-accept; `review_actions` guards RuntimeError; `ai_analyzer` prints traceback on failure.
- **DB repair:** Marked `__rerun_20260718_215754` (id=22) `status=completed` (4741 events, dets 0–871000ms) without re-running GPU.
- **Conflict:** Another agent had started `__rerun_20260719_152408` (id=23) at ~2–4%; stopped to avoid duplicate GPU work. Events already exist on 215754.
- **KPIs unchanged:** exact 22 / manual-only 31 / AI-only 2726 — next issue is precision, not coverage.
- **Side-by-side:** regenerated; run_status=`completed`.

### Files

- `helpers.py`, `event_generator.py`, `review_actions.py`, `ai_analyzer.py`
- `tests/test_refresh_game_stats_no_app_context.py`
