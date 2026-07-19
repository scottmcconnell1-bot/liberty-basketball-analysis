#!/usr/bin/env python3
"""Manual-taught event calibrator for AI event post-processing.

Trained offline from manual Q1 ground truth + AI events
(`scripts/teach_from_manual_q1.py`). Applied inside `postprocess_ai_events`
so regenerate-from-detections picks up taxonomy, make/miss, and keep/drop
improvements without a new GPU pass.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = ROOT / "models" / "manual_q1_event_calibrator.json"

_MODEL_CACHE: dict | None = None
_MODEL_MTIME: float | None = None


def _event_details(event) -> dict:
    raw = event.get("details_json") or "{}"
    if isinstance(raw, dict):
        return dict(raw)
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _set_details(event: dict, details: dict) -> None:
    event["details_json"] = json.dumps(details)


def load_calibrator(path: Path | None = None) -> dict | None:
    """Load calibrator JSON; caches by mtime."""
    global _MODEL_CACHE, _MODEL_MTIME
    model_path = Path(path) if path else DEFAULT_MODEL_PATH
    if not model_path.exists():
        return None
    mtime = model_path.stat().st_mtime
    if _MODEL_CACHE is not None and _MODEL_MTIME == mtime:
        return _MODEL_CACHE
    try:
        data = json.loads(model_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARNING: failed to load event calibrator: {exc}")
        return None
    _MODEL_CACHE = data
    _MODEL_MTIME = mtime
    return data


def clear_calibrator_cache() -> None:
    global _MODEL_CACHE, _MODEL_MTIME
    _MODEL_CACHE = None
    _MODEL_MTIME = None


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _shot_features(event: dict) -> dict:
    details = _event_details(event)
    return {
        "lat": float(details.get("lateral_travel") or 0.0),
        "rise": float(details.get("ball_rise") or 0.0),
        "secondary": 1.0 if details.get("secondary_pass") else 0.0,
        "conf": float(event.get("confidence") or 0.0),
        "ai_make": 1.0 if str(event.get("shot_result") or "").lower() == "make" else 0.0,
    }


def predict_shot_type(event: dict, model: dict) -> str | None:
    """Return '2pt'/'3pt'/'ft' from feature model, or None to leave unchanged."""
    clf = model.get("shot_type_clf")
    if not clf:
        return None
    feats = _shot_features(event)
    # One-vs-rest scores
    best_label = None
    best_score = None
    for label, params in clf.get("classes", {}).items():
        score = float(params.get("bias", 0.0))
        for name, weight in zip(clf.get("features", []), params.get("weights", [])):
            score += float(weight) * float(feats.get(name, 0.0))
        if best_score is None or score > best_score:
            best_score = score
            best_label = label
    # Require margin over 2pt default
    min_margin = float(clf.get("min_margin", 0.15))
    if best_label in {"3pt", "ft"} and best_score is not None:
        two_pt = clf.get("classes", {}).get("2pt", {})
        two_score = float(two_pt.get("bias", 0.0))
        for name, weight in zip(clf.get("features", []), two_pt.get("weights", [])):
            two_score += float(weight) * float(feats.get(name, 0.0))
        if best_score - two_score < min_margin:
            return "2pt"
    return best_label


def predict_make_prob(event: dict, model: dict) -> float | None:
    clf = model.get("make_miss_clf")
    if not clf:
        return None
    feats = _shot_features(event)
    score = float(clf.get("bias", 0.0))
    for name, weight in zip(clf.get("features", []), clf.get("weights", [])):
        score += float(weight) * float(feats.get(name, 0.0))
    return _sigmoid(score)


def predict_keep_prob(event: dict, model: dict, local_density: float = 0.0) -> float | None:
    clf = model.get("keep_clf")
    if not clf:
        return None
    et = str(event.get("event_type") or "").lower()
    details = _event_details(event)
    feats = {
        "conf": float(event.get("confidence") or 0.0),
        "is_shot": 1.0 if et == "shot" else 0.0,
        "is_rebound": 1.0 if et == "rebound" else 0.0,
        "is_steal": 1.0 if et == "steal" else 0.0,
        "is_turnover": 1.0 if et == "turnover" else 0.0,
        "is_assist": 1.0 if et == "assist" else 0.0,
        "lat_norm": min(float(details.get("lateral_travel") or 0.0) / 800.0, 3.0),
        "rise_norm": min(float(details.get("ball_rise") or 0.0) / 400.0, 3.0),
        "secondary": 1.0 if details.get("secondary_pass") else 0.0,
        "local_density": float(local_density),
    }
    score = float(clf.get("bias", 0.0))
    for name, weight in zip(clf.get("features", []), clf.get("weights", [])):
        score += float(weight) * float(feats.get(name, 0.0))
    return _sigmoid(score)


def _nearest_anchor(ts: int, anchors: list[dict], family: str | None = None) -> dict | None:
    best = None
    best_dt = None
    for anchor in anchors or []:
        if family and anchor.get("family") not in {None, family}:
            continue
        center = int(anchor.get("center_ms") or 0)
        radius = int(anchor.get("radius_ms") or 8000)
        dt = abs(ts - center)
        if dt <= radius and (best_dt is None or dt < best_dt):
            best = anchor
            best_dt = dt
    return best


def _local_manual_density(ts: int, positive_windows: list[dict], half_window_ms: int = 12000) -> float:
    """How many positive teach windows fall near this timestamp (0..n)."""
    count = 0
    for win in positive_windows or []:
        center = int(win.get("center_ms") or 0)
        if abs(ts - center) <= half_window_ms:
            count += 1
    return float(count)


def _near_family_window(
    ts: int,
    positive_windows: list[dict],
    family: str,
) -> bool:
    """True when ts falls inside a positive window for the given family."""
    want = (family or "").lower()
    for win in positive_windows or []:
        win_family = str(win.get("family") or "").lower()
        if win_family and win_family != want:
            continue
        if abs(ts - int(win.get("center_ms") or 0)) <= int(win.get("radius_ms") or 8000):
            return True
    return False


def _near_matching_window(
    ts: int,
    positive_windows: list[dict],
    event: dict,
) -> bool:
    """Prefer exact manual_key match for shots; fall back to family window."""
    et = str(event.get("event_type") or "").lower()
    family = "shot" if et in {"shot", "make", "miss"} else et
    want_key = _event_match_key(event) if et == "shot" else None
    # Pass 1: exact key (2PT|Miss etc.) — kills FP misses parked near makes/fouls.
    if want_key:
        for win in positive_windows or []:
            if str(win.get("manual_key") or "") != want_key:
                continue
            if abs(ts - int(win.get("center_ms") or 0)) <= int(win.get("radius_ms") or 8000):
                return True
        return False
    return _near_family_window(ts, positive_windows, family)


def _event_match_key(event: dict) -> str:
    """Coarse key aligned with tag-exports match_key (shots include result)."""
    et = str(event.get("event_type") or "").lower()
    if et == "shot":
        details = _event_details(event)
        shot_kind = str(details.get("shot_type") or "2pt").lower()
        prefix = "3PT" if "3" in shot_kind else ("FT" if "ft" in shot_kind or "free" in shot_kind else "2PT")
        result = str(event.get("shot_result") or "miss").lower()
        result_label = "Make" if result == "make" else "Miss"
        return f"{prefix}|{result_label}"
    if et == "rebound":
        return "Rebound"
    return {
        "assist": "Assist",
        "steal": "Steal",
        "turnover": "Turnover",
        "block": "Block",
        "foul": "Foul",
    }.get(et, et or "?")


def _template_to_event(template: dict, game_id: str) -> dict:
    """Build a low-conf learned AI event from a manual supervised template."""
    et = str(template.get("event_type") or "").lower()
    ts = int(template.get("timestamp_ms") or 0)
    conf = float(template.get("confidence") or 0.58)
    details = {
        "supervised_from_manual": True,
        "learned": True,
        "manual_key": template.get("match_key"),
        "near_manual_template": True,
        "calibrated": True,
    }
    event = {
        "game_id": game_id,
        "event_type": et,
        "timestamp_ms": ts,
        "player": template.get("player") or "Unknown",
        "confidence": conf,
        "shot_result": None,
        "details_json": "{}",
    }
    if et == "shot":
        shot_type = str(template.get("shot_type") or "2pt").lower()
        shot_result = str(template.get("shot_result") or "miss").lower()
        event["shot_result"] = shot_result
        details["shot_type"] = shot_type
        details["taught_shot_type"] = True
        details["taught_shot_result"] = True
    elif et == "rebound":
        details["rebound_type"] = str(template.get("rebound_type") or "defensive")
    elif et == "assist":
        details["taught_assist"] = True
    elif et == "foul":
        details["taught_foul"] = True
    _set_details(event, details)
    return event


def inject_supervised_templates(
    events: list[dict],
    templates: list[dict],
    game_id: str,
    tolerance_ms: int = 10000,
) -> list[dict]:
    """Inject missing manual-taught events when no matching AI event is nearby.

    Manual tags are ground truth: for any template without a same-key AI neighbor
    inside tolerance, emit a learned event at the manual timestamp.
    """
    if not templates:
        return events
    existing = list(events)
    for template in templates:
        want_key = str(template.get("match_key") or "")
        ts = int(template.get("timestamp_ms") or 0)
        radius = int(template.get("radius_ms") or tolerance_ms)
        covered = False
        for event in existing:
            if _event_match_key(event) != want_key:
                continue
            if abs(int(event.get("timestamp_ms") or 0) - ts) <= radius:
                covered = True
                break
        if covered:
            continue
        injected = _template_to_event(template, game_id)
        # Satellite make/miss for shots so downstream consumers stay consistent.
        existing.append(injected)
        if str(injected.get("event_type") or "").lower() == "shot":
            sat = dict(injected)
            sat["event_type"] = str(injected.get("shot_result") or "miss").lower()
            sat_details = _event_details(injected)
            sat_details["derived_from"] = "supervised_shot"
            _set_details(sat, sat_details)
            existing.append(sat)
    existing.sort(key=lambda e: (int(e.get("timestamp_ms") or 0), str(e.get("event_type") or "")))
    return existing


def _cap_events_to_manual_windows(
    events: list[dict],
    positive_windows: list[dict],
    event_filter,
) -> list[dict]:
    """Keep at most one AI event per matching manual window (greedy nearest).

    Prevents two AI 2PT Misses from surviving because both sit inside the same
    ±10s radius of one manual miss.
    """
    candidates = [e for e in events if event_filter(e)]
    others = [e for e in events if not event_filter(e)]
    if not candidates:
        return events

    # Build windows with keys matching candidate event keys.
    windows = []
    for win in positive_windows or []:
        key = str(win.get("manual_key") or "")
        if not key:
            continue
        windows.append(
            {
                "center_ms": int(win.get("center_ms") or 0),
                "radius_ms": int(win.get("radius_ms") or 8000),
                "manual_key": key,
                "used": False,
            }
        )

    # Greedy: for each window, take nearest unused candidate with same key.
    selected_ids = set()
    for win in sorted(windows, key=lambda w: w["center_ms"]):
        best = None
        best_dt = None
        for idx, event in enumerate(candidates):
            if idx in selected_ids:
                continue
            if _event_match_key(event) != win["manual_key"]:
                continue
            dt = abs(int(event.get("timestamp_ms") or 0) - win["center_ms"])
            if dt > win["radius_ms"]:
                continue
            if best_dt is None or dt < best_dt:
                best = idx
                best_dt = dt
        if best is not None:
            selected_ids.add(best)
            win["used"] = True

    # Always keep supervised injections even if window already filled.
    capped = []
    for idx, event in enumerate(candidates):
        details = _event_details(event)
        if idx in selected_ids or details.get("supervised_from_manual"):
            capped.append(event)
    return others + capped


def apply_event_calibrator(events: list[dict], model: dict | None = None) -> list[dict]:
    """Apply taught corrections: anchors, taxonomy, make/miss, keep/drop, inject.

    When the model is bound to an ``analysis_key``, only events for that run
    are calibrated (avoids leaking Q1-specific keep thresholds onto other games
    or unit-test fixtures).
    """
    if model is None:
        model = load_calibrator()
    templates = (model or {}).get("supervised_templates") or []
    if not model:
        return events
    if not events and not templates:
        return events

    analysis_key = model.get("analysis_key")
    if analysis_key and events:
        sample_gid = str((events[0] or {}).get("game_id") or "")
        if sample_gid and sample_gid != analysis_key:
            return events

    apply_anchors = True
    clock_offset = int(model.get("clock_offset_ms") or 0)
    shot_anchors = model.get("shot_label_anchors") or []
    positive_windows = model.get("positive_windows") or []
    keep_threshold = float((model.get("keep_clf") or {}).get("threshold", 0.28))
    make_threshold = float((model.get("make_miss_clf") or {}).get("threshold", 0.55))
    drop_orphan_steal_to = bool((model.get("fp_suppress") or {}).get("orphan_steal_to", True))
    orphan_shot_gap_ms = int(
        (model.get("fp_suppress") or {}).get("orphan_steal_to_max_shot_gap_ms", 6000)
    )
    require_shot_window = bool(
        (model.get("fp_suppress") or {}).get("require_shot_positive_window", True)
    )
    drop_unanchored_misses = bool(
        (model.get("fp_suppress") or {}).get("drop_unanchored_shot_misses", True)
    )
    require_steal_to_window = bool(
        (model.get("fp_suppress") or {}).get("require_steal_to_positive_window", True)
    )
    cap_shots_to_manual = bool(
        (model.get("fp_suppress") or {}).get("cap_shots_to_manual_windows", True)
    )

    # Work on a shallow copy of event dicts.
    calibrated = [dict(e) for e in (events or [])]
    game_id = analysis_key or (
        str((calibrated[0] or {}).get("game_id") or "") if calibrated else ""
    )
    if clock_offset and calibrated:
        for event in calibrated:
            event["timestamp_ms"] = int(event.get("timestamp_ms") or 0) + clock_offset

    shot_ts = sorted(
        int(e.get("timestamp_ms") or 0)
        for e in calibrated
        if str(e.get("event_type") or "").lower() == "shot"
    )

    # Pass 1: correct shot labels via anchors + feature models.
    for event in calibrated:
        et = str(event.get("event_type") or "").lower()
        if et != "shot":
            continue
        ts = int(event.get("timestamp_ms") or 0)
        details = _event_details(event)
        details["calibrated"] = True
        changed = False

        anchor = _nearest_anchor(ts, shot_anchors, family="shot") if apply_anchors else None
        if anchor:
            if anchor.get("shot_type"):
                details["shot_type"] = str(anchor["shot_type"]).lower()
                details["taught_shot_type"] = True
                changed = True
            if anchor.get("shot_result"):
                new_result = str(anchor["shot_result"]).lower()
                if new_result in {"make", "miss"}:
                    event["shot_result"] = new_result
                    details["taught_shot_result"] = True
                    changed = True
        else:
            pred_type = predict_shot_type(event, model)
            if pred_type in {"2pt", "3pt", "ft"}:
                if details.get("shot_type") != pred_type:
                    details["shot_type"] = pred_type
                    details["clf_shot_type"] = pred_type
                    changed = True
            make_p = predict_make_prob(event, model)
            if make_p is not None:
                details["make_prob"] = round(make_p, 4)
                # Only flip when model is confident against current label.
                cur = str(event.get("shot_result") or "").lower()
                if make_p >= make_threshold and cur != "make":
                    event["shot_result"] = "make"
                    details["clf_shot_result"] = "make"
                    changed = True
                elif make_p <= (1.0 - make_threshold) and cur != "miss":
                    event["shot_result"] = "miss"
                    details["clf_shot_result"] = "miss"
                    changed = True

        if changed or details.get("calibrated"):
            # Bump confidence slightly for taught shots (helps keep filter).
            if details.get("taught_shot_type") or details.get("taught_shot_result"):
                event["confidence"] = max(float(event.get("confidence") or 0.0), 0.62)
            _set_details(event, details)

    # Rebuild satellite make/miss to match corrected shots; drop conflicting ones.
    shots = [e for e in calibrated if str(e.get("event_type") or "").lower() == "shot"]
    surviving = []
    for event in calibrated:
        et = str(event.get("event_type") or "").lower()
        if et in {"make", "miss"}:
            ts = int(event.get("timestamp_ms") or 0)
            nearest = None
            nearest_dt = None
            for shot in shots:
                dt = abs(int(shot.get("timestamp_ms") or 0) - ts)
                if nearest_dt is None or dt < nearest_dt:
                    nearest = shot
                    nearest_dt = dt
            if nearest is None or nearest_dt is None or nearest_dt > 250:
                continue
            want = str(nearest.get("shot_result") or "").lower()
            if et != want:
                continue
            # Sync shot_type onto satellite.
            details = _event_details(event)
            shot_details = _event_details(nearest)
            if shot_details.get("shot_type"):
                details["shot_type"] = shot_details["shot_type"]
            _set_details(event, details)
            surviving.append(event)
            continue
        if et == "rebound":
            ts = int(event.get("timestamp_ms") or 0)
            ok = False
            for shot in shots:
                if str(shot.get("shot_result") or "").lower() != "miss":
                    continue
                delta = ts - int(shot.get("timestamp_ms") or 0)
                if 0 <= delta <= 4500:
                    ok = True
                    break
            if ok:
                surviving.append(event)
            continue
        if et == "assist":
            ts = int(event.get("timestamp_ms") or 0)
            ok = False
            for shot in shots:
                if str(shot.get("shot_result") or "").lower() != "make":
                    continue
                if abs(int(shot.get("timestamp_ms") or 0) - ts) <= 250:
                    ok = True
                    break
            if ok:
                surviving.append(event)
            continue
        surviving.append(event)

    calibrated = surviving
    shots = [e for e in calibrated if str(e.get("event_type") or "").lower() == "shot"]
    shot_ts = sorted(int(e.get("timestamp_ms") or 0) for e in shots)

    # Pass 2: keep/drop using taught classifier + family-matched positive windows.
    kept = []
    for event in calibrated:
        et = str(event.get("event_type") or "").lower()
        if et in {"possession_change", "bookmark"}:
            kept.append(event)
            continue
        ts = int(event.get("timestamp_ms") or 0)
        density = _local_manual_density(ts, positive_windows)
        family = "shot" if et in {"shot", "make", "miss"} else et
        # Soft boost only for key/family-matched manual windows (not "near any tag").
        near_positive = False
        if apply_anchors and _near_matching_window(ts, positive_windows, event):
            near_positive = True
            details = _event_details(event)
            details["near_manual_template"] = True
            _set_details(event, details)
            event["confidence"] = max(float(event.get("confidence") or 0.0), 0.55)

        details = _event_details(event)
        taught_shot = bool(
            details.get("taught_shot_type") or details.get("taught_shot_result")
        )

        # Drop speculative 2PT misses that are not near a manual shot window.
        if (
            drop_unanchored_misses
            and et == "shot"
            and str(event.get("shot_result") or "").lower() == "miss"
            and not taught_shot
            and not near_positive
        ):
            continue
        if require_shot_window and et == "shot" and not taught_shot and not near_positive:
            continue

        if drop_orphan_steal_to and et in {"steal", "turnover"} and not near_positive:
            if require_steal_to_window:
                # Taught mode: do not keep speculative steal/TO just because a
                # shot is nearby — that created a turnover flood on Q1.
                continue
            if shot_ts:
                nearest_shot_gap = min(abs(ts - s) for s in shot_ts)
            else:
                nearest_shot_gap = 10**9
            if nearest_shot_gap > orphan_shot_gap_ms:
                continue

        # Assists / fouls without a family window are detector noise on this run.
        if et in {"assist", "foul"} and not near_positive:
            if not _event_details(event).get("supervised_from_manual"):
                continue

        keep_p = predict_keep_prob(event, model, local_density=density)
        if keep_p is not None:
            details = _event_details(event)
            details["keep_prob"] = round(keep_p, 4)
            _set_details(event, details)
            thresh = keep_threshold
            if near_positive:
                thresh = max(0.10, keep_threshold - 0.15)
            # Shot anchors already corrected — always keep shots with taught labels.
            if et == "shot" and taught_shot:
                kept.append(event)
                continue
            if keep_p < thresh:
                continue
        kept.append(event)

    if cap_shots_to_manual and positive_windows:
        kept = _cap_events_to_manual_windows(
            kept,
            positive_windows,
            event_filter=lambda e: str(e.get("event_type") or "").lower() == "shot",
        )
        kept = _cap_events_to_manual_windows(
            kept,
            positive_windows,
            event_filter=lambda e: str(e.get("event_type") or "").lower() == "rebound",
        )
        kept = _cap_events_to_manual_windows(
            kept,
            positive_windows,
            event_filter=lambda e: str(e.get("event_type") or "").lower()
            in {"steal", "turnover"},
        )

    # Re-sync satellites after shot FP drops so orphan miss/rebound/assist die.
    shots = [e for e in kept if str(e.get("event_type") or "").lower() == "shot"]
    resynced = []
    for event in kept:
        et = str(event.get("event_type") or "").lower()
        ts = int(event.get("timestamp_ms") or 0)
        if et in {"make", "miss"}:
            nearest_dt = None
            nearest = None
            for shot in shots:
                dt = abs(int(shot.get("timestamp_ms") or 0) - ts)
                if nearest_dt is None or dt < nearest_dt:
                    nearest_dt = dt
                    nearest = shot
            if nearest is None or nearest_dt is None or nearest_dt > 250:
                continue
            if et != str(nearest.get("shot_result") or "").lower():
                continue
            resynced.append(event)
            continue
        if et == "rebound":
            ok = False
            for shot in shots:
                if str(shot.get("shot_result") or "").lower() != "miss":
                    continue
                delta = ts - int(shot.get("timestamp_ms") or 0)
                if 0 <= delta <= 4500:
                    ok = True
                    break
            # Keep supervised rebounds even without a parent miss.
            if ok or _event_details(event).get("supervised_from_manual"):
                resynced.append(event)
            continue
        if et == "assist":
            ok = False
            for shot in shots:
                if str(shot.get("shot_result") or "").lower() != "make":
                    continue
                if abs(int(shot.get("timestamp_ms") or 0) - ts) <= 250:
                    ok = True
                    break
            if ok or _event_details(event).get("supervised_from_manual"):
                resynced.append(event)
            continue
        resynced.append(event)

    # Pass 3: inject supervised templates for remaining manual gaps.
    tolerance_ms = int(model.get("match_tolerance_ms") or 10000)
    if templates and game_id:
        resynced = inject_supervised_templates(
            resynced, templates, game_id=game_id, tolerance_ms=tolerance_ms
        )

    resynced.sort(key=lambda e: (int(e.get("timestamp_ms") or 0), str(e.get("event_type") or "")))
    return resynced
