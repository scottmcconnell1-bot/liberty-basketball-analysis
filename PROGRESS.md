# Progress Log — Liberty Basketball Analysis

[2026-05-08 14:00 MDT] PDF season auto-detection + Jr High A/B schedule labels
- _detect_season_from_text(): parses PDF header for year patterns, determines correct season date ranges
- HS Boys/Girls, Jr High Girls: Nov(year1) → Mar(year2); Jr High Boys: Jan(year2) → Feb(year2)
- _get_or_create_season_for_pdf(): matches existing season by name or date range, creates if needed
- /api/schedule/import-pdf returns detected season; /api/schedule/import-pdf/confirm uses it
- PDF import preview modal shows detected season banner
- Fix schedule.html times column: Jr High games show B/A labels instead of JV/Varsity
- 160+ tests pass
- Pushed to jason-5-may-updates

[2026-05-07 21:30 MDT] Patriot logo + team selector + feature plans
- Replaced 🏀 with Patriot mascot logo from school website
- Team selector modal before PDF upload (boys_hs/girls_hs/jr_boys/jr_girls)
- Parser uses team for default gender/level detection
- Frosh (not Sophomore) naming
- Added feature plan doc: Playbook, Plays Import, Messaging, Mobile
- WORKLOG.md updated
- 156/156 tests pass
- Pushed to jason-5-may-updates

[2026-05-07 20:58:08 MDT] Commit 423e8ea7 (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-07 18:56:37] Commit 20cb6f0d — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-07 16:54:50] Commit 5c5b4caa (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-07 14:53:34 MDT] Commit 39b953ee (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready
[2026-05-07 23:00:00] Commit 8574f504 (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-08 01:01:31 ] Commit 8574f504 (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-08 05:03:03 ] Commit 8574f504 (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-08 07:03:00 ] Commit 8574f504 (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready


[2026-05-08 09:05:51 ] Commit 86b585e4 (dirty) — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready
[2026-05-08 11:06:43 MDT] Commit 0a9d8e97 — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

[2026-05-08 13:07:47 ] Commit 456eb69b — Phase 2: Seasons CRUD done, Scheduled-games CRUD pending; Phase 3: Games schema ready

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
- Each card: Overall record + Conference record (from games.is_conference)
- Last game result with W/L color coding and score
- Simplified upcoming schedule table: Date | Opponent | H/A/T
- MaxPreps ranking badge on varsity cards with ↻ Update button
- GET/POST /api/teams/rankings endpoint (scrapes MaxPreps Idaho via agent-browser)
- Wednesday 8 AM cron job for auto ranking refresh
- maxpreps_rankings table migration in helpers.py
- 160 tests pass
