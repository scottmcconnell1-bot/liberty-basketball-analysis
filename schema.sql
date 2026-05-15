-- schema.sql — Liberty Basketball Analysis
-- Single source of truth for the database schema.
-- All tables use CREATE TABLE IF NOT EXISTS so it's safe to re-run.

-- ---------- Seasons ----------
CREATE TABLE IF NOT EXISTS seasons (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------- Scheduled Games ----------
CREATE TABLE IF NOT EXISTS scheduled_games (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  season_id INTEGER NOT NULL REFERENCES seasons(id),
  program_name TEXT NOT NULL,
  gender TEXT NOT NULL CHECK(gender IN ('boys', 'girls')),
  level TEXT NOT NULL CHECK(level IN ('varsity', 'jv', 'jr_high')),
  game_date DATE NOT NULL,
  game_time TIME NOT NULL,
  location_type TEXT NOT NULL CHECK(location_type IN ('home', 'away', 'neutral')),
  opponent_name TEXT NOT NULL,
  tournament_name TEXT,
  status TEXT NOT NULL DEFAULT 'scheduled'
    CHECK(status IN ('scheduled', 'cancelled', 'rescheduled', 'completed')),
  notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------- Games (actual instances) ----------
CREATE TABLE IF NOT EXISTS games (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scheduled_game_id INTEGER REFERENCES scheduled_games(id),
  start_time TIMESTAMP,
  end_time TIMESTAMP,
  source_type TEXT NOT NULL CHECK(source_type IN ('pixellot', 'nfhs', 'manual')),
  source_key TEXT NOT NULL,
  nfhs_game_id TEXT,
  nfhs_url TEXT,
  home_score INTEGER DEFAULT 0,
  away_score INTEGER DEFAULT 0,
  result TEXT CHECK(result IN ('W', 'L', 'T')),
  is_conference INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------- NFHS Matches ----------
CREATE TABLE IF NOT EXISTS nfhs_matches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scheduled_game_id INTEGER NOT NULL REFERENCES scheduled_games(id),
  nfhs_game_id TEXT NOT NULL,
  nfhs_url TEXT NOT NULL,
  match_status TEXT NOT NULL DEFAULT 'candidate'
    CHECK(match_status IN ('candidate', 'confirmed', 'rejected')),
  confidence REAL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------- Sources (video sources per game) ----------
CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  game_id INTEGER NOT NULL REFERENCES games(id),
  source_type TEXT NOT NULL,
  source_path TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------- Players (roster mapping) ----------
CREATE TABLE IF NOT EXISTS players (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  season_id INTEGER NOT NULL REFERENCES seasons(id),
  jersey_number INTEGER,
  name TEXT NOT NULL,
  position TEXT,
  grade INTEGER,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------- Events (in-game events) ----------
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  game_id TEXT NOT NULL,
  player TEXT,
  event_type TEXT NOT NULL,
  shot_result TEXT,
  timestamp_ms INTEGER NOT NULL,
  details_json TEXT,
  source_video TEXT,
  source_frame INTEGER,
  human_verified INTEGER DEFAULT 0,
  confidence REAL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------- Analysis Runs ----------
CREATE TABLE IF NOT EXISTS analysis_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  game_id TEXT NOT NULL,
  video_path TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  completed_at TIMESTAMP,
  error_message TEXT
);

-- ---------- Detections (per-frame object detections) ----------
CREATE TABLE IF NOT EXISTS detections (
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

-- ---------- Stats (per-game per-player box score) ----------
CREATE TABLE IF NOT EXISTS stats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  game_id TEXT NOT NULL,
  player TEXT NOT NULL,
  team TEXT,
  minutes INTEGER DEFAULT 0,
  pts INTEGER DEFAULT 0,
  fgm INTEGER DEFAULT 0,
  fga INTEGER DEFAULT 0,
  threes_made INTEGER DEFAULT 0,
  threes_att INTEGER DEFAULT 0,
  ast INTEGER DEFAULT 0,
  reb INTEGER DEFAULT 0,
  tov INTEGER DEFAULT 0,
  stl INTEGER DEFAULT 0,
  blk INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------- Practices ----------
CREATE TABLE IF NOT EXISTS practices (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  season_id INTEGER NOT NULL REFERENCES seasons(id),
  practice_date DATE NOT NULL,
  start_time TIME,
  end_time TEXT,
  location TEXT,
  focus TEXT,
  coach_notes TEXT,
  ai_notes TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
