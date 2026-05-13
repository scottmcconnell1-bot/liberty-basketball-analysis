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
    team            TEXT NOT NULL DEFAULT 'boys_hs',
    gender          TEXT NOT NULL DEFAULT 'boys',
    level           TEXT NOT NULL DEFAULT 'jr_high',
    game_date       DATE NOT NULL,
    game_time       TIME,
    jv_game_time    TIME,
    frosh_game_time TIME,
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

-- ── Player Development (Phase 7) ──────────────────────────

CREATE TABLE IF NOT EXISTS player_development_clips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id       INTEGER REFERENCES players(id),
    game_id         TEXT,
    event_id        INTEGER REFERENCES events(id),
    clip_start_ms   INTEGER NOT NULL,
    clip_end_ms     INTEGER NOT NULL,
    clip_label      TEXT NOT NULL,
    clip_category   TEXT NOT NULL DEFAULT 'general',
    season_id       INTEGER REFERENCES seasons(id),
    notes           TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS practice_playlists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    season_id       INTEGER REFERENCES seasons(id),
    level           TEXT NOT NULL DEFAULT 'jr_high',
    status          TEXT NOT NULL DEFAULT 'draft',
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS practice_playlist_clips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id     INTEGER NOT NULL REFERENCES practice_playlists(id) ON DELETE CASCADE,
    clip_id         INTEGER NOT NULL REFERENCES player_development_clips(id) ON DELETE CASCADE,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(playlist_id, clip_id)
);

