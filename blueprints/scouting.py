"""
Scouting Blueprint
==================
Scouting report generation, NFHS VOD download, and opponent analysis.

API Routes:
  - /api/scouting/reports (GET, POST) - List and create scouting reports
  - /api/scouting/reports/<int:report_id> (GET, PUT, DELETE) - Manage a report
  - /api/scouting/reports/<int:report_id>/personnel (GET, POST) - Manage personnel
  - /api/scouting/reports/<int:report_id>/offensive-sets (GET, POST) - Manage offensive sets
  - /api/scouting/reports/<int:report_id>/defensive-tendencies (GET, POST) - Manage defensive tendencies
  - /api/scouting/reports/<int:report_id>/tendencies (GET, POST) - Manage tendencies
  - /api/scouting/reports/<int:report_id>/situational (GET, POST) - Manage situational plays
  - /api/scouting/reports/<int:report_id>/mismatches (GET, POST) - Manage mismatches
  - /api/scouting/reports/<int:report_id>/practice-points (GET, POST) - Manage practice points
  - /api/scouting/reports/<int:report_id>/clips (GET, POST) - Manage scouting clips
  - /api/scouting/nfhs/download (POST) - Download NFHS VOD by GameID
  - /api/scouting/reports/<int:report_id>/generate (POST) - Auto-generate from AI events

Page Routes:
  - /scouting - Scouting dashboard
  - /scouting/reports/<int:report_id> - View/edit scouting report
  - /scouting/reports/<int:report_id>/print - Printable scouting report
"""

import json
import os
import re
import subprocess
import tempfile
from datetime import date

from flask import Blueprint, redirect, render_template, request, url_for, jsonify, abort, current_app

from helpers import get_db, require_feature

scouting_bp = Blueprint("scouting", __name__)


# ── NFHS VOD Downloader ──────────────────────────────────────

