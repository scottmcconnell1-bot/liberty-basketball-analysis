WORKLOG — Liberty Basketball Analysis
Started: 2026-04-27

CURRENT STATUS (updated 2026-05-07 by Rex)
============================================

Repository: https://github.com/scottmcconnell1-bot/liberty-basketball-analysis
Local path: /home/monk-admin/PROJECTS/liberty-basketball-analysis
Branch: jason-5-may-updates
Flask app runs on port 8080 (development server) or 8081 (cloudflared tunnel)

COMPLETED PHASES (per Master Project Outline)
----------------------------------------------

Phase 1 — Data Model & Schema:
  ✅ All tables created in schema.sql (analysis_runs, detections, events, seasons,
     scheduled_games, games, nfhs_matches, sources, players, stats, practices,
     videos, app_settings, issue_reports)
  ✅ tracker_id column added to detections table
  ✅ schema.sql is source of truth for DB

Phase 2 — Core Schedule & Season Management:
  ✅ Seasons CRUD (season_management.py + /api/seasons + /schedule page)
  ✅ Scheduled Games CRUD (season_management.py + /api/scheduled_games + /schedule page)
  ✅ /schedule route and schedule.html with server-rendered games table
  ✅ Filtering by season, level, gender, status
  ✅ Cascade delete (deleting season removes its games)
  ✅ Feature flag: ENABLE_SEASONS_SCHEDULE (default: True)

Phase 3 — Games & Film Sources:
  ✅ Games CRUD (/api/games) — create from scheduled_game or standalone
  ✅ Result fields: home_score, away_score, result (win/loss), is_conference
  ✅ Sources CRUD (/api/sources) — attach NFHS VOD links, manual uploads, local files
  ✅ Multiple sources per game supported
  ✅ Feature flag: ENABLE_GAMES_SOURCES (default: True)

Phase 4 — NFHS Matching & Light Automation:
  ✅ Manual NFHS candidate add (/api/nfhs_matches POST)
  ✅ Confirm match (auto-creates game + nfhs_vod source)
  ✅ Reject match
  ✅ match_status tracking: candidate, confirmed, rejected

Phase 5 — Stats & Event Usage:
  ✅ stats.py aggregates events into box-score stats
  ✅ Stats persisted to stats table (pts, fgm, fga, threes_made, threes_att, ast, reb, tov, stl, blk)
  ✅ UNIQUE constraint on (game_id, player_id)

Phase 6 — Practices & Practice Reports:
  ✅ Practices table in schema.sql (season_id, level, practice_date, status, plan_source,
     plan_text, coach_notes, ai_notes, combined_summary)
  ✅ /practices route and practices.html — full CRUD with season/level/status filters
  ✅ /practices/<id>/report — practice report page with toggleable sections
     (plan, coach notes, AI notes, combined summary)
  ✅ AI notes generation (build_practice_ai_notes) — heuristic-based theme inference
     from plan + coach notes, with recommended next-block suggestions
  ✅ Combined summary (build_practice_combined_summary) — Plan/Coach/AI/Film source tags
  ✅ Date-range practice summary (/practice-summary) — counts, theme frequency, suggestions
  ✅ Feature flag: ENABLE_PRACTICES (default: True)

AI Pipeline:
  ✅ ai_analyzer.py — YOLO detection, writes to detections table with tracker_id placeholder
  ✅ Class name normalization: 'sports ball' → 'ball' in both ai_analyzer and event_generator
  ✅ tracker_assigner.py — lightweight centroid-based tracker (nearest-neighbor matching)
  ✅ event_generator.py — ball possession, dribble detection (heuristic), expanded event
     generation (possession segments → shots, rebounds, assists, blocks, turnovers, fouls)
  ✅ Config: USE_DRIBBLE_EVENTS=False, USE_DRIBBLE_HEURISTICS=True
  ✅ event_generator_mode: "expanded" (default)

Infrastructure:
  ✅ Feature flags in config.py (ENABLE_* and USE_* pattern)
  ✅ 90/90 tests passing (test_api.py, test_season_management.py, test_schema.py,
     test_event_pipeline.py)
  ✅ .gitignore properly configured
  ✅ GitHub SSH auth via ~/.ssh/basketball_deploy_key
  ✅ Cloudflare tunnel active (port 8081 for PROJECTS copy)

