"""NFHS counting rules locked with Scott 2026-09-15.

Pure functions. Callers supply detections / teams; these decide the stat.
"""

from __future__ import annotations

from typing import Any, Iterable

# ~1–2 dribbles after the catch, then a shot. Time, not frames (stride varies).
ASSIST_MAX_SCORER_HOLD_MS = 1600
ASSIST_MAX_PASS_GAP_FRAMES = 15

# Block: deflection as the ball leaves the shooter, before it is a make.
BLOCK_MAX_GAP_FRAMES = 5

# Steal: next possessor must be close to the ball (they took it).
STEAL_MAX_BALL_DISTANCE = 45


def credit_assist(
    *,
    shot_made: bool,
    shot_kind: str | None,
    passer_id: Any,
    scorer_id: Any,
    pass_gap_frames: int | None,
    scorer_hold_ms: int | None,
    max_scorer_hold_ms: int = ASSIST_MAX_SCORER_HOLD_MS,
    max_pass_gap_frames: int = ASSIST_MAX_PASS_GAP_FRAMES,
) -> bool:
    """Last pass that directly leads to a made field goal. No FT assists."""
    if not shot_made:
        return False
    if (shot_kind or "").lower() in {"ft", "free_throw", "free-throw"}:
        return False
    if passer_id is None or scorer_id is None or str(passer_id) == str(scorer_id):
        return False
    if pass_gap_frames is None or pass_gap_frames > max_pass_gap_frames:
        return False
    if scorer_hold_ms is None or scorer_hold_ms > max_scorer_hold_ms:
        return False
    return True


def classify_rebound(
    *,
    shooter_team: str | None,
    rebounder_team: str | None,
    shooter_id: Any = None,
    rebounder_id: Any = None,
    offense_ids: Iterable[Any] | None = None,
) -> str:
    """OREB if same team/color as shooter; DREB if different.

    Fallback without colors: shooter themselves, or anyone in this possession's
    touch-chain, is offensive. Everyone else is defensive until jersey color lands.
    """
    if shooter_team and rebounder_team:
        return "oreb" if shooter_team == rebounder_team else "dreb"
    if shooter_id is not None and rebounder_id is not None and str(shooter_id) == str(rebounder_id):
        return "oreb"
    if offense_ids is not None and rebounder_id is not None:
        known = {str(x) for x in offense_ids}
        return "oreb" if str(rebounder_id) in known else "dreb"
    return "rebound"


def credit_steal(
    *,
    after_shot: bool,
    dead_ball: bool,
    next_ball_distance: float | None,
    prev_lost_abruptly: bool,
    max_ball_distance: float = STEAL_MAX_BALL_DISTANCE,
) -> bool:
    """Steal = defender initiates the takeaway. Not a dead-ball whistle or a fumble pickup."""
    if after_shot or dead_ball or not prev_lost_abruptly:
        return False
    if next_ball_distance is None or next_ball_distance > max_ball_distance:
        return False
    return True


def classify_turnover_kind(*, dead_ball: bool, after_shot: bool) -> str | None:
    """Live vs dead TO. Do not name travel / charge / 5-second from vision."""
    if after_shot:
        return None
    return "dead" if dead_ball else "live"


def credit_block(
    *,
    shot_went_in: bool,
    defender_is_shooter: bool,
    gap_frames: int | None,
    ball_deflected_away: bool,
    defender_near_ball: bool,
    max_gap_frames: int = BLOCK_MAX_GAP_FRAMES,
) -> bool:
    """Deflection at the shooter as the ball goes up. Makes are FGs, not blocks. HS goaltending ignored."""
    if shot_went_in or defender_is_shooter:
        return False
    if gap_frames is None or gap_frames > max_gap_frames:
        return False
    return bool(ball_deflected_away and defender_near_ball)


def classify_shot_kind(
    *,
    ft_formation: str | None,
    in_paint: bool,
    dist_from_basket: float | None,
    three_pt_threshold: float = 0.50,
) -> str:
    """ft | 2 | 3. FT formation wins because the camera sits on the key."""
    if ft_formation in {"lane", "technical"}:
        return "ft"
    if dist_from_basket is not None and dist_from_basket > three_pt_threshold:
        return "3"
    if in_paint:
        return "2"
    return "2"


def scoring_event_type(shot_kind: str, made: bool) -> str:
    kind = (shot_kind or "2").lower()
    if kind == "ft":
        return "made_free_throw" if made else "missed_free_throw"
    if kind == "3":
        return "made_three" if made else "missed_three"
    return "made_two" if made else "missed_two"


def second_chance_make(*, previous_rebound_kind: str | None, same_team_still_offense: bool, made: bool) -> bool:
    if not made or not same_team_still_offense:
        return False
    return previous_rebound_kind == "oreb"


def points_off_turnover(*, previous_was_live_to: bool, scoring_team_is_defense_of_that_to: bool, made: bool) -> bool:
    return bool(made and previous_was_live_to and scoring_team_is_defense_of_that_to)


def points_for_kind(shot_kind: str, made: bool) -> int:
    if not made:
        return 0
    kind = (shot_kind or "2").lower()
    if kind == "ft":
        return 1
    if kind == "3":
        return 3
    return 2