CREATE TABLE IF NOT EXISTS practice_plan_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    practice_id     INTEGER NOT NULL REFERENCES practices(id) ON DELETE CASCADE,
    playlist_id     INTEGER REFERENCES practice_playlists(id),
    item_type       TEXT NOT NULL DEFAULT 'drill',
    title           TEXT NOT NULL,
    description     TEXT,
    duration_min    INTEGER,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ── Playbook ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS playbooks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    description     TEXT,
    created_by      TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plays (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    playbook_id     INTEGER REFERENCES playbooks(id) ON DELETE SET NULL,
    name            TEXT NOT NULL,
    description     TEXT,
    category        TEXT NOT NULL DEFAULT 'offense',
    tags            TEXT,
    diagram_json    TEXT,
    created_by      TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS play_steps (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    play_id         INTEGER NOT NULL REFERENCES plays(id) ON DELETE CASCADE,
    step_number     INTEGER NOT NULL DEFAULT 0,
    label           TEXT,
    positions_json  TEXT NOT NULL DEFAULT '{}',
    movements_json  TEXT NOT NULL DEFAULT '[]',
    notes           TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ── Messaging ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS conversations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT,
    type            TEXT NOT NULL DEFAULT 'direct',
    created_by      TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_members (
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'member',
    last_read_at    TIMESTAMP,
    joined_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (conversation_id, user_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sender_id       TEXT NOT NULL,
    body            TEXT NOT NULL,
    attachment_url  TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS message_read_receipts (
    message_id      INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    user_id         TEXT NOT NULL,
    read_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (message_id, user_id)
);

-- ── User Accounts ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'player',
    avatar_url      TEXT,
    phone           TEXT,
    is_active       INTEGER NOT NULL DEFAULT 1,
    email_verified  INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at   TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_token   TEXT UNIQUE NOT NULL,
    ip_address      TEXT,
    user_agent      TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS user_notification_prefs (
    user_id                 INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    notify_email_messages   INTEGER NOT NULL DEFAULT 1,
    notify_email_schedule   INTEGER NOT NULL DEFAULT 1,
    notify_push_messages    INTEGER NOT NULL DEFAULT 1,
    notify_push_schedule    INTEGER NOT NULL DEFAULT 1,
    notify_sms_game_reminder INTEGER NOT NULL DEFAULT 0,
    quiet_hours_start       TEXT,
    quiet_hours_end         TEXT,
    updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint        TEXT NOT NULL,
    p256dh          TEXT NOT NULL,
    auth_key        TEXT NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, endpoint)
);

CREATE TABLE IF NOT EXISTS notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type            TEXT NOT NULL,
    title           TEXT NOT NULL,
    body            TEXT,
    link            TEXT,
    is_read         INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ── Scouting ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS scouting_reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id         INTEGER REFERENCES games(id),
    opponent_name   TEXT NOT NULL,
    scout_date      DATE NOT NULL,
    film_source     TEXT,  -- 'nfhs_vod', 'pixellot', 'manual_upload'
    nfhs_game_id    TEXT,
    status          TEXT NOT NULL DEFAULT 'draft',  -- 'draft', 'in_progress', 'completed'
    offensive_identity TEXT,
    defensive_identity TEXT,
    tempo           TEXT,  -- 'fast', 'slow', 'methodical', 'varies'
    executive_summary TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scouting_personnel (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES scouting_reports(id) ON DELETE CASCADE,
    jersey_number   INTEGER,
    player_name     TEXT,
    role            TEXT NOT NULL,  -- 'ball_handler', 'go_to_scorer', 'rim_protector', 'best_rebounder', 'spot_up_shooter', 'role_player'
    notes           TEXT,
    usage_rate      REAL,  -- estimated % of possessions used
    ppp             REAL,  -- points per possession when involved
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scouting_offensive_sets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES scouting_reports(id) ON DELETE CASCADE,
    set_name        TEXT NOT NULL,  -- 'horns', 'sideline_out', 'early_pnr', 'isolation', 'spread_pnr', 'post_up'
    trigger_action  TEXT,  -- what starts the set
    frequency       INTEGER DEFAULT 0,  -- times observed
    ppp             REAL,  -- points per possession on this set
    result_vs_pressure TEXT,  -- what they do when pressured
    notes           TEXT,
    clip_timestamps TEXT,  -- JSON array of {game_time, quarter, description}
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scouting_defensive_tendencies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES scouting_reports(id) ON DELETE CASCADE,
    scheme          TEXT NOT NULL,  -- 'man', 'zone_23', 'zone_32', 'press', 'trap'
    pnr_coverage    TEXT,  -- 'drop', 'switch', 'ice', 'show', 'hedge'
    frequency       REAL,  -- % of possessions
    ppp_allowed     REAL,
    weak_rotations  TEXT,  -- JSON array of weak rotation points
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scouting_tendencies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES scouting_reports(id) ON DELETE CASCADE,
    tendency_type   TEXT NOT NULL,  -- 'offensive', 'defensive', 'situational', 'habit'
    category        TEXT,  -- 'shot_selection', 'drive_direction', 'late_clock', 'transition', 'rebounding', 'turnover'
    description     TEXT NOT NULL,
    frequency       TEXT,  -- 'always', 'often', 'sometimes', 'rarely' or percentage
    clip_timestamps TEXT,  -- JSON array of {game_time, quarter, description}
    exploitable     INTEGER DEFAULT 0,  -- 1 if this is something we can exploit
    practice_drill  TEXT,  -- mapped drill to counter this
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scouting_situational (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES scouting_reports(id) ON DELETE CASCADE,
    situation       TEXT NOT NULL,  -- 'late_shot_clock', 'end_of_quarter', 'out_of_bounds', 'press_breaker', 'foul_game'
    description     TEXT NOT NULL,
    frequency       INTEGER DEFAULT 0,
    ppp             REAL,
    clip_timestamps TEXT,
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scouting_mismatches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES scouting_reports(id) ON DELETE CASCADE,
    opponent_jersey INTEGER,
    opponent_name   TEXT,
    vulnerability   TEXT NOT NULL,  -- 'struggles_vs_smaller', 'struggles_vs_bigger', 'poor_closeout', 'slow_rotation', 'turnover_under_pressure'
    exploit_action  TEXT,  -- what we should do to exploit
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scouting_practice_points (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES scouting_reports(id) ON DELETE CASCADE,
    point_number    INTEGER NOT NULL,  -- 1, 2, 3
    description     TEXT NOT NULL,
    drill_name      TEXT,
    measurable_target TEXT,  -- e.g., "reduce open corner 3s off PnR by 50%"
    clip_timestamps TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS nfhs_credentials (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL,
    password_enc    TEXT NOT NULL,  -- encrypted password
    is_active       INTEGER NOT NULL DEFAULT 1,
    last_login_at   TIMESTAMP,
    last_login_status TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scouting_clips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       INTEGER NOT NULL REFERENCES scouting_reports(id) ON DELETE CASCADE,
    clip_type       TEXT NOT NULL,  -- 'offensive_set', 'defensive_action', 'tendency', 'mismatch', 'situational', 'practice_example'
    game_time       TEXT,  -- e.g., "Q2 5:32"
    quarter         INTEGER,
    description     TEXT NOT NULL,
    coach_cue       TEXT,  -- short cue line for pre-game meeting
    video_timestamp_ms INTEGER,  -- timestamp in the source video
    source          TEXT,  -- 'ai_detected', 'manual_tag'
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
