"""
Core Blueprint
==============

This blueprint contains all core/domain routes for the Liberty Basketball Analysis
application. These are the main page-rendering and utility routes that don't belong
to a specific API subdomain.

Routes included:
- index (/)                          – Home page
- schedule (/schedule)               – Season/game schedule management
- schedule_save_season (/schedule/seasons/save POST)
- schedule_delete_season (/schedule/seasons/<int:season_id>/delete POST)
- schedule_save_game (/schedule/games/save POST)
- schedule_delete_game (/schedule/games/<int:game_id>/delete POST)
- videos_page (/videos)              – Video listing page
- film (/film, /film/<filename>)    – Film tool page
- uploaded_file (/uploads/<filename>) – Serve uploaded files
- settings_page (/settings GET POST) – Application settings
- custom_weights_guide_page (/settings/custom-weights)
- pull_ollama_model (/settings/ollama/pull POST)
- debug_page (/debug)                – Debug/issues page
- create_issue_report (/debug/issues POST)
- complete_issue_report (/debug/issues/<int:issue_id>/complete POST)
- api_dashboard (/api/dashboard)     – Dashboard JSON API
- api_resource_status (/api/resource-status) – Resource status JSON API
- status_page (/status)              – Live analysis status page
- dashboard_page (/dashboard)        – Dashboard page
- users_page (/users)                – Users page
- admin_reset (/api/admin/reset POST) – Admin reset endpoint
"""

import os
import re
import sqlite3
import subprocess

from flask import Blueprint, current_app, redirect, render_template, request, url_for, jsonify, send_from_directory

from helpers import (
    AI_DEFAULTS,
    build_resource_status,
    build_settings_catalog,
    extract_local_path,
    get_db,
    get_runtime_settings,
    read_filtered_app_logs,
    render_schedule_page,
    require_feature,
    safe_return_path,
    append_query_params,
    save_settings,
)

core = Blueprint("core", __name__)


@core.route("/")
def index():
    return render_template("index.html")


@core.route("/schedule")
@require_feature("ENABLE_SEASONS_SCHEDULE")
def schedule():
    return render_schedule_page(
        message=request.args.get("message"),
        error=request.args.get("error"),
        edit_game_id=request.args.get("edit_game_id", type=int),
        edit_season_id=request.args.get("edit_season_id", type=int),
    )


