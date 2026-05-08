"""
Playbook Blueprint
==================

Interactive basketball play creator and playbook manager.

Routes included:
- playbook (/playbook)                          — Playbook list / plays library
- playbook_create (/playbook/create)            — Create new play (canvas editor)
- playbook_edit (/playbook/play/<id>/edit)      — Edit existing play
- playbook_view (/playbook/play/<id>)           — View play with animation
- playbook_delete (/playbook/play/<id>/delete)  — Delete a play
- playbook_save (/playbook/save POST)           — Save play (create or update)
- playbook_api_play (/api/playbook/play/<id>)   — Get play JSON
- playbook_export (/playbook/export/<id>)       — Export play as JSON file
"""

import json

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash

from helpers import get_db, require_feature

playbook_bp = Blueprint("playbook", __name__)


def _serialize(obj):
    """Convert non-JSON-serializable objects (datetime, etc.) to strings."""
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj

PLAYBOOK_CATEGORIES = [
    ("offense", "Offense"),
    ("defense", "Defense"),
    ("press", "Press"),
    ("transition", "Transition"),
    ("out_of_bounds", "Out of Bounds"),
    ("special", "Special"),
]


@playbook_bp.route("/playbook")
@require_feature("ENABLE_PRACTICES")
def playbook_list():
    """Playbook list / plays library page."""
    db = get_db()
    plays = db.execute(
        """SELECT p.*, pb.name as playbook_name,
                  (SELECT COUNT(*) FROM play_steps ps WHERE ps.play_id = p.id) as step_count
           FROM plays p
           LEFT JOIN playbooks pb ON pb.id = p.playbook_id
           ORDER BY p.updated_at DESC"""
    ).fetchall()
    playbooks = db.execute("SELECT * FROM playbooks ORDER BY name").fetchall()
    return render_template(
        "playbook.html",
        plays=[dict(p) for p in plays],
        playbooks=[dict(p) for p in playbooks],
        categories=PLAYBOOK_CATEGORIES,
        editing_play=None,
        editing_steps=[],
        view_mode="list",
    )


@playbook_bp.route("/playbook/create")
@require_feature("ENABLE_PRACTICES")
def playbook_create():
    """Create new play — opens the canvas editor."""
    db = get_db()
    playbooks = db.execute("SELECT * FROM playbooks ORDER BY name").fetchall()
    return render_template(
        "playbook.html",
        plays=[],
        playbooks=playbooks,
        categories=PLAYBOOK_CATEGORIES,
        editing_play=None,
        editing_steps=[],
        view_mode="editor",
    )


