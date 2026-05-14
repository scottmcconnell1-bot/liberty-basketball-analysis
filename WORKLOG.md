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

[2026-05-12 11:00 MDT] Architecture Decision — Hosting & Storage
- VPS + Backblaze B2: VPS runs the app, B2 stores film files
- Cloudflare Tunnel for access from school/phone/anywhere
- Nightly GitHub backup of SQLite database
- Long-term: migrate to school server when ready
- Film pipeline: upload → B2 storage → AI analysis → data in SQLite
- Current data: 37MB DB + 273MB uploads (mostly test files), 3 video records
- Next: set up VPS, deploy app, configure B2, test film upload pipeline

[2026-05-12 11:00 MDT] Repo Inventory & Decisions (all repos)
- Liberty Basketball: VPS + B2 + Cloudflare Tunnel (data-intensive, film files)
- Classroom Manager: Local on Scott's work PC, GitHub backup
- Finances: Stay on Render, GitHub auto-backup for data persistence
- Dinner Planner: Stay on Render, add data persistence later (recipe ratings/meal plans)
- Harbor Room: Empty/testing, no action needed

NEXT STEPS (updated 2026-05-12)
------------------------------------------
1. Set up VPS with persistent storage for Liberty Basketball
2. Configure Backblaze B2 for film file storage
3. Set up Cloudflare Tunnel for school/phone access
4. Add nightly GitHub backup for database
5. Build film upload → B2 → AI analysis pipeline
6. Eventually migrate to school server

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
[2026-05-11 11:54 MDT] Check-in:
- Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
- Latest commits:
  - b5dc86d9 — Fix AI analysis: install libgl1, increase frame_stride to 5, add processing time estimate
  - cf8fe83f — Film controls: single line with horizontal scroll
  - 11838f45 — Redesign film tool Tagger view — video-first layout, collapsible sections, color-coded tag buttons, prominent scoreboard
  - e6e0791b — Rebuild film_tool.html — extract CSS/JS, clean structure, remove dead code
  - ec332b44 — Lock in Teams/Schedule tab state — PROGRESS + WORKLOG updates
- Uncommitted: none (working tree clean)

[2026-05-11 07:49 MDT] Previous check-in:
  - ec332b44 — Lock in Teams/Schedule tab state — PROGRESS + WORKLOG updates
  - b8ca54dd — fix: jr high boys year 2027→2026 + preview date edits now respected
  - 330de984 — docs: annotate dashboard complete in IMPLEMENTATION_PLAN.md
  - e8bcd584 — fix: team photos full-width, one per row
- Uncommitted: PROGRESS.md (modified), WORKLOG.md (modified), film_analysis.db (modified)
- No new commits since 2026-05-11 07:49 check.

[2026-05-11 13:56 MDT] Check-in:
  - c990bf23 — Fix AI analysis subprocess + delete video bugs
  - 2ea7dd43 — AI analyzer: optical flow tracking for 10x speedup
  - cd0fe16d — Optimize AI analyzer: stride=3, class-filtered ball detection
  - (3 new commits since 11:54 check)
  - Uncommitted: none (working tree clean)

[2026-05-12 06:12 MDT] Cron status check:
  - Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
  - No new commits since 06:00 check (HEAD: c5efac92)
  - 5 latest commits:
    - c5efac92 — Wrap init() in try-catch to prevent JS errors from blocking initAiUpload
    - c990bf23 — Fix AI analysis subprocess + delete video bugs
    - 2ea7dd43 — AI analyzer: optical flow tracking for 10x speedup
    - cd0fe16d — Optimize AI analyzer: stride=3, class-filtered ball detection
    - b5dc86d9 — Fix AI analysis: install libgl1, increase frame_stride to 5, add processing time estimate
  - Uncommitted: WORKLOG.md (modified), film_analysis.db (modified)
  - All Master Outline phases 1-7 complete. Dashboard complete.
  - Next: Mobile/PWA or Playbook per coach direction.

[2026-05-12 06:00 MDT] Cron status check:
  - Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
  - 1 new commit since last check:
    - c5efac92 — Wrap init() in try-catch to prevent JS errors from blocking initAiUpload
  - Uncommitted: film_analysis.db (modified — expected)
  - Tests: 188 passed, 0 failed
  - All Master Outline phases 1-7 complete. Dashboard complete.
  - Next: Mobile/PWA or Playbook per coach direction.

