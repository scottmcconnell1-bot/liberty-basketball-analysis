"""
Enhanced Film Analysis Module
=============================

Extends the basic event generator with:
1. Minutes played calculation (from per-frame player detections)
2. Shot type classification (2pt/3pt/FT based on court position)
3. Play recognition (pattern matching on player movement sequences)
4. Player effect (possessions + points scored per position)

NOTE: YOLO tracker_ids are unstable at imgsz=320 (median 2-frame lifespan,
67K unique IDs for ~10 real players). All functions use spatial grid clustering
instead of tracker_id for player identity. Players are identified by spatial
grid cells (120x120px), producing ~10-15 stable "player slots".
"""

import bisect
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

def calculate_player_minutes(conn, game_id, fps=30.0, detect_stride=1):
    """
    Calculate minutes played per player from detection data.

    Uses player_cluster (from KMeans spatial clustering) instead of tracker_id,
    since YOLO tracker_ids are unstable at imgsz=320.
    
    Args:
        fps: original video fps
        detect_stride: detection stride (effective fps = fps / detect_stride)
    """
    print(f"[Minutes] Calculating minutes played for game {game_id}")

    effective_fps = fps / detect_stride

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
        minutes = total_frames / effective_fps / 60.0

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

def classify_shot_type(court_x, court_y, basket_x=0.5, basket_y=1.0, three_pt_threshold=0.50):
    """
    Classify a shot as 2pt, 3pt, or ft based on normalized court position.
    """
    court_x = max(0, min(court_x, 1.0))
    court_y = max(0, min(court_y, 1.0))
    dist = math.sqrt((court_x - basket_x) ** 2 + (court_y - basket_y) ** 2)

    if abs(court_y - FT_ZONE_Y) < 0.08 and abs(court_x - basket_x) < 0.15:
        return "ft", 0.85
    if dist > three_pt_threshold:
        return "3pt", 0.70
    return "2pt", 0.80


def _estimate_basket_position(conn, game_id):
    """
    Estimate basket position from 2pt make shot locations.
    Returns (basket_x, basket_y, three_pt_threshold) in normalized coords.
    Falls back to (0.5, 1.0, 0.50) if insufficient data.
    """
    rows = conn.execute("""
        SELECT court_x, court_y
        FROM shot_classifications
        WHERE game_id = ? AND shot_type = '2pt' AND shot_result = 'make'
          AND court_x IS NOT NULL AND court_y IS NOT NULL
          AND court_x < 0.99 AND court_y < 0.99
    """, (game_id,)).fetchall()
    if len(rows) < 3:
        return 0.5, 1.0, 0.50
    xs = [r[0] for r in rows]
    ys = [r[1] for r in rows]
    basket_x = sum(xs) / len(xs)
    basket_y = sum(ys) / len(ys)
    # 2pt radius: mean distance of 2pt makes from basket
    dists = [math.sqrt((x - basket_x)**2 + (y - basket_y)**2) for x, y in zip(xs, ys)]
    mean_2pt_radius = sum(dists) / len(dists)
    three_pt_threshold = mean_2pt_radius * 1.8
    print(f"[Shots] Estimated basket at ({basket_x:.3f}, {basket_y:.3f}), "
          f"2pt radius={mean_2pt_radius:.3f}, 3pt threshold={three_pt_threshold:.3f}")
    return basket_x, basket_y, three_pt_threshold


