IMPLEMENTATION PLAN — Liberty Basketball Analysis
Date: 2026-04-28
Goal: Build an assistant-coach pipeline that automatically watches uploaded game film, produces NBA-style box scores and per-game/season stats, links each stat to the exact video timestamp/frame, and generates human-readable game summaries and practice recommendations. The system must allow coach overrides and preserve season history.

High-level architecture
- Ingest: file upload UI → uploads/ (Flask app) and analysis_runs table records job.
- Detection: ai_analyzer runs YOLO on video frames, writes detections (+tracker_id) to detections table.
- Tracking: integrate a multi-object tracker (ByteTrack / DeepSort / OC-SORT) to assign tracker_id per player across frames.
- Events: event_generator converts detections+tracking into events (possession, dribble, shot attempt, assist, rebound, turnover, foul) and writes to events table with timestamp_ms and a link (video filename + timestamp/frame).
- Stats: aggregator builds box scores and stat lines per player/team per game and persists them in a stats table (or derives on-demand from events table).
- UI: Flask routes + templates present games, video player with time-linked event markers, box scores with clickable links, game summary and coach notes editable.
- Persistence: film_analysis.db stores detections, events, analysis_runs, stats; nightly/periodic backups and season partitioning.

Acceptance criteria (minimum viable)
- Upload a video and start an analysis run from the UI/API.
- Analyzer writes detections and tracker_ids to the DB.
- Event generator produces at least: possessions, dribbles, shot attempts, made/missed shots, rebounds.
- Box score page for a game shows per-player statistics and each stat links to a playable timestamp in the film.
- Coach can edit any event via the UI; edits update events and stats.
- WORKLOG.md and docs/IMPLEMENTATION_PLAN.md are committed to GitHub with clear tasks.

Bite-sized task list (ordered, copy-paste commands included)
1) Confirm DB schema & migrations (5–10 min)
   - Files: schema.sql
   - Task: Add tables for stats and link columns to events. Verify existing DB has tracker_id column.
   - Command: sqlite3 film_analysis.db "PRAGMA table_info(detections);"
   - Verify: tracker_id present; create stats table if absent.

2) Integrate tracker and write tracker_id (30–90 min)
   - Files: ai_analyzer.py (modify), requirements.txt (add tracker lib), event_generator.py (read tracker_id)
   - Plan: Implement ByteTrack/DeepSort wrapper that consumes YOLO detections per frame and returns tracked identities; write tracker_id into detections; run on a short sample and verify persistence.
   - Verify: SELECT DISTINCT tracker_id FROM detections WHERE game_id='sample' AND tracker_id IS NOT NULL;

3) Improve event_generator to use tracker_id (30–90 min)
   - Files: event_generator.py
   - Task: Replace spatial-binning fallback with tracker-based grouping; implement robust dribble detection using ball y-oscillation relative to player and frame frequency.
   - Verify: Run event_generator.main on sample and inspect inserted events table.

4) Implement shot detection & classify result (45–120 min)
   - Files: event_generator.py, ai_analyzer.py (optional post-frame crop for hoop area), schema.sql (event details)
   - Plan: Detect shot attempts when player with ball exhibits forward motion + ball leaves player and moves toward hoop region; classify by follow-up frames (ball in hoop bounds) as made/missed.
   - Verify: events table contains event_type='shot_attempt' with shot_result in {made, missed, unknown}.

5) Build stats aggregator (30–60 min)
   - Files: stats.py (new), possibly stats table in schema.sql
   - Task: Translate events into box score counts (PTS, FGM-FGA, 3PM-3PA, AST, REB, TO, STL, BLK, MIN (approx)). Persist per-game and per-season aggregation.
   - Verify: stats API returns correct aggregates from events.

6) Wire front-end pages (60–120 min)
   - Files: templates/game.html, templates/boxscore.html, static/js/player-links.js
   - Task: Add box score UI with clickable timestamps (links use /video/<filename>#t=<seconds> or a JS player API). Add editor UI for correcting events.
   - Verify: clicking a stat seeks the video player to the timestamp; coach edits update the DB.

7) Generate game summary & coaching recommendations (45–90 min)
   - Files: ai_summary.py (new), templates/summary.html
   - Plan: Use rules + heuristics to summarize strengths/weaknesses (e.g., "Top scorers: A, B; Turnover hotspots: press defense leading to 12 TOs in Q2"). Optionally integrate an LLM to produce human-friendly prose from structured stats.
   - Verify: summary page exists and editable notes are saved.

8) Season history & persistence (30–60 min)
   - Files: schema.sql (season table), stats.py (season aggregation)
   - Task: Store game_id→season mapping; query seasonal leaders; maintain per-season backups.

9) Tests & sample run (30–60 min)
   - Files: tests/test_event_pipeline.py
   - Task: Add a small video sample or mocked detections to run full pipeline in CI; unit tests for possession/dribble detection.

10) Docs & annotations (ongoing)
   - Files: WORKLOG.md, docs/IMPLEMENTATION_PLAN.md, README.md
   - Task: Every code change must update WORKLOG.md with a one-line summary and link to the commit. Add inline docstrings and top-level README section "Assistant coach features" describing expected outputs.

Notes on user interaction & coach overrides
- Every generated event must include: game_id, event_id, timestamp_ms, source_frame, video_filename, confidence, inferred_tracker_id (if any), and a boolean "human_verified" flag.
- UI must allow editing event fields and marking human_verified; edits should trigger stats re-aggregation for that game.

Data model suggestions (minimum)
- events: keep as-is, add source_video TEXT, source_frame INTEGER, human_verified BOOLEAN DEFAULT 0, confidence REAL
- stats: per game per player table: (game_id, player_id/tracker_id, team, minutes, pts, fgm, fga, threes_made, threes_att, ast, reb, tov, stl, blk)
- players: maintain a players table mapping tracker_id metadata to roster entries (season, jersey number, name) via a manual mapping UI.

Security & operations
- Do not keep PATs in repo or remote URL. Revoke the PAT used and set up gh auth or SSH deploy key.
- Keep film & DB out of cloud-sync while processing to avoid locking.
- Implement periodic DB backups and optionally export per-season CSV/JSON.

Deliverables & milestones
- M1 (upload → detections + tracker, events written): 2–4 days of focused work.
- M2 (shots, rebounds, box scores): +2–3 days.
- M3 (UI with clickable video links + coach edit): +2–4 days.
- M4 (summaries, season history, tests, docs): +2–4 days.

Next immediate step I will take (if you confirm)
- Start tracker integration in ai_analyzer (ByteTrack/DeepSort). This will: add dependency, implement per-frame tracker update, and persist tracker_id to DB. I will update WORKLOG.md and commit changes.


