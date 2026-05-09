import os


class Features:
    ENABLE_SEASONS_SCHEDULE = True
    ENABLE_GAMES_SOURCES = True
    ENABLE_NFHS_MATCHING = True
    ENABLE_MANUAL_TAG_MVP = True
    ENABLE_AUTO_STATS_M1 = True
    ENABLE_EXTENDED_EVENTS_M2 = False
    ENABLE_PRACTICES = True
    ENABLE_PLAYER_DEVELOPMENT = True
    ENABLE_PRACTICE_PLAYLISTS = True
    ENABLE_WEEKLY_PACKET = False
    ENABLE_SEASON_REVIEW = False


class AnalysisConfig:
    USE_DRIBBLE_EVENTS = False
    USE_DRIBBLE_HEURISTICS = True


class Config:
    DATABASE = os.environ.get("LIBERTY_DATABASE", "film_analysis.db")
    UPLOAD_FOLDER = os.environ.get("LIBERTY_UPLOAD_FOLDER", "uploads")
    FEATURES = {
        name: getattr(Features, name)
        for name in dir(Features)
        if name.startswith("ENABLE_")
    }
    ANALYSIS_CONFIG = {
        name: getattr(AnalysisConfig, name)
        for name in dir(AnalysisConfig)
        if name.startswith("USE_")
    }

    # ── VAPID Keys (Browser Push) ──────────────────────────
    # Generated on 2026-05-08. Override via env vars if needed.
    VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", """-----BEGIN PRIVATE KEY-----
MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgvXgGzvO9gi39B6vi
sYX5M4ZeesmmBFw7a5RfEY3QcV2hRANCAATUd8oSuyEx9UnKKUb/l3lPqCkgHvjP
1s0mBkGy2bYrJ8tEUS4e5ej5IOvsslQOGghfEKM5aIJIeQGPwFBT6A8Q
-----END PRIVATE KEY-----""")
    VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", """-----BEGIN PUBLIC KEY-----
MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE1HfKErshMfVJyilG/5d5T6gpIB74
z9bNJgZBstm2KyfLRFEuHuXo+SDr7LJUDhoIXxCjOWiCSHkBj8BQU+gPEA==
-----END PUBLIC KEY-----""")

    # ── SMTP (Email) ───────────────────────────────────────
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "")
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