@playbook_bp.route("/playbook/play/<int:play_id>")
@require_feature("ENABLE_PRACTICES")
def playbook_view(play_id):
    """View a play with step-by-step animation."""
    db = get_db()
    play = db.execute("SELECT * FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        flash("Play not found.", "error")
        return redirect(url_for("playbook.playbook_list"))
    steps = db.execute(
        "SELECT * FROM play_steps WHERE play_id = ? ORDER BY step_number", (play_id,)
    ).fetchall()
    playbooks = db.execute("SELECT * FROM playbooks ORDER BY name").fetchall()
    return render_template(
        "playbook.html",
        plays=[],
        playbooks=[dict(p) for p in playbooks],
        categories=PLAYBOOK_CATEGORIES,
        editing_play=dict(play),
        editing_steps=[dict(s) for s in steps],
        view_mode="view",
    )


@playbook_bp.route("/playbook/play/<int:play_id>/edit")
@require_feature("ENABLE_PRACTICES")
def playbook_edit(play_id):
    """Edit an existing play."""
    db = get_db()
    play = db.execute("SELECT * FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        flash("Play not found.", "error")
        return redirect(url_for("playbook.playbook_list"))
    steps = db.execute(
        "SELECT * FROM play_steps WHERE play_id = ? ORDER BY step_number", (play_id,)
    ).fetchall()
    playbooks = db.execute("SELECT * FROM playbooks ORDER BY name").fetchall()
    return render_template(
        "playbook.html",
        plays=[],
        playbooks=[dict(p) for p in playbooks],
        categories=PLAYBOOK_CATEGORIES,
        editing_play=dict(play),
        editing_steps=[dict(s) for s in steps],
        view_mode="editor",
    )


@playbook_bp.route("/playbook/play/<int:play_id>/delete", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_delete(play_id):
    """Delete a play and its steps."""
    db = get_db()
    db.execute("DELETE FROM play_steps WHERE play_id = ?", (play_id,))
    db.execute("DELETE FROM plays WHERE id = ?", (play_id,))
    db.commit()
    flash("Play deleted.", "success")
    return redirect(url_for("playbook.playbook_list"))


@playbook_bp.route("/playbook/play/<int:play_id>/duplicate", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_duplicate(play_id):
    """Duplicate a play (copy with new name)."""
    db = get_db()
    play = db.execute("SELECT * FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        flash("Play not found.", "error")
        return redirect(url_for("playbook.playbook_list"))
    steps = db.execute(
        "SELECT * FROM play_steps WHERE play_id = ? ORDER BY step_number", (play_id,)
    ).fetchall()
    cur = db.execute(
        """INSERT INTO plays (name, description, category, tags, playbook_id, diagram_json)
           VALUES (?,?,?,?,?,?)""",
        (
            play["name"] + " (copy)",
            play["description"],
            play["category"],
            play["tags"],
            play["playbook_id"],
            play["diagram_json"],
        ),
    )
    new_id = cur.lastrowid
    for step in steps:
        db.execute(
            """INSERT INTO play_steps (play_id, step_number, label, positions_json, movements_json, notes)
               VALUES (?,?,?,?,?,?)""",
            (new_id, step["step_number"], step["label"], step["positions_json"], step["movements_json"], step["notes"]),
        )
    db.commit()
    flash("Play duplicated.", "success")
    return redirect(url_for("playbook.playbook_edit", play_id=new_id))


@playbook_bp.route("/playbook/save", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_save():
    """Save a play (create new or update existing)."""
    form = request.form
    play_id = (form.get("play_id") or "").strip()
    name = (form.get("name") or "").strip()
    description = (form.get("description") or "").strip()
    category = (form.get("category") or "offense").strip()
    tags = (form.get("tags") or "").strip()
    playbook_id = (form.get("playbook_id") or "").strip()
    diagram_json = (form.get("diagram_json") or "{}").strip()
    steps_json = (form.get("steps_json") or "[]").strip()

    if not name:
        flash("Play name is required.", "error")
        return redirect(url_for("playbook.playbook_list"))

    db = get_db()
    now = "CURRENT_TIMESTAMP"

    if play_id:
        # Update existing play
        db.execute(
            """UPDATE plays SET name=?, description=?, category=?, tags=?,
               playbook_id=?, diagram_json=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (
                name, description, category, tags,
                int(playbook_id) if playbook_id else None,
                diagram_json, int(play_id),
            ),
        )
        # Delete old steps and re-insert
        db.execute("DELETE FROM play_steps WHERE play_id = ?", (int(play_id),))
        play_db_id = int(play_id)
    else:
        # Create new play
        cur = db.execute(
            """INSERT INTO plays (name, description, category, tags, playbook_id, diagram_json)
               VALUES (?,?,?,?,?,?)""",
            (
                name, description, category, tags,
                int(playbook_id) if playbook_id else None,
                diagram_json,
            ),
        )
        play_db_id = cur.lastrowid

    # Insert steps
    try:
        steps = json.loads(steps_json)
        for i, step in enumerate(steps):
            positions = json.dumps(step.get("positions", {}))
            movements = json.dumps(step.get("movements", []))
            label = step.get("label", "")
            notes = step.get("notes", "")
            db.execute(
                """INSERT INTO play_steps (play_id, step_number, label, positions_json, movements_json, notes)
                   VALUES (?,?,?,?,?,?)""",
                (play_db_id, i, label, positions, movements, notes),
            )
    except (json.JSONDecodeError, KeyError):
        pass

    db.commit()
    flash("Play saved.", "success")
    return redirect(url_for("playbook.playbook_view", play_id=play_db_id))


@playbook_bp.route("/api/playbook/play/<int:play_id>")
@require_feature("ENABLE_PRACTICES")
def playbook_api_play(play_id):
    """Get play data as JSON (for canvas editor)."""
    db = get_db()
    play = db.execute("SELECT * FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        return jsonify({"error": "Play not found"}), 404
    steps = db.execute(
        "SELECT * FROM play_steps WHERE play_id = ? ORDER BY step_number", (play_id,)
    ).fetchall()
    return jsonify({
        "play": _serialize(dict(play)),
        "steps": [_serialize(dict(s)) for s in steps],
    })


@playbook_bp.route("/playbook/export/<int:play_id>")
@require_feature("ENABLE_PRACTICES")
def playbook_export(play_id):
    """Export play as downloadable JSON."""
    db = get_db()
    play = db.execute("SELECT * FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        return jsonify({"error": "Play not found"}), 404
    steps = db.execute(
        "SELECT * FROM play_steps WHERE play_id = ? ORDER BY step_number", (play_id,)
    ).fetchall()
    data = {
        "play": _serialize(dict(play)),
        "steps": [_serialize(dict(s)) for s in steps],
    }
    from flask import Response
    return Response(
        json.dumps(data, indent=2, default=str),
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment; filename=play_{play_id}.json"},
    )
