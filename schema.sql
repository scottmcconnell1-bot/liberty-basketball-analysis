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
  tracker_id INTEGER,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Seasons table: stores seasons/years/competitions for grouping games
CREATE TABLE IF NOT EXISTS seasons (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  start_date DATE,
  end_date DATE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Scheduled games: planned games tied to a season
CREATE TABLE IF NOT EXISTS scheduled_games (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  season_id INTEGER NOT NULL,
  program_name TEXT,
  gender TEXT,
  level TEXT,
  game_date DATE,
  game_time TIME,
  location_type TEXT,
  opponent_name TEXT,
  tournament_name TEXT,
  status TEXT DEFAULT 'scheduled',
  notes TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP
);