[2026-05-12 08:15 MDT] Cron status check:
  - Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
  - 1 new commit since last check:
    - f068a0d9 — fix: increase upload limit to 4GB + better error messages for film tool
  - Uncommitted: scripts/check_tunnel_url.sh (untracked)
  - All Master Outline phases 1-7 complete. Dashboard complete.
  - Next: Mobile/PWA or Playbook per coach direction.

[2026-05-12 10:20 MDT] Cron status check:
  - Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
  - 1 new commit since last check:
    - d5a49db1 — fix: improve upload timeout handling and progress display for large files
  - 5 latest commits:
    - d5a49db1 — fix: improve upload timeout handling and progress display for large files
    - f068a0d9 — fix: increase upload limit to 4GB + better error messages for film tool
    - c5efac92 — Wrap init() in try-catch to prevent JS errors from blocking initAiUpload
    - c990bf23 — Fix AI analysis subprocess + delete video bugs
    - 2ea7dd43 — AI analyzer: optical flow tracking for 10x speedup
  - All Master Outline phases 1-7 complete. Dashboard complete.
  - Next: Mobile/PWA or Playbook per coach direction.

[2026-05-12 ~11:00 MDT] Film tool upload fix + Cloudflare named tunnel:
- Diagnosed upload failure: Cloudflare quick tunnel drops connections on large file uploads
- Increased Flask MAX_CONTENT_LENGTH to 4GB (was default 16MB)
- Improved upload JS: 1hr XHR timeout, file validation, MB progress display, better error messages
- Set up Cloudflare named tunnel "liberty-film-room" (replaces ephemeral quick tunnel)
- Named tunnel running with 4 edge connections, awaiting hostname configuration
- User purchased domain via Cloudflare Registrar, configuring public hostname next
- Commits: f068a0d9, d5a49db1

---
[2026-05-12 12:24 MDT] Cron status check:
  - Branch: jason-5-may-updates (ahead of origin by 1 commit — previous cron log commit)
  - Working tree: clean, no uncommitted changes
  - Latest commits:
    - 6bda59c1 — docs: update PROGRESS.md and WORKLOG.md for cron status check
    - d5a49db1 — fix: improve upload timeout handling and progress display for large files
    - f068a0d9 — fix: increase upload limit to 4GB + better error messages for film tool
    - c5efac92 — Wrap init() in try-catch to prevent JS errors from blocking initAiUpload
    - c990bf23 — Fix AI analysis subprocess + delete video bugs
  - No new user commits since 2026-05-11. Project stable, awaiting next coach direction.

---
[2026-05-12 14:31 MDT] Cron status check:
  - Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
  - Working tree: clean, no uncommitted changes
  - Latest commits:
    - bf94bde2 — docs: update WORKLOG with film tool fix and cloudflare tunnel work
    - 6c91da2b — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 12:24 MDT
    - 6bda59c1 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 10:20 MDT
    - d5a49db1 — fix: improve upload timeout handling and progress display for large files
    - f068a0d9 — fix: increase upload limit to 4GB + better error messages for film tool
  - 1 new commit since 12:24 check (bf94bde2 — WORKLOG documentation update). No new user-facing changes. Project stable.

---
[2026-05-12 16:34 MDT] Cron status check:
  - Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
  - Working tree: clean, no uncommitted changes
  - Latest commits:
    - 2b51a872 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 14:31 MDT
    - bf94bde2 — docs: update WORKLOG with film tool fix and cloudflare tunnel work
    - 6c91da2b — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 12:24 MDT
    - 6bda59c1 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 10:20 MDT
    - d5a49db1 — fix: improve upload timeout handling and progress display for large files
  - No new user-facing commits since 14:31 check. Project stable, awaiting next coach direction.
---
[2026-05-12 18:36 MDT] Cron status check:
  - Branch: jason-5-may-updates (ahead of origin/jason-5-may-updates by 1 commit)
  - Working tree: clean, no uncommitted changes
  - Latest commits:
    - 5d2fa01b — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 16:34 MDT
    - 2b51a872 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 14:31 MDT
    - bf94bde2 — docs: update WORKLOG with film tool fix and cloudflare tunnel work
    - 6c91da2b — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 12:24 MDT
    - 6bda59c1 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 10:20 MDT
  - No new user-facing commits since 16:34 check. Project stable, awaiting next coach direction.
