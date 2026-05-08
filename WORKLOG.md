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
