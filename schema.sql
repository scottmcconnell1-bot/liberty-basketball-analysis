-- ============================================================
-- Liberty Basketball Analysis — Database Schema
-- Source of truth: all tables defined here.
-- Use CREATE TABLE IF NOT EXISTS to support safe re-init.
-- ============================================================

-- ── Analysis pipeline ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS analysis_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id      TEXT NOT NULL,
    video_path   TEXT NOT NULL,
    source_video_id INTEGER REFERENCES videos(id),
    base_game_id TEXT,
    run_label    TEXT,
    settings_json TEXT,
    run_kind     TEXT NOT NULL DEFAULT 'primary',
    status       TEXT NOT NULL DEFAULT 'pending',
    started_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS detections (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id      TEXT NOT NULL,
    frame_number INTEGER NOT NULL,
    timestamp_ms INTEGER NOT NULL,
    object_class TEXT NOT NULL,
    confidence   REAL NOT NULL,
    x_center     INTEGER NOT NULL,
    y_center     INTEGER NOT NULL,
    width        INTEGER NOT NULL,
    height       INTEGER NOT NULL,
    tracker_id   INTEGER,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id        TEXT NOT NULL,
    player         TEXT,
    event_type     TEXT NOT NULL,
    shot_result    TEXT,
    timestamp_ms   INTEGER NOT NULL,
    details_json   TEXT,
    source_video   TEXT,
    source_frame   INTEGER,
    human_verified INTEGER NOT NULL DEFAULT 0,
    confidence     REAL,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ── Season & schedule ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS seasons (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    start_date DATE NOT NULL,
    end_date   DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scheduled_games (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id       INTEGER NOT NULL REFERENCES seasons(id),
    program_name    TEXT NOT NULL DEFAULT 'Liberty',
    gender          TEXT NOT NULL DEFAULT 'boys',
    level           TEXT NOT NULL DEFAULT 'jr_high',
    game_date       DATE NOT NULL,
    game_time       TIME,
    location_type   TEXT NOT NULL DEFAULT 'home',
    opponent_name   TEXT NOT NULL,
    tournament_name TEXT,
    status          TEXT NOT NULL DEFAULT 'scheduled',
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS games (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    scheduled_game_id  INTEGER REFERENCES scheduled_games(id),
    start_time         TIMESTAMP,
    end_time           TIMESTAMP,
    source_type        TEXT NOT NULL DEFAULT 'manual',
    source_key         TEXT NOT NULL,
    nfhs_game_id       TEXT,
    nfhs_url           TEXT,
    home_score         INTEGER,
    away_score         INTEGER,
    result             TEXT,
    is_conference      INTEGER NOT NULL DEFAULT 0,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nfhs_matches (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    scheduled_game_id  INTEGER NOT NULL REFERENCES scheduled_games(id),
    nfhs_game_id       TEXT NOT NULL,
    nfhs_url           TEXT NOT NULL,
    match_status       TEXT NOT NULL DEFAULT 'candidate',
    confidence         REAL,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     INTEGER NOT NULL REFERENCES games(id),
    source_type TEXT NOT NULL,
    source_path TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Players ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS players (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    jersey_number INTEGER,
    position      TEXT,
    grade         INTEGER,
    program_name  TEXT NOT NULL DEFAULT 'Liberty',
    gender        TEXT NOT NULL DEFAULT 'boys',
    level         TEXT NOT NULL DEFAULT 'jr_high',
    season_id     INTEGER REFERENCES seasons(id),
    tracker_id    INTEGER,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Stats ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS stats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id     TEXT NOT NULL,
    player_id   INTEGER REFERENCES players(id),
    tracker_id  INTEGER,
    player_name TEXT,
    team        TEXT,
    minutes     REAL,
    pts         INTEGER NOT NULL DEFAULT 0,
    fgm         INTEGER NOT NULL DEFAULT 0,
    fga         INTEGER NOT NULL DEFAULT 0,
    threes_made INTEGER NOT NULL DEFAULT 0,
    threes_att  INTEGER NOT NULL DEFAULT 0,
    ast         INTEGER NOT NULL DEFAULT 0,
    reb         INTEGER NOT NULL DEFAULT 0,
    tov         INTEGER NOT NULL DEFAULT 0,
    stl         INTEGER NOT NULL DEFAULT 0,
    blk         INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(game_id, player_id)
);

-- ── Practices (Phase 6) ───────────────────────────────────

CREATE TABLE IF NOT EXISTS practices (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    season_id        INTEGER REFERENCES seasons(id),
    level            TEXT NOT NULL DEFAULT 'jr_high',
    practice_date    DATE NOT NULL,
    status           TEXT NOT NULL DEFAULT 'planned',
    plan_source      TEXT DEFAULT 'manual',
    plan_text        TEXT,
    coach_notes      TEXT,
    ai_notes         TEXT,
    combined_summary TEXT,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Video library ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS videos (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    original_filename TEXT NOT NULL,
    stored_filename   TEXT NOT NULL UNIQUE,
    file_path         TEXT NOT NULL,
    file_size_bytes   INTEGER,
    opponent          TEXT,
    game_id           TEXT,
    upload_timestamp  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_duplicate      INTEGER NOT NULL DEFAULT 0,
    duplicate_of_id   INTEGER REFERENCES videos(id)
);

CREATE TABLE IF NOT EXISTS app_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS issue_reports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_type   TEXT NOT NULL DEFAULT 'issue',
    title        TEXT NOT NULL,
    details      TEXT NOT NULL,
    source_path  TEXT,
    browser_console TEXT,
    status       TEXT NOT NULL DEFAULT 'open',
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