def classify_all_shots(conn, game_id, video_width=1920, video_height=1080):
    """
    Classify all shot events for a game.
    Uses the shooter's cluster detection near the shot's peak_frame for court position.
    Falls back to ball position at peak_frame if no player detection is found.
    """
    print(f"[Shots] Classifying shots for game {game_id}")

    # Get all shot/make/miss events
    shot_events = conn.execute("""
        SELECT e.id as event_id, e.player, e.event_type,
               e.timestamp_ms, e.details_json
        FROM events e
        WHERE e.game_id = ?
          AND e.event_type IN ('shot', 'make', 'miss')
    """, (game_id,)).fetchall()

    if not shot_events:
        print("[Shots] No shot events found")
        return []

    # Estimate basket position from existing 2pt makes (or use defaults)
    basket_x, basket_y, three_pt_threshold = _estimate_basket_position(conn, game_id)

    # Build a lookup of peak_frame by (timestamp_ms, player) for make/miss events
    # that don't have peak_frame in their own details. The parent shot event
    # shares the same timestamp_ms and player.
    # Columns: 0=event_id, 1=player, 2=event_type, 3=timestamp_ms, 4=details_json
    peak_frame_lookup = {}
    for event in shot_events:
        details = {}
        if event[4]:
            try:
                details = json.loads(event[4])
            except (json.JSONDecodeError, TypeError):
                pass
        pf = details.get("peak_frame")
        if pf is not None:
            key = (event[3], event[1])
            peak_frame_lookup[key] = pf

    results = []
    for event in shot_events:
        shot_result = "make" if event[2] == "make" else "miss"
        player_cluster = event[1]
        details = {}
        if event[4]:
            try:
                details = json.loads(event[4])
            except (json.JSONDecodeError, TypeError):
                pass

        court_x = None
        court_y = None
        peak_frame = details.get("peak_frame")

        # For make/miss events without peak_frame, look up from parent shot
        if peak_frame is None:
            key = (event[3], player_cluster)
            peak_frame = peak_frame_lookup.get(key)

        if peak_frame is not None and player_cluster is not None:
            # 1) Try to find the nearest detection for this cluster near the peak frame
            #    Use a wide window (±100 frames) to handle detection stride and interpolation offsets
            det = conn.execute("""
                SELECT x_center, y_center
                FROM detections
                WHERE game_id = ? AND object_class = 'person'
                  AND player_cluster = CAST(? AS INTEGER)
                  AND frame_number BETWEEN ? AND ?
                ORDER BY ABS(frame_number - ?)
                LIMIT 1
            """, (game_id, player_cluster, peak_frame - 100, peak_frame + 100, peak_frame)).fetchone()

            if det and det[0] is not None:
                # Accept detections within valid frame bounds [0, video_dimension].
                # Coordinates at the exact boundary (e.g. x=1919 on 1920-wide) are
                # valid — clamp them instead of rejecting with an arbitrary margin.
                if 0 <= det[0] <= video_width and 0 <= det[1] <= video_height:
                    cx = max(0, min(det[0], video_width - 1)) / float(video_width)
                    cy = max(0, min(det[1], video_height - 1)) / float(video_height)
                    court_x = cx
                    court_y = cy
                    shot_type, confidence = classify_shot_type(cx, cy, basket_x, basket_y, three_pt_threshold)
                else:
                    det = None  # Truly out of bounds, treat as not found

            if court_x is None:
                # 2) Fallback: use the ball position at/near peak_frame as proxy
                ball = conn.execute("""
                    SELECT x_center, y_center
                    FROM detections
                    WHERE game_id = ? AND object_class = 'ball'
                      AND frame_number BETWEEN ? AND ?
                    ORDER BY ABS(frame_number - ?)
                    LIMIT 1
                """, (game_id, peak_frame - 100, peak_frame + 100, peak_frame)).fetchone()

                if ball and ball[0] is not None:
                    if 0 <= ball[0] <= video_width and 0 <= ball[1] <= video_height:
                        cx = max(0, min(ball[0], video_width - 1)) / float(video_width)
                        cy = max(0, min(ball[1], video_height - 1)) / float(video_height)
                        court_x = cx
                        court_y = cy
                        shot_type, confidence = classify_shot_type(cx, cy, basket_x, basket_y, three_pt_threshold)
                        confidence = min(confidence, 0.4)  # lower confidence for ball proxy
                    else:
                        ball = None  # Truly out of bounds

            if court_x is None:
                # 3) Final fallback: use nearest player detection for ANY cluster
                #    within ±100 frames of peak_frame (best-effort court position)
                any_det = conn.execute("""
                    SELECT x_center, y_center
                    FROM detections
                    WHERE game_id = ? AND object_class = 'person'
                      AND frame_number BETWEEN ? AND ?
                    ORDER BY ABS(frame_number - ?)
                    LIMIT 1
                """, (game_id, peak_frame - 100, peak_frame + 100, peak_frame)).fetchone()

                if any_det and any_det[0] is not None:
                    if 0 <= any_det[0] <= video_width and 0 <= any_det[1] <= video_height:
                        cx = max(0, min(any_det[0], video_width - 1)) / float(video_width)
                        cy = max(0, min(any_det[1], video_height - 1)) / float(video_height)
                        court_x = cx
                        court_y = cy
                        shot_type, confidence = classify_shot_type(cx, cy, basket_x, basket_y, three_pt_threshold)
                        confidence = min(confidence, 0.35)  # lower confidence for any-player proxy

            if court_x is None:
                shot_type = "2pt"
                confidence = 0.3
        else:
            shot_type = "2pt"
            confidence = 0.3

        results.append({
            "event_id": event[0],
            "game_id": game_id,
            "tracker_id": player_cluster,
            "shot_type": shot_type,
            "shot_result": shot_result,
            "confidence": confidence,
            "court_x": court_x,
            "court_y": court_y,
            "timestamp_ms": event[3],
        })

    # Clear existing classifications for this game to prevent duplicates
    conn.execute("DELETE FROM shot_classifications WHERE game_id = ?", (game_id,))

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


