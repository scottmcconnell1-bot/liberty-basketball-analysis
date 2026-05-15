# Progress Log -- Liberty Basketball Analysis

[2026-05-13 19:06 MDT] Latest commits (5 latest on jason-5-may-updates):
- 2752ead6 — Fix shot classification and player effect errors
- b5b29e08 — Fix tracker persistence and shot classification
- e319bc92 — Rewrite ball detection: YOLO + virtual ball estimator
- 7da9054f — Fix ai_analyzer.py: tracker persistence across anchor frames
- 01a0ae40 — docs: update WORKLOG with film analysis test results and root cause
Branch: jason-5-may-updates (up to date with origin)
Uncommitted changes: film_analysis.db (modified)

[2026-05-13 17:03 MDT] Latest commits (5 latest on jason-5-may-updates):
- 01a0ae40 — docs: update WORKLOG with film analysis test results and root cause
- 475ac06b — Fix event generator: ball interpolation, auto possession threshold, sparse data handling
- 74243948 — Fix event generator: auto possession threshold, sparse ball data handling
- 741449ef — Add enhanced film analysis: minutes, shot classification, play recognition, player effect
- 73a502e7 — docs: update WORKLOG with scouting system build session details
Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
Uncommitted changes: ai_analyzer.py (modified), film_analysis.db (modified), film_analysis.db-shm (untracked), film_analysis.db-wal (untracked)
1 new commit since 06:44 check: WORKLOG updated with film analysis test results and root cause.

[2026-05-13 06:44 MDT] Latest commits (5 latest on jason-5-may-updates):
- 9a1f7ad6 — fix: align upload form fields with proper CSS scoping
- 8a549712 — fix: align upload form fields (Video File / Opponent)
- afdedacc — feat: split upload into tagging + AI analysis, add client-side compression
- 4b169313 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 18:36 MDT
- 5d2fa01b — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 16:34 MDT
Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
Uncommitted changes: film_analysis.db (modified), scripts/tunnel-watchdog.sh (untracked)
3 new commits since 18:36 check: upload form CSS fixes + major upload workflow refactor (tagging + AI analysis split, client-side compression).

[2026-05-12 16:34 MDT] Latest commits (5 latest on jason-5-may-updates):
- 2b51a872 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 14:31 MDT
- bf94bde2 — docs: update WORKLOG with film tool fix and cloudflare tunnel work
- 6c91da2b — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 12:24 MDT
- 6bda59c1 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 10:20 MDT
- d5a49db1 — fix: improve upload timeout handling and progress display for large files
Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
Uncommitted changes: none (working tree clean)
No new user-facing commits since 14:31 check. Project stable.

[2026-05-12 14:31 MDT] Latest commits (5 latest on jason-5-may-updates):
- bf94bde2 — docs: update WORKLOG with film tool fix and cloudflare tunnel work
- 6c91da2b — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 12:24 MDT
- 6bda59c1 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 10:20 MDT
- d5a49db1 — fix: improve upload timeout handling and progress display for large files
- f068a0d9 — fix: increase upload limit to 4GB + better error messages for film tool
Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
Uncommitted changes: none (working tree clean)
1 new commit since 12:24 check (WORKLOG documentation update).

[2026-05-12 12:24 MDT] Latest commits (5 latest on jason-5-may-updates):
- 6bda59c1 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 12:24 MDT
- d5a49db1 — fix: improve upload timeout handling and progress display for large files
- f068a0d9 — fix: increase upload limit to 4GB + better error messages for film tool
- c5efac92 — Wrap init() in try-catch to prevent JS errors from blocking initAiUpload
- c990bf23 — Fix AI analysis subprocess + delete video bugs
Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
Uncommitted changes: none (working tree clean)
No new user commits since 08:15 check.

[2026-05-12 10:20 MDT] Latest commits (5 latest on jason-5-may-updates):
- d5a49db1 — fix: improve upload timeout handling and progress display for large files
- f068a0d9 — fix: increase upload limit to 4GB + better error messages for film tool
- c5efac92 — Wrap init() in try-catch to prevent JS errors from blocking initAiUpload
- c990bf23 — Fix AI analysis subprocess + delete video bugs
- 2ea7dd43 — AI analyzer: optical flow tracking for 10x speedup
Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
Uncommitted changes: none (working tree clean)
1 new commit since 08:15 check.

