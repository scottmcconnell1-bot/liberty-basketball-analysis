"""
Practice Blueprint
==================
Covers all practice-related routes for the Liberty Basketball Analysis app.

Routes:
  GET  /practices                              — practices_page
  POST /practices/save                         — practices_save
  POST /practices/<int:practice_id>/delete     — practices_delete
  POST /practices/<int:practice_id>/generate   — practice_generate_notes
  GET  /practices/<int:practice_id>/report     — practice_report_page
  GET  /practice-summary                       — practice_summary_page
  GET  /api/practices/<int:practice_id>/plan-items  — api_plan_items_list
  POST /api/practices/<int:practice_id>/plan-items  — api_plan_items_create
  PUT  /api/plan-items/<int:item_id>                — api_plan_items_update
  DELETE /api/plan-items/<int:item_id>              — api_plan_items_delete
"""

from flask import Blueprint, abort, g, redirect, render_template, request, url_for, jsonify

from helpers import require_feature, get_db, render_practices_page, fetch_practices_with_context
from helpers import build_practice_ai_notes, build_practice_combined_summary, build_practice_range_summary
from helpers import get_runtime_settings, SCHEDULE_LEVEL_OPTIONS, PRACTICE_STATUS_OPTIONS

import player_development as pd_helpers

practice = Blueprint("practice", __name__)


@practice.route("/practices")
@require_feature("ENABLE_PRACTICES")
def practices_page():
    return render_practices_page(
        message=request.args.get("message"),
        error=request.args.get("error"),
        edit_practice_id=request.args.get("edit_practice_id", type=int),
    )


