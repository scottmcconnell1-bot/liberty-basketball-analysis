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
                "team": (form.get("team") or "boys_hs").strip(),
                "gender": (form.get("gender") or "boys").strip(),
                "level": (form.get("level") or "jr_high").strip(),
                "game_date": game_date,
                "game_time": (form.get("game_time") or "").strip(),
                "jv_game_time": (form.get("jv_game_time") or "").strip(),
                "frosh_game_time": (form.get("frosh_game_time") or "").strip(),
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
        (form.get("team") or "boys_hs").strip() or "boys_hs",
        (form.get("gender") or "boys").strip() or "boys",
        (form.get("level") or "jr_high").strip() or "jr_high",
        game_date,
        (form.get("game_time") or "").strip() or None,
        (form.get("jv_game_time") or "").strip() or None,
        (form.get("frosh_game_time") or "").strip() or None,
        (form.get("location_type") or "home").strip() or "home",
        opponent_name,
        (form.get("tournament_name") or "").strip() or None,
        (form.get("status") or "scheduled").strip() or "scheduled",
        (form.get("notes") or "").strip() or None,
    )

    if game_id:
        db.execute(
            """UPDATE scheduled_games SET
               season_id=?, program_name=?, team=?, gender=?, level=?, game_date=?, game_time=?,
               jv_game_time=?, frosh_game_time=?,
               location_type=?, opponent_name=?, tournament_name=?, status=?, notes=?,
               updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            values + (int(game_id),),
        )
        message = "Scheduled game updated."
    else:
        db.execute(
            """INSERT INTO scheduled_games
               (season_id, program_name, team, gender, level, game_date, game_time,
                jv_game_time, frosh_game_time,
                location_type, opponent_name, tournament_name, status, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
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
    pdf_team = (request.form.get("team") or "boys_hs").strip()
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
        games = _parse_schedule_text(text, pdf_team=pdf_team)
        return {"games": games}
    except Exception as e:
        return {"error": f"Failed to parse PDF: {str(e)}"}, 500


def _parse_schedule_text(text, pdf_team="boys_hs"):
    """Parse extracted PDF text into game dicts. Handles common schedule formats
    including multi-time layouts like '4:30/6:00/7:30' (JV/Frosh/Varsity).

    The pdf_team parameter sets default gender/level based on which team
    the user selected before uploading:
      boys_hs   → gender=boys,  level=varsity
      girls_hs  → gender=girls, level=varsity
      jr_boys   → gender=boys,  level=jr_high
      jr_girls  → gender=girls, level=jr_high

    Handles two main PDF layouts:
    1. Column-based: 'DATE OPPONENT TIMES' headers with data in columns
       (times appear on same line or next line after opponent)
    2. Row-based: '12/2 Marsing 7:30p' all on one line
    """
    import re, datetime
    games = []
    lines = text.splitlines()

    # Pre-process: detect column-based layout by looking for DATE/OPPONENT/TIMES headers
    has_column_layout = False
    for line in lines:
        if re.match(r'\s*DATE\s+OPPONENT\s+TIMES', line, re.IGNORECASE):
            has_column_layout = True
            break

    if has_column_layout:
        # Column-based layout: join continuation lines and split into game entries
        # Pattern: date followed by opponent, then times (on same or next line)
        joined_lines = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            # Skip header/footer lines
            if re.search(r'^DATE\s+OPPONENT\s+TIMES', line, re.IGNORECASE):
                i += 1
                continue
            if re.search(r'Revised \d+/\d+/\d+|Schedule and times|Schedule Legend|\* Denotes|THANK YOU|Advanced Family', line):
                i += 1
                continue
            if re.search(r'Printable|America\'s Source|Liberty Charter Basketball Schedule|^LIBERTY CHARTER', line):
                i += 1
                continue

            # Check if this line starts with a date pattern
            has_date = bool(re.search(
                r'(\w+,?\s+\w+\s+\d{1,2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2})',
                line
            ))

            if has_date:
                # This is a new game line — check if next line is just times (no date, short)
                full_line = line
                # Look ahead for time-only continuation lines
                while i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if not next_line:
                        break
                    # If next line starts with a date, it's a new game
                    if re.search(r'^\w+,?\s+\w+\s+\d{1,2}|^\d{1,2}/\d{1,2}/\d{2,4}', next_line):
                        break
                    # Only join if next line is purely times (e.g. "4:30/6:00/7:30")
                    if re.match(r'^\d{1,2}:\d{2}(?:\s*/\s*\d{1,2}:\d{2})+$', next_line):
                        full_line += ' ' + next_line
                        i += 1
                    else:
                        break
                joined_lines.append(full_line)
            i += 1
    else:
        # Row-based layout: join time-only lines to previous game line
        joined_lines = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            # Check if this line is a "time-only" line
            time_only = re.match(r'^(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\s*/?\s*)+$', line)
            if time_only and joined_lines:
                joined_lines[-1] = joined_lines[-1] + ' TIMES:' + line
                i += 1
                continue

            # Check if this line is a continuation of the previous
            if joined_lines and not re.search(
                r'\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}|\w+\s+\d{1,2},?\s+\d{4}',
                line
            ):
                prev = joined_lines[-1]
                if 'TIMES:' not in prev and len(line) < 80:
                    joined_lines[-1] = prev + ' ' + line
                    i += 1
                    continue

            joined_lines.append(line)
            i += 1

    for line in joined_lines:
        if len(line) < 10:
            continue
        # Jr High: detect "A team" / "B team" continuation lines
        # e.g. "B 4:30" or "B team 4:30" on a line after the opponent
        ab_continuation = re.match(r'^[AaBb]\s*(?:team)?\s*(\d{1,2}:\d{2}(?:\s*(?:AM|PM|am|pm)?)?)\s*$', line.strip())
        if ab_continuation and games and games[-1].get('level') == 'jr_high':
            time_val = _normalize_time(ab_continuation.group(1))
            if line.strip().upper().startswith('B'):
                games[-1]['jv_game_time'] = time_val  # B team
            else:
                games[-1]['game_time'] = time_val  # A team
            continue
        game = _parse_schedule_line(line, pdf_team=pdf_team)
        if game:
            games.append(game)
    return games


def _normalize_time(time_str):
    """Convert a time string to HH:MM format."""
    import datetime
    time_str = time_str.strip()
    for fmt in ['%I:%M %p', '%I:%M%p', '%I:%M', '%H:%M']:
        try:
            return datetime.datetime.strptime(time_str, fmt).strftime('%H:%M')
        except ValueError:
            continue
    return time_str  # Return as-is if can't parse


def _parse_schedule_line(line, pdf_team="boys_hs"):
    """Try to parse a single line of schedule text into a game dict.
    Handles formats like:
      'TUES, DEC 2 MARSING (H) 4:30/6:00/7:30'
      '12/2 Marsing (Marsing, ID) 7:30p'
      '1/5 @ Idaho City (A) 7:30p'

    pdf_team sets default gender/level:
      boys_hs/girls_hs → level=varsity
      jr_boys/jr_girls → level=jr_high
      gender is boys for *_hs/boys_*, girls for girls_*
    """
    import re, datetime

    jv_time = None
    frosh_time = None
    varsity_time = None
    tournament_name = None

    # Check for TIMES: marker (from joined lines)
    times_match = re.search(r'TIMES:(.+)$', line)
    if times_match:
        times_str = times_match.group(1).strip()
        line = line[:times_match.start()].strip()
        time_parts = [t.strip() for t in times_str.split('/')]
        if len(time_parts) == 3:
            jv_time = _normalize_time(time_parts[0])
            frosh_time = _normalize_time(time_parts[1])
            varsity_time = _normalize_time(time_parts[2])
        elif len(time_parts) == 2:
            # For Jr High: 2 times = B team (first) / A team (second)
            # For HS: 2 times = JV / Varsity
            if _team_level == 'jr_high':
                jv_time = _normalize_time(time_parts[0])  # B team
                varsity_time = _normalize_time(time_parts[1])  # A team
            else:
                jv_time = _normalize_time(time_parts[0])
                varsity_time = _normalize_time(time_parts[1])
        elif len(time_parts) == 1:
            varsity_time = _normalize_time(time_parts[0])

    # Pattern: date (various formats) — order matters, try most specific first
    date_patterns = [
        r'(\w+\s*-\s*\w+,?\s+\w+\s+\d{1,2}\s*-\s*\d{1,2})',  # Thurs-Sat, Dec 4-6
        r'(\w+\s+\d{1,2}\s*-\s*\d{1,2},?\s+\d{4})',          # Dec 4-6, 2025
        r'(\w+\s+\d{1,2},?\s+\d{4})',                         # December 1, 2025
        r'(\d{1,2}/\d{1,2}/\d{2,4})',                         # 12/01/2025
        r'(\d{4}-\d{2}-\d{2})',                               # 2025-12-01
        r'(\w+,?\s+\w+\s+\d{1,2})',                           # TUES, DEC 2
        r'(\d{1,2}\s+\w+\s+\d{4})',                           # 1 December 2025
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
    # Handle date ranges: "Thurs-Sat, Dec 4-6" → use first date "Dec 4"
    date_for_parse = re.sub(r'\w+\s*-\s*\w+,?\s+', '', date_str)  # "Dec 4-6" from "Thurs-Sat, Dec 4-6"
    date_for_parse = re.sub(r'\s*-\s*\d{1,2}(,|$)', r'\1', date_for_parse)  # "Dec 4-6" → "Dec 4"
    # Strip day-of-week prefix (e.g. "TUES, " or "Thurs-Sat, " already handled above)
    date_for_parse = re.sub(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun|THURS|TUES|WED|THUR|FRI|SAT|SUN),?\s+', '', date_for_parse, flags=re.IGNORECASE).strip()

    # First try parsing directly
    for fmt in ['%B %d, %Y', '%b %d, %Y', '%B %d %Y', '%b %d %Y',
                '%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d',
                '%B %d', '%b %d',
                '%d %B %Y', '%d %b %Y']:
        try:
            parsed = datetime.datetime.strptime(date_for_parse, fmt)
            if parsed.year == 1900:
                parsed = parsed.replace(year=datetime.datetime.now().year)
            game_date = parsed.strftime('%Y-%m-%d')
            break
        except ValueError:
            continue
    # If that failed, try the original date_str
    if not game_date:
        date_clean = re.sub(r'^\w+,?\s+', '', date_str).strip()
        for fmt in ['%b %d %Y', '%B %d %Y', '%b %d', '%B %d',
                    '%m/%d/%Y', '%m/%d/%y', '%Y-%m-%d',
                    '%B %d, %Y', '%b %d, %Y', '%d %B %Y', '%d %b %Y']:
            try:
                parsed = datetime.datetime.strptime(date_clean, fmt)
                if parsed.year == 1900:
                    parsed = parsed.replace(year=datetime.datetime.now().year)
                game_date = parsed.strftime('%Y-%m-%d')
                break
            except ValueError:
                continue
    if not game_date:
        return None

    # Get remainder after date
    remainder = line[line.index(date_str) + len(date_str):].strip()
    remainder = re.sub(r'^\s*[:\\-–—]\s*', '', remainder)

    # Detect location: (H), (A), (N) or @/at prefix
    location_type = 'home'
    loc_h = re.search(r'\((H|A|N)\)', remainder, re.IGNORECASE)
    if loc_h:
        loc_code = loc_h.group(1).upper()
        location_type = {'H': 'home', 'A': 'away', 'N': 'neutral'}.get(loc_code, 'home')
        remainder = remainder[:loc_h.start()] + remainder[loc_h.end():]
        remainder = remainder.strip()
    else:
        loc_match = re.search(r'(?:^|\s)(@|at)\s+', remainder, re.IGNORECASE)
        if loc_match:
            location_type = 'away'
            remainder = remainder[:loc_match.start()] + remainder[loc_match.end():]
            remainder = remainder.strip()

    # Detect A team / B team pattern (Jr High format)
    # Patterns: "B team 4:30 / A team 6:00" or "B 4:30/A 6:00" or "4:30 B / 6:00 A"
    # B team plays first (earlier time), A team plays second
    is_jr_high = 'jr_high' == _team_level
    if is_jr_high and not jv_time and not varsity_time:
        # Check for A/B team time patterns like "B 4:30 / A 6:00" or "4:30B/6:00A"
        ab_time_match = re.search(
            r'(\d{1,2}:\d{2})\s*(?:B|b)\s*/\s*(\d{1,2}:\d{2})\s*(?:A|a)', remainder
        )
        if ab_time_match:
            jv_time = _normalize_time(ab_time_match.group(1))  # B team → jv_game_time
            varsity_time = _normalize_time(ab_time_match.group(2))  # A team → game_time
            remainder = remainder[:ab_time_match.start()] + remainder[ab_time_match.end():]
            remainder = remainder.strip()
        else:
            # Check for "B team 4:30 / A team 6:00" format
            ab_time_match2 = re.search(
                r'[Bb]\s*(?:team)?\s*(\d{1,2}:\d{2})\s*/\s*[Aa]\s*(?:team)?\s*(\d{1,2}:\d{2})', remainder
            )
            if ab_time_match2:
                jv_time = _normalize_time(ab_time_match2.group(1))  # B team → jv_game_time
                varsity_time = _normalize_time(ab_time_match2.group(2))  # A team → game_time
                remainder = remainder[:ab_time_match2.start()] + remainder[ab_time_match2.end():]
                remainder = remainder.strip()

    # Detect inline multi-time pattern at end of remainder: "4:30/6:00/7:30" or "4:30/7:30"
    # This handles the PDF column layout where times appear after (H)/(A)
    if not varsity_time:
        multi_time_match = re.search(r'(\d{1,2}:\d{2}(?:\s*/\s*\d{1,2}:\d{2})+)\s*$', remainder)
        if multi_time_match:
            times_str = multi_time_match.group(1)
            remainder = remainder[:multi_time_match.start()].strip()
            time_parts = [t.strip() for t in times_str.split('/')]
            if len(time_parts) == 3:
                jv_time = _normalize_time(time_parts[0])
                frosh_time = _normalize_time(time_parts[1])
                varsity_time = _normalize_time(time_parts[2])
            elif len(time_parts) == 2:
                # Jr High: 2 times = B team (first) / A team (second)
                if _team_level == 'jr_high':
                    jv_time = _normalize_time(time_parts[0])  # B team
                    varsity_time = _normalize_time(time_parts[1])  # A team
                else:
                    jv_time = _normalize_time(time_parts[0])
                    varsity_time = _normalize_time(time_parts[1])
            elif len(time_parts) == 1:
                varsity_time = _normalize_time(time_parts[0])

    # Detect single time if not already found
    if not varsity_time:
        time_match = re.search(r'(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)', remainder)
        if time_match:
            time_str = time_match.group(1)
            remainder = remainder[:time_match.start()] + remainder[time_match.end():]
            remainder = remainder.strip()
            varsity_time = _normalize_time(time_str)

    # Detect tournament names and vs. pattern
    # "Small School Showcase vs. Camas County" → tournament=Small School Showcase, opponent=Camas County
    # "Varsity vs Westside" → opponent=Westside, level=varsity (pre_vs is a level keyword)
    # Detect tournament names and vs. pattern
    # "Small School Showcase vs. Camas County" → tournament=Small School Showcase, opponent=Camas County
    # "Varsity vs Westside" → opponent=Westside, level=varsity (pre_vs is a level keyword)
    # "Girls vs Eastside" → opponent=Eastside, gender=girls
    # Derive defaults from the selected team
    _team_gender = "girls" if "girls" in pdf_team else "boys"
    _team_level = "jr_high" if "jr_" in pdf_team else "varsity"

    level = _team_level  # May be overridden by vs. handler or level detection below
    gender = _team_gender  # May be overridden by vs. handler or detection below
    vs_match = re.search(r'(.+?)\s+vs\.?\s+(.+?)$', remainder, re.IGNORECASE)
    if vs_match:
        pre_vs = vs_match.group(1).strip()
        post_vs = vs_match.group(2).strip()
        # Check if pre_vs is a level/gender keyword
        pre_is_keyword = bool(re.match(r'^(varsity|jv|junior varsity|boys|girls|freshman)$', pre_vs, re.IGNORECASE))
        if pre_is_keyword:
            remainder = post_vs
            if re.match(r'^varsity$', pre_vs, re.IGNORECASE):
                level = 'varsity'
            elif re.match(r'^(jv|junior varsity)$', pre_vs, re.IGNORECASE):
                level = 'jv'
            elif re.match(r'^girls$', pre_vs, re.IGNORECASE):
                gender = 'girls'
            elif re.match(r'^boys$', pre_vs, re.IGNORECASE):
                gender = 'boys'
        elif len(pre_vs.split()) >= 2:
            tournament_name = pre_vs
            remainder = post_vs
        else:
            remainder = post_vs

    # Detect level and gender from remainder (if not already set by vs. handler)
    if level == _team_level:
        level_lower = remainder.lower()
        if 'varsity' in level_lower:
            level = 'varsity'
        elif 'junior varsity' in level_lower or ' jv ' in level_lower:
            level = 'jv'
    if gender == _team_gender:
        if 'girls' in remainder.lower():
            gender = 'girls'

    # Clean up opponent name
    opponent = remainder
    opponent = re.sub(r'\*+', '', opponent).strip()  # Remove conference markers like *
    opponent = re.sub(r'\b(varsity|jv|junior varsity|boys|girls|freshman|tbd)\b', '', opponent, flags=re.IGNORECASE).strip()
    opponent = re.sub(r'\b(vs\.?|versus)\b', '', opponent, flags=re.IGNORECASE).strip()
    opponent = re.sub(r'\s+', ' ', opponent).strip()
    opponent = re.sub(r'[,;:\-–—]+$', '', opponent).strip()
    opponent = re.sub(r'\(H\)|\(A\)|\(N\)', '', opponent, flags=re.IGNORECASE).strip()
    opponent = re.sub(r'\s+', ' ', opponent).strip()

    if not opponent:
        return None

    return {
        "game_date": game_date,
        "game_time": varsity_time or "",
        "jv_game_time": jv_time or "",
        "frosh_game_time": frosh_time or "",
        "opponent_name": opponent,
        "team": pdf_team,
        "level": level,
        "gender": gender,
        "location_type": location_type,
        "tournament_name": tournament_name or "",
        "status": "scheduled",
        "notes": "",
    }


@core.route("/api/schedule/import-pdf/confirm", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def schedule_import_pdf_confirm():
    data = request.get_json(force=True)
    games = data.get("games", [])
    pdf_team = (data.get("team") or "boys_hs").strip()
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
                   (season_id, program_name, team, gender, level, game_date, game_time,
                    jv_game_time, frosh_game_time,
                    location_type, opponent_name, tournament_name, status, notes)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    season_id,
                    "Liberty",
                    pdf_team,
                    (g.get("gender") or "boys").strip(),
                    (g.get("level") or "jr_high").strip(),
                    game_date,
                    (g.get("game_time") or "").strip() or None,
                    (g.get("jv_game_time") or "").strip() or None,
                    (g.get("frosh_game_time") or "").strip() or None,
                    (g.get("location_type") or "home").strip(),
                    opponent,
                    (g.get("tournament_name") or "").strip() or None,
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
        """SELECT sg.id, sg.game_date, sg.game_time, sg.jv_game_time, sg.frosh_game_time,
                  sg.team, sg.opponent_name, sg.level, sg.gender, sg.location_type, sg.status,
                  sg.program_name, sg.tournament_name,
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
        "Date", "JV Time", "Frosh Time", "Varsity Time", "Opponent", "Location",
        "Team", "Level", "Gender", "Tournament", "Conference", "Season"
    ])
    for g in games:
        location = "Away" if g["location_type"] == "away" else "Home"
        writer.writerow([
            g["game_date"],
            g["jv_game_time"] or "",
            g["frosh_game_time"] or "",
            g["game_time"] or "",
            g["opponent_name"],
            location,
            _team_display_name(g["team"]),
            _level_display_name(g["level"]),
            _gender_display_name(g["gender"]),
            g["tournament_name"] or "",
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


def _team_display_name(val):
    mapping = {
        "boys_hs": "Boys HS",
        "girls_hs": "Girls HS",
        "jr_boys": "Jr High Boys",
        "jr_girls": "Jr High Girls",
    }
    return mapping.get(val, val)


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


@core.route("/api/users")
def api_users_list():
    """Return all users as JSON."""
    db = get_db()
    users = db.execute(
        "SELECT id, username, email, is_admin, created_at FROM users ORDER BY created_at DESC"
    ).fetchall()
    return jsonify([dict(u) for u in users])


@core.route("/api/users/<int:user_id>", methods=["DELETE"])
def api_users_delete(user_id):
    """Delete a non-admin user."""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not user:
        return jsonify({"error": "User not found"}), 404
    if user["is_admin"]:
        return jsonify({"error": "Cannot delete admin user"}), 403
    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    return jsonify({"status": "deleted"})
