"""
Enhanced Film Analysis Module
=============================

Extends the basic event generator with:
1. Minutes played calculation (from per-frame player detections)
2. Shot type classification (2pt/3pt/FT based on court position)
3. Play recognition (pattern matching on player movement sequences)
4. Player effect (+/- while on court)
5. Scouting tendencies aggregation (across games)
6. Human corrections tracking (feedback loop for learning)

All functions write results to the enhanced analysis tables.
"""

import json
import sqlite3
import math
from collections import defaultdict

import pandas as pd
import numpy as np
from scipy.spatial import distance


# ── Court Position Constants ─────────────────────────────────
# Standard NBA/NCAA court dimensions (in feet)
FT_LINE = 19.0  # free throw line from baseline
THREE_POINT_RADIUS = 22.0 + 4.0  # ~22ft from rim (corner: 22ft, top: ~23.9ft)
COURT_WIDTH = 50.0
COURT_LENGTH = 94.0

# Normalized court zones (x: 0=baseline-left, 1=baseline-right; y: 0=defensive, 1=offensive)
# These are used when we don't have calibrated court coordinates
# Shot type thresholds (normalized distance from basket)
FT_ZONE_Y = 0.85  # free throw line ~85% of court length from defensive baseline
THREEPT_ZONE_DIST = 0.35  # normalized distance threshold for 3pt


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

    For each tracked player (tracker_id), find their first and last frame
    of appearance, then calculate minutes based on fps.
    """
    print(f"[Minutes] Calculating minutes played for game {game_id}")

    query = """
        SELECT tracker_id, MIN(frame_number) as first_frame, MAX(frame_number) as last_frame,
               COUNT(DISTINCT frame_number) as total_frames
        FROM detections
        WHERE game_id = ? AND object_class = 'person' AND tracker_id IS NOT NULL
        GROUP BY tracker_id
        ORDER BY tracker_id
    """
    rows = conn.execute(query, (game_id,)).fetchall()

    results = []
    for row in rows:
        tracker_id = row["tracker_id"]
        first_frame = row["first_frame"]
        last_frame = row["last_frame"]
        total_frames = row["total_frames"]
        minutes = total_frames / fps / 60.0

        results.append({
            "game_id": game_id,
            "tracker_id": tracker_id,
            "first_frame": first_frame,
            "last_frame": last_frame,
            "total_frames": total_frames,
            "minutes_played": round(minutes, 2),
        })

    # Upsert into player_minutes table
    conn.executemany("""
        INSERT OR REPLACE INTO player_minutes (game_id, tracker_id, first_frame, last_frame, total_frames, minutes_played, jersey_number, player_name)
        VALUES (:game_id, :tracker_id, :first_frame, :last_frame, :total_frames, :minutes_played, NULL, NULL)
    """, results)
    conn.commit()

    print(f"[Minutes] Calculated minutes for {len(results)} players")
    return results


# ── 2. Shot Type Classification ─────────────────────────────

def classify_shot_type(court_x, court_y, basket_x=0.5, basket_y=1.0):
    """
    Classify a shot as 2pt, 3pt, or ft based on normalized court position.

    Args:
        court_x: normalized x position (0-1, where 0.5 is center)
        court_y: normalized y position (0-1, where 1.0 is offensive baseline/basket)
        basket_x: normalized x position of the basket (default: center)
        basket_y: normalized y position of the basket (default: offensive end)

    Returns: (shot_type: str, confidence: float)
    """
    # Distance from basket (normalized)
    dist = math.sqrt((court_x - basket_x) ** 2 + (court_y - basket_y) ** 2)

    # Free throw: near the free throw line, close to center
    if abs(court_y - FT_ZONE_Y) < 0.05 and abs(court_x - basket_x) < 0.1:
        return "ft", 0.85

    # Three point: far from basket
    if dist > THREEPT_ZONE_DIST:
        return "3pt", 0.75

    # Two point: close to basket
    return "2pt", 0.80


def classify_all_shots(conn, game_id, video_width=1280, video_height=720):
    """
    Classify all shot events for a game using a single batch query.
    """
    print(f"[Shots] Classifying shots for game {game_id}")

    # Single batch query: get all shot events with nearest player detection
    # First get all shot events, then join to closest detection per event
    rows = conn.execute("""
        SELECT e.id as event_id, e.player as tracker_id, e.event_type,
               e.timestamp_ms, e.details_json,
               d.x_center, d.y_center
        FROM events e
        LEFT JOIN (
            SELECT d2.game_id, d2.timestamp_ms as det_ts,
                   d2.x_center, d2.y_center, d2.tracker_id,
                   e2.id as eid,
                   ROW_NUMBER() OVER (
                       PARTITION BY e2.id ORDER BY ABS(d2.timestamp_ms - e2.timestamp_ms)
                   ) as rn
            FROM events e2
            JOIN detections d2 ON d2.game_id = e2.game_id
                AND d2.object_class = 'person'
                AND d2.tracker_id IS NOT NULL
                AND d2.tracker_id = CAST(e2.player AS INTEGER)
                AND ABS(d2.timestamp_ms - e2.timestamp_ms) < 2000
            WHERE e2.game_id = ?
              AND e2.event_type IN ('shot', 'make', 'miss')
        ) d ON d.eid = e.id AND d.rn = 1
        WHERE e.game_id = ?
          AND e.event_type IN ('shot', 'make', 'miss')
    """, (game_id, game_id)).fetchall()

    results = []
    for row in rows:
        shot_result = "make" if row["event_type"] == "make" else "miss"
        tracker_id = row["tracker_id"]
        court_x = None
        court_y = None

        if row["x_center"] is not None:
            court_x = row["x_center"] / float(video_width)
            court_y = row["y_center"] / float(video_height)
            shot_type, confidence = classify_shot_type(court_x, court_y)
        else:
            details = {}
            if row["details_json"]:
                try:
                    details = json.loads(row["details_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            shot_type = details.get("shot_type", "2pt")
            confidence = 0.3

        results.append({
            "event_id": row["event_id"],
            "game_id": game_id,
            "tracker_id": tracker_id,
            "shot_type": shot_type,
            "shot_result": shot_result,
            "confidence": confidence,
            "court_x": court_x,
            "court_y": court_y,
            "timestamp_ms": row["timestamp_ms"],
        })

    # Upsert into shot_classifications
    for r in results:
        conn.execute("""
            INSERT OR REPLACE INTO shot_classifications (event_id, game_id, tracker_id, shot_type, shot_result, court_x, court_y, confidence, timestamp_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (r["event_id"], r["game_id"], r["tracker_id"], r["shot_type"], r["shot_result"],
              r.get("court_x"), r.get("court_y"), r["confidence"], r["timestamp_ms"]))
    conn.commit()

    print(f"[Shots] Classified {len(results)} shots")

    # Print summary
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

    # Check if we have enough data to work with
    row = conn.execute("SELECT COUNT(*) FROM detections WHERE game_id = ?", (game_id,)).fetchone()
    if not row or row[0] < 100:
        print("[Plays] Not enough detections")
        return []

    plays = []

    # --- Pattern 1: Pick and Roll ---
    # Use possession_change events as triggers, look at nearby detections via SQL
    pnr_plays = _detect_pick_and_roll(conn, game_id)
    plays.extend(pnr_plays)

    # --- Pattern 2: Transition / Fast Break ---
    transition_plays = _detect_transitions(conn, game_id)
    plays.extend(transition_plays)

    # --- Pattern 3: Isolation ---
    iso_plays = _detect_isolation(conn, game_id)
    plays.extend(iso_plays)

    # --- Pattern 4: Post Up ---
    postup_plays = _detect_post_up(conn, game_id)
    plays.extend(postup_plays)

    # Store results
    for play in plays:
        conn.execute("""
            INSERT INTO play_recognitions (game_id, play_type, play_subtype, start_frame, end_frame, start_timestamp_ms, end_timestamp_ms, primary_tracker_id, secondary_tracker_id, confidence, details_json)
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

    # Get possession change events as potential PnR triggers
    events = conn.execute("""
        SELECT id, player, timestamp_ms, source_frame
        FROM events
        WHERE game_id = ? AND event_type IN ('possession_change', 'turnover', 'assist')
        ORDER BY timestamp_ms
    """, (game_id,)).fetchall()

    for event in events:
        frame = event["source_frame"] or 0
        if frame == 0:
            ts = event["timestamp_ms"] or 0
            if ts > 0:
                frame = int(ts / 1000.0 * 3.75)
            else:
                continue

        # Look at detections in a window around this event
        window = conn.execute("""
            SELECT tracker_id, x_center, y_center, object_class
            FROM detections
            WHERE game_id = ? AND object_class = 'person'
              AND frame_number BETWEEN ? AND ?
        """, (game_id, max(0, frame - 30), frame + 30)).fetchall()

        if len(window) < 4:
            continue

        # Check for 2+ players in top half with low movement
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

    return plays


def _detect_transitions(conn, game_id):
    """Detect transition/fast break plays using SQL."""
    plays = []

    # Get ball detections ordered by frame
    ball_rows = conn.execute("""
        SELECT frame_number, x_center, y_center, timestamp_ms
        FROM detections
        WHERE game_id = ? AND object_class = 'ball'
        ORDER BY frame_number
    """, (game_id,)).fetchall()

    if len(ball_rows) < 10:
        return plays

    # Find high-velocity segments (rapid vertical ball movement)
    segments = []
    current_start = None
    current_start_ts = 0

    for i in range(1, len(ball_rows)):
        prev = ball_rows[i - 1]
        curr = ball_rows[i]
        frame_diff = curr["frame_number"] - prev["frame_number"]
        if frame_diff <= 0 or frame_diff > 3:
            # End current segment
            if current_start is not None and curr["frame_number"] - current_start >= 15:
                segments.append((current_start, curr["frame_number"], current_start_ts, curr["timestamp_ms"]))
            current_start = None
            continue

        dy = abs(curr["y_center"] - prev["y_center"]) if curr["y_center"] and prev["y_center"] else 0
        velocity = dy / frame_diff

        if velocity > 5.0:
            if current_start is None:
                current_start = prev["frame_number"]
                current_start_ts = prev["timestamp_ms"]
        else:
            if current_start is not None:
                end_frame = prev["frame_number"]
                if end_frame - current_start >= 15:
                    segments.append((current_start, end_frame, current_start_ts, prev["timestamp_ms"]))
                current_start = None

    # Handle last segment
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

    # Sample frames with ball detections (every 15th frame for speed)
    ball_frames = conn.execute("""
        SELECT DISTINCT frame_number
        FROM detections
        WHERE game_id = ? AND object_class = 'ball'
        ORDER BY frame_number
    """, (game_id,)).fetchall()

    if not ball_frames:
        return plays

    # Sample every 15th frame
    sampled = [r["frame_number"] for i, r in enumerate(ball_frames) if i % 15 == 0]

    for frame in sampled:
        # Get all person detections for this frame
        persons = conn.execute("""
            SELECT tracker_id, x_center, y_center
            FROM detections
            WHERE game_id = ? AND object_class = 'person' AND frame_number = ?
        """, (game_id, frame)).fetchall()

        if len(persons) < 4:
            continue

        x_vals = [p["x_center"] for p in persons if p["x_center"] is not None]
        y_vals = [p["y_center"] for p in persons if p["y_center"] is not None]
        if len(x_vals) < 4 or len(y_vals) < 4:
            continue

        # Calculate std dev manually
        x_mean = sum(x_vals) / len(x_vals)
        y_mean = sum(y_vals) / len(y_vals)
        x_std = (sum((x - x_mean) ** 2 for x in x_vals) / len(x_vals)) ** 0.5
        y_std = (sum((y - y_mean) ** 2 for y in y_vals) / len(y_vals)) ** 0.5

        if x_std > 200 and y_std > 150:
            # Find ball position
            ball = conn.execute("""
                SELECT x_center, y_center, timestamp_ms
                FROM detections
                WHERE game_id = ? AND object_class = 'ball' AND frame_number = ?
                LIMIT 1
            """, (game_id, frame)).fetchone()

            if ball and ball["x_center"] is not None:
                # Find closest player to ball
                min_dist = float("inf")
                ball_handler = None
                for p in persons:
                    if p["x_center"] is not None and p["y_center"] is not None:
                        d = ((p["x_center"] - ball["x_center"]) ** 2 + (p["y_center"] - ball["y_center"]) ** 2) ** 0.5
                        if d < min_dist:
                            min_dist = d
                            ball_handler = p["tracker_id"]

                plays.append({
                    "play_type": "isolation",
                    "play_subtype": "iso",
                    "start_frame": frame,
                    "end_frame": frame + 30,
                    "start_timestamp_ms": ball["timestamp_ms"] or 0,
                    "primary_tracker_id": ball_handler,
                    "confidence": 0.35,
                    "details": {"x_spround": x_std, "y_spread": y_std, "method": "player_spread"},
                })

    return plays


def _detect_post_up(conn, game_id):
    """Detect post-up plays using SQL."""
    plays = []

    # Find players who spend sustained time near the basket area
    # Basket area = top 15% of y range (offensive end)
    post_players = conn.execute("""
        SELECT tracker_id,
               MIN(frame_number) as min_frame,
               MAX(frame_number) as max_frame,
               COUNT(*) as frame_count,
               MIN(timestamp_ms) as min_ts
        FROM detections
        WHERE game_id = ? AND object_class = 'person'
          AND y_center IS NOT NULL
          AND y_center > (SELECT MAX(y_center) * 0.85 FROM detections WHERE game_id = ? AND object_class = 'person' AND y_center IS NOT NULL)
        GROUP BY tracker_id
        HAVING COUNT(*) >= 30
    """, (game_id, game_id)).fetchall()

    for pp in post_players:
        # Check if ball is nearby during this time
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
                "primary_tracker_id": pp["tracker_id"],
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

    # Get player minutes (who's on court when)
    minutes = conn.execute("""
        SELECT * FROM player_minutes WHERE game_id = ?
    """, (game_id,)).fetchall()

    if not minutes:
        print("[Effect] No player minutes data — run calculate_player_minutes first")
        return []

    # Build score events list (single pass)
    events = conn.execute("""
        SELECT timestamp_ms, source_frame, player, event_type, details_json
        FROM events WHERE game_id = ? AND event_type = 'make'
        ORDER BY timestamp_ms
    """, (game_id,)).fetchall()

    score_events = []
    for event in events:
        points = 2  # default
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

    # Build timeline of score events for efficient lookup
    # For each player, use binary search to find score events during their time on court
    se_frames = [se["frame"] for se in score_events]
    se_timestamps = [se["timestamp_ms"] for se in score_events]
    se_points = [se["points"] for se in score_events]

    results = []
    for pm in minutes:
        tracker_id = pm["tracker_id"]
        first_frame = pm["first_frame"] or 0
        last_frame = pm["last_frame"] or 0
        if first_frame == 0 and last_frame == 0:
            continue

        # Count score events during this player's time on court
        points_for = 0
        points_against = 0

        # Use frame-based matching if frames are available
        for i, se in enumerate(score_events):
            se_frame = se["frame"]
            se_ts = se["timestamp_ms"]
            if se_frame > 0 and first_frame <= se_frame <= last_frame:
                points_for += se["points"]
            elif se_frame > 0:
                points_against += se["points"]
            elif se_ts > 0:
                # Fallback: use timestamp comparison
                player_start_ms = (first_frame / fps) * 1000
                player_end_ms = (last_frame / fps) * 1000
                if player_start_ms <= se_ts <= player_end_ms:
                    points_for += se["points"]
                else:
                    points_against += se["points"]

        frame_diff = max(1, last_frame - first_frame)
        possessions = max(1, frame_diff / (fps * 24))  # ~24 sec per possession
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

    # Upsert
    for r in results:
        conn.execute("""
            INSERT OR REPLACE INTO player_effect (game_id, tracker_id, plus_minus, possessions_on, possessions_off, points_for, points_against, ortg, drtg, net_rating)
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

    This should be called AFTER the basic event generation is complete.
    """
    print(f"\n{'='*60}")
    print(f"Enhanced Film Analysis for game: {game_id}")
    print(f"{'='*60}\n")

    conn = get_db(db_path)

    try:
        # Get video dimensions — use provided values or try DB, don't open the video file
        if video_width is None or video_height is None:
            video_width, video_height = 1920, 1080  # default for this project
            try:
                video_path_row = conn.execute("SELECT video_path FROM analysis_runs WHERE game_id = ? LIMIT 1", (game_id,)).fetchone()
                if video_path_row and video_path_row[0]:
                    import cv2 as _cv2
                    _cap = _cv2.VideoCapture(video_path_row[0])
                    if _cap.isOpened():
                        video_width = int(_cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
                        video_height = int(_cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
                        _cap.release()
            except Exception:
                pass

        # Step 1: Minutes played
        minutes = calculate_player_minutes(conn, game_id, fps)

        # Step 2: Shot classification
        shots = classify_all_shots(conn, game_id, video_width, video_height)

        # Step 3: Play recognition
        plays = recognize_plays(conn, game_id)

        # Step 4: Player effect
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