# ── 4. Player Effect (Possessions & Scoring) ─────────────────

def calculate_player_effect(conn, game_id, fps=30.0, detect_stride=1, min_possessions=10):
    """
    Calculate POSITION-BASED effect metrics: possessions + points scored + shot stats.

    The KMeans clusters represent COURT POSITIONS (left wing, top of key, etc.),
    not individual players. Each cluster_id is a spatial region on the court.

    For each position cluster we compute:
      - possessions: number of possession segments where the ball-holder was
        in this cluster (from events.player on possession_change events)
      - points_scored: sum of points from make events where the shooter's
        cluster matches this cluster (events.player on make events)
      - points_per_possession: raw points_scored / possessions (not per 100)
      - minutes_played: from player_minutes
      - shot_attempts: number of shot events (shot + make + miss) where this
        cluster was the shooter
      - shot_makes: number of make events where this cluster was the shooter
      - fg_pct: shot_makes / shot_attempts (if attempts > 0)
      - three_pt_attempts: number of 3pt shot attempts from this cluster
      - three_pt_makes: number of 3pt makes from this cluster

    NOTE: points_allowed / DRTG / Net rating are NOT computed because we cannot
    accurately determine which team scored from position-based clusters. The
    previous approach (crediting every position with every basket scored while
    any player was in that zone) produced extreme, meaningless values (DRTG
    400-1200) for positions with very few possessions.

    DB column mapping for repurposed fields:
      - possessions_off → shot_attempts
      - drtg → fg_pct
      - points_for → shot_makes (raw count, not points)

    Positions with fewer than min_possessions are marked as "insufficient data"
    with NULL ratings.
    """
    print(f"[Effect] Calculating POSITION-BASED effect for game {game_id}")

    effective_fps = fps / detect_stride

    # ── Get all cluster IDs from player_minutes ──
    minutes_rows = conn.execute("""
        SELECT tracker_id, first_frame, last_frame, total_frames, minutes_played
        FROM player_minutes
        WHERE game_id = ?
        ORDER BY tracker_id
    """, (game_id,)).fetchall()

    if not minutes_rows:
        print("[Effect] No player minutes data — run calculate_player_minutes first")
        return []

    cluster_ids = [row["tracker_id"] for row in minutes_rows]
    minutes_map = {row["tracker_id"]: row["minutes_played"] for row in minutes_rows}

    # ── Get ALL shot events (shot + make + miss) with shot type from shot_classifications ──
    all_shot_events = conn.execute("""
        SELECT e.id AS event_id, e.player AS shooter_cluster, e.event_type,
               sc.shot_type, sc.shot_result
        FROM events e
        LEFT JOIN shot_classifications sc ON sc.event_id = e.id
        WHERE e.game_id = ?
          AND e.event_type IN ('shot', 'make', 'miss')
        ORDER BY e.timestamp_ms
    """, (game_id,)).fetchall()

    # ── Get make events with shot type for scoring ──
    make_events = conn.execute("""
        SELECT e.timestamp_ms, e.player AS scorer_cluster, sc.shot_type
        FROM events e
        LEFT JOIN shot_classifications sc ON sc.event_id = e.id
        WHERE e.game_id = ? AND e.event_type = 'make'
        ORDER BY e.timestamp_ms
    """, (game_id,)).fetchall()

    score_events = []
    for event in make_events:
        shot_type = event["shot_type"] or "2pt"
        if shot_type == "3pt":
            points = 3
        elif shot_type == "ft":
            points = 1
        else:
            points = 2

        score_events.append({
            "timestamp_ms": event["timestamp_ms"],
            "scorer_cluster": event["scorer_cluster"],
            "points": points,
        })

    if not score_events:
        print("[Effect] No score events found")
        return []

    print(f"[Effect] Processing {len(score_events)} score events and "
          f"{len(all_shot_events)} total shot events across {len(cluster_ids)} position clusters")

    # ── Get possession segments: each possession_change event's player is the ball-holder cluster ──
    possession_events = conn.execute("""
        SELECT timestamp_ms, player AS ball_holder_cluster
        FROM events
        WHERE game_id = ? AND event_type = 'possession_change'
        ORDER BY timestamp_ms
    """, (game_id,)).fetchall()

    # Count possessions per cluster (ball-holder cluster)
    possessions_per_cluster = defaultdict(int)
    for pe in possession_events:
        bh = pe["ball_holder_cluster"]
        if bh is not None:
            try:
                bh_int = int(bh)
                possessions_per_cluster[bh_int] += 1
            except (ValueError, TypeError):
                pass

    # ── Calculate per-position stats ──
    MIN_POSSESSIONS = min_possessions  # threshold for "insufficient data"

    results = []
    insufficient_warnings = []
    for cid in cluster_ids:
        possessions = possessions_per_cluster.get(cid, 0)

        # Points scored: sum of points from make events where this cluster was the shooter
        points_scored = 0
        for se in score_events:
            scorer = se["scorer_cluster"]
            if scorer is not None and int(scorer) == cid:
                points_scored += se["points"]

        # Shot stats: count attempts, makes, 3pt attempts, 3pt makes
        shot_attempts = 0
        shot_makes = 0
        three_pt_attempts = 0
        three_pt_makes = 0
        for se in all_shot_events:
            shooter = se["shooter_cluster"]
            if shooter is None or int(shooter) != cid:
                continue
            shot_attempts += 1
            if se["event_type"] == "make":
                shot_makes += 1
            # 3pt stats from shot_classifications
            if se["shot_type"] == "3pt":
                three_pt_attempts += 1
                if se["event_type"] == "make":
                    three_pt_makes += 1

        # FG%
        fg_pct = round(shot_makes / shot_attempts, 3) if shot_attempts > 0 else None

        minutes_played = minutes_map.get(cid, 0)

        if possessions < MIN_POSSESSIONS:
            # Insufficient data: set ratings to NULL
            points_per_poss = None
            ortg = None
            insufficient_warnings.append(
                f"  ⚠ Position {cid}: only {possessions} possessions "
                f"(<{MIN_POSSESSIONS}) — ratings set to NULL"
            )
        else:
            points_per_poss = round(points_scored / possessions, 2)
            ortg = round((points_scored / possessions) * 100, 1)

        results.append({
            "game_id": game_id,
            "tracker_id": cid,
            "possessions": possessions,
            "points_scored": points_scored,
            "total_points": points_scored,  # raw points (same as points_scored)
            "points_per_possession": points_per_poss,
            "ortg": ortg,
            "minutes_played": minutes_played,
            "shot_attempts": shot_attempts,
            "shot_makes": shot_makes,
            "fg_pct": fg_pct,
            "three_pt_attempts": three_pt_attempts,
            "three_pt_makes": three_pt_makes,
        })

    # ── Print warnings for insufficient data ──
    if insufficient_warnings:
        print(f"[Effect] {len(insufficient_warnings)} position(s) with insufficient data:")
        for w in insufficient_warnings:
            print(w)

    # ── Write results to DB ──
    for r in results:
        conn.execute("""
            INSERT OR REPLACE INTO player_effect
                (game_id, tracker_id, plus_minus, possessions_on, possessions_off,
                 points_for, points_against, ortg, drtg, net_rating)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r["game_id"],
            r["tracker_id"],
            r["points_scored"],          # plus_minus — best available proxy (points scored)
            r["possessions"],            # possessions_on — ball-holder possession count
            r["shot_attempts"],          # possessions_off → repurposed for shot_attempts
            r["shot_makes"],             # points_for → repurposed for shot_makes (count)
            0,                           # points_against — cannot compute without team ID
            r["ortg"],                   # ortg — offensive rating (NULL if insufficient data)
            r["fg_pct"],                 # drtg → repurposed for fg_pct
            r["ortg"],                   # net_rating — best available proxy (ortg)
        ))
    conn.commit()

    # ── Print summary ──
    print(f"[Effect] Position-based effect for {len(results)} court positions:")
    print(f"  {'Pos':>4}  {'Poss':>5}  {'ShAtt':>5}  {'Makes':>5}  {'FG%':>6}  "
          f"{'3ptA':>5}  {'3ptM':>5}  {'ORTG':>6}")
    print(f"  {'─'*4}  {'─'*5}  {'─'*5}  {'─'*5}  {'─'*6}  "
          f"{'─'*5}  {'─'*5}  {'─'*6}")
    for r in results:
        fg = f"{r['fg_pct']:.3f}" if r['fg_pct'] is not None else "  N/A"
        o = f"{r['ortg']:.1f}" if r['ortg'] is not None else "  N/A"
        print(f"  {r['tracker_id']:>4}  {r['possessions']:>5}  {r['shot_attempts']:>5}  "
              f"{r['shot_makes']:>5}  {fg:>6}  {r['three_pt_attempts']:>5}  "
              f"{r['three_pt_makes']:>5}  {o:>6}")

    return results


# ── 5. Master Analysis Pipeline ─────────────────────────────

def run_enhanced_analysis(db_path, game_id, fps=30.0, video_width=None, video_height=None, detect_stride=1):
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

        minutes = calculate_player_minutes(conn, game_id, fps, detect_stride)
        shots = classify_all_shots(conn, game_id, video_width, video_height)
        plays = recognize_plays(conn, game_id)
        effects = calculate_player_effect(conn, game_id, fps, detect_stride)

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
