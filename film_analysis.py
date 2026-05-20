"""
Enhanced Film Analysis Module
=============================

Extends the basic event generator with:
1. Minutes played calculation (from per-frame player detections)
2. Shot type classification (2pt/3pt/FT based on court position)
3. Play recognition (pattern matching on player movement sequences)
4. Player effect (+/- while on court)

NOTE: YOLO tracker_ids are unstable at imgsz=320 (median 2-frame lifespan,
67K unique IDs for ~10 real players). All functions use spatial grid clustering
instead of tracker_id for player identity. Players are identified by spatial
grid cells (120x120px), producing ~10-15 stable "player slots".
"""

import json
import sqlite3
import math
from collections import defaultdict

import numpy as np


# ── Court Position Constants ─────────────────────────────────
FT_ZONE_Y = 0.85
THREEPT_ZONE_DIST = 0.35


def get_db(db_path):
    """Get database connection with row factory."""
    conn = sqlite3.connect(db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


# ── 1. Minutes Played ───────────────────────────────────────

def calculate_player_minutes(conn, game_id, fps=30.0):
    """
    Calculate minutes played per player from detection data.

    Uses player_cluster (from KMeans spatial clustering) instead of tracker_id,
    since YOLO tracker_ids are unstable at imgsz=320.
    """
    print(f"[Minutes] Calculating minutes played for game {game_id}")

    rows = conn.execute("""
        SELECT player_cluster as cluster_id,
               MIN(frame_number) as first_frame,
               MAX(frame_number) as last_frame,
               COUNT(DISTINCT frame_number) as total_frames
        FROM detections
        WHERE game_id = ? AND object_class = 'person' AND player_cluster >= 0
        GROUP BY player_cluster
        ORDER BY total_frames DESC
    """, (game_id,)).fetchall()

    results = []
    for i, row in enumerate(rows):
        first_frame = row["first_frame"]
        last_frame = row["last_frame"]
        total_frames = row["total_frames"]
        minutes = total_frames / fps / 60.0

        results.append({
            "game_id": game_id,
            "tracker_id": row["cluster_id"],
            "first_frame": first_frame,
            "last_frame": last_frame,
            "total_frames": total_frames,
            "minutes_played": round(minutes, 2),
        })

    conn.executemany("""
        INSERT OR REPLACE INTO player_minutes
            (game_id, tracker_id, first_frame, last_frame, total_frames, minutes_played, jersey_number, player_name)
        VALUES (:game_id, :tracker_id, :first_frame, :last_frame, :total_frames, :minutes_played, NULL, NULL)
    """, results)
    conn.commit()

    print(f"[Minutes] Calculated minutes for {len(results)} players")
    return results


# ── 2. Shot Type Classification ─────────────────────────────

def classify_shot_type(court_x, court_y, basket_x=0.5, basket_y=1.0):
    """
    Classify a shot as 2pt, 3pt, or ft based on normalized court position.

    NOTE: Coordinates are normalized to 0-1 based on video frame. The basket
    position is approximate. For junior high games, most shots are 2pt since
    the 3pt line is closer to the basket.
    """
    # Clamp to valid range
    court_x = max(0, min(court_x, 1.0))
    court_y = max(0, min(court_y, 1.0))

    dist = math.sqrt((court_x - basket_x) ** 2 + (court_y - basket_y) ** 2)

    # Free throw: near the free throw line, close to center
    if abs(court_y - FT_ZONE_Y) < 0.08 and abs(court_x - basket_x) < 0.15:
        return "ft", 0.85

    # Three point: far from basket (threshold accounts for noisy coordinates)
    if dist > 0.50:
        return "3pt", 0.70

    # Two point: close to basket
    return "2pt", 0.80


def classify_all_shots(conn, game_id, video_width=1920, video_height=1080):
    """
    Classify all shot events for a game.
    Uses a single batch query to find nearest person detection per shot event.
    """
    print(f"[Shots] Classifying shots for game {game_id}")

    # Single query: get all shot events with nearest person detection
    shot_events = conn.execute("""
        SELECT e.id as event_id, e.player, e.event_type,
               e.timestamp_ms, e.details_json,
               d.x_center, d.y_center
        FROM events e
        LEFT JOIN (
            SELECT d2.game_id, d2.timestamp_ms as det_ts,
                   d2.x_center, d2.y_center,
                   e2.id as eid,
                   ROW_NUMBER() OVER (
                       PARTITION BY e2.id ORDER BY ABS(d2.timestamp_ms - e2.timestamp_ms)
                   ) as rn
            FROM events e2
            JOIN detections d2 ON d2.game_id = e2.game_id
                AND d2.object_class = 'person'
                AND ABS(d2.timestamp_ms - e2.timestamp_ms) < 2000
            WHERE e2.game_id = ?
              AND e2.event_type IN ('shot', 'make', 'miss')
        ) d ON d.eid = e.id AND d.rn = 1
        WHERE e.game_id = ?
          AND e.event_type IN ('shot', 'make', 'miss')
    """, (game_id, game_id)).fetchall()

    if not shot_events:
        print("[Shots] No shot events found")
        return []

    results = []
    for event in shot_events:
        shot_result = "make" if event["event_type"] == "make" else "miss"

        court_x = None
        court_y = None
        if event["x_center"] is not None:
            cx = max(0, min(event["x_center"], video_width)) / float(video_width)
            cy = max(0, min(event["y_center"], video_height)) / float(video_height)
            court_x = cx
            court_y = cy
            shot_type, confidence = classify_shot_type(cx, cy)
        else:
            details = {}
            if event["details_json"]:
                try:
                    details = json.loads(event["details_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            shot_type = details.get("shot_type", "2pt")
            confidence = 0.3

        results.append({
            "event_id": event["event_id"],
            "game_id": game_id,
            "tracker_id": event["player"],
            "shot_type": shot_type,
            "shot_result": shot_result,
            "confidence": confidence,
            "court_x": court_x,
            "court_y": court_y,
            "timestamp_ms": event["timestamp_ms"],
        })

    for r in results:
        conn.execute("""
            INSERT OR REPLACE INTO shot_classifications
                (event_id, game_id, tracker_id, shot_type, shot_result, court_x, court_y, confidence, timestamp_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (r["event_id"], r["game_id"], r["tracker_id"], r["shot_type"],
              r["shot_result"], r["court_x"], r["court_y"],
              r["confidence"], r["timestamp_ms"]))
    conn.commit()

    print(f"[Shots] Classified {len(results)} shots")
    type_counts = defaultdict(lambda: {"made": 0, "missed": 0})
    for r in results:
        t = r["shot_type"]
        if r["shot_result"] == "make":
            type_counts[t]["made"] += 1
        else:
            type_counts[t]["missed"] += 1
    for t, c in sorted(type_counts.items()):
        total = c["made"] + c["missed"]
        pct = c["made"] / total * 100 if total > 0 else 0
        print(f"  {t}: {c['made']}/{total} ({pct:.0f}%)")

    return results


# ── 3. Play Recognition ─────────────────────────────────────

def recognize_plays(conn, game_id):
    """
    Recognize plays from player movement patterns.
    Uses SQL-based aggregation to avoid loading all detections into memory.
    """
    print(f"[Plays] Recognizing plays for game_id={game_id}")

    row = conn.execute("SELECT COUNT(*) FROM detections WHERE game_id = ?", (game_id,)).fetchone()
    if not row or row[0] < 100:
        print("[Plays] Not enough detections")
        return []

    plays = []
    pnr_plays = _detect_pick_and_roll(conn, game_id)
    plays.extend(pnr_plays)
    transition_plays = _detect_transitions(conn, game_id)
    plays.extend(transition_plays)
    iso_plays = _detect_isolation(conn, game_id)
    plays.extend(iso_plays)
    postup_plays = _detect_post_up(conn, game_id)
    plays.extend(postup_plays)

    for play in plays:
        conn.execute("""
            INSERT INTO play_recognitions
                (game_id, play_type, play_subtype, start_frame, end_frame,
                 start_timestamp_ms, end_timestamp_ms, primary_tracker_id,
                 secondary_tracker_id, confidence, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            game_id, play["play_type"], play.get("play_subtype"),
            play["start_frame"], play["end_frame"],
            play["start_timestamp_ms"], play.get("end_timestamp_ms"),
            play.get("primary_tracker_id"), play.get("secondary_tracker_id"),
            play["confidence"], json.dumps(play.get("details", {})),
        ))
    conn.commit()

    print(f"[Plays] Recognized {len(plays)} plays: PnR={len(pnr_plays)}, Trans={len(transition_plays)}, Iso={len(iso_plays)}, Post={len(postup_plays)}")
    return plays


def _detect_pick_and_roll(conn, game_id):
    """Detect pick and roll plays using SQL queries."""
    plays = []
    events = conn.execute("""
        SELECT id, player, timestamp_ms, source_frame
        FROM events
        WHERE game_id = ? AND event_type IN ('possession_change', 'turnover', 'assist')
        ORDER BY timestamp_ms
    """, (game_id,)).fetchall()

    last_detected_ts = -99999  # cooldown tracker

    for event in events:
        # Cooldown: don't detect PnR within 30 seconds of last detection
        if event["timestamp_ms"] - last_detected_ts < 30000:
            continue

        frame = event["source_frame"] or 0
        if frame == 0:
            ts = event["timestamp_ms"] or 0
            if ts > 0:
                frame = int(ts / 1000.0 * 3.75)
            else:
                continue

        window = conn.execute("""
            SELECT x_center, y_center
            FROM detections
            WHERE game_id = ? AND object_class = 'person'
              AND frame_number BETWEEN ? AND ?
        """, (game_id, max(0, frame - 30), frame + 30)).fetchall()

        if len(window) < 4:
            continue

        y_values = [r["y_center"] for r in window if r["y_center"] is not None]
        if not y_values:
            continue
        median_y = sorted(y_values)[len(y_values) // 2]
        top_players = [r for r in window if r["y_center"] and r["y_center"] < median_y]

        if len(top_players) >= 2:
            plays.append({
                "play_type": "pick_and_roll",
                "play_subtype": "pnr_ball_handler",
                "start_frame": max(0, frame - 15),
                "end_frame": frame + 15,
                "start_timestamp_ms": event["timestamp_ms"] - 5000,
                "end_timestamp_ms": event["timestamp_ms"] + 5000,
                "primary_tracker_id": event["player"],
                "confidence": 0.45,
                "details": {"trigger_frame": frame, "method": "heuristic_pnr"},
            })
            last_detected_ts = event["timestamp_ms"]

    return plays

def _detect_transitions(conn, game_id):
    """Detect transition/fast break plays using SQL."""
    plays = []
    ball_rows = conn.execute("""
        SELECT frame_number, x_center, y_center, timestamp_ms
        FROM detections
        WHERE game_id = ? AND object_class = 'ball'
        ORDER BY frame_number
    """, (game_id,)).fetchall()

    if len(ball_rows) < 10:
        return plays

    segments = []
    current_start = None
    current_start_ts = 0

    for i in range(1, len(ball_rows)):
        prev = ball_rows[i - 1]
        curr = ball_rows[i]
        frame_diff = curr["frame_number"] - prev["frame_number"]
        if frame_diff <= 0 or frame_diff > 30:
            if current_start is not None and curr["frame_number"] - current_start >= 15:
                segments.append((current_start, curr["frame_number"], current_start_ts, curr["timestamp_ms"]))
            current_start = None
            continue

        dy = abs(curr["y_center"] - prev["y_center"]) if curr["y_center"] and prev["y_center"] else 0
        velocity = dy / frame_diff  # pixels per frame

        # Fast break: ball moving very rapidly downcourt (>15 pixels/frame sustained)
        if velocity > 15.0:
            if current_start is None:
                current_start = prev["frame_number"]
                current_start_ts = prev["timestamp_ms"]
        else:
            if current_start is not None:
                end_frame = prev["frame_number"]
                if end_frame - current_start >= 15:
                    segments.append((current_start, end_frame, current_start_ts, prev["timestamp_ms"]))
                current_start = None

    if current_start is not None:
        last = ball_rows[-1]
        if last["frame_number"] - current_start >= 15:
            segments.append((current_start, last["frame_number"], current_start_ts, last["timestamp_ms"]))

    for start, end, start_ts, end_ts in segments:
        plays.append({
            "play_type": "transition",
            "play_subtype": "fast_break",
            "start_frame": start,
            "end_frame": end,
            "start_timestamp_ms": start_ts or 0,
            "end_timestamp_ms": end_ts or 0,
            "confidence": 0.40,
            "details": {"velocity_threshold": 5.0, "method": "ball_velocity"},
        })

    return plays


def _detect_isolation(conn, game_id):
    """Detect isolation plays using SQL."""
    plays = []
    ball_frames = conn.execute("""
        SELECT DISTINCT frame_number
        FROM detections
        WHERE game_id = ? AND object_class = 'ball'
        ORDER BY frame_number
    """, (game_id,)).fetchall()

    if not ball_frames:
        return plays

    sampled = [r["frame_number"] for i, r in enumerate(ball_frames) if i % 15 == 0]

    for frame in sampled:
        persons = conn.execute("""
            SELECT x_center, y_center
            FROM detections
            WHERE game_id = ? AND object_class = 'person' AND frame_number = ?
        """, (game_id, frame)).fetchall()

        if len(persons) < 4:
            continue

        x_vals = [p["x_center"] for p in persons if p["x_center"] is not None]
        y_vals = [p["y_center"] for p in persons if p["y_center"] is not None]
        if len(x_vals) < 4 or len(y_vals) < 4:
            continue

        # Normalize to 0-1 range for std dev calculation
        x_min, x_max = min(x_vals), max(x_vals)
        y_min, y_max = min(y_vals), max(y_vals)
        x_range = x_max - x_min if x_max > x_min else 1
        y_range = y_max - y_min if y_max > y_min else 1
        x_norm = [(x - x_min) / x_range for x in x_vals]
        y_norm = [(y - y_min) / y_range for y in y_vals]

        x_mean = sum(x_norm) / len(x_norm)
        y_mean = sum(y_norm) / len(y_norm)
        x_std = (sum((x - x_mean) ** 2 for x in x_norm) / len(x_norm)) ** 0.5
        y_std = (sum((y - y_mean) ** 2 for y in y_norm) / len(y_norm)) ** 0.5

        # Isolation: players spread out in both directions (high spread = isolation setup)
        # Using high thresholds since normalized std dev is typically 0.1-0.3 for normal play
        if x_std > 0.45 and y_std > 0.35:
            ball = conn.execute("""
                SELECT x_center, y_center, timestamp_ms
                FROM detections
                WHERE game_id = ? AND object_class = 'ball' AND frame_number = ?
                LIMIT 1
            """, (game_id, frame)).fetchone()

            if ball and ball["x_center"] is not None:
                plays.append({
                    "play_type": "isolation",
                    "play_subtype": "iso",
                    "start_frame": frame,
                    "end_frame": frame + 30,
                    "start_timestamp_ms": ball["timestamp_ms"] or 0,
                    "confidence": 0.35,
                    "details": {"x_spread": x_std, "y_spread": y_std, "method": "player_spread"},
                })

    return plays


def _detect_post_up(conn, game_id):
    """Detect post-up plays using SQL."""
    plays = []

    post_players = conn.execute("""
        SELECT player_cluster,
               MIN(frame_number) as min_frame,
               MAX(frame_number) as max_frame,
               COUNT(*) as frame_count,
               MIN(timestamp_ms) as min_ts
        FROM detections
        WHERE game_id = ? AND object_class = 'person'
          AND player_cluster >= 0
          AND y_center > (SELECT MAX(y_center) * 0.85 FROM detections WHERE game_id = ? AND object_class = 'person' AND y_center IS NOT NULL)
        GROUP BY player_cluster
        HAVING COUNT(*) >= 30
    """, (game_id, game_id)).fetchall()

    for pp in post_players:
        ball_nearby = conn.execute("""
            SELECT COUNT(*) as cnt
            FROM detections
            WHERE game_id = ? AND object_class = 'ball'
              AND frame_number BETWEEN ? AND ?
        """, (game_id, pp["min_frame"], pp["max_frame"])).fetchone()

        if ball_nearby and ball_nearby["cnt"] > 0:
            plays.append({
                "play_type": "post_up",
                "play_subtype": "low_post",
                "start_frame": pp["min_frame"],
                "end_frame": pp["max_frame"],
                "start_timestamp_ms": pp["min_ts"] or 0,
                "primary_tracker_id": pp["player_cluster"],
                "confidence": 0.30,
                "details": {"frames_in_post": pp["frame_count"], "method": "proximity_to_basket"},
            })

    return plays


# ── 4. Player Effect (+/-) ──────────────────────────────────

def calculate_player_effect(conn, game_id, fps=30.0):
    """
    Calculate player effect metrics: +/-, possessions, ratings.
    Uses events to track score changes while each player is on court.
    """
    print(f"[Effect] Calculating player effect for game {game_id}")

    minutes = conn.execute("""
        SELECT * FROM player_minutes WHERE game_id = ?
    """, (game_id,)).fetchall()

    if not minutes:
        print("[Effect] No player minutes data — run calculate_player_minutes first")
        return []

    # Get score events (only 'make' events)
    make_events = conn.execute("""
        SELECT timestamp_ms, source_frame, player, details_json
        FROM events WHERE game_id = ? AND event_type = 'make'
        ORDER BY timestamp_ms
    """, (game_id,)).fetchall()

    score_events = []
    for event in make_events:
        points = 2
        details = {}
        if event["details_json"]:
            try:
                details = json.loads(event["details_json"])
            except (json.JSONDecodeError, TypeError):
                pass
        shot_type = details.get("shot_type", "2pt")
        if shot_type == "3pt":
            points = 3
        elif shot_type == "ft":
            points = 1

        score_events.append({
            "timestamp_ms": event["timestamp_ms"],
            "frame": event["source_frame"] or 0,
            "points": points,
            "player": event["player"],
        })

    if not score_events:
        print("[Effect] No score events found")
        return []

    results = []
    for pm in minutes:
        tracker_id = pm["tracker_id"]
        first_frame = pm["first_frame"] or 0
        last_frame = pm["last_frame"] or 0
        if first_frame == 0 and last_frame == 0:
            continue

        points_for = 0
        points_against = 0

        for se in score_events:
            se_frame = se["frame"]
            se_ts = se["timestamp_ms"]
            if se_frame > 0 and first_frame <= se_frame <= last_frame:
                points_for += se["points"]
            elif se_frame > 0:
                points_against += se["points"]
            elif se_ts > 0:
                player_start_ms = (first_frame / fps) * 1000
                player_end_ms = (last_frame / fps) * 1000
                if player_start_ms <= se_ts <= player_end_ms:
                    points_for += se["points"]
                else:
                    points_against += se["points"]

        frame_diff = max(1, last_frame - first_frame)
        possessions = max(1, frame_diff / (fps * 24))
        plus_minus = points_for - points_against
        ortg = (points_for / possessions) * 100 if possessions > 0 else 0
        drtg = (points_against / possessions) * 100 if possessions > 0 else 0

        results.append({
            "game_id": game_id,
            "tracker_id": tracker_id,
            "plus_minus": plus_minus,
            "possessions_on": int(possessions),
            "possessions_off": 0,
            "points_for": points_for,
            "points_against": points_against,
            "ortg": round(ortg, 1),
            "drtg": round(drtg, 1),
            "net_rating": round(ortg - drtg, 1),
        })

    for r in results:
        conn.execute("""
            INSERT OR REPLACE INTO player_effect
                (game_id, tracker_id, plus_minus, possessions_on, possessions_off,
                 points_for, points_against, ortg, drtg, net_rating)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (r["game_id"], r["tracker_id"], r["plus_minus"], r["possessions_on"],
              r["possessions_off"], r["points_for"], r["points_against"],
              r["ortg"], r["drtg"], r["net_rating"]))
    conn.commit()

    print(f"[Effect] Calculated effect for {len(results)} players")
    return results


# ── 5. Master Analysis Pipeline ─────────────────────────────

def run_enhanced_analysis(db_path, game_id, fps=30.0, video_width=None, video_height=None):
    """
    Run the full enhanced analysis pipeline for a game.
    """
    print(f"\n{'='*60}")
    print(f"Enhanced Film Analysis for game: {game_id}")
    print(f"{'='*60}\n")

    conn = get_db(db_path)

    try:
        if video_width is None or video_height is None:
            video_width, video_height = 1920, 1080

        minutes = calculate_player_minutes(conn, game_id, fps)
        shots = classify_all_shots(conn, game_id, video_width, video_height)
        plays = recognize_plays(conn, game_id)
        effects = calculate_player_effect(conn, game_id, fps)

        print(f"\n{'='*60}")
        print(f"Enhanced analysis complete for {game_id}")
        print(f"  Minutes: {len(minutes)} players")
        print(f"  Shots: {len(shots)} classified")
        print(f"  Plays: {len(plays)} recognized")
        print(f"  Effects: {len(effects)} players")
        print(f"{'='*60}\n")

        return {
            "minutes": minutes,
            "shots": shots,
            "plays": plays,
            "effects": effects,
        }
    finally:
        conn.close()