[2026-05-12 08:15 MDT] Latest commits (5 latest on jason-5-may-updates):
- f068a0d9 — fix: increase upload limit to 4GB + better error messages for film tool
- c5efac92 — Wrap init() in try-catch to prevent JS errors from blocking initAiUpload
- c990bf23 — Fix AI analysis subprocess + delete video bugs
- 2ea7dd43 — AI analyzer: optical flow tracking for 10x speedup
- cd0fe16d — Optimize AI analyzer: stride=3, class-filtered ball detection
Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
Uncommitted changes: scripts/check_tunnel_url.sh (untracked)

[2026-05-12 06:12 MDT] Latest commits (5 latest on jason-5-may-updates):
- c5efac92 — Wrap init() in try-catch to prevent JS errors from blocking initAiUpload
- c990bf23 — Fix AI analysis subprocess + delete video bugs
- 2ea7dd43 — AI analyzer: optical flow tracking for 10x speedup
- cd0fe16d — Optimize AI analyzer: stride=3, class-filtered ball detection
- b5dc86d9 — Fix AI analysis: install libgl1, increase frame_stride to 5, add processing time estimate
Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
Uncommitted changes: WORKLOG.md (modified), film_analysis.db (modified)

[2026-05-11 13:56 MDT] Latest commits (5 latest on jason-5-may-updates):
- c990bf23 — Fix AI analysis subprocess + delete video bugs
- 2ea7dd43 — AI analyzer: optical flow tracking for 10x speedup
- cd0fe16d — Optimize AI analyzer: stride=3, class-filtered ball detection
- b5dc86d9 — Fix AI analysis: install libgl1, increase frame_stride to 5, add processing time estimate
- cf8fe83f — Film controls: single line with horizontal scroll
Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
Uncommitted changes: none (working tree clean)

[2026-05-11 11:54 MDT] Latest commits (5 latest on jason-5-may-updates):
- b5dc86d9 — Fix AI analysis: install libgl1, increase frame_stride to 5, add processing time estimate
- cf8fe83f — Film controls: single line with horizontal scroll
- 11838f45 — Redesign film tool Tagger view — video-first layout, collapsible sections, color-coded tag buttons, prominent scoreboard
- e6e0791b — Rebuild film_tool.html — extract CSS/JS, clean structure, remove dead code
- ec332b44 — Lock in Teams/Schedule tab state — PROGRESS + WORKLOG updates
Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
Uncommitted changes: none (working tree clean)

[2026-05-10 15:20 MDT] Latest commits (5 latest on jason-5-may-updates):
- b8ca54dd — fix: jr high boys year 2027→2026 + preview date edits now respected
- 330de984 — docs: annotate dashboard complete in IMPLEMENTATION_PLAN.md
- e8bcd584 — fix: team photos full-width, one per row
- 25e1d194 — fix: improve schedule column layout + enlarge team photos
- bca8c1ec — fix: UI overflow audit - all 17 pages passing
- Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
- Uncommitted changes: none (working tree clean)

[2026-05-10 13:17 MDT] Latest commits (5 latest on jason-5-may-updates):
- bca8c1ec — fix: UI overflow audit - all 17 pages passing
- 0124d839 — feat: team photos section with selector dropdown
- cc0f08ff — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-10 11:14 MDT
- 6b2645b2 — fix: add DB teardown + busy_timeout to fix photo upload lock
- 010f19e8 — Fix schedule layout: proper 3-column grid for aligned rows
- Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
- Uncommitted changes: film_analysis.db (modified), templates/base.html (modified)

[2026-05-10 11:14 MDT] Latest commits (5 latest on jason-5-may-updates):
- 6b2645b2 — fix: add DB teardown + busy_timeout to fix photo upload lock
- 010f19e8 — Fix schedule layout: proper 3-column grid for aligned rows
- eac86c7d — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-10 09:12 MDT
- 7143ce40 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-10 07:09 MDT
- 2d797564 — Fix card layout: 2-column grid + stacked schedule rows
- Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
- Uncommitted changes: tests/screenshots/ (untracked), tests/test_ui_overflow.py (untracked), tests/test_visual_regression.py (untracked)