---
[2026-05-13 06:44 MDT] Cron status check:
  - Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
  - Working tree: 1 modified (film_analysis.db), 1 untracked (scripts/tunnel-watchdog.sh)
  - Latest commits:
    - 9a1f7ad6 — fix: align upload form fields with proper CSS scoping
    - 8a549712 — fix: align upload form fields (Video File / Opponent)
    - afdedacc — feat: split upload into tagging + AI analysis, add client-side compression
    - 4b169313 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 18:36 MDT
    - 5d2fa01b — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 16:34 MDT
  - 3 new commits since 18:36 check: CSS fixes for upload form + major upload workflow refactor (tagging/AI split, client-side compression). Project active.

[2026-05-13 08:50 MDT] Cron status check:
  - Branch: jason-5-may-updates (up to date with origin)
  - Working tree: 2 modified (PROGRESS.md, WORKLOG.md), 1 db change (film_analysis.db), 1 untracked (scripts/tunnel-watchdog.sh)
  - Latest commits:
    - 9a1f7ad6 — fix: align upload form fields with proper CSS scoping
    - 8a549712 — fix: align upload form fields (Video File / Opponent)
    - afdedacc — feat: split upload into tagging + AI analysis, add client-side compression
    - 4b169313 — docs: cron status check 2026-05-12 18:36 MDT
    - 5d2fa01b — docs: cron status check 2026-05-12 16:34 MDT
  - No new commits since 06:44 check. Project stable.

[2026-05-13 10:53 MDT] Cron status check:
  - Branch: jason-5-may-updates (up to date with origin)
  - No new commits since 06:44 MDT check
  - Uncommitted: PROGRESS.md, WORKLOG.md (modified), film_analysis.db (modified); scripts/tunnel-watchdog.sh (untracked)
  - Project stable, no action needed

[2026-05-13 14:30 MDT] Dribble Removal + AI Analysis Intent Discussion
========================================
Dribble removed from all AI analysis code (12 files changed, 88 insertions, 288 deletions).
Commit: c65705d0.

CRITICAL: Scott's intended use of the program (from prior discussion, not previously logged):
------------------------------------------------------------------------
The AI film analysis is meant to track:
1. **Minutes played** — which player is on the court at each point in the game
2. **Shots** — broken down into 2pt, 3pt, and free throw (FT) made/attempts
3. **Play recognition** — identifying offensive/defensive plays (pick and roll, isolation, zone press, etc.)
4. **Player effect on game** — impact metrics like +/- (score changes while player is on court)
5. **Scouting** — finding plays and player tendencies across games
   - "Player X tends to drive left 70% of the time in pick and roll"
   - "Team Y runs zone press after made baskets"
6. **Learning/improvement** — system should get better over time from human corrections
   - When coach corrects an AI event, that feedback should improve future predictions

The practice sections and player development sections exist to support this:
- Practice plans should connect to game film (what to work on based on game analysis)
- Player development should track tendencies and improvement over time
- Scouting section should aggregate patterns across opponents

CURRENT GAPS:
- Minutes played: NOT tracked (need to calculate from frame appearances per player)
- Shot types: event generator marks "shot" + "make/miss" but does NOT distinguish 2pt vs 3pt vs FT
- Play recognition: NOT implemented (no pattern matching on player movement sequences)
- Player effect (+/-): NOT implemented (no score tracking per player on court)
- Scouting tendencies: NOT implemented (no cross-game aggregation)
- Learning from corrections: NOT implemented (human feedback not fed back to models)

