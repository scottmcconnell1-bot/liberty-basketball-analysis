"""
Canonical module entitlement keys for Stage 6A.

These keys are separate from config.py development feature flags.
"""

BASE_PLATFORM = "base_platform"
STATS = "stats"
MINUTES_LINEUPS = "minutes_lineups"
FILM_ROOM = "film_room"
SCOUTING = "scouting"
PLAYBOOK_RECOGNITION = "playbook_recognition"
STRATEGY = "strategy"
AI_ASSIST = "ai_assist"
ADVANCED_TRACKING = "advanced_tracking"

LEGACY_BASE_ALIAS = "base"

MODULE_KEY_LABELS = {
    BASE_PLATFORM: "Base Platform",
    STATS: "Stats",
    MINUTES_LINEUPS: "Minutes & Lineups",
    FILM_ROOM: "Film Room",
    SCOUTING: "Scouting",
    PLAYBOOK_RECOGNITION: "Playbook",
    STRATEGY: "Strategy",
    AI_ASSIST: "AI Assist",
    ADVANCED_TRACKING: "Advanced Tracking",
}

ALL_MODULE_KEYS = (
    BASE_PLATFORM,
    STATS,
    MINUTES_LINEUPS,
    FILM_ROOM,
    SCOUTING,
    PLAYBOOK_RECOGNITION,
    STRATEGY,
    AI_ASSIST,
    ADVANCED_TRACKING,
)


def canonicalize_module_key(module_key):
    if module_key is None:
        return None
    normalized = str(module_key).strip().lower()
    if normalized == LEGACY_BASE_ALIAS:
        return BASE_PLATFORM
    return normalized
