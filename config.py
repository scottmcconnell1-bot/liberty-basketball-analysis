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
