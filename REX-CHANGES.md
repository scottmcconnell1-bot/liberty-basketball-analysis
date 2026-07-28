# Rex Changes — Liberty Basketball Analysis

**Author:** Rex (Hermes Agent)  
**Date:** 2026-05-12  
**Branch:** jason-5-may-updates  
**Commit:** fec78530

## Summary of All Changes

This file documents all changes made by Rex in response to a Perplexity AI code review of the repository at https://github.com/scottmcconnell1-bot/liberty-basketball-analysis.

---

## Critical Fixes

### 1. Debug Mode Disabled by Default
- **File:** `app.py`
- **Change:** `debug=True` → controlled by `FLASK_DEBUG=1` environment variable
- **Why:** Running with `debug=True` on `host="0.0.0.0"` exposes the Werkzeug debugger and all API routes without authentication

### 2. Auth Middleware for /api/* Routes
- **File:** `app.py`
- **Change:** Added `@app.before_request` handler that checks `_current_user()` for all `/api/*` routes, returns 401 if not authenticated
- **Why:** All API routes were accessible without login

---

## High Fixes

### 3. save_event Input Validation + Error Handling
- **File:** `blueprints/clips.py`
- **Changes:**
  - Validates `event_type` is present and non-empty
  - Validates `timestamp_ms` is an integer
  - Validates `details_json` is valid JSON (if provided)
  - Sanitizes string inputs with length limits (game_id: 128, player: 128, shot_result: 32, source_video: 256)
  - Wraps DB writes in `try/except sqlite3.Error` with rollback and 500 response
- **Why:** Missing validation caused unhandled DB errors; bad types and oversized strings were accepted

### 4. Stored XSS Prevention
- **Files:** `templates/base.html`, `templates/analysis_results.html`, `templates/scouting_report.html`
- **Changes:**
  - Added global `escapeHtml()` JavaScript function to `base.html`
  - Applied `escapeHtml()` to all user-controlled values in innerHTML concatenations:
    - `analysis_results.html`: `e.event_type`, `p.play_type`
    - `scouting_report.html`: all personnel, offensive sets, defensive, tendencies, situational, mismatches, practice points, and clips fields
- **Why:** User-controlled data from DB was rendered via innerHTML without escaping, creating stored XSS risk

### 5. analysis_runs Lifecycle Fix
- **File:** `ai_analyzer.py`
- **Changes:**
  - Moved `generate_events` and progress updates from `finally` to `else` block (only runs on success)
  - Added `status='failed'` + `error_message` update in `except` block
  - Resource cleanup (`cap.release()`, `db.close()`) remains in `finally`
- **Why:** `generate_events` was running even after failures, and `analysis_runs` was never marked as failed

### 6. SQLite WAL + busy_timeout on All Connections
- **Files:** `ai_analyzer.py`, `event_generator.py`, `film_analysis.py`, `tracker_assigner.py`
- **Changes:** Added `timeout=10`, `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout = 10000` to all `sqlite3.connect()` calls
- **Why:** Multiple per-request/process SQLite writers without WAL caused "database is locked" failures

---

## Medium Fixes

### 7. tracker_assigner Transaction Framing
- **File:** `tracker_assigner.py`
- **Changes:**
  - Wrapped `write_tracker_ids` in `BEGIN IMMEDIATE` transaction
  - Added proper rollback on exception
- **Why:** Many single-row updates without explicit transaction framing caused lock contention

### 8. str(dict) → json.dumps (Already Fixed)
- **File:** `event_generator.py`
- **Status:** Already using `json.dumps` in `make_event()` — no change needed

---

## Files Modified (9 total)

1. `app.py` — debug mode + auth middleware
2. `blueprints/clips.py` — save_event validation
3. `ai_analyzer.py` — lifecycle fix + WAL
4. `event_generator.py` — WAL
5. `film_analysis.py` — WAL
6. `tracker_assigner.py` — WAL + transactions
7. `templates/base.html` — escapeHtml function
8. `templates/analysis_results.html` — XSS fixes
9. `templates/scouting_report.html` — XSS fixes

---

## Verification

- All existing tests should still pass (no breaking changes to public APIs)
- Auth middleware only affects `/api/*` routes; public pages remain accessible
- Debug mode can be re-enabled with `FLASK_DEBUG=1` for local development