NEXT STEPS (per Scott's direction):
1. Add minutes played tracking (calculate from detection frame data)
2. Add shot type classification (2pt/3pt/FT based on court position)
3. Build play recognition (pattern matching on movement data)
4. Build scouting tendencies (aggregate stats across games)
5. Add learning/feedback loop from human corrections

---

[2026-05-13 21:00 MDT] Scouting System + NFHS Integration — Major Build Session
================================================================================

WHAT WAS BUILT:

1. NFHS Network Login & Game Lookup
   - New nfhs.py module: OAuth login via member.nfhsnetwork.com/oauth/token
   - Game lookup via search-api.nfhsnetwork.com/v3/search?id=<game_id>
   - Supports alphanumeric GameIDs (e.g., gam12d9559efc) and full URLs
   - Returns: teams, gender, level, date, status, score, VOD availability, headline
   - Credentials stored encrypted (XOR obfuscation) in nfhs_credentials table
   - Session tokens cached to disk with expiry checking

2. Scouting Report System
   - 10 new DB tables: scouting_reports, scouting_personnel, scouting_offensive_sets,
     scouting_defensive_tendencies, scouting_tendencies, scouting_situational,
     scouting_mismatches, scouting_practice_points, scouting_clips, nfhs_credentials
   - Full CRUD API for all sections
   - Auto-generate from AI events: analyzes events table → personnel roles, shot tendencies, turnover patterns
   - Tabbed report editor UI (Overview, Personnel, Offense, Defense, Tendencies, Situational, Mismatches, Practice, Clips)
   - Printable report template

3. Updated Scouting Dashboard (/scouting)
   - NFHS login form (email + password)
   - Game lookup: paste GameID → see teams, gender, level, VOD status
   - Download film: uses yt-dlp with OAuth token for authenticated downloads
   - Reports list with create/edit/print

4. Infrastructure Fixes
   - Fixed gunicorn path: must use .venv/bin/gunicorn (not system)
   - Fixed extract_nfhs_game_id() to support alphanumeric IDs
   - Fixed port 8081 conflict (old gunicorn process blocking restart)

HOW SCOTT WANTS IT TO WORK — NFHS FLOW:
1. User goes to /scouting page
2. If no NFHS credentials stored → show login form (email + password)
3. On login: authenticate against NFHS, save encrypted credentials, show game lookup
4. User pastes GameID (or URL) → click "Look Up Game"
5. System shows: teams playing, gender, level, date, status, VOD availability
6. If VOD available → click "Download Film" → downloads via yt-dlp with auth token
7. After download → create scouting report, run AI analysis, auto-generate tendencies

HOW SCOTT WANTS IT TO WORK — SCOUTING REPORT FLOW:
1. Create new scouting report (opponent, date, optional NFHS GameID)
2. Download film via NFHS or manual upload
3. Run AI analysis on film
4. Click "Auto-Generate" → system populates:
   - Personnel (by jersey number, since names may not be known)
   - Shot selection tendencies
   - Turnover patterns
5. Coach reviews and edits each section
6. Add practice points (top 3 things to work on)
7. Print/share scouting report

KEY DESIGN DECISIONS:
- Jersey numbers used instead of player names (Scott won't always know names)
- NFHS GameID format: alphanumeric (e.g., gam12d9559efc), not just numeric
- Credentials encrypted at rest (XOR obfuscation — not crypto-secure but better than plaintext)
- OAuth tokens cached to disk, refreshed on expiry
- Quick Cloudflare tunnel changes URL on restart — always provide new URL when it changes

GAME LOOKUP TEST RESULT (gam12d9559efc):
- Matchup: Shaker Senior High School (Bison) vs Albertus Magnus High School (Falcons)
- Gender: Girls
- Level: Varsity
- Type: NYSPHSAA Class AAA Semifinals #2
- Date: 2026-03-19, Troy, NY
- Status: Complete, VOD available

COMMITS:
- 89356c20 — Add NFHS login, game lookup, and scouting report system
- (plus prior commits for dribble removal, AI film breakdown spec, etc.)

CURRENT URL: https://practitioners-friend-distant-billy.trycloudflare.com
(Quick tunnel — changes on restart)

UNPUSHED COMMITS: 1 (89356c20)

---

[2026-05-13 12:56 MDT] Cron status check
- Branch: jason-5-may-updates (ahead of origin by 2 commits, unpushed)
- Working tree: clean (no uncommitted changes)
- New commits since last check:
  - 74788927 — docs: log intended AI analysis use - minutes, shots, play recognition, scouting
  - c65705d0 — Remove dribble from all AI analysis code
- Prior commits still on branch:
  - 9a1f7ad6 — fix: align upload form fields with proper CSS scoping
  - 8a549712 — fix: align upload form fields (Video File / Opponent)
  - afdedacc — feat: split upload into tagging + AI analysis, add client-side compression
- Note: 2 newest commits (74788927, c65705d0) are local-only and not yet pushed to origin.

---
[2026-05-13 14:59 MDT] Cron status check
- Branch: jason-5-may-updates (ahead of origin by 4 commits, unpushed)
- Working tree: dirty — blueprints/scouting.py (modified), schema.sql (modified), templates/scouting.html (modified), nfhs.py (untracked)
- New commits since 12:56 check:
  - 92ac45fb — feat: add scouting system - reports, NFHS download, personnel, tendencies, practice points
  - a679e68d — docs: add AI Film Breakdown spec from Scott's document
- Prior commits on branch (still unpushed):
  - 74788927 — docs: log intended AI analysis use - minutes, shots, play recognition, scouting
  - c65705d0 — Remove dribble from all AI analysis code
  - 9a1f7ad6 — fix: align upload form fields with proper CSS scoping
  - 8a549712 — fix: align upload form fields (Video File / Opponent)
  - afdedacc — feat: split upload into tagging + AI analysis, add client-side compression
- Note: 4 newest commits are local-only and not yet pushed. Active development on scouting system with uncommitted edits to blueprint, schema, and template files.

---
[2026-05-13 21:30 MDT] Film Analysis Testing & Repairs — Liberty vs Riverstone
================================================================================

TEST RESULTS on "Liberty_Vs_Riverstone_20260513_105151.webm" (103MB, 13532 frames, 60min):

Run #26 (stride=15): 617 detections, 0 events
  - Person frames: 0-1095 only (324 unique frames)
  - Ball frames: 1050-27165 (9 detections)
  - Overlap: 2 frames, distances 454-548px → 0 possession → 0 events
  - Problem: optical flow tracking dropped after frame 1095

Run #27 (stride=3): 328 detections, 0 events
  - Even fewer detections than stride=15 (unexpected)
  - Ball: 34 detections, Person-ball overlap: 0 frames
  - 0 active trackers at end of analysis
  - Tracker_assigner failed: "cannot convert dictionary update sequence element #0 to a sequence"
  - Problem: optical flow tracking is completely broken — not writing to DB

ROOT CAUSE IDENTIFIED:
The ai_analyzer.py optical flow tracking loop is not persisting tracked positions
to the database. Only YOLO anchor frame detections are written. The optical flow
cv2.calcOpticalFlowPyrLK() calls may be failing silently, or the results aren't
being committed to the DB within the loop.

EFFECTIVE ANALYSIS CODE IS WORKING:
- Enhanced analysis (minutes, shots, plays, effect) runs correctly when given data
- Event generator ball interpolation works (9→54, 38→54 ball positions)
- Auto possession threshold works (calculates from frame dimensions)
- Q1 video with interpolation: produced 3 events (shot, make, foul)

NEEDED FOR PRODUCTION:
1. Fix ai_analyzer.py optical flow tracking to write per-frame positions to DB
2. OR: run YOLO on every frame (very slow but would work)
3. OR: improve ball detection (class 32 is unreliable)

COMMITS TODAY:
- 92ac45fb — feat: add scouting system with NFHS login, game lookup, reports
- 741449ef — Add enhanced film analysis: minutes, shots, plays, player effect
- 74243948 — Fix event generator: auto possession threshold, sparse ball data
- 475ac06b — Fix event generator: ball interpolation, handle sparse data
- All pushed to origin/jason-5-may-updates

===
2026-05-13 17:03 MDT — Cron Status Check
- Branch: jason-5-may-updates (up to date with origin)
- 1 new commit since last check: 01a0ae40 (docs: update WORKLOG with film analysis test results and root cause)
- Uncommitted: ai_analyzer.py modified, film_analysis.db modified (+ db-shm, db-wal untracked)
- No new user-facing changes since 06:44 check; working tree has local dev modifications.

===
2026-05-13 19:06 MDT — Cron Status Check
- Branch: jason-5-may-updates (up to date with origin)
- 4 new commits since 17:03 check:
  - 2752ead6 — Fix shot classification and player effect errors
  - b5b29e08 — Fix tracker persistence and shot classification
  - e319bc92 — Rewrite ball detection: YOLO + virtual ball estimator
  - 7da9054f — Fix ai_analyzer.py: tracker persistence across anchor frames
- Uncommitted: film_analysis.db (modified)
- Notable: significant rework of ball detection pipeline (YOLO + virtual ball estimator), plus fixes to shot classification and tracker persistence.