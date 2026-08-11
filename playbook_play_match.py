"""Match film possession movement against FastDraw / sticky playbook vectors.

MVP approach (confidence-as-rank, not auto-accept):
  1. Build a fingerprint per playbook play from sticky choreography JSON
     (preferred) or play_steps positions + movement polylines.
  2. Build a fingerprint per possession from person detections in the
     possession time window (spatial tracks; tracker_id used when present).
  3. Score formation + path-displacement similarity (permutation-tolerant)
     and optional action-bag overlap; return ranked suggestions.

Limits (documented for coaches):
  - No reliable court homography: film coords are normalized relative to the
    possession's own player cloud, not absolute half-court SVG space.
  - YOLO tracker_id is unstable; tracks fall back to nearest-neighbor linking.
  - Sticky choreography is authoritative; without it, play_steps / empty library
    yields weak or empty suggestions.
  - Scores are relative ranks among the loaded library, not calibrated probabilities.
  - Does not write to the official ledger and does not auto-accept.
"""

from __future__ import annotations

import json
import math
import re
import time
from pathlib import Path
from typing import Any

from playbook_choreography import load_choreography
from playbook_vector_extract import COURT_H, COURT_W

MATCH_VERSION = 1
DEFAULT_TOP_K = 5
_SAFE_GAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


# ── Storage (JSON side file; no schema.sql) ───────────────────


def matches_dir(base: str | Path | None = None) -> Path:
    root = Path(base) if base else Path("data") / "play_matches"
    root.mkdir(parents=True, exist_ok=True)
    return root


def matches_path(game_id: str, base: str | Path | None = None) -> Path:
    safe = _SAFE_GAME_RE.sub("_", str(game_id or "unknown"))[:120] or "unknown"
    return matches_dir(base) / f"{safe}.json"


def load_match_results(game_id: str, base: str | Path | None = None) -> dict[str, Any] | None:
    path = matches_path(game_id, base)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or int(data.get("version") or 0) != MATCH_VERSION:
        return None
    return data


def save_match_results(
    game_id: str,
    payload: dict[str, Any],
    *,
    base: str | Path | None = None,
) -> dict[str, Any]:
    doc = {
        "version": MATCH_VERSION,
        "game_id": str(game_id),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": payload.get("method") or "formation_path_rank",
        "limits": payload.get("limits") or MVP_LIMITS,
        "library_size": int(payload.get("library_size") or 0),
        "possessions": payload.get("possessions") or [],
    }
    path = matches_path(game_id, base)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc


MVP_LIMITS = [
    "Film points are cloud-normalized (no court homography).",
    "Scores are ranks within the loaded playbook library, not probabilities.",
    "Sticky choreography preferred; missing sticky/steps weakens matches.",
    "Suggestions only — never auto-accepted into the ledger.",
]


# ── Geometry helpers ──────────────────────────────────────────


def _norm_court_xy(x: float, y: float) -> tuple[float, float]:
    return (float(x) / COURT_W, float(y) / COURT_H)


def _centroid(pts: list[tuple[float, float]]) -> tuple[float, float]:
    if not pts:
        return (0.0, 0.0)
    n = float(len(pts))
    return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)