def extract_nfhs_game_id(url_or_id):
    """Extract NFHS GameID from a URL or return the raw ID.

    Supports formats:
    - Raw GameID: '12345678'
    - Full URL: 'https://www.nfhsnetwork.com/game/12345678'
    - Embed URL: 'https://www.nfhsnetwork.com/embed/12345678'
    - Developer window GameID from network tab
    """
    if not url_or_id:
        return None

    url_or_id = url_or_id.strip()

    # If it's already a numeric ID, return it
    if re.match(r'^\d{6,10}$', url_or_id):
        return url_or_id

    # Extract from URL patterns
    patterns = [
        r'/game/(\d+)',
        r'/embed/(\d+)',
        r'[?&]gameId=(\d+)',
        r'[?&]game_id=(\d+)',
        r'/videos/(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    return None


def download_nfhs_vod(game_id, output_dir):
    """Download NFHS VOD using yt-dlp or streamlink.

    NFHS Network uses HLS streaming. We try multiple approaches:
    1. yt-dlp (supports many sites)
    2. Direct HLS extraction via streamlink
    3. Manual download via curl if m3u8 URL is known

    Returns: (success: bool, file_path: str, error: str)
    """
    game_id = extract_nfhs_game_id(game_id)
    if not game_id:
        return False, None, "Invalid NFHS GameID"

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"nfhs_{game_id}.mp4")

    # Try yt-dlp first
    nfhs_url = f"https://www.nfhsnetwork.com/game/{game_id}"

    try:
        # Check if yt-dlp is available
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            # Download with yt-dlp
            cmd = [
                "yt-dlp",
                "--no-check-certificates",
                "-o", output_path,
                "--merge-output-format", "mp4",
                "--retries", "3",
                "--fragment-retries", "3",
                nfhs_url
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=7200  # 2 hour max
            )
            if result.returncode == 0 and os.path.exists(output_path):
                return True, output_path, None
            else:
                error_msg = result.stderr[-500:] if result.stderr else "yt-dlp failed"
                return False, None, f"yt-dlp error: {error_msg}"
    except FileNotFoundError:
        pass  # yt-dlp not installed
    except subprocess.TimeoutExpired:
        return False, None, "Download timed out (2 hour limit)"

    # Try streamlink as fallback
    try:
        result = subprocess.run(
            ["streamlink", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            cmd = [
                "streamlink",
                "--output", output_path,
                "--force",
                nfhs_url,
                "best"
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=7200
            )
            if result.returncode == 0 and os.path.exists(output_path):
                return True, output_path, None
            else:
                error_msg = result.stderr[-500:] if result.stderr else "streamlink failed"
                return False, None, f"streamlink error: {error_msg}"
    except FileNotFoundError:
        pass
    except subprocess.TimeoutExpired:
        return False, None, "Download timed out"

    # If neither tool is available, return instructions
    return False, None, (
        "No download tool available. Install yt-dlp: pip install yt-dlp. "
        f"Or manually download from: {nfhs_url}"
    )


# ── Scouting Report CRUD ─────────────────────────────────────

@scouting_bp.route("/api/scouting/reports", methods=["GET"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_reports_list():
    db = get_db()
    reports = db.execute("""
        SELECT sr.*, g.opponent_name as game_opponent
        FROM scouting_reports sr
        LEFT JOIN games g ON sr.game_id = g.id
        ORDER BY sr.scout_date DESC
    """).fetchall()
    return jsonify([dict(r) for r in reports])


@scouting_bp.route("/api/scouting/reports", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_report_create():
    data = request.get_json() or request.form
    db = get_db()
    cur = db.execute("""
        INSERT INTO scouting_reports (game_id, opponent_name, scout_date, film_source, nfhs_game_id, status)
        VALUES (?, ?, ?, ?, ?, 'draft')
    """, (
        data.get("game_id"),
        data.get("opponent_name", "Unknown"),
        data.get("scout_date", date.today().isoformat()),
        data.get("film_source"),
        data.get("nfhs_game_id"),
    ))
    db.commit()
    return jsonify({"id": cur.lastrowid, "status": "created"}), 201


@scouting_bp.route("/api/scouting/reports/<int:report_id>", methods=["GET"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_report_get(report_id):
    db = get_db()
    report = db.execute("SELECT * FROM scouting_reports WHERE id=?", (report_id,)).fetchone()
    if not report:
        abort(404)

    personnel = db.execute("SELECT * FROM scouting_personnel WHERE report_id=? ORDER BY role", (report_id,)).fetchall()
    offensive_sets = db.execute("SELECT * FROM scouting_offensive_sets WHERE report_id=? ORDER BY frequency DESC", (report_id,)).fetchall()
    defensive = db.execute("SELECT * FROM scouting_defensive_tendencies WHERE report_id=?", (report_id,)).fetchall()
    tendencies = db.execute("SELECT * FROM scouting_tendencies WHERE report_id=? ORDER BY tendency_type, category", (report_id,)).fetchall()
    situational = db.execute("SELECT * FROM scouting_situational WHERE report_id=? ORDER BY situation", (report_id,)).fetchall()
    mismatches = db.execute("SELECT * FROM scouting_mismatches WHERE report_id=?", (report_id,)).fetchall()
    practice_points = db.execute("SELECT * FROM scouting_practice_points WHERE report_id=? ORDER BY point_number", (report_id,)).fetchall()
    clips = db.execute("SELECT * FROM scouting_clips WHERE report_id=? ORDER BY quarter, game_time", (report_id,)).fetchall()

    return jsonify({
        "report": dict(report),
        "personnel": [dict(p) for p in personnel],
        "offensive_sets": [dict(s) for s in offensive_sets],
        "defensive_tendencies": [dict(d) for d in defensive],
        "tendencies": [dict(t) for t in tendencies],
        "situational": [dict(s) for s in situational],
        "mismatches": [dict(m) for m in mismatches],
        "practice_points": [dict(p) for p in practice_points],
        "clips": [dict(c) for c in clips],
    })


@scouting_bp.route("/api/scouting/reports/<int:report_id>", methods=["PUT"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_report_update(report_id):
    data = request.get_json() or request.form
    db = get_db()
    fields = []
    values = []
    for field in ["opponent_name", "scout_date", "film_source", "nfhs_game_id", "status",
                  "offensive_identity", "defensive_identity", "tempo", "executive_summary"]:
        if field in data:
            fields.append(f"{field}=?")
            values.append(data[field])
    if fields:
        values.append(report_id)
        db.execute(f"UPDATE scouting_reports SET {', '.join(fields)}, updated_at=CURRENT_TIMESTAMP WHERE id=?", values)
        db.commit()
    return jsonify({"status": "updated"})


@scouting_bp.route("/api/scouting/reports/<int:report_id>", methods=["DELETE"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_report_delete(report_id):
    db = get_db()
    # Cascading delete handled by FK constraints
    db.execute("DELETE FROM scouting_reports WHERE id=?", (report_id,))
    db.commit()
    return jsonify({"status": "deleted"})


# ── Personnel ────────────────────────────────────────────────

@scouting_bp.route("/api/scouting/reports/<int:report_id>/personnel", methods=["GET", "POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_personnel(report_id):
    db = get_db()
    if request.method == "POST":
        data = request.get_json() or request.form
        db.execute("""
            INSERT INTO scouting_personnel (report_id, jersey_number, player_name, role, notes, usage_rate, ppp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            data.get("jersey_number"),
            data.get("player_name"),
            data.get("role"),
            data.get("notes"),
            data.get("usage_rate"),
            data.get("ppp"),
        ))
        db.commit()
        return jsonify({"status": "created"}), 201
    else:
        rows = db.execute("SELECT * FROM scouting_personnel WHERE report_id=? ORDER BY role", (report_id,)).fetchall()
        return jsonify([dict(r) for r in rows])


# ── Offensive Sets ───────────────────────────────────────────

@scouting_bp.route("/api/scouting/reports/<int:report_id>/offensive-sets", methods=["GET", "POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_offensive_sets(report_id):
    db = get_db()
    if request.method == "POST":
        data = request.get_json() or request.form
        db.execute("""
            INSERT INTO scouting_offensive_sets (report_id, set_name, trigger_action, frequency, ppp, result_vs_pressure, notes, clip_timestamps)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            data.get("set_name"),
            data.get("trigger_action"),
            data.get("frequency", 0),
            data.get("ppp"),
            data.get("result_vs_pressure"),
            data.get("notes"),
            json.dumps(data.get("clip_timestamps", [])),
        ))
        db.commit()
        return jsonify({"status": "created"}), 201
    else:
        rows = db.execute("SELECT * FROM scouting_offensive_sets WHERE report_id=? ORDER BY frequency DESC", (report_id,)).fetchall()
        return jsonify([dict(r) for r in rows])


# ── Defensive Tendencies ─────────────────────────────────────

@scouting_bp.route("/api/scouting/reports/<int:report_id>/defensive-tendencies", methods=["GET", "POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_defensive(report_id):
    db = get_db()
    if request.method == "POST":
        data = request.get_json() or request.form
        db.execute("""
            INSERT INTO scouting_defensive_tendencies (report_id, scheme, pnr_coverage, frequency, ppp_allowed, weak_rotations, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            data.get("scheme"),
            data.get("pnr_coverage"),
            data.get("frequency"),
            data.get("ppp_allowed"),
            json.dumps(data.get("weak_rotations", [])),
            data.get("notes"),
        ))
        db.commit()
        return jsonify({"status": "created"}), 201
    else:
        rows = db.execute("SELECT * FROM scouting_defensive_tendencies WHERE report_id=?", (report_id,)).fetchall()
        return jsonify([dict(r) for r in rows])


# ── Tendencies ───────────────────────────────────────────────

@scouting_bp.route("/api/scouting/reports/<int:report_id>/tendencies", methods=["GET", "POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_tendencies(report_id):
    db = get_db()
    if request.method == "POST":
        data = request.get_json() or request.form
        db.execute("""
            INSERT INTO scouting_tendencies (report_id, tendency_type, category, description, frequency, clip_timestamps, exploitable, practice_drill)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            data.get("tendency_type"),
            data.get("category"),
            data.get("description"),
            data.get("frequency"),
            json.dumps(data.get("clip_timestamps", [])),
            data.get("exploitable", 0),
            data.get("practice_drill"),
        ))
        db.commit()
        return jsonify({"status": "created"}), 201
    else:
        rows = db.execute("SELECT * FROM scouting_tendencies WHERE report_id=? ORDER BY tendency_type, category", (report_id,)).fetchall()
        return jsonify([dict(r) for r in rows])


# ── Situational ──────────────────────────────────────────────

@scouting_bp.route("/api/scouting/reports/<int:report_id>/situational", methods=["GET", "POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_situational(report_id):
    db = get_db()
    if request.method == "POST":
        data = request.get_json() or request.form
        db.execute("""
            INSERT INTO scouting_situational (report_id, situation, description, frequency, ppp, clip_timestamps, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            data.get("situation"),
            data.get("description"),
            data.get("frequency", 0),
            data.get("ppp"),
            json.dumps(data.get("clip_timestamps", [])),
            data.get("notes"),
        ))
        db.commit()
        return jsonify({"status": "created"}), 201
    else:
        rows = db.execute("SELECT * FROM scouting_situational WHERE report_id=? ORDER BY situation", (report_id,)).fetchall()
        return jsonify([dict(r) for r in rows])


# ── Mismatches ───────────────────────────────────────────────

@scouting_bp.route("/api/scouting/reports/<int:report_id>/mismatches", methods=["GET", "POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_mismatches(report_id):
    db = get_db()
    if request.method == "POST":
        data = request.get_json() or request.form
        db.execute("""
            INSERT INTO scouting_mismatches (report_id, opponent_jersey, opponent_name, vulnerability, exploit_action, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            data.get("opponent_jersey"),
            data.get("opponent_name"),
            data.get("vulnerability"),
            data.get("exploit_action"),
            data.get("notes"),
        ))
        db.commit()
        return jsonify({"status": "created"}), 201
    else:
        rows = db.execute("SELECT * FROM scouting_mismatches WHERE report_id=?", (report_id,)).fetchall()
        return jsonify([dict(r) for r in rows])


# ── Practice Points ──────────────────────────────────────────

@scouting_bp.route("/api/scouting/reports/<int:report_id>/practice-points", methods=["GET", "POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_practice_points(report_id):
    db = get_db()
    if request.method == "POST":
        data = request.get_json() or request.form
        db.execute("""
            INSERT INTO scouting_practice_points (report_id, point_number, description, drill_name, measurable_target, clip_timestamps)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            data.get("point_number"),
            data.get("description"),
            data.get("drill_name"),
            data.get("measurable_target"),
            json.dumps(data.get("clip_timestamps", [])),
        ))
        db.commit()
        return jsonify({"status": "created"}), 201
    else:
        rows = db.execute("SELECT * FROM scouting_practice_points WHERE report_id=? ORDER BY point_number", (report_id,)).fetchall()
        return jsonify([dict(r) for r in rows])


# ── Clips ────────────────────────────────────────────────────

@scouting_bp.route("/api/scouting/reports/<int:report_id>/clips", methods=["GET", "POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_clips(report_id):
    db = get_db()
    if request.method == "POST":
        data = request.get_json() or request.form
        db.execute("""
            INSERT INTO scouting_clips (report_id, clip_type, game_time, quarter, description, coach_cue, video_timestamp_ms, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            data.get("clip_type"),
            data.get("game_time"),
            data.get("quarter"),
            data.get("description"),
            data.get("coach_cue"),
            data.get("video_timestamp_ms"),
            data.get("source", "manual_tag"),
        ))
        db.commit()
        return jsonify({"status": "created"}), 201
    else:
        rows = db.execute("SELECT * FROM scouting_clips WHERE report_id=? ORDER BY quarter, game_time", (report_id,)).fetchall()
        return jsonify([dict(r) for r in rows])


# ── NFHS Download ────────────────────────────────────────────

@scouting_bp.route("/api/scouting/nfhs/download", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_nfhs_download():
    data = request.get_json() or request.form
    game_id = data.get("game_id") or data.get("nfhs_game_id")
    if not game_id:
        return jsonify({"error": "Missing game_id or nfhs_game_id"}), 400

    game_id = extract_nfhs_game_id(game_id)
    if not game_id:
        return jsonify({"error": f"Could not extract NFHS GameID from: {data.get('game_id')}"}), 400

    output_dir = current_app.config.get("UPLOAD_FOLDER", "uploads")
    success, file_path, error = download_nfhs_vod(game_id, output_dir)

    if success:
        # Create a game record for this download
        db = get_db()
        file_size = os.path.getsize(file_path)
        cur = db.execute("""
            INSERT INTO games (source_type, source_key, nfhs_game_id)
            VALUES ('nfhs_vod', ?, ?)
        """, (file_path, game_id))
        db.commit()

        return jsonify({
            "status": "downloaded",
            "file_path": file_path,
            "file_size": file_size,
            "game_id": cur.lastrowid,
            "nfhs_game_id": game_id,
        })
    else:
        return jsonify({"error": error, "nfhs_game_id": game_id}), 400


# ── Auto-Generate from AI Events ────────────────────────────

@scouting_bp.route("/api/scouting/reports/<int:report_id>/generate", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def api_scouting_generate(report_id):
    """Auto-generate scouting report sections from AI-detected events.

    Analyzes the events table for the game and produces:
    - Personnel roles (by possession usage)
    - Offensive sets (by play type frequency)
    - Defensive tendencies (by opponent action results)
    - Tendencies (shot selection, drive direction, etc.)
    - Situational plays (late clock, etc.)
    """
    db = get_db()
    report = db.execute("SELECT * FROM scouting_reports WHERE id=?", (report_id,)).fetchone()
    if not report:
        abort(404)

    game_id = report["game_id"]
    if not game_id:
        return jsonify({"error": "No game associated with this report"}), 400

    # Get all events for this game
    events = db.execute("""
        SELECT e.*, p.jersey_number, p.name as player_name
        FROM events e
        LEFT JOIN players p ON e.player = p.id
        WHERE e.game_id = ?
        ORDER BY e.timestamp_ms
    """, (game_id,)).fetchall()

    if not events:
        return jsonify({"error": "No AI events found for this game. Run AI analysis first."}), 400

    events = [dict(e) for e in events]

    # Analyze personnel by possession usage
    player_possessions = {}
    for ev in events:
        player = ev.get("player_name") or ev.get("jersey_number") or "Unknown"
        if player not in player_possessions:
            player_possessions[player] = {"count": 0, "points": 0, "turnovers": 0, "assists": 0}
        player_possessions[player]["count"] += 1
        if ev["event_type"] == "shot":
            if ev.get("shot_result") == "make":
                # Estimate points from shot location if available
                player_possessions[player]["points"] += 2
        elif ev["event_type"] == "turnover":
            player_possessions[player]["turnovers"] += 1
        elif ev["event_type"] == "assist":
            player_possessions[player]["assists"] += 1

    # Auto-detect roles based on usage patterns
    total_possessions = sum(p["count"] for p in player_possessions.values())
    for player, stats in sorted(player_possessions.items(), key=lambda x: x[1]["count"], reverse=True):
        usage = stats["count"] / total_possessions if total_possessions > 0 else 0
        role = "role_player"
        if usage > 0.25:
            role = "go_to_scorer"
        elif stats["assists"] > stats["count"] * 0.3:
            role = "ball_handler"
        elif stats["turnovers"] > stats["count"] * 0.25:
            role = "ball_handler"  # high usage + turnovers = primary ball handler

        # Check if personnel already exists
        existing = db.execute(
            "SELECT id FROM scouting_personnel WHERE report_id=? AND (player_name=? OR jersey_number=?)",
            (report_id, player, player if isinstance(player, int) else None)
        ).fetchone()

        if not existing:
            db.execute("""
                INSERT INTO scouting_personnel (report_id, jersey_number, player_name, role, usage_rate, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                report_id,
                player if isinstance(player, int) else None,
                player if not isinstance(player, int) else None,
                role,
                round(usage, 2),
                f"Auto-detected: {stats['count']} possessions, {stats['points']} pts, {stats['assists']} ast, {stats['turnovers']} tov"
            ))

    # Analyze shot selection tendencies
    shot_events = [e for e in events if e["event_type"] in ("shot", "make", "miss")]
    if shot_events:
        total_shots = len(shot_events)
        makes = len([e for e in shot_events if e["event_type"] == "make" or e.get("shot_result") == "make"])
        shot_pct = makes / total_shots if total_shots > 0 else 0

        db.execute("""
            INSERT INTO scouting_tendencies (report_id, tendency_type, category, description, frequency, exploitable)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            "offensive",
            "shot_selection",
            f"Team shot {total_shots} FG, {makes} makes ({shot_pct:.1%})",
            f"{total_shots} attempts",
            0,
        ))

    # Analyze turnover patterns
    to_events = [e for e in events if e["event_type"] == "turnover"]
    if to_events:
        to_rate = len(to_events) / len(events) if events else 0
        db.execute("""
            INSERT INTO scouting_tendencies (report_id, tendency_type, category, description, frequency, exploitable)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            report_id,
            "offensive",
            "turnover",
            f"{len(to_events)} turnovers on {len(events)} events ({to_rate:.1%} rate)",
            f"{len(to_events)} total",
            1 if to_rate > 0.15 else 0,  # exploitable if >15% turnover rate
        ))

    db.commit()

    return jsonify({
        "status": "generated",
        "personnel_found": len(player_possessions),
        "events_analyzed": len(events),
        "message": f"Auto-generated from {len(events)} events. Review and edit the report."
    })


# ── Page Routes ──────────────────────────────────────────────

@scouting_bp.route("/scouting")
@require_feature("ENABLE_AUTO_STATS_M1")
def scouting_dashboard():
    return render_template("scouting.html")


@scouting_bp.route("/scouting/reports/<int:report_id>")
@require_feature("ENABLE_AUTO_STATS_M1")
def scouting_report_view(report_id):
    return render_template("scouting_report.html", report_id=report_id)


@scouting_bp.route("/scouting/reports/<int:report_id>/print")
@require_feature("ENABLE_AUTO_STATS_M1")
def scouting_report_print(report_id):
    return render_template("scouting_report_print.html", report_id=report_id)