[2026-05-10 09:12 MDT] Latest commits (5 latest on jason-5-may-updates):
- 7143ce40 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-10 07:09 MDT
- 2d797564 — Fix card layout: 2-column grid + stacked schedule rows
- e687b02d — Fix card layout: opponent names no longer truncated
- 540c93bb — Fix date format: show 'Wed 4 Nov 25 7:00pm' instead of raw RFC date
- 5dee44dc — Fix photo upload: WAL mode, timeout, and subfolder serving
- Branch: jason-5-may-updates (ahead of origin/jason-5-may-updates by 1 commit)
- Uncommitted changes: film_analysis.db (modified — expected), film_analysis.db-shm (untracked), film_analysis.db-wal (untracked)

[2026-05-10 07:09 MDT] Latest commits (5 latest on jason-5-may-updates):
- 2d797564 — Fix card layout: 2-column grid + stacked schedule rows
- e687b02d — Fix card layout: opponent names no longer truncated
- 540c93bb — Fix date format: show 'Wed 4 Nov 25 7:00pm' instead of raw RFC date
- 5dee44dc — Fix photo upload: WAL mode, timeout, and subfolder serving
- 90cc839a — Fix team photos API and remove Recent Events section
- Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
- Uncommitted changes: PROGRESS.md (modified), WORKLOG.md (modified), film_analysis.db (modified — expected), film_analysis.db-shm (untracked), film_analysis.db-wal (untracked)

[2026-05-09 19:00 MDT] Previous check — 5 commits:
- 2fb039d8 — Fix team card widths: compact date format, table-layout fixed, card overflow handling
- 538388bc — Compact date/time format in dashboard cards and upcoming games
- af3a0808 — Equal card heights, fix MaxPreps scraper URLs, add girls 2A ranking
- 1ae6798d — docs: update PROGRESS.md and WORKLOG.md for dashboard team cards + MaxPreps rankings
- c8ddb20e — feat(dashboard): team cards with conference/overall record + MaxPreps rankings

[Previous entries preserved as previously recorded...]
[2026-05-09 08:43 MDT] Commit af6bef32 – UI standardization + dropdown/resource bar fixes
- Standardize UI across all pages
- Fix dropdown menus (remove overflow hidden on nav clipping dropdowns)
- Move resource status bar from global nav to Debug page only

... [full historical content]...

[2026-05-10 19:44 MDT] Latest commits (5 latest on jason-5-may-updates):
- b8ca54dd — fix: jr high boys year 2027→2026 + preview date edits now respected
- 330de984 — docs: annotate dashboard complete in IMPLEMENTATION_PLAN.md
- e8bcd584 — fix: team photos full-width, one per row
- 25e1d194 — fix: improve schedule column layout + enlarge team photos
- bca8c1ec — fix: UI overflow audit - all 17 pages passing
Uncommitted: PROGRESS.md (modified), WORKLOG.md (modified)

[2026-05-11 07:49 MDT] Latest commits (5 latest on jason-5-may-updates):
- e6e0791b — Rebuild film_tool.html — extract CSS/JS, clean structure, remove dead code
- ec332b44 — Lock in Teams/Schedule tab state — PROGRESS + WORKLOG updates
- b8ca54dd — fix: jr high boys year 2027→2026 + preview date edits now respected
- 330de984 — docs: annotate dashboard complete in IMPLEMENTATION_PLAN.md
- e8bcd584 — fix: team photos full-width, one per row
Uncommitted: WORKLOG.md (modified), film_analysis.db (modified)

[2026-05-11 09:51 MDT] Latest commits (5 latest on jason-5-may-updates):
- e6e0791b — Rebuild film_tool.html — extract CSS/JS, clean structure, remove dead code
- ec332b44 — Lock in Teams/Schedule tab state — PROGRESS + WORKLOG updates
- b8ca54dd — fix: jr high boys year 2027→2026 + preview date edits now respected
- 330de984 — docs: annotate dashboard complete in IMPLEMENTATION_PLAN.md
- e8bcd584 — fix: team photos full-width, one per row
Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
Uncommitted changes: PROGRESS.md (modified), WORKLOG.md (modified), film_analysis.db (modified)
No new commits since 2026-05-11 07:49 check.