KNOWN ISSUES / TECHNICAL DEBT
------------------------------
1. ~~Dribble detection is heuristic-only~~ — improved with ByteTrack integration
2. ~~tracker_assigner is lightweight centroid matching~~ — now uses ByteTrack via model.track()
3. ~~AI notes for practices are heuristic/rule-based~~ — now uses Ollama LLM with heuristic fallback
4. ~~No production WSGI server~~ — gunicorn configured
5. ~~No automated backup/restore~~ — backup.sh script added
6. ~~No deployment smoke tests~~ — smoke_test.sh script added
7. ~~app.py monolith (3,297 lines)~~ — split into 7 Flask Blueprints

PRODUCTION HARDENING (completed 2026-05-07)
--------------------------------------------
- gunicorn installed and configured in systemd service
- nginx reverse proxy config added
- deploy_production.sh: automated install/start/stop/restart/status/logs
- backup.sh: backup/restore/list for DB and uploads
- smoke_test.sh: HTTP health checks for all pages and APIs

BLUEPRINT REFACTORING (completed 2026-05-07)
---------------------------------------------
- app.py split from 3,297 lines → 60-line blueprint registry
- helpers.py: all 48 shared utility functions
- 7 blueprint modules: core, games, clips, stats, practice, player_dev, ai
- All url_for() calls updated to blueprint.endpoint format
- 128 tests passing (112 original + 16 LLM)

LLM INTEGRATION (completed 2026-05-07)
----------------------------------------
- call_ollama(): subprocess call to Ollama with timeout and error handling
- generate_practice_ai_notes_llm(): generates notes via Ollama when configured
- build_practice_ai_notes(): tries LLM first, falls back to heuristic
- Feature flag: settings ai.llm_provider ("ollama" or "none") and ai.llm_model
- 16 new tests for LLM functions

NEXT STEPS
----------
- Phase 8+: Per coach direction
- All Master Outline phases complete

SCHEDULE TAB ENHANCEMENTS (completed 2026-05-07)
-------------------------------------------------
- Multi-time layout: JV / Frosh / Varsity times per game (jv_game_time, frosh_game_time, game_time columns)
- Schedule table redesigned: DATE | OPPONENT | TIMES | Actions
- Times column shows "JV / Frosh / Varsity", "JV / Varsity", "Varsity only", or "JV only" labels
- Add Scheduled Game form: JV Time, Frosh Time, Varsity Time fields
- PDF schedule import: full rewrite for column-based layout, multi-time patterns, date ranges, vs. patterns
- Team selector on PDF upload: Boys HS, Girls HS, Jr High Boys, Jr High Girls
- Parser uses team to auto-set gender/level defaults
- MaxPreps CSV export: includes JV/Frosh/Varsity time columns + Team column
- Frosh (not Sophomore) naming throughout
- All 156 tests pass

PATRIOT LOGO (completed 2026-05-07)
------------------------------------
- Replaced 🏀 emoji in nav bar with Liberty Charter Patriot mascot logo
- Downloaded from school website (finalsite CDN)
- Served from static/img/patriot-logo.jpg with 28px height, flex-aligned

FEATURE PLANNED (documented in docs/FEATURE_PLAYBOOK_MESSAGING_MOBILE.md)
------------------------------------------------------------------------
1. Playbook — Interactive court canvas, draggable players, step animations, organize into playbooks
2. Plays Import — PDF/image upload, auto-extract diagrams, side-by-side editor
3. Messaging — GameChanger-style team chat, DMs, announcements, file attachments, notifications
4. Mobile Responsive — Bottom nav, hamburger menu, card layouts, PWA support
Implementation order: Finish schedule tab → Playbook MVP → Plays Import → Messaging → Mobile

NEXT STEPS (per Master Project Outline)
-----------------------------------------
1. Phase 2.5 — Manual Tagging & Bookmarks MVP (added 2026-05-04 to outline)
2. Phase 7 — Player Development & Practice Engine
   - Development clips per player tied to games/events
   - Practice playlists from prior clips
   - Practice plan assembly tools
3. Production hardening (gunicorn + reverse proxy, backup/restore, smoke tests)
4. Replace centroid tracker with ByteTrack/DeepSort for better ID persistence

How to resume / commands to run
--------------------------------
- Activate venv and start app:
  cd /home/monk-admin/PROJECTS/liberty-basketball-analysis && source .venv/bin/activate && python app.py
- Run tests:
  source .venv/bin/activate && python -m pytest tests/ -q