@practice.route("/practices/save", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def practices_save():
    form = request.form
    filters = {
        "season_id": request.form.get("filter_season_id", type=int),
        "level": (request.form.get("filter_level") or "").strip(),
        "status": (request.form.get("filter_status") or "").strip(),
    }
    practice_id = form.get("practice_id", "").strip()
    season_id = form.get("season_id", "").strip()
    practice_date = (form.get("practice_date") or "").strip()

    if not season_id or not practice_date:
        return render_practices_page(
            error="Season and practice date are required.",
            filters=filters,
            edit_practice_id=int(practice_id) if practice_id else None,
            form_data={
                "id": practice_id,
                "season_id": season_id,
                "level": (form.get("level") or "jr_high").strip(),
                "practice_date": practice_date,
                "status": (form.get("status") or "planned").strip(),
                "plan_source": (form.get("plan_source") or "manual").strip(),
                "plan_text": (form.get("plan_text") or "").strip(),
                "coach_notes": (form.get("coach_notes") or "").strip(),
            },
        ), 400

    db = get_db()
    values = (
        int(season_id),
        (form.get("level") or "jr_high").strip() or "jr_high",
        practice_date,
        (form.get("status") or "planned").strip() or "planned",
        (form.get("plan_source") or "manual").strip() or "manual",
        (form.get("plan_text") or "").strip() or None,
        (form.get("coach_notes") or "").strip() or None,
    )
    if practice_id:
        db.execute(
            """UPDATE practices SET
               season_id=?, level=?, practice_date=?, status=?, plan_source=?,
               plan_text=?, coach_notes=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            values + (int(practice_id),),
        )
        message = "Practice updated."
    else:
        db.execute(
            """INSERT INTO practices
               (season_id, level, practice_date, status, plan_source, plan_text, coach_notes)
               VALUES (?,?,?,?,?,?,?)""",
            values,
        )
        message = "Practice created."
    db.commit()
    return redirect(
        url_for(
            "practice.practices_page",
            season_id=filters["season_id"],
            level=filters["level"] or None,
            status=filters["status"] or None,
            message=message,
        )
    )


@practice.route("/practices/<int:practice_id>/delete", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def practices_delete(practice_id):
    filters = {
        "season_id": request.form.get("filter_season_id", type=int),
        "level": (request.form.get("filter_level") or "").strip(),
        "status": (request.form.get("filter_status") or "").strip(),
    }
    db = get_db()
    db.execute("DELETE FROM practices WHERE id=?", (practice_id,))
    db.commit()
    return redirect(
        url_for(
            "practice.practices_page",
            season_id=filters["season_id"],
            level=filters["level"] or None,
            status=filters["status"] or None,
            message="Practice deleted.",
        )
    )


@practice.route("/practices/<int:practice_id>/generate", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def practice_generate_notes(practice_id):
    db = get_db()
    practice = db.execute("SELECT * FROM practices WHERE id=?", (practice_id,)).fetchone()
    if not practice:
        abort(404)
    ai_notes = build_practice_ai_notes(practice, get_runtime_settings())
    combined_summary = build_practice_combined_summary(practice, ai_notes)
    db.execute(
        "UPDATE practices SET ai_notes=?, combined_summary=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (ai_notes, combined_summary, practice_id),
    )
    db.commit()
    return redirect(url_for("practice.practice_report_page", practice_id=practice_id, message="Practice report refreshed."))


@practice.route("/practices/<int:practice_id>/report")
@require_feature("ENABLE_PRACTICES")
def practice_report_page(practice_id):
    db = get_db()
    practice = db.execute(
        """
        SELECT p.*, s.name AS season_name
        FROM practices p
        LEFT JOIN seasons s ON s.id = p.season_id
        WHERE p.id=?
        """,
        (practice_id,),
    ).fetchone()
    if not practice:
        abort(404)
    return render_template(
        "practice_report.html",
        practice=practice,
        show_plan=request.args.get("show_plan", "1") != "0",
        show_coach=request.args.get("show_coach", "1") != "0",
        show_ai=request.args.get("show_ai", "1") != "0",
        show_combined=request.args.get("show_combined", "1") != "0",
        message=request.args.get("message"),
    )


@practice.route("/practice-summary")
@require_feature("ENABLE_PRACTICES")
def practice_summary_page():
    db = get_db()
    filters = {
        "season_id": request.args.get("season_id", type=int),
        "level": (request.args.get("level") or "").strip(),
        "status": (request.args.get("status") or "").strip(),
        "start_date": (request.args.get("start_date") or "").strip(),
        "end_date": (request.args.get("end_date") or "").strip(),
    }
    seasons = db.execute("SELECT * FROM seasons ORDER BY start_date DESC, id DESC").fetchall()
    practices = fetch_practices_with_context(
        db,
        season_id=filters["season_id"],
        level=filters["level"],
        status=filters["status"],
        start_date=filters["start_date"] or None,
        end_date=filters["end_date"] or None,
    )
    range_summary = build_practice_range_summary(practices)
    return render_template(
        "practice_summary.html",
        seasons=seasons,
        practices=practices,
        filters=filters,
        range_summary=range_summary,
        level_options=SCHEDULE_LEVEL_OPTIONS,
        practice_status_options=PRACTICE_STATUS_OPTIONS,
    )


@practice.route("/api/practices/<int:practice_id>/plan-items")
@require_feature("ENABLE_PRACTICE_PLAYLISTS")
def api_plan_items_list(practice_id):
    db = get_db()
    items = pd_helpers.get_plan_items(db, practice_id)
    return jsonify(items)


@practice.route("/api/practices/<int:practice_id>/plan-items", methods=["POST"])
@require_feature("ENABLE_PRACTICE_PLAYLISTS")
def api_plan_items_create(practice_id):
    db = get_db()
    data = request.get_json(force=True)
    try:
        item = pd_helpers.create_plan_item(
            db,
            practice_id=practice_id,
            title=data["title"],
            playlist_id=data.get("playlist_id"),
            item_type=data.get("item_type", "drill"),
            description=data.get("description"),
            duration_min=data.get("duration_min"),
            sort_order=data.get("sort_order", 0),
        )
        return jsonify(item), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@practice.route("/api/plan-items/<int:item_id>", methods=["PUT"])
@require_feature("ENABLE_PRACTICE_PLAYLISTS")
def api_plan_items_update(item_id):
    db = get_db()
    data = request.get_json(force=True)
    try:
        item = pd_helpers.update_plan_item(db, item_id, **data)
        return jsonify(item)
    except KeyError as e:
        return jsonify({"error": str(e)}), 404


@practice.route("/api/plan-items/<int:item_id>", methods=["DELETE"])
@require_feature("ENABLE_PRACTICE_PLAYLISTS")
def api_plan_items_delete(item_id):
    db = get_db()
    pd_helpers.delete_plan_item(db, item_id)
    return jsonify({"status": "deleted"})