[2026-05-12 12:24 MDT] Latest commits (5 latest on jason-5-may-updates):
- 6bda59c1 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 10:20 MDT
- d5a49db1 — fix: improve upload timeout handling and progress display for large files
- f068a0d9 — fix: increase upload limit to 4GB + better error messages for film tool
- c5efac92 — Wrap init() in try-catch to prevent JS errors from blocking initAiUpload
- c990bf23 — Fix AI analysis subprocess + delete video bugs
Branch: jason-5-may-updates (ahead of origin/jason-5-may-updates by 1 commit)
Uncommitted changes: none (working tree clean)
[2026-05-12 18:36 MDT] Latest commits (5 latest on jason-5-may-updates):
- 5d2fa01b — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 16:34 MDT
- 2b51a872 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 14:31 MDT
- bf94bde2 — docs: update WORKLOG with film tool fix and cloudflare tunnel work
- 6c91da2b — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 12:24 MDT
- 6bda59c1 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 10:20 MDT
Branch: jason-5-may-updates (ahead of origin/jason-5-may-updates by 1 commit)
Uncommitted changes: none (working tree clean)
No new user-facing commits since 16:34 check. Project stable.

[2026-05-13 08:50 MDT] Latest commits (5 latest on jason-5-may-updates):
- 9a1f7ad6 — fix: align upload form fields with proper CSS scoping
- 8a549712 — fix: align upload form fields (Video File / Opponent)
- afdedacc — feat: split upload into tagging + AI analysis, add client-side compression
- 4b169313 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 18:36 MDT
- 5d2fa01b — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 16:34 MDT
Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
Uncommitted changes: PROGRESS.md, WORKLOG.md (modified), film_analysis.db (modified); scripts/tunnel-watchdog.sh (untracked)
No new commits since 06:44 check. Project stable; working tree has minor uncommitted edits.

[2026-05-13 10:53 MDT] Latest commits (5 latest on jason-5-may-updates):
- 9a1f7ad6 — fix: align upload form fields with proper CSS scoping
- 8a549712 — fix: align upload form fields (Video File / Opponent)
- afdedacc — feat: split upload into tagging + AI analysis, add client-side compression
- 4b169313 — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 18:36 MDT
- 5d2fa01b — docs: update PROGRESS.md and WORKLOG.md for cron status check 2026-05-12 16:34 MDT
Branch: jason-5-may-updates (up to date with origin/jason-5-may-updates)
Uncommitted changes: PROGRESS.md, WORKLOG.md (modified), film_analysis.db (modified); scripts/tunnel-watchdog.sh (untracked)
No new commits since 06:44 check. Project stable; working tree has minor uncommitted edits.

[2026-05-13 12:56 MDT] Latest commits (5 latest on jason-5-may-updates):
- 74788927 — docs: log intended AI analysis use - minutes, shots, play recognition, scouting
- c65705d0 — Remove dribble from all AI analysis code
- 9a1f7ad6 — fix: align upload form fields with proper CSS scoping
- 8a549712 — fix: align upload form fields (Video File / Opponent)
- afdedacc — feat: split upload into tagging + AI analysis, add client-side compression
Branch: jason-5-may-updates (ahead of origin by 2 commits)
Uncommitted changes: none (working tree clean)

[2026-05-13 14:59 MDT] Latest commits (5 latest on jason-5-may-updates):
- 92ac45fb — feat: add scouting system - reports, NFHS download, personnel, tendencies, practice points
- a679e68d — docs: add AI Film Breakdown spec from Scott's document
- 74788927 — docs: log intended AI analysis use - minutes, shots, play recognition, scouting
- c65705d0 — Remove dribble from all AI analysis code
- 9a1f7ad6 — fix: align upload form fields with proper CSS scoping
Branch: jason-5-may-updates (ahead of origin by 4 commits)
Uncommitted changes: blueprints/scouting.py (modified), schema.sql (modified), templates/scouting.html (modified), nfhs.py (untracked)
2 new commits since 12:56 check: major scouting system feature + AI Film Breakdown spec doc. Working tree has active edits to scouting blueprint, schema, template, plus new nfhs.py utility.

