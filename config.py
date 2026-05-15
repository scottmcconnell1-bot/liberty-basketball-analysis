"""config.py — Feature flags and app-wide settings for Liberty Basketball Analysis.

Every major feature/phase is behind a single flag so it can be disabled
without DB migrations or code removal.
"""


class Features:
    ENABLE_MANUAL_TAG_MVP = True
    ENABLE_AUTO_STATS_M1 = True
    ENABLE_EXTENDED_EVENTS_M2 = False
    ENABLE_WEEKLY_PACKET = False
    ENABLE_SEASON_REVIEW = False
    ENABLE_SCHEDULE = True
    ENABLE_GAMES = False
    ENABLE_NFHS_MATCHING = False
    ENABLE_PRACTICES = False


class AnalysisConfig:
    USE_DRIBBLE_EVENTS = False      # default: no dribble events as stats
    USE_DRIBBLE_HEURISTICS = True   # internal only, if needed
