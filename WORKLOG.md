WORKLOG — Liberty Basketball Analysis
Started: 2026-04-27

CURRENT STATUS (where we left off)
- Repository cloned from: https://github.com/scottmcconnell1-bot/liberty-basketball-analysis
- Local path: /home/smcconnell/projects/liberty-basketball-analysis
- Flask app runs on port 8080 (development server). I moved the HTML template into templates/ so the app could render.

AI pipeline files examined:
- ai_analyzer.py
  - Uses ultralytics YOLO model (yolov8n.pt) to run object detection on frames.
  - Writes detections to the SQLite DB (film_analysis.db) into the detections table.
  - Inserts: game_id, frame_number, timestamp_ms, object_class, confidence, x_center, y_center, width, height
  - Calls event_generator.generate_events(game_id, db_path) after finishing analysis.

- event_generator.py
  - get_detections(conn, game_id): reads detections into a pandas DataFrame.
  - find_ball_possession(detections_df): implemented. It computes distances between ball and player detections per frame and flags the closest player as having the ball when within a possession_threshold (default 50 px). It expects column names like 'class_name', 'x_center', etc.
  - find_dribbles(...): placeholder / not implemented. Contains notes to group by tracker_id and find continuous sequences.
  - main(game_id, db_path): runs the pipeline: load detections -> determine possession -> (dribble detection incomplete)

Database (film_analysis.db)
- Tables: analysis_runs, detections, events
- detections table columns (PRAGMA):
  id | game_id | frame_number | timestamp_ms | object_class | confidence | x_center | y_center | width | height | created_at
  (No tracker_id column at present.)

NOTED MISMATCHES / POTENTIAL ISSUES (action items)
1) Column names mismatch:
   - ai_analyzer writes object_class into the DB. event_generator code expects a column named 'class_name'. We need to standardize on one name (recommendation: use 'class_name' or update event_generator to use 'object_class').
2) Class label mismatch for the ball:
   - ai_analyzer uses model names (likely 'person' and 'sports ball'). event_generator looks for 'ball'. Decide on a canonical label (e.g., 'ball') and map 'sports ball' -> 'ball' when inserting detections, or update event_generator to accept 'sports ball'.
3) No tracker_id in detections:
   - find_dribbles references tracker_id; current detections table has none. To identify dribbles and continuous possessions we must add tracking (DeepSort/ByteTrack or opencv tracker) and store tracker_id per detection. This requires DB schema update and changes to ai_analyzer to run tracking or to run a separate tracker pass.
4) Dribble detection not implemented:
   - Next technical step is to group possession frames by tracker_id and detect rhythmic vertical movement of the ball relative to the player (or repeated close ball distance toggling) to mark dribbles.
5) Concurrency and DB locking:
   - The analyzer runs in a separate process and writes to the DB. Using SQLite in a cloud-synced folder can produce file locks. Keep DB local and/or pause sync during runs.

IMMEDIATE NEXT STEPS (short-term task list)
- [ ] Standardize column and class names between ai_analyzer.py and event_generator.py.
      Suggestion: update ai_analyzer to insert object_class values 'person' and 'ball' (map 'sports ball'->'ball'), OR update event_generator to read 'object_class'.
- [ ] Add tracker support and a tracker_id column to detections.
- [ ] Implement find_dribbles() grouping by tracker_id and detecting dribble sequences.
- [ ] Add unit/functional test: run ai_analyzer on a short sample (first N frames) and verify detections -> run event_generator.main(game_id, db_path) and confirm events are generated.
- [ ] Commit WORKLOG.md and code changes to Git, push to GitHub so you can resume from another machine.

How to resume / commands to run (one-liners)
- Activate venv and start app: cd /home/scmcconnell/projects/liberty-basketball-analysis && source .venv/bin/activate && python app.py
- Run analyzer for a video (example):
  source .venv/bin/activate && python -c "from ai_analyzer import run_ai_analysis; run_ai_analysis('film_analysis.db', 'uploads/myvideo.mp4', 'game_001')"
- Run event generation alone:
  source .venv/bin/activate && python -c "from event_generator import main; main('game_001', 'film_analysis.db')"

Notes on GitHub / collaboration
- Yes — the project is hosted on GitHub (private repo). To make progress portable between machines, commit local changes and push them. If you want, I can create the commit and push it for you (you should revoke the PAT you pasted earlier and set up gh/SSH auth instead).

Log location
- This Worklog file: /home/smcconnell/projects/liberty-basketball-analysis/WORKLOG.md (created by the assistant). Please back it up to GitHub by committing it.

If you'd like I can now:
- Commit and push WORKLOG.md to the repo (I can do it if you want me to push with the credentials you used earlier, or I can show the exact git commands for you to run),
- Standardize the column names now (I can patch the code to make event_generator use 'object_class' and map 'sports ball'->'ball' in ai_analyzer),
- Add a tracker_id column and scaffold tracker integration,
- Implement dribble detection logic (I can start with a heuristic or integrate an existing tracker).

— End of current snapshot