@core.route("/schedule/seasons/save", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def schedule_save_season():
    form = request.form
    season_id = form.get("season_id", "").strip()
    name = (form.get("name") or "").strip()
    start_date = (form.get("start_date") or "").strip()
    end_date = (form.get("end_date") or "").strip()

    if not name or not start_date or not end_date:
        return render_schedule_page(
            error="Season name, start date, and end date are required.",
            edit_season_id=int(season_id) if season_id else None,
            season_form_data={
                "id": season_id,
                "name": name,
                "start_date": start_date,
                "end_date": end_date,
            },
        ), 400

    db = get_db()
    try:
        if season_id:
            db.execute(
                "UPDATE seasons SET name=?, start_date=?, end_date=? WHERE id=?",
                (name, start_date, end_date, int(season_id)),
            )
            message = "Season updated."
        else:
            db.execute(
                "INSERT INTO seasons (name, start_date, end_date) VALUES (?,?,?)",
                (name, start_date, end_date),
            )
            message = "Season created."
        db.commit()
    except sqlite3.IntegrityError:
        return render_schedule_page(
            error="Season name already exists.",
            edit_season_id=int(season_id) if season_id else None,
            season_form_data={
                "id": season_id,
                "name": name,
                "start_date": start_date,
                "end_date": end_date,
            },
        ), 409

    return redirect(url_for("core.schedule", message=message))


@core.route("/schedule/seasons/<int:season_id>/delete", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def schedule_delete_season(season_id):
    db = get_db()
    db.execute("DELETE FROM scheduled_games WHERE season_id=?", (season_id,))
    db.execute("DELETE FROM seasons WHERE id=?", (season_id,))
    db.commit()
    return redirect(url_for("core.schedule", message="Season deleted."))


@core.route("/schedule/games/save", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def schedule_save_game():
    form = request.form
    filters = {
        "season_id": int(form["filter_season_id"]) if form.get("filter_season_id") else None,
        "level": (form.get("filter_level") or "").strip(),
        "gender": (form.get("filter_gender") or "").strip(),
        "status": (form.get("filter_status") or "").strip(),
    }
    game_id = form.get("game_id", "").strip()
    season_id = form.get("season_id", "").strip()
    game_date = (form.get("game_date") or "").strip()
    opponent_name = (form.get("opponent_name") or "").strip()

    if not season_id or not game_date or not opponent_name:
        return render_schedule_page(
            error="Season, date, and opponent are required.",
            filters=filters,
            edit_game_id=int(game_id) if game_id else None,
            game_form_data={
                "id": game_id,
                "season_id": season_id,
                "program_name": (form.get("program_name") or "Liberty").strip(),
                "gender": (form.get("gender") or "boys").strip(),
                "level": (form.get("level") or "jr_high").strip(),
                "game_date": game_date,
                "game_time": (form.get("game_time") or "").strip(),
                "location_type": (form.get("location_type") or "home").strip(),
                "opponent_name": opponent_name,
                "tournament_name": (form.get("tournament_name") or "").strip(),
                "status": (form.get("status") or "scheduled").strip(),
                "notes": (form.get("notes") or "").strip(),
            },
        ), 400

    db = get_db()
    values = (
        int(season_id),
        (form.get("program_name") or "Liberty").strip() or "Liberty",
        (form.get("gender") or "boys").strip() or "boys",
        (form.get("level") or "jr_high").strip() or "jr_high",
        game_date,
        (form.get("game_time") or "").strip() or None,
        (form.get("location_type") or "home").strip() or "home",
        opponent_name,
        (form.get("tournament_name") or "").strip() or None,
        (form.get("status") or "scheduled").strip() or "scheduled",
        (form.get("notes") or "").strip() or None,
    )

    if game_id:
        db.execute(
            """UPDATE scheduled_games SET
               season_id=?, program_name=?, gender=?, level=?, game_date=?, game_time=?,
               location_type=?, opponent_name=?, tournament_name=?, status=?, notes=?,
               updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            values + (int(game_id),),
        )
        message = "Scheduled game updated."
    else:
        db.execute(
            """INSERT INTO scheduled_games
               (season_id, program_name, gender, level, game_date, game_time,
                location_type, opponent_name, tournament_name, status, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
        message = "Scheduled game created."
    db.commit()

    return redirect(
        url_for(
            "core.schedule",
            season_id=filters["season_id"],
            level=filters["level"] or None,
            gender=filters["gender"] or None,
            status=filters["status"] or None,
            message=message,
        )
    )


@core.route("/schedule/games/<int:game_id>/delete", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def schedule_delete_game(game_id):
    filters = {
        "season_id": request.form.get("filter_season_id", type=int),
        "level": (request.form.get("filter_level") or "").strip(),
        "gender": (request.form.get("filter_gender") or "").strip(),
        "status": (request.form.get("filter_status") or "").strip(),
    }
    db = get_db()
    db.execute("DELETE FROM scheduled_games WHERE id=?", (game_id,))
    db.commit()
    return redirect(
        url_for(
            "core.schedule",
            season_id=filters["season_id"],
            level=filters["level"] or None,
            gender=filters["gender"] or None,
            status=filters["status"] or None,
            message="Scheduled game deleted.",
        )
    )


# ── PDF Import ──────────────────────────────────────────

@core.route("/api/schedule/import-pdf", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def schedule_import_pdf():
    if "pdf" not in request.files:
        return {"error": "No PDF file provided"}, 400
    pdf_file = request.files["pdf"]
    if not pdf_file.filename.lower().endswith(".pdf"):
        return {"error": "File must be a PDF"}, 400
    try:
        import io
        try:
            import pdfplumber
            text = ""
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except ImportError:
            try:
                import PyPDF2
                reader = PyPDF2.PdfReader(pdf_file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() or ""
            except ImportError:
                return {"error": "PDF parsing requires pdfplumber or PyPDF2. Install with: pip install pdfplumber"}, 500
        if not text.strip():
            return {"error": "Could not extract text from PDF. Try a different file."}, 400
        games = _parse_schedule_text(text)
        return {"games": games}
    except Exception as e:
        return {"error": f"Failed to parse PDF: {str(e)}"}, 500


def _parse_schedule_text(text):
    """Parse extracted PDF text into game dicts. Handles common schedule formats."""
    import re, datetime
    games = []
    lines = text.splitlines()
    for line in lines:
        line = line.strip()
        if not line or len(line) < 10:
            continue
        game = _parse_schedule_line(line)
        if game:
            games.append(game)
    return games


def _parse_schedule_line(line):
    """Try to parse a single line of schedule text into a game dict."""
    import re, datetime
    # Pattern: date (various formats) + opponent + optional time + optional location
    date_patterns = [
        r'(\d{1,2}/\d{1,2}/\d{2,4})',
        r'(\d{4}-\d{2}-\d{2})',
        r'(\w+\s+\d{1,2},?\s+\d{4})',
        r'(\d{1,2}\s+\w+\s+\d{4})',
    ]
    date_str = None
    for pat in date_patterns:
        m = re.search(pat, line)
        if m:
            date_str = m.group(1)
            break
    if not date_str:
        return None
    # Normalize date
    game_date = None
    for fmt in ['%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d', '%B %d, %Y', '%b %d, %Y', '%d %B %Y', '%d %b %Y']:
        try:
            game_date = datetime.datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
            break
        except ValueError:
            continue
    if not game_date:
        return None
    # Detect opponent — text after date that looks like a team name
    remainder = line.replace(date_str, '', 1).strip()
    # Remove common prefixes (but NOT @ or at which are location markers)
    remainder = re.sub(r'^\s*[:\-–—]\s*', '', remainder)
    # Detect time
    time_str = None
    time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)', remainder)
    if time_match:
        time_str = time_match.group(1)
        remainder = remainder.replace(time_str, '').strip()
    # Detect level and gender from full remainder BEFORE extracting opponent
    level = 'jr_high'
    level_lower = remainder.lower()
    if 'varsity' in level_lower:
        level = 'varsity'
    elif 'junior varsity' in level_lower or ' jv ' in level_lower:
        level = 'jv'
    gender = 'boys'
    if 'girls' in level_lower:
        gender = 'girls'

    # Detect location keywords
    location_type = 'home'
    loc_match = re.search(r'(?:\s|^)(@|at|vs\.?)\s+', remainder, re.IGNORECASE)
    if loc_match:
        pre_loc = remainder[:loc_match.start()].strip()
        post_loc = remainder[loc_match.end():].strip()
        if loc_match.group(1).lower() in ('@', 'at'):
            location_type = 'away'
            opponent = post_loc
        else:
            pre_loc_clean = re.sub(r'\b(versus|vs\.?)\b', '', pre_loc, flags=re.IGNORECASE).strip()
            # Check if pre_loc_clean is only a level/gender keyword
            pre_is_only_keyword = not re.sub(r'\b(varsity|jv|junior varsity|boys|girls|freshman)\b', '', pre_loc_clean, flags=re.IGNORECASE).strip()
            if not pre_loc_clean and post_loc:
                opponent = post_loc
            elif pre_is_only_keyword and post_loc:
                opponent = post_loc
            else:
                opponent = pre_loc_clean if pre_loc_clean else post_loc
    else:
        opponent = remainder

    # Clean up opponent — remove level/gender markers
    opponent = re.sub(r'\b(varsity|jv|junior varsity|boys|girls|freshman)\b', '', opponent, flags=re.IGNORECASE).strip()
    opponent = re.sub(r'\s+', ' ', opponent).strip()
    opponent = re.sub(r'[,;:\-–—]+$', '', opponent).strip()
    # Normalize time
    game_time = None
    if time_str:
        try:
            for fmt in ['%I:%M %p', '%I:%M%p', '%I:%M', '%H:%M']:
                try:
                    game_time = datetime.datetime.strptime(time_str.strip(), fmt).strftime('%H:%M')
                    break
                except ValueError:
                    continue
        except Exception:
            pass
    return {
        "game_date": game_date,
        "game_time": game_time or "",
        "opponent_name": opponent,
        "level": level,
        "gender": gender,
        "location_type": location_type,
        "status": "scheduled",
        "notes": "",
    }


@core.route("/api/schedule/import-pdf/confirm", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def schedule_import_pdf_confirm():
    data = request.get_json(force=True)
    games = data.get("games", [])
    if not games:
        return {"error": "No games to import"}, 400
    db = get_db()
    imported = 0
    errors = []
    # Get or create a default season
    season_id = _get_or_create_default_season(db)
    for i, g in enumerate(games):
        game_date = (g.get("game_date") or "").strip()
        opponent = (g.get("opponent_name") or "").strip()
        if not game_date or not opponent:
            errors.append(f"Row {i+1}: date and opponent required")
            continue
        try:
            db.execute(
                """INSERT INTO scheduled_games
                   (season_id, program_name, gender, level, game_date, game_time,
                    location_type, opponent_name, status, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    season_id,
                    "Liberty",
                    (g.get("gender") or "boys").strip(),
                    (g.get("level") or "jr_high").strip(),
                    game_date,
                    (g.get("game_time") or "").strip() or None,
                    (g.get("location_type") or "home").strip(),
                    opponent,
                    "scheduled",
                    (g.get("notes") or "").strip() or None,
                ),
            )
            imported += 1
        except Exception as e:
            errors.append(f"Row {i+1}: {str(e)}")
    db.commit()
    if errors:
        return {"imported": imported, "errors": errors}, 200
    return {"imported": imported, "message": f"Imported {imported} games"}


def _get_or_create_default_season(db):
    """Get the most recent season, or create a default one."""
    row = db.execute("SELECT id FROM seasons ORDER BY start_date DESC LIMIT 1").fetchone()
    if row:
        return row["id"]
    import datetime
    year = datetime.date.today().year
    cur = db.execute(
        "INSERT INTO seasons (name, start_date, end_date) VALUES (?,?,?)",
        (f"{year}-{year+1} Season", f"{year}-09-01", f"{year+1}-06-30"),
    )
    db.commit()
    return cur.lastrowid


# ── MaxPreps Export ──────────────────────────────────────

@core.route("/schedule/export/maxpreps")
@require_feature("ENABLE_SEASONS_SCHEDULE")
def schedule_export_maxpreps():
    db = get_db()
    games = db.execute(
        """SELECT sg.id, sg.game_date, sg.game_time, sg.opponent_name,
                  sg.level, sg.gender, sg.location_type, sg.status, sg.program_name,
                  s.name as season_name
           FROM scheduled_games sg
           JOIN seasons s ON s.id = sg.season_id
           WHERE sg.status = 'scheduled'
           ORDER BY sg.game_date, sg.game_time"""
    ).fetchall()
    # Build CSV in MaxPreps-compatible format
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    # MaxPreps standard columns
    writer.writerow([
        "Date", "Time", "Opponent", "Location", "Level", "Gender", "Conference", "Season"
    ])
    for g in games:
        location = "Away" if g["location_type"] == "away" else "Home"
        writer.writerow([
            g["game_date"],
            g["game_time"] or "",
            g["opponent_name"],
            location,
            _level_display_name(g["level"]),
            _gender_display_name(g["gender"]),
            "No",
            g["season_name"] or "",
        ])
    response = output.getvalue()
    from flask import Response
    return Response(
        response,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=maxpreps_schedule_export.csv"},
    )


def _level_display_name(val):
    mapping = {"jr_high": "Jr High", "jv": "JV", "varsity": "Varsity"}
    return mapping.get(val, val)


def _gender_display_name(val):
    mapping = {"boys": "Boys", "girls": "Girls"}
    return mapping.get(val, val)


@core.route("/videos")
@require_feature("ENABLE_AUTO_STATS_M1")
def videos_page():
    return render_template("videos.html")


@core.route("/film")
@core.route("/film/<filename>")
@require_feature("ENABLE_MANUAL_TAG_MVP")
def film(filename=None):
    game_id = (request.args.get("game_id") or "").strip() or None
    if filename and not game_id:
        db = get_db()
        # Find the most recent analysis run for this video file
        row = db.execute(
            "SELECT game_id FROM analysis_runs WHERE video_path LIKE ? ORDER BY id DESC LIMIT 1",
            (f"%{filename}",),
        ).fetchone()
        if row:
            game_id = row["game_id"]
    return render_template(
        "film_tool.html",
        filename=filename,
        game_id=game_id,
        uploaded_video_url=url_for("core.uploaded_file", filename=filename) if filename else None,
    )


@core.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@core.route("/settings", methods=["GET", "POST"])
def settings_page():
    db = get_db()
    catalog = build_settings_catalog()
    runtime_settings = get_runtime_settings()

    if request.method == "POST":
        detector_values = {option["value"] for option in catalog["detector_options"]}
        device_values = {option["value"] for option in catalog["device_options"]}
        event_generator_mode_values = {option["value"] for option in catalog["event_generator_mode_options"]}
        llm_provider_values = {option["value"] for option in catalog["llm_provider_options"]}
        llm_model_values = {option["value"] for option in catalog["llm_model_options"]}

        updates = {}
        for flag_name in current_app.config.get("FEATURES", {}):
            updates[f"feature.{flag_name}"] = bool(request.form.get(f"feature_{flag_name}"))
        for option_name in current_app.config.get("ANALYSIS_CONFIG", {}):
            updates[f"analysis.{option_name}"] = bool(request.form.get(f"analysis_{option_name}"))

        detector_model = (request.form.get("ai_detector_model") or AI_DEFAULTS["detector_model"]).strip()
        updates["ai.detector_model"] = detector_model if detector_model in detector_values else AI_DEFAULTS["detector_model"]
        custom_detector_model = (request.form.get("ai_custom_detector_model") or "").strip()
        updates["ai.custom_detector_model"] = custom_detector_model

        inference_device = (request.form.get("ai_inference_device") or AI_DEFAULTS["inference_device"]).strip()
        if inference_device not in device_values:
            inference_device = AI_DEFAULTS["inference_device"]
        updates["ai.inference_device"] = inference_device

        event_generator_mode = (request.form.get("ai_event_generator_mode") or AI_DEFAULTS["event_generator_mode"]).strip()
        if event_generator_mode not in event_generator_mode_values:
            event_generator_mode = AI_DEFAULTS["event_generator_mode"]
        updates["ai.event_generator_mode"] = event_generator_mode

        try:
            frame_stride = max(1, int(request.form.get("ai_frame_stride", AI_DEFAULTS["frame_stride"])))
        except ValueError:
            frame_stride = AI_DEFAULTS["frame_stride"]
        updates["ai.frame_stride"] = frame_stride

        try:
            tracker_distance = max(1, int(request.form.get("ai_tracker_max_distance", AI_DEFAULTS["tracker_max_distance"])))
        except ValueError:
            tracker_distance = AI_DEFAULTS["tracker_max_distance"]
        updates["ai.tracker_max_distance"] = tracker_distance

        try:
            tracker_gap = max(1, int(request.form.get("ai_tracker_max_frame_gap", AI_DEFAULTS["tracker_max_frame_gap"])))
        except ValueError:
            tracker_gap = AI_DEFAULTS["tracker_max_frame_gap"]
        updates["ai.tracker_max_frame_gap"] = tracker_gap

        llm_provider = (request.form.get("ai_llm_provider") or "none").strip()
        if llm_provider not in llm_provider_values:
            llm_provider = "none"
        updates["ai.llm_provider"] = llm_provider

        llm_model = (request.form.get("ai_llm_model") or "").strip()
        if llm_provider == "ollama" and llm_model not in llm_model_values:
            llm_model = catalog["llm_model_options"][0]["value"] if catalog["llm_model_options"] else ""
        if llm_provider == "none":
            llm_model = ""
        updates["ai.llm_model"] = llm_model

        save_settings(db, updates)
        return redirect(url_for("core.settings_page", message="Settings saved."))

    return render_template(
        "settings.html",
        message=request.args.get("message"),
        runtime_settings=runtime_settings,
        catalog=catalog,
    )


@core.route("/settings/custom-weights")
def custom_weights_guide_page():
    return render_template("custom_weights_guide.html")


@core.route("/settings/ollama/pull", methods=["POST"])
def pull_ollama_model():
    model_name = (request.form.get("model_name") or "").strip()
    if not model_name or not re.fullmatch(r"[A-Za-z0-9._:-]+", model_name):
        return redirect(url_for("core.settings_page", message="Invalid Ollama model name."))

    log_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", model_name)
    log_path = f"/tmp/liberty-basketball-ollama-pull-{log_slug}.log"
    try:
        with open(log_path, "ab") as log_file:
            subprocess.Popen(
                ["ollama", "pull", model_name],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except FileNotFoundError:
        return redirect(url_for("core.settings_page", message="Ollama is not installed in the current environment."))
    return redirect(
        url_for(
            "core.settings_page",
            message=f"Started pulling {model_name}. Refresh settings later to see it in the installed models list. Log: {log_path}",
        )
    )


@core.route("/debug")
def debug_page():
    db = get_db()
    entry_type = (request.args.get("entry_type") or "all").strip()
    entry_status = (request.args.get("entry_status") or "all").strip()
    query = (request.args.get("q") or "").strip()
    log_query = (request.args.get("log_query") or "").strip()

    sql_query = "SELECT * FROM issue_reports WHERE 1=1"
    params = []
    if entry_type != "all":
        sql_query += " AND entry_type = ?"
        params.append(entry_type)
    if entry_status != "all":
        sql_query += " AND status = ?"
        params.append(entry_status)
    if query:
        sql_query += " AND (title LIKE ? OR details LIKE ? OR COALESCE(source_path, '') LIKE ? OR COALESCE(browser_console, '') LIKE ?)"
        wildcard = f"%{query}%"
        params.extend([wildcard, wildcard, wildcard, wildcard])
    sql_query += " ORDER BY CASE WHEN status = 'open' THEN 0 ELSE 1 END, created_at DESC, id DESC"

    issue_reports = db.execute(sql_query, params).fetchall()
    recent_failures = db.execute(
        """SELECT id, game_id, error_message, started_at, completed_at
           FROM analysis_runs
           WHERE error_message IS NOT NULL AND TRIM(error_message) != ''
           ORDER BY id DESC
           LIMIT 20"""
    ).fetchall()
    app_log_lines = read_filtered_app_logs(log_query, limit=250)

    return render_template(
        "debug_issues.html",
        issue_reports=issue_reports,
        recent_failures=recent_failures,
        app_log_lines=app_log_lines,
        filters={
            "entry_type": entry_type,
            "entry_status": entry_status,
            "q": query,
            "log_query": log_query,
        },
        compose_source=(
            extract_local_path(request.args.get("source"))
            or extract_local_path(request.referrer)
            or request.path
        ),
        message=request.args.get("message"),
    )


@core.route("/debug/issues", methods=["POST"])
def create_issue_report():
    db = get_db()
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    entry_type = (request.form.get("entry_type") or "issue").strip()
    if entry_type not in {"bug", "issue", "recommendation", "note"}:
        entry_type = "issue"

    title = (request.form.get("title") or "").strip() or f"{entry_type.title()} report"
    details = (request.form.get("details") or "").strip()
    return_to = safe_return_path(request.form.get("return_to"))
    source_path = extract_local_path(request.form.get("source_path")) or return_to
    browser_console = (request.form.get("browser_console") or "").strip() or None

    if not details:
        message = "Details are required before submitting a report."
        if wants_json:
            return jsonify({"status": "error", "message": message}), 400
        return redirect(append_query_params(return_to, message=message))

    cursor = db.execute(
        """INSERT INTO issue_reports (entry_type, title, details, source_path, browser_console, status)
           VALUES (?, ?, ?, ?, ?, 'open')""",
        (entry_type, title, details, source_path, browser_console),
    )
    db.commit()
    if wants_json:
        return jsonify({
            "status": "ok",
            "message": "Report saved.",
            "report_id": cursor.lastrowid,
            "source_path": source_path,
        })
    return redirect(append_query_params(return_to, message="Report saved."))


@core.route("/debug/issues/<int:issue_id>/complete", methods=["POST"])
def complete_issue_report(issue_id):
    db = get_db()
    db.execute(
        "UPDATE issue_reports SET status='completed', completed_at=CURRENT_TIMESTAMP WHERE id=?",
        (issue_id,),
    )
    db.commit()
    return redirect(safe_return_path(request.form.get("return_to")))


# ── API: Dashboard ────────────────────────────────────────

@core.route("/api/dashboard")
def api_dashboard():
    db = get_db()
    seasons   = db.execute("SELECT COUNT(*) FROM seasons").fetchone()[0]
    scheduled = db.execute("SELECT COUNT(*) FROM scheduled_games").fetchone()[0]
    events    = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    players   = db.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    upcoming  = db.execute(
        """SELECT * FROM scheduled_games
           WHERE game_date >= date('now') AND status != 'cancelled'
           ORDER BY game_date, game_time LIMIT 5"""
    ).fetchall()
    recent    = db.execute(
        "SELECT * FROM events ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    return jsonify({
        "seasons":       seasons,
        "scheduled":     scheduled,
        "events":        events,
        "players":       players,
        "upcoming_games": [dict(r) for r in upcoming],
        "recent_events":  [dict(r) for r in recent],
    })


@core.route("/api/resource-status")
def api_resource_status():
    return jsonify(build_resource_status())


@core.route("/status")
@require_feature("ENABLE_AUTO_STATS_M1")
def status_page():
    """Live status page showing all analysis runs."""
    db = get_db()
    runs = db.execute(
        "SELECT * FROM analysis_runs ORDER BY id DESC"
    ).fetchall()

    # Count detections and events per game
    det_counts = {r[0]: r[1] for r in db.execute(
        "SELECT game_id, COUNT(*) FROM detections GROUP BY game_id"
    ).fetchall()}
    evt_counts = {r[0]: r[1] for r in db.execute(
        "SELECT game_id, COUNT(*) FROM events GROUP BY game_id"
    ).fetchall()}

    return render_template(
        "status.html",
        runs=[dict(row) for row in runs],
        detection_rows=[
            {
                "game_id": game_id,
                "detections": det_counts.get(game_id, 0),
                "events": evt_counts.get(game_id, 0),
            }
            for game_id in sorted(set(list(det_counts) + list(evt_counts)))
        ],
    )


@core.route("/api/admin/reset", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def admin_reset():
    """Wipe all video uploads, analysis data, and uploaded files. Fresh start."""
    db = get_db()

    # Collect file paths before deleting
    rows = db.execute("SELECT file_path FROM videos").fetchall()
    for row in rows:
        fp = row["file_path"]
        if fp and os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass

    # Clear all analysis/video data (preserve seasons, games, players)
    db.executescript("""
        DELETE FROM events;
        DELETE FROM detections;
        DELETE FROM analysis_runs;
        DELETE FROM stats;
        DELETE FROM videos;
    """)
    db.commit()

    return jsonify({"success": True, "message": "All video data cleared."})


@core.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")


@core.route("/users")
def users_page():
    return render_template("users.html")