- Run analyzer for a video:
  source .venv/bin/activate && python -c "from ai_analyzer import run_ai_analysis; run_ai_analysis('film_analysis.db', 'uploads/myvideo.mp4', 'game_001')"
- Run event generation alone:
  source .venv/bin/activate && python -c "from event_generator import main; main('game_001', 'film_analysis.db')"
- Run tracker assigner:
  source .venv/bin/activate && python tracker_assigner.py --db film_analysis.db --game_id game_001

— End of current snapshot (Rex, 2026-05-07)
[2026-05-10 15:20 MDT] Cron status check:
- Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
- 5 latest commits:
  - b8ca54dd — fix: jr high boys year 2027→2026 + preview date edits now respected
  - 330de984 — docs: annotate dashboard complete in IMPLEMENTATION_PLAN.md
  - e8bcd584 — fix: team photos full-width, one per row
  - 25e1d194 — fix: improve schedule column layout + enlarge team photos
  - bca8c1ec — fix: UI overflow audit - all 17 pages passing
- Uncommitted: none (working tree clean)

[2026-05-07 12:52:28 MDT] Commit 524d56b8 (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-07 16:54:50 ] Commit 5c5b4caa (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-07 18:56:37 ] Commit 20cb6f0d — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready
[2026-05-07 20:58:08 MDT] Commit 423e8ea7 (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready
[2026-05-07 23:00:00] Commit 8574f504 (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-08 01:01:31 ] Commit 8574f504 (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-08 05:03:03 ] Commit 8574f504 (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-08 07:03:00 ] Commit 8574f504 (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready


[2026-05-08 09:05:51 ] Commit 86b585e4 (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready
[2026-05-08 11:06:43 MDT] Commit 0a9d8e97 — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-08 13:07:47 ] Commit 456eb69b — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-08 14:00 MDT] Commit ad86599c — PDF season auto-detection + Jr High A/B schedule labels
- New: _detect_season_from_text() parses PDF header for year patterns (2025-26, 2025-2026)
- New: _get_or_create_season_for_pdf() matches/creates correct season
- HS Boys/Girls, Jr High Girls: Nov(year1)→Mar(year2); Jr High Boys: Jan(year2)→Feb(year2)
- /api/schedule/import-pdf returns detected season; confirm endpoint uses it
- PDF import preview modal shows detected season banner
- Fix: schedule.html times column shows B/A for Jr High instead of JV/Varsity
- 160+ tests pass

[2026-05-08 15:08:36 ] Commit 87ac836f (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-08 17:11:29 ] Commit f5a0ff7a (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-08 21:13:21 MDT] Commit 77a77181 (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-09 08:43 MDT] Commit af6bef32 — UI standardization + dropdown/resource bar fixes
- Standardize UI across all pages
- Fix dropdown menus (remove overflow hidden on nav clipping dropdowns)
- Fix broken template (restore report drawer script, remove resource bar CSS)
- Move resource status bar from global nav to Debug page only
- Fix dropdown z-index so menus appear above CPU/resource bar
- Uncommitted changes: film_analysis.db, templates/index.html

[2026-05-09 14:xx MDT] Commit c8ddb20e — Dashboard team cards + MaxPreps rankings
- Frame 1.1: 3x2 team card grid (Varsity Boys/Girls, JV Boys/Girls, Jr High Boys/Girls)
- Each card shows Overall + Conference W-L record
- Last game result with W/L color coding and score
- Simplified upcoming schedule: Date | Opponent | H/A/T badges
- MaxPreps ranking badge on varsity cards with ↻ Update button
- GET/POST /api/teams/rankings endpoint (scrapes MaxPreps Idaho)
- Wednesday 8 AM cron job for auto ranking refresh
- maxpreps_rankings table migration
- 160 tests pass

[2026-05-10 13:17 MDT] Cron status check:
- Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
- 5 latest commits:
  - bca8c1ec — fix: UI overflow audit - all 17 pages passing
  - 0124d839 — feat: team photos section with selector dropdown
  - cc0f08ff — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-10 11:14 MDT
  - 6b2645b2 — fix: add DB teardown + busy_timeout to fix photo upload lock
  - 010f19e8 — Fix schedule layout: proper 3-column grid for aligned rows
- Uncommitted: film_analysis.db (modified), templates/base.html (modified)

[2026-05-10 11:14 MDT] Cron status check:
- Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
- 5 latest commits:
  - 6b2645b2 — fix: add DB teardown + busy_timeout to fix photo upload lock
  - 010f19e8 — Fix schedule layout: proper 3-column grid for aligned rows
  - eac86c7d — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-10 09:12 MDT
  - 7143ce40 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-10 07:09 MDT
  - 2d797564 — Fix card layout: 2-column grid + stacked schedule rows
- Uncommitted: tests/screenshots/ (untracked), tests/test_ui_overflow.py (untracked), tests/test_visual_regression.py (untracked)

[2026-05-10 09:12 MDT] Cron status check:
- Branch: jason-5-may-updates (ahead of origin/jason-5-may-updates by 1 commit)
- 5 latest commits:
  - 7143ce40 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-10 07:09 MDT
  - 2d797564 — Fix card layout: 2-column grid + stacked schedule rows
  - e687b02d — Fix card layout: opponent names no longer truncated
  - 540c93bb — Fix date format: show 'Wed 4 Nov 25 7:00pm' instead of raw RFC date
  - 5dee44dc — Fix photo upload: WAL mode, timeout, and subfolder serving
- Uncommitted: film_analysis.db (modified — expected), film_analysis.db-shm/db-wal (untracked)

[2026-05-10 07:09 MDT] Cron status check:
- Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
- 5 latest commits:
  - 2d797564 — Fix card layout: 2-column grid + stacked schedule rows
  - e687b02d — Fix card layout: opponent names no longer truncated
  - 540c93bb — Fix date format: show 'Wed 4 Nov 25 7:00pm' instead of raw RFC date
  - 5dee44dc — Fix photo upload: WAL mode, timeout, and subfolder serving
  - 90cc839a — Fix team photos API and remove Recent Events section
- Uncommitted: PROGRESS.md (modified), WORKLOG.md (modified), film_analysis.db (modified — expected), film_analysis.db-shm/db-wal (untracked)

[2026-05-09 19:00 MDT] Cron status check — 3 new commits since 16:52:
- 2fb039d8 — Fix team card widths: compact date format, table-layout fixed, card overflow
- 538388bc — Compact date/time format in dashboard cards and upcoming games
- af3a0808 — Equal card heights, fix MaxPreps scraper URLs, add girls 2A ranking
- Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
- Uncommitted: PROGRESS.md (modified), film_analysis.db (modified — expected)

[2026-05-10 19:44 MDT] Cron status check — no new commits since 19:00 yesterday:
- Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
- HEAD: b8ca54dd — fix: jr high boys year 2027→2026 + preview date edits now respected
- Uncommitted: PROGRESS.md (modified), WORKLOG.md (modified)

[2026-05-11 06:00 MDT] Cron status check:
- Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
- 2 new commits since last check:
  - ec332b44 — Lock in Teams/Schedule tab state — PROGRESS + WORKLOG updates
  - e6e0791b — Rebuild film_tool.html — extract CSS/JS, clean structure, remove dead code
- Uncommitted: none (working tree clean)
- Tests: 188 passed, 0 failed
- All Master Outline phases 1-7 complete. Dashboard complete. Next: Mobile/PWA or Playbook per coach direction.

[2026-05-11 07:49 MDT] Cron check:
- 5 latest commits on jason-5-may-updates (no new commits since last check):
  - e6e0791b — Rebuild film_tool.html — extract CSS/JS, clean structure, remove dead code
  - ec332b44 — Lock in Teams/Schedule tab state — PROGRESS + WORKLOG updates
  - b8ca54dd — fix: jr high boys year 2027→2026 + preview date edits now respected
  - 330de984 — docs: annotate dashboard complete in IMPLEMENTATION_PLAN.md
  - e8bcd584 — fix: team photos full-width, one per row
- Uncommitted: WORKLOG.md (modified), film_analysis.db (modified)
- No new commits since 2026-05-10 15:20 check.

[2026-05-11 09:51 MDT] Cron check:
- 5 latest commits on jason-5-may-updates (no new commits since last check):
  - e6e0791b — Rebuild film_tool.html — extract CSS/JS, clean structure, remove dead code
  - ec332b44 — Lock in Teams/Schedule tab state — PROGRESS + WORKLOG updates
  - b8ca54dd — fix: jr high boys year 2027→2026 + preview date edits now respected
  - 330de984 — docs: annotate dashboard complete in IMPLEMENTATION_PLAN.md
  - e8bcd584 — fix: team photos full-width, one per row
- Uncommitted: PROGRESS.md (modified), WORKLOG.md (modified), film_analysis.db (modified)
- No new commits since 2026-05-11 07:49 check.
