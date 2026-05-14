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
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
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
    Classify all shot events for a game.

    Uses the player's position at the time of the shot to determine shot type.
    Falls back to heuristic: if we don't have a clear position, mark as unknown.
    """
    print(f"[Shots] Classifying shots for game {game_id}")

    # Get all shot events for this game
    shot_events = conn.execute("""
        SELECT e.*
        FROM events e
        WHERE e.game_id = ?
          AND e.event_type IN ('shot', 'make', 'miss')
    """, (game_id,)).fetchall()

    results = []
    for event in shot_events:
        tracker_id = event["player"]  # events use 'player' column, not 'tracker_id'
        shot_result = "make" if event["event_type"] == "make" else "miss"
        timestamp_ms = event["timestamp_ms"]
        
        # Get player position at shot time using timestamp proximity
        # Find the detection closest in time for this player/tracker
        pos = conn.execute("""
            SELECT x_center, y_center, width, height, tracker_id, frame_number
            FROM detections
            WHERE game_id = ? AND object_class = 'person'
              AND tracker_id IS NOT NULL
              AND ABS(timestamp_ms - ?) < 500
            ORDER BY ABS(timestamp_ms - ?) ASC, confidence DESC
            LIMIT 1
        """, (game_id, timestamp_ms, timestamp_ms)).fetchone()

        if pos:
            # Normalize position based on court
            # In video coordinates, we need to know which team is on which end
            # For now, assume: lower half of frame = one end, upper half = other
            court_x = pos["x_center"] / float(video_width)
            court_y = pos["y_center"] / float(video_height)

            shot_type, confidence = classify_shot_type(court_x, court_y)
        else:
            # Fallback: use details_json if available
            details = {}
            if event["details_json"]:
                try:
                    details = json.loads(event["details_json"])
                except (json.JSONDecodeError, TypeError):
                    pass
            shot_type = details.get("shot_type", "2pt")
            confidence = 0.3  # low confidence for fallback

        results.append({
            "event_id": event["id"],
            "game_id": game_id,
            "tracker_id": tracker_id,
            "shot_type": shot_type,
            "shot_result": shot_result,
            "court_x": court_x if pos else None,
            "court_y": court_y if pos else None,
            "confidence": confidence,
            "timestamp_ms": timestamp_ms,
        })

    # Upsert into shot_classifications
    for r in results:
        conn.execute("""
            INSERT OR REPLACE INTO shot_classifications (event_id, game_id, tracker_id, shot_type, shot_result, court_x, court_y, confidence, timestamp_ms, details_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """, (r["event_id"], r["game_id"], r["tracker_id"], r["shot_type"], r["shot_result"],
              r["court_x"], r["court_y"], r["confidence"], r["timestamp_ms"]))
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

    Uses heuristic pattern matching on:
    - Player clustering (screens, picks)
    - Movement vectors (cuts, drives)
    - Ball possession changes (turnovers, passes)
    - Speed/tempo indicators (transition vs half-court)
    """
    print(f"[Plays] Recognizing plays for game {game_id}")

    # Get all detections sorted by frame
    detections = pd.read_sql_query("""
        SELECT * FROM detections WHERE game_id = ? ORDER BY frame_number, tracker_id
    """, conn, params=(game_id,))

    if detections.empty:
        print("[Plays] No detections found")
        return []

    # Get all events sorted by timestamp
    events = pd.read_sql_query("""
        SELECT * FROM events WHERE game_id = ? ORDER BY timestamp_ms
    """, conn, params=(game_id,))

    plays = []

    # --- Pattern 1: Pick and Roll Detection ---
    # Look for: screener setting a pick (stationary near top) + ball handler driving
    pnr_plays = _detect_pick_and_roll(detections, events, conn)
    plays.extend(pnr_plays)

    # --- Pattern 2: Transition / Fast Break ---
    # Look for: rapid ball movement downcourt with few players
    transition_plays = _detect_transitions(detections, events, conn)
    plays.extend(transition_plays)

    # --- Pattern 3: Isolation ---
    # Look for: ball handler + 1v1 situation (others spread out)
    iso_plays = _detect_isolation(detections, events, conn)
    plays.extend(iso_plays)

    # --- Pattern 4: Post Up ---
    # Look for: player near basket with ball, backing down
    postup_plays = _detect_post_up(detections, events, conn)
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


def _detect_pick_and_roll(detections, events, conn):
    """Detect pick and roll plays."""
    plays = []

    # Get possession change events as potential PnR triggers
    possession_changes = events[events["event_type"].isin(["possession_change", "turnover", "assist"])]

    for _, event in possession_changes.iterrows():
        frame = event.get("source_frame", 0)
        if frame == 0:
            continue

        # Look at detections around this event
        window = detections[
            (detections["frame_number"] >= frame - 30) &
            (detections["frame_number"] <= frame + 30)
        ]

        if len(window) < 4:
            continue

        # Check for a screener (player moving toward top then stopping)
        persons = window[window["object_class"] == "person"]
        if len(persons) < 2:
            continue

        # Simple heuristic: if we have 2+ players in the top half with low movement
        top_players = persons[persons["y_center"] < persons["y_center"].median()]
        if len(top_players) >= 2:
            # Potential PnR — check if one player is near the 3pt line
            near_three = top_players[
                (top_players["x_center"].abs() - 0.3).abs() < 0.15
            ]
            if len(near_three) >= 1:
                plays.append({
                    "play_type": "pick_and_roll",
                    "play_subtype": "pnr_ball_handler",
                    "start_frame": max(0, frame - 15),
                    "end_frame": frame + 15,
                    "start_timestamp_ms": event["timestamp_ms"] - 5000,
                    "end_timestamp_ms": event["timestamp_ms"] + 5000,
                    "primary_tracker_id": event["player"],
                    "confidence": 0.45,
                    "details": {"trigger_frame": int(frame), "method": "heuristic_pnr"}
                })

    return plays


def _detect_transitions(detections, events, conn):
    """Detect transition/fast break plays."""
    plays = []

    # Group detections by frame to get ball speed per frame
    ball_detections = detections[detections["object_class"] == "ball"].sort_values("frame_number")

    if len(ball_detections) < 10:
        return plays

    # Calculate ball velocity between consecutive frames
    ball_detections = ball_detections.copy()
    ball_detections["dy"] = ball_detections["y_center"].diff()
    ball_detections["frame_diff"] = ball_detections["frame_number"].diff()
    ball_detections["velocity"] = ball_detections["dy"] / ball_detections["frame_diff"].replace(0, 1)

    # High velocity downward = fast break
    high_velocity = ball_detections[
        (ball_detections["velocity"].abs() > 5.0) &  # rapid vertical movement
        (ball_detections["frame_diff"] <= 3)  # consecutive or near-consecutive frames
    ]

    # Group consecutive high-velocity frames into play segments
    if not high_velocity.empty:
        segments = []
        current_start = high_velocity.iloc[0]["frame_number"]
        current_end = current_start

        for _, row in high_velocity.iloc[1:].iterrows():
            if row["frame_number"] <= current_end + 30:  # within 30 frames
                current_end = row["frame_number"]
            else:
                if current_end - current_start >= 15:  # at least half a second
                    segments.append((int(current_start), int(current_end)))
                current_start = row["frame_number"]
                current_end = current_start

        if current_end - current_start >= 15:
            segments.append((int(current_start), int(current_end)))

        for start, end in segments:
            plays.append({
                "play_type": "transition",
                "play_subtype": "fast_break",
                "start_frame": start,
                "end_frame": end,
                "start_timestamp_ms": int(ball_detections[ball_detections["frame_number"] == start]["timestamp_ms"].values[0]) if len(ball_detections[ball_detections["frame_number"] == start]) > 0 else 0,
                "end_timestamp_ms": int(ball_detections[ball_detections["frame_number"] == end]["timestamp_ms"].values[0]) if len(ball_detections[ball_detections["frame_number"] == end]) > 0 else 0,
                "confidence": 0.40,
                "details": {"velocity_threshold": 5.0, "method": "ball_velocity"}
            })

    return plays


def _detect_isolation(detections, events, conn):
    """Detect isolation plays."""
    plays = []

    # Look for frames where 1 player has the ball and others are spread out
    frames_with_ball = detections[detections["object_class"] == "ball"]["frame_number"].unique()

    for frame in frames_with_ball[::15]:  # sample every 15th frame for speed
        frame_detections = detections[detections["frame_number"] == frame]
        persons = frame_detections[frame_detections["object_class"] == "person"]

        if len(persons) < 4:  # need enough players on court
            continue

        # Check if players are spread apart (high std deviation in positions)
        x_std = persons["x_center"].std()
        y_std = persons["y_center"].std()

        if x_std > 200 and y_std > 150:  # spread out = isolation setup
            # Find who has the ball
            ball = frame_detections[frame_detections["object_class"] == "ball"]
            if not ball.empty:
                ball_pos = ball.iloc[0]
                distances = np.sqrt(
                    (persons["x_center"] - ball_pos["x_center"]) ** 2 +
                    (persons["y_center"] - ball_pos["y_center"]) ** 2
                )
                closest_idx = distances.argmin()
                ball_handler_id = persons.iloc[closest_idx]["tracker_id"]

                plays.append({
                    "play_type": "isolation",
                    "play_subtype": "iso",
                    "start_frame": int(frame),
                    "end_frame": int(frame) + 30,
                    "start_timestamp_ms": int(ball_pos["timestamp_ms"]) if "timestamp_ms" in ball_pos else 0,
                    "primary_tracker_id": int(ball_handler_id) if pd.notna(ball_handler_id) else None,
                    "confidence": 0.35,
                    "details": {"x_spread": float(x_std), "y_spread": float(y_std), "method": "player_spread"}
                })

    return plays


def _detect_post_up(detections, events, conn):
    """Detect post-up plays (player near basket, backing down)."""
    plays = []

    # Look for players near the basket area (bottom 20% of frame)
    persons = detections[detections["object_class"] == "person"].copy()
    if persons.empty:
        return plays

    # Normalize y to 0-1
    y_max = persons["y_center"].max()
    y_min = persons["y_center"].min()
    if y_max == y_min:
        return plays

    persons["y_norm"] = (persons["y_center"] - y_min) / (y_max - y_min)

    # Players near basket (top 15% of normalized y = near basket in offensive end)
    post_players = persons[persons["y_norm"] > 0.85]

    # Group by tracker_id and find sustained post-up sequences
    for tracker_id, group in post_players.groupby("tracker_id"):
        if len(group) >= 30:  # at least 1 second of post-up
            # Check if ball is nearby
            ball = detections[
                (detections["object_class"] == "ball") &
                (detections["frame_number"] >= group["frame_number"].min()) &
                (detections["frame_number"] <= group["frame_number"].max())
            ]
            if not ball.empty:
                plays.append({
                    "play_type": "post_up",
                    "play_subtype": "low_post",
                    "start_frame": int(group["frame_number"].min()),
                    "end_frame": int(group["frame_number"].max()),
                    "start_timestamp_ms": int(group.iloc[0]["timestamp_ms"]) if "timestamp_ms" in group.columns else 0,
                    "primary_tracker_id": int(tracker_id),
                    "confidence": 0.30,
                    "details": {"frames_in_post": len(group), "method": "proximity_to_basket"}
                })

    return plays


# ── 4. Player Effect (+/-) ──────────────────────────────────

def calculate_player_effect(conn, game_id, fps=30.0):
    """
    Calculate player effect metrics: +/-, possessions, ratings.

    Uses events to track score changes while each player is on court.
    """
    print(f"[Effect] Calculating player effect for game {game_id}")

    # Get events in chronological order
    events = conn.execute("""
        SELECT * FROM events WHERE game_id = ? ORDER BY timestamp_ms, id
    """, (game_id,)).fetchall()

    # Get player minutes (who's on court when)
    minutes = conn.execute("""
        SELECT * FROM player_minutes WHERE game_id = ?
    """, (game_id,)).fetchall()

    if not minutes:
        print("[Effect] No player minutes data — run calculate_player_minutes first")
        return []

    # Track score by analyzing events
    # Heuristic: a "make" event scores points (2 for regular, 3 for 3pt, 1 for FT)
    # We need to know which team scored — use shot classification if available
    score_events = []
    for event in events:
        if event["event_type"] in ("make",):
            # Determine points
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
                "frame": event.get("source_frame", 0) or 0,
                "points": points,
                "player": event["player"],
            })

    # For each player, calculate +/- by checking which score events happened
    # while they were on court
    results = []
    for pm in minutes:
        tracker_id = pm["tracker_id"]
        first_frame = pm.get("first_frame") or 0
        last_frame = pm.get("last_frame") or 0
        if first_frame == 0 and last_frame == 0:
            continue

        # Score events during this player's time on court
        points_for = 0
        points_against = 0
        for se in score_events:
            se_frame = se.get("frame", 0)
            se_ts = se.get("timestamp_ms", 0)
            # Use frame if available, otherwise approximate from timestamp
            if se_frame > 0 and first_frame <= se_frame <= last_frame:
                points_for += se["points"]
            elif se_frame > 0:
                points_against += se["points"]
            elif se_ts > 0:
                # Fallback: use timestamp comparison
                # Convert player frame range to approximate timestamp range
                player_duration_frames = max(1, last_frame - first_frame)
                fps_est = fps  # passed from caller
                player_duration_ms = (player_duration_frames / fps_est) * 1000
                player_start_ms = (first_frame / fps_est) * 1000
                player_end_ms = player_start_ms + player_duration_ms
                if player_start_ms <= se_ts <= player_end_ms:
                    points_for += se["points"]
                else:
                    points_against += se["points"]

        frame_diff = max(1, last_frame - first_frame)
        if frame_diff <= 0:
            frame_diff = 1
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

def run_enhanced_analysis(db_path, game_id, fps=30.0):
    """
    Run the full enhanced analysis pipeline for a game.

    This should be called AFTER the basic event generation is complete.
    """
    print(f"\n{'='*60}")
    print(f"Enhanced Film Analysis for game: {game_id}")
    print(f"{'='*60}\n")

    conn = get_db(db_path)

    try:
        # Get video dimensions from the video file
        video_width, video_height = 1280, 720  # defaults
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