[2026-05-14 07:13 MDT] Latest commits (5 latest on jason-5-may-updates):
- 65aaaedc — Fix film_analysis shot classification + player effect; add track merger; update .gitignore
- 3846f838 — Rewrite ai_analyzer: YOLO every frame + track-pool matching (200px/120 frames)
- b2242856 — Fix tracker ID proliferation: only match recent trackers (60 frame window)
- a589aa6d — Clamp detection_stride to min 5, tighten tracker matching thresholds
- 2752ead6 — Fix shot classification and player effect errors
Branch: jason-5-may-updates (up to date with origin)
Working tree: clean — no uncommitted changes.

[2026-05-14 09:21 MDT] Latest commits (5 latest on jason-5-may-updates):
- 65aaaedc — Fix film_analysis shot classification + player effect; add track merger; update .gitignore
- 3846f838 — Rewrite ai_analyzer: YOLO every frame + track-pool matching (200px/120 frames)
- b2242856 — Fix tracker ID proliferation: only match recent trackers (60 frame window)
- a589aa6d — Clamp detection_stride to min 5, tighten tracker matching thresholds
- 2752ead6 — Fix shot classification and player effect errors
Branch: jason-5-may-updates (up to date with origin)
Uncommitted changes: modified — PROGRESS.md, WORKLOG.md, app.py, blueprints/ai.py, film_analysis.py, templates/videos.html; untracked — templates/analysis_results.html

[2026-05-14 11:24 MDT] Latest commits (5 latest on jason-5-may-updates):
- 4c7db914 — Add analysis results page and API endpoint
- 65aaaedc — Fix film_analysis shot classification + player effect; add track merger; update .gitignore
- 3846f838 — Rewrite ai_analyzer: YOLO every frame + track-pool matching (200px/120 frames)
- b2242856 — Fix tracker ID proliferation: only match recent trackers (60 frame window)
- a589aa6d — Clamp detection_stride to min 5, tighten tracker matching thresholds
Branch: jason-5-may-updates (up to date with origin)
Uncommitted changes: modified — app.py

[2026-05-14 13:27 MDT] Status check:
- Branch: jason-5-may-updates (up to date with origin)
- No new commits since last check (4c7db914 still latest)
- 5 latest commits:
  - 4c7db914 — Add analysis results page and API endpoint
  - 65aaaedc — Fix film_analysis shot classification + player effect; add track merger; update .gitignore
  - 3846f838 — Rewrite ai_analyzer: YOLO every frame + track-pool matching (200px/120 frames)
  - b2242856 — Fix tracker ID proliferation: only match recent trackers (60 frame window)
  - a589aa6d — Clamp detection_stride to min 5, tighten tracker matching thresholds
- Uncommitted changes: modified — app.py, PROGRESS.md, WORKLOG.md, templates/analysis_results.html

[2026-05-14 15:29 MDT] Status check:
- Branch: jason-5-may-updates (up to date with origin)
- No new commits since last check (4c7db914 still latest)
- 5 latest commits:
  - 4c7db914 — Add analysis results page and API endpoint
  - 65aaaedc — Fix film_analysis shot classification + player effect; add track merger; update .gitignore
  - 3846f838 — Rewrite ai_analyzer: YOLO every frame + track-pool matching (200px/120 frames)
  - b2242856 — Fix tracker ID proliferation: only match recent trackers (60 frame window)
  - a589aa6d — Clamp detection_stride to min 5, tighten tracker matching thresholds
- Uncommitted changes: modified — ai_analyzer.py, app.py, blueprints/ai.py, PROGRESS.md, static/js/film-tool.js, templates/analysis_results.html, templates/film_tool.html, WORKLOG.md

[2026-05-14 17:33 MDT] Latest commits (5 latest on jason-5-may-updates):
- 4c7db914 — Add analysis results page and API endpoint
- 65aaaedc — Fix film_analysis shot classification + player effect; add track merger; update .gitignore
- 3846f838 — Rewrite ai_analyzer: YOLO every frame + track-pool matching (200px/120 frames)
- b2242856 — Fix tracker ID proliferation: only match recent trackers (60 frame window)
- a589aa6d — Clamp detection_stride to min 5, tighten tracker matching thresholds
Branch: jason-5-may-updates (up to date with origin)
Uncommitted changes (staged): PROGRESS.md, WORKLOG.md, ai_analyzer.py, app.py, blueprints/ai.py, static/js/film-tool.js, templates/analysis_results.html, templates/film_tool.html
