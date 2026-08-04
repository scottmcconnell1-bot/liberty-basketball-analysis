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
    ENABLE_ASSISTANT_READ_ONLY = True
    ENABLE_COACH_PORTAL = True  # Approach A — Scott: default True intentional; toggle off in Settings if needed
    ENABLE_WEEKLY_PACKET = False
    ENABLE_SEASON_REVIEW = False


class AnalysisConfig:
    pass


class Config:
    DATABASE = os.environ.get("LIBERTY_DATABASE", "film_analysis.db")
    UPLOAD_FOLDER = os.environ.get("LIBERTY_UPLOAD_FOLDER", "uploads")
    # Shared coach portal password (env / .env only — no schema.sql / DB storage).
    COACH_PASSWORD = os.environ.get("LIBERTY_COACH_PASSWORD", "")
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
    # Set via environment. Do not commit key material to the repository.
    VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
    VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")

    # ── SMTP (Email) ───────────────────────────────────────
    SMTP_SERVER = os.environ.get("SMTP_SERVER", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "")
    SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