def _cloud_normalize(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Centroid-subtract + scale by RMS radius so film and playbook share a frame."""
    if not pts:
        return []
    cx, cy = _centroid(pts)
    centered = [(p[0] - cx, p[1] - cy) for p in pts]
    rms = math.sqrt(sum(x * x + y * y for x, y in centered) / len(centered)) or 1.0
    return [(x / rms, y / rms) for x, y in centered]


def _angle_sorted(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return sorted(pts, key=lambda p: (math.atan2(p[1], p[0]), p[0], p[1]))


def _point_set_distance(
    a: list[tuple[float, float]],
    b: list[tuple[float, float]],
) -> float:
    """Greedy bipartite mean distance after trying circular shifts of angle-sorted sets."""
    if not a or not b:
        return 1.0
    aa = _angle_sorted(a)
    bb = _angle_sorted(b)
    n = min(len(aa), len(bb))
    if n == 0:
        return 1.0
    best = float("inf")
    # Try rotating the shorter circular order against the longer.
    for shift in range(len(bb)):
        total = 0.0
        for i in range(n):
            p = aa[i % len(aa)]
            q = bb[(i + shift) % len(bb)]
            total += math.hypot(p[0] - q[0], p[1] - q[1])
        best = min(best, total / n)
    # Size mismatch penalty
    size_pen = abs(len(aa) - len(bb)) * 0.15
    return best + size_pen


def _score_from_distance(dist: float, scale: float = 1.2) -> float:
    return max(0.0, min(1.0, 1.0 - dist / scale))


def _action_jaccard(a: dict[str, int], b: dict[str, int]) -> float:
    keys = set(a) | set(b)
    if not keys:
        return 0.5  # neutral when neither side has actions
    inter = sum(min(a.get(k, 0), b.get(k, 0)) for k in keys)
    union = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    if union <= 0:
        return 0.5
    return inter / union


# ── Fingerprints ──────────────────────────────────────────────


def fingerprint_from_choreography_steps(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """Build fingerprint from sticky / vector choreography steps."""
    if not steps:
        return empty_fingerprint()

    first = steps[0] if isinstance(steps[0], dict) else {}
    positions = first.get("positions") or {}
    pts: list[tuple[float, float]] = []
    for _oid, val in positions.items():
        if not isinstance(val, dict):
            continue
        try:
            pts.append(_norm_court_xy(float(val["x"]), float(val["y"])))
        except (KeyError, TypeError, ValueError):
            continue

    displacements: list[tuple[float, float]] = []
    actions: dict[str, int] = {"cut": 0, "pass": 0, "dribble": 0, "screen": 0}

    for step in steps:
        if not isinstance(step, dict):
            continue
        ink = step.get("ink") or {}
        if not isinstance(ink, dict):
            continue
        paths = ink.get("paths") or {}
        if isinstance(paths, dict):
            for _oid, poly in paths.items():
                if not isinstance(poly, list) or len(poly) < 2:
                    continue
                try:
                    x0, y0 = float(poly[0]["x"]), float(poly[0]["y"])
                    x1, y1 = float(poly[-1]["x"]), float(poly[-1]["y"])
                except (KeyError, TypeError, ValueError, IndexError):
                    continue
                s = _norm_court_xy(x0, y0)
                e = _norm_court_xy(x1, y1)
                displacements.append((e[0] - s[0], e[1] - s[1]))
        marks = ink.get("marks") or {}
        if isinstance(marks, dict):
            for kind in marks.values():
                k = str(kind or "").lower().strip()
                if k in actions:
                    actions[k] += 1
        passes = ink.get("passes") or []
        if isinstance(passes, list):
            actions["pass"] += len(passes)

    return {
        "formation": _cloud_normalize(pts),
        "displacements": _cloud_normalize(displacements) if displacements else [],
        "actions": actions,
        "n_players": len(pts),
        "source": "choreography",
    }


def fingerprint_from_play_steps_rows(rows: list[Any]) -> dict[str, Any]:
    """Fallback fingerprint from DB play_steps positions_json / movements_json."""
    if not rows:
        return empty_fingerprint()

    first = rows[0]
    try:
        positions = json.loads(first["positions_json"] or "{}")
    except (TypeError, json.JSONDecodeError, KeyError):
        positions = {}
    if not isinstance(positions, dict):
        positions = {}

    pts: list[tuple[float, float]] = []
    for key, val in positions.items():
        if not str(key).startswith("o"):
            continue
        if not isinstance(val, dict):
            continue
        try:
            pts.append(_norm_court_xy(float(val["x"]), float(val["y"])))
        except (KeyError, TypeError, ValueError):
            continue

    displacements: list[tuple[float, float]] = []
    actions: dict[str, int] = {"cut": 0, "pass": 0, "dribble": 0, "screen": 0}

    for row in rows:
        try:
            mov = json.loads(row["movements_json"] or "[]")
        except (TypeError, json.JSONDecodeError, KeyError):
            mov = []
        # movements_json may be list of {from,to,type,points} or ink-like dict
        if isinstance(mov, dict):
            paths = mov.get("paths") or {}
            if isinstance(paths, dict):
                for poly in paths.values():
                    if isinstance(poly, list) and len(poly) >= 2:
                        try:
                            s = _norm_court_xy(float(poly[0]["x"]), float(poly[0]["y"]))
                            e = _norm_court_xy(float(poly[-1]["x"]), float(poly[-1]["y"]))
                            displacements.append((e[0] - s[0], e[1] - s[1]))
                        except (KeyError, TypeError, ValueError, IndexError):
                            pass
            marks = mov.get("marks") or {}
            if isinstance(marks, dict):
                for kind in marks.values():
                    k = str(kind or "").lower().strip()
                    if k in actions:
                        actions[k] += 1
        elif isinstance(mov, list):
            for item in mov:
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("type") or item.get("mark") or "").lower()
                if kind in actions:
                    actions[kind] += 1
                pts_m = item.get("points") or item.get("path")
                if isinstance(pts_m, list) and len(pts_m) >= 2:
                    try:
                        s = _norm_court_xy(float(pts_m[0]["x"]), float(pts_m[0]["y"]))
                        e = _norm_court_xy(float(pts_m[-1]["x"]), float(pts_m[-1]["y"]))
                        displacements.append((e[0] - s[0], e[1] - s[1]))
                    except (KeyError, TypeError, ValueError, IndexError):
                        pass

    return {
        "formation": _cloud_normalize(pts),
        "displacements": _cloud_normalize(displacements) if displacements else [],
        "actions": actions,
        "n_players": len(pts),
        "source": "play_steps",
    }


def empty_fingerprint() -> dict[str, Any]:
    return {
        "formation": [],
        "displacements": [],
        "actions": {"cut": 0, "pass": 0, "dribble": 0, "screen": 0},
        "n_players": 0,
        "source": "empty",
    }


def fingerprint_from_tracks(
    tracks: list[list[tuple[float, float]]],
) -> dict[str, Any]:
    """Film fingerprint from player tracks (each track = list of (x,y) in frame pixels)."""
    start_pts: list[tuple[float, float]] = []
    displacements: list[tuple[float, float]] = []
    for track in tracks:
        if not track:
            continue
        start_pts.append(track[0])
        if len(track) >= 2:
            s, e = track[0], track[-1]
            displacements.append((e[0] - s[0], e[1] - s[1]))

    return {
        "formation": _cloud_normalize(start_pts),
        "displacements": _cloud_normalize(displacements) if displacements else [],
        "actions": {"cut": 0, "pass": 0, "dribble": 0, "screen": 0},
        "n_players": len(start_pts),
        "source": "film_tracks",
    }


def score_fingerprints(film_fp: dict[str, Any], book_fp: dict[str, Any]) -> dict[str, Any]:
    """Return component scores and combined score in [0, 1]."""
    if not film_fp.get("formation") or not book_fp.get("formation"):
        return {
            "score": 0.0,
            "formation": 0.0,
            "path": 0.0,
            "action": 0.0,
        }

    form_dist = _point_set_distance(film_fp["formation"], book_fp["formation"])
    form_score = _score_from_distance(form_dist, scale=1.4)

    if film_fp.get("displacements") and book_fp.get("displacements"):
        path_dist = _point_set_distance(film_fp["displacements"], book_fp["displacements"])
        path_score = _score_from_distance(path_dist, scale=1.6)
        path_w = 0.35
    else:
        path_score = 0.0
        path_w = 0.0

    action_score = _action_jaccard(film_fp.get("actions") or {}, book_fp.get("actions") or {})
    # Only weight actions when playbook has them
    book_actions = book_fp.get("actions") or {}
    has_actions = sum(book_actions.values()) > 0
    action_w = 0.15 if has_actions else 0.0

    form_w = 1.0 - path_w - action_w
    combined = form_w * form_score + path_w * path_score + action_w * action_score
    return {
        "score": round(combined, 4),
        "formation": round(form_score, 4),
        "path": round(path_score, 4),
        "action": round(action_score, 4),
    }


# ── Library loading ───────────────────────────────────────────


def load_play_library(
    db,
    *,
    choreography_base: str | Path | None = None,
    play_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Load named plays with fingerprints from sticky choreography or play_steps."""
    if play_ids:
        placeholders = ",".join("?" * len(play_ids))
        rows = db.execute(
            f"SELECT id, name, category FROM plays WHERE id IN ({placeholders}) ORDER BY name",
            tuple(int(p) for p in play_ids),
        ).fetchall()
    else:
        try:
            rows = db.execute(
                """SELECT id, name, category FROM plays
                   WHERE (parent_play_id IS NULL OR parent_play_id = 0)
                   ORDER BY name"""
            ).fetchall()
        except Exception:
            rows = db.execute(
                "SELECT id, name, category FROM plays ORDER BY name"
            ).fetchall()

    library: list[dict[str, Any]] = []
    for row in rows:
        play_id = int(row["id"])
        name = row["name"] or f"Play {play_id}"
        sticky = load_choreography(play_id, base=choreography_base)
        fp: dict[str, Any]
        source = "empty"
        if sticky and sticky.get("steps"):
            fp = fingerprint_from_choreography_steps(sticky["steps"])
            source = "sticky"
        else:
            steps = db.execute(
                """SELECT positions_json, movements_json FROM play_steps
                   WHERE play_id = ? ORDER BY step_number""",
                (play_id,),
            ).fetchall()
            fp = fingerprint_from_play_steps_rows(steps)
            source = fp.get("source") or "play_steps"
        if fp.get("n_players", 0) < 2:
            continue
        library.append(
            {
                "play_id": play_id,
                "play_name": name,
                "category": row["category"] if "category" in row.keys() else None,
                "fingerprint": fp,
                "source": source,
            }
        )
    return library


# ── Film tracks from detections ───────────────────────────────


def _detections_game_filter(game_id: str, relational_game_id: int | None):
    if relational_game_id is not None:
        return "relational_game_id = ?", (relational_game_id,)
    return "game_id = ?", (str(game_id),)


def build_tracks_for_window(
    db,
    game_id: str,
    start_ms: int,
    end_ms: int,
    *,
    relational_game_id: int | None = None,
    max_tracks: int = 5,
) -> list[list[tuple[float, float]]]:
    """Link person detections in [start_ms, end_ms] into up to 5 tracks."""
    filt_sql, filt_params = _detections_game_filter(game_id, relational_game_id)
    # Pad tiny windows so we always have some motion sample
    if end_ms <= start_ms:
        end_ms = start_ms + 8000
    rows = db.execute(
        f"""SELECT timestamp_ms, x_center, y_center, tracker_id
            FROM detections
            WHERE {filt_sql}
              AND object_class = 'person'
              AND timestamp_ms BETWEEN ? AND ?
            ORDER BY timestamp_ms ASC
            LIMIT 4000""",
        filt_params + (int(start_ms), int(end_ms)),
    ).fetchall()
    if not rows:
        return []

    by_tracker: dict[Any, list[tuple[float, float]]] = {}
    orphan_pts: list[tuple[int, float, float]] = []
    for r in rows:
        try:
            x = float(r["x_center"])
            y = float(r["y_center"])
            ts = int(r["timestamp_ms"])
        except (TypeError, ValueError, KeyError):
            continue
        tid = r["tracker_id"]
        if tid is not None:
            by_tracker.setdefault(tid, []).append((x, y))
        else:
            orphan_pts.append((ts, x, y))

    tracks = [pts for pts in by_tracker.values() if len(pts) >= 2]
    if len(tracks) < 3 and orphan_pts:
        # Nearest-neighbor link orphans when tracker_id is missing/sparse
        tracks.extend(_link_orphans(orphan_pts, max_tracks=max_tracks))

    # Prefer longer tracks; keep top max_tracks
    tracks.sort(key=len, reverse=True)
    return tracks[:max_tracks]


def _link_orphans(
    pts: list[tuple[int, float, float]],
    *,
    max_tracks: int = 5,
    max_dist: float = 120.0,
) -> list[list[tuple[float, float]]]:
    """Greedy NN linking of (ts,x,y) points into short tracks."""
    if not pts:
        return []
    # Sample by time buckets to keep cost down
    pts = sorted(pts, key=lambda p: p[0])
    active: list[dict[str, Any]] = []
    finished: list[list[tuple[float, float]]] = []
    for ts, x, y in pts:
        best_i = -1
        best_d = max_dist
        for i, tr in enumerate(active):
            if ts - tr["last_ts"] > 2500:
                continue
            lx, ly = tr["pts"][-1]
            d = math.hypot(x - lx, y - ly)
            if d < best_d:
                best_d = d
                best_i = i
        if best_i >= 0:
            active[best_i]["pts"].append((x, y))
            active[best_i]["last_ts"] = ts
        else:
            if len(active) >= max_tracks * 2:
                # retire shortest
                active.sort(key=lambda t: len(t["pts"]))
                finished.append(active.pop(0)["pts"])
            active.append({"pts": [(x, y)], "last_ts": ts})
    finished.extend(t["pts"] for t in active)
    return [t for t in finished if len(t) >= 2][:max_tracks]


# ── Possession windows ────────────────────────────────────────


def list_possession_windows(db, game_id: str, relational_game_id: int | None) -> list[dict[str, Any]]:
    """Prefer possessions table; fall back to consecutive possession_change events."""
    windows: list[dict[str, Any]] = []
    if relational_game_id is not None:
        rows = db.execute(
            """SELECT id, start_timestamp_ms, end_timestamp_ms, outcome
               FROM possessions
               WHERE game_id = ?
               ORDER BY start_timestamp_ms""",
            (relational_game_id,),
        ).fetchall()
        for r in rows:
            start = int(r["start_timestamp_ms"] or 0)
            end = r["end_timestamp_ms"]
            end_ms = int(end) if end is not None else start + 12000
            windows.append(
                {
                    "possession_id": int(r["id"]),
                    "start_ms": start,
                    "end_ms": end_ms,
                    "outcome": r["outcome"],
                    "source": "possessions",
                }
            )
    if windows:
        return windows

    # Fallback: event boundaries on analysis_key / game_id text
    events = db.execute(
        """SELECT id, timestamp_ms, event_type FROM events
           WHERE game_id = ?
             AND event_type IN ('possession_change', 'turnover', 'made_two', 'made_three',
                                'missed_two', 'missed_three', 'defensive_rebound', 'offensive_rebound')
           ORDER BY timestamp_ms""",
        (str(game_id),),
    ).fetchall()
    if len(events) < 2:
        # Last resort: single window spanning all detections
        filt_sql, filt_params = _detections_game_filter(game_id, relational_game_id)
        span = db.execute(
            f"""SELECT MIN(timestamp_ms) AS a, MAX(timestamp_ms) AS b
                FROM detections WHERE {filt_sql} AND object_class = 'person'""",
            filt_params,
        ).fetchone()
        if span and span["a"] is not None and span["b"] is not None and span["b"] > span["a"]:
            return [
                {
                    "possession_id": None,
                    "start_ms": int(span["a"]),
                    "end_ms": int(span["b"]),
                    "outcome": None,
                    "source": "detections_span",
                }
            ]
        return []

    # Slice into ~possession-length chunks from event timeline
    for i in range(len(events) - 1):
        start = int(events[i]["timestamp_ms"] or 0)
        end = int(events[i + 1]["timestamp_ms"] or start)
        if end - start < 1500:
            continue
        windows.append(
            {
                "possession_id": None,
                "start_ms": start,
                "end_ms": end,
                "outcome": None,
                "source": "event_boundaries",
                "start_event_id": int(events[i]["id"]),
            }
        )
    return windows[:80]


# ── Ranking ───────────────────────────────────────────────────


def rank_against_library(
    film_fp: dict[str, Any],
    library: list[dict[str, Any]],
    *,
    top_k: int = DEFAULT_TOP_K,
) -> list[dict[str, Any]]:
    scored: list[dict[str, Any]] = []
    for entry in library:
        components = score_fingerprints(film_fp, entry["fingerprint"])
        scored.append(
            {
                "play_id": entry["play_id"],
                "play_name": entry["play_name"],
                "library_source": entry.get("source"),
                "score": components["score"],
                "components": {
                    "formation": components["formation"],
                    "path": components["path"],
                    "action": components["action"],
                },
            }
        )
    scored.sort(key=lambda s: (-s["score"], s["play_name"]))
    out = []
    for i, item in enumerate(scored[: max(1, int(top_k))]):
        row = dict(item)
        row["rank"] = i + 1
        out.append(row)
    return out


def match_possessions_for_game(
    db,
    game_id: str,
    *,
    relational_game_id: int | None = None,
    choreography_base: str | Path | None = None,
    top_k: int = DEFAULT_TOP_K,
    play_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Compute ranked play suggestions for each possession window."""
    library = load_play_library(db, choreography_base=choreography_base, play_ids=play_ids)
    windows = list_possession_windows(db, game_id, relational_game_id)

    possessions_out: list[dict[str, Any]] = []
    for win in windows:
        tracks = build_tracks_for_window(
            db,
            game_id,
            win["start_ms"],
            win["end_ms"],
            relational_game_id=relational_game_id,
        )
        film_fp = fingerprint_from_tracks(tracks)
        suggestions = rank_against_library(film_fp, library, top_k=top_k) if library else []
        # Drop near-zero noise
        suggestions = [s for s in suggestions if s["score"] >= 0.15]
        for i, s in enumerate(suggestions):
            s["rank"] = i + 1
        possessions_out.append(
            {
                "possession_id": win.get("possession_id"),
                "start_ms": win["start_ms"],
                "end_ms": win["end_ms"],
                "outcome": win.get("outcome"),
                "window_source": win.get("source"),
                "track_count": len(tracks),
                "suggestions": suggestions,
                "top_play_name": suggestions[0]["play_name"] if suggestions else None,
                "top_rank_score": suggestions[0]["score"] if suggestions else None,
            }
        )

    return {
        "method": "formation_path_rank",
        "limits": list(MVP_LIMITS),
        "library_size": len(library),
        "possessions": possessions_out,
        "auto_accept": False,
    }
