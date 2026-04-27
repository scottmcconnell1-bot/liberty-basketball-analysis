DROP TABLE IF EXISTS events;

CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  game_id TEXT NOT NULL,
  player TEXT,
  event_type TEXT NOT NULL,
  shot_result TEXT,
  timestamp_ms INTEGER NOT NULL,
  details_json TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id TEXT NOT NULL,
    video_path TEXT NOT NULL,
    status TEXT NOT NULL,        -- e.g. 'pending', 'running', 'completed', 'failed'
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

DROP TABLE IF EXISTS detections;

CREATE TABLE detections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  game_id TEXT NOT NULL,
  frame_number INTEGER NOT NULL,
  timestamp_ms INTEGER NOT NULL,
  object_class TEXT NOT NULL,
  confidence REAL NOT NULL,
  x_center INTEGER NOT NULL,
  y_center INTEGER NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
