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
- playbook_import (/playbook/import)            — Upload PDF/image for import
- playbook_import_parse (/playbook/import/parse POST) — Extract diagram from upload
- playbook_import_save (/playbook/import/save POST)   — Save imported play
"""

import json

from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, current_app

from helpers import get_db, require_feature, get_default_team_id
from module_entitlements import enforce_module_access
from module_keys import PLAYBOOK_RECOGNITION

playbook_bp = Blueprint("playbook", __name__)

_PUBLIC_ENDPOINTS = frozenset({
    "playbook.playbook_share",
})


@playbook_bp.before_request
def _playbook_module_gate():
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return
    db = get_db()
    enforce_module_access(db, get_default_team_id(db), PLAYBOOK_RECOGNITION)


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


def _load_playbook_taxonomy(db):
    from playbook_taxonomy import build_category_tree, ensure_playbook_taxonomy

    ensure_playbook_taxonomy(db)
    db.commit()
    return build_category_tree(db)


def _plays_query(db):
    return db.execute(
        """SELECT p.*, pb.name as playbook_name,
                  pc.name as category_name,
                  pc.slug_path as category_path,
                  (SELECT COUNT(*) FROM play_steps ps WHERE ps.play_id = p.id) as step_count
           FROM plays p
           LEFT JOIN playbooks pb ON pb.id = p.playbook_id
           LEFT JOIN play_categories pc ON pc.id = p.category_id
           ORDER BY p.updated_at DESC"""
    ).fetchall()


def _default_category_id(db):
    from playbook_taxonomy import resolve_category_id_by_path

    return resolve_category_id_by_path(db, "offense/man/plays")


def _share_url_for_play(play):
    token = play["share_token"] if play else None
    if not token:
        return None
    return url_for("playbook.playbook_share", token=token, _external=True)


@playbook_bp.route("/playbook")
@require_feature("ENABLE_PRACTICES")
def playbook_list():
    """Playbook list / plays library page."""
    db = get_db()
    category_tree = _load_playbook_taxonomy(db)
    plays = _plays_query(db)
    playbooks = db.execute("SELECT * FROM playbooks ORDER BY name").fetchall()
    return render_template(
        "playbook.html",
        plays=[dict(p) for p in plays],
        playbooks=[dict(p) for p in playbooks],
        categories=PLAYBOOK_CATEGORIES,
        category_tree=category_tree,
        editing_play=None,
        editing_steps=[],
        view_mode="list",
        selected_category_id=None,
    )


@playbook_bp.route("/playbook/create")
@require_feature("ENABLE_PRACTICES")
def playbook_create():
    """Create new play — opens the canvas editor."""
    db = get_db()
    category_tree = _load_playbook_taxonomy(db)
    playbooks = db.execute("SELECT * FROM playbooks ORDER BY name").fetchall()
    selected_category_id = request.args.get("category_id", type=int) or _default_category_id(db)
    return render_template(
        "playbook.html",
        plays=[],
        playbooks=playbooks,
        categories=PLAYBOOK_CATEGORIES,
        category_tree=category_tree,
        editing_play=None,
        editing_steps=[],
        view_mode="editor",
        selected_category_id=selected_category_id,
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
    category_tree = _load_playbook_taxonomy(db)
    return render_template(
        "playbook.html",
        plays=[],
        playbooks=[dict(p) for p in playbooks],
        categories=PLAYBOOK_CATEGORIES,
        category_tree=category_tree,
        editing_play=dict(play),
        editing_steps=[dict(s) for s in steps],
        view_mode="view",
        selected_category_id=play["category_id"],
        share_url=_share_url_for_play(play),
    )


@playbook_bp.route("/play/share/<token>")
def playbook_share(token):
    """Public read-only view of a play via share link."""
    db = get_db()
    from playbook_sharing import get_play_by_share_token

    play = get_play_by_share_token(db, token)
    if not play:
        return (
            "<!DOCTYPE html><html><body style='font-family:sans-serif;padding:40px;'>"
            "<h2>Play not found</h2><p>This share link is invalid or has been revoked.</p>"
            "</body></html>",
            404,
            {"Content-Type": "text/html"},
        )
    steps = db.execute(
        "SELECT * FROM play_steps WHERE play_id = ? ORDER BY step_number", (play["id"],)
    ).fetchall()
    category_tree = _load_playbook_taxonomy(db)
    return render_template(
        "playbook.html",
        plays=[],
        playbooks=[],
        categories=PLAYBOOK_CATEGORIES,
        category_tree=category_tree,
        editing_play=dict(play),
        editing_steps=[dict(s) for s in steps],
        view_mode="share",
        selected_category_id=play["category_id"],
        share_url=url_for("playbook.playbook_share", token=token, _external=True),
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
    category_tree = _load_playbook_taxonomy(db)
    return render_template(
        "playbook.html",
        plays=[],
        playbooks=[dict(p) for p in playbooks],
        categories=PLAYBOOK_CATEGORIES,
        category_tree=category_tree,
        editing_play=dict(play),
        editing_steps=[dict(s) for s in steps],
        view_mode="editor",
        selected_category_id=play["category_id"],
        share_url=_share_url_for_play(play),
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
        """INSERT INTO plays (name, description, category, category_id, tags, playbook_id, diagram_json)
           VALUES (?,?,?,?,?,?,?)""",
        (
            play["name"] + " (copy)",
            play["description"],
            play["category"],
            play["category_id"],
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
    category_id_raw = (form.get("category_id") or "").strip()
    tags = (form.get("tags") or "").strip()
    playbook_id = (form.get("playbook_id") or "").strip()
    diagram_json = (form.get("diagram_json") or "{}").strip()
    steps_json = (form.get("steps_json") or "[]").strip()

    if not name:
        flash("Play name is required.", "error")
        return redirect(url_for("playbook.playbook_list"))

    db = get_db()
    from playbook_taxonomy import legacy_category_from_id, resolve_category_id_by_path

    _load_playbook_taxonomy(db)
    category_id = None
    if category_id_raw:
        try:
            category_id = int(category_id_raw)
        except ValueError:
            category_id = None
    if not category_id:
        category_id = resolve_category_id_by_path(db, "offense/man/plays")
    category = legacy_category_from_id(db, category_id)

    if play_id:
        # Update existing play
        db.execute(
            """UPDATE plays SET name=?, description=?, category=?, category_id=?, tags=?,
               playbook_id=?, diagram_json=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (
                name, description, category, category_id, tags,
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
            """INSERT INTO plays (name, description, category, category_id, tags, playbook_id, diagram_json)
               VALUES (?,?,?,?,?,?,?)""",
            (
                name, description, category, category_id, tags,
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
            movements = list(step.get("movements", []))
            ball = step.get("ball")
            if ball:
                movements = [m for m in movements if not (isinstance(m, dict) and m.get("_meta"))]
                movements.append({"_meta": True, "_ball": ball})
            movements = json.dumps(movements)
            label = step.get("label", "")
            notes = step.get("notes", "")
            source_image = step.get("source_image", "")
            db.execute(
                """INSERT INTO play_steps (play_id, step_number, label, positions_json, movements_json, notes, source_image)
                   VALUES (?,?,?,?,?,?,?)""",
                (play_db_id, i, label, positions, movements, notes, source_image),
            )
    except (json.JSONDecodeError, KeyError):
        pass

    db.commit()
    flash("Play saved.", "success")
    return redirect(url_for("playbook.playbook_view", play_id=play_db_id))


@playbook_bp.route("/api/playbook/play/<int:play_id>/share", methods=["POST"])
def playbook_share_api(play_id):
    """Create or return a shareable public link for a play."""
    from playbook_sharing import ensure_share_token

    db = get_db()
    play = db.execute("SELECT id FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        return jsonify({"error": "Play not found"}), 404
    try:
        token = ensure_share_token(db, play_id)
        db.commit()
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    share_url = url_for("playbook.playbook_share", token=token, _external=True)
    return jsonify({"token": token, "url": share_url})


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


@playbook_bp.route("/api/playbook/play/<int:play_id>/digitize", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_digitize_play(play_id):
    """Auto-detect O/X markers on imported step PNGs and write positions_json."""
    import os
    from pathlib import Path

    from playbook_digitize import digitize_play_steps

    data = request.get_json(silent=True) or {}
    force = bool(data.get("force"))
    dry_run = bool(data.get("dry_run"))
    min_markers = int(data.get("min_markers") or 3)

    upload_root = current_app.config.get("UPLOAD_FOLDER") or os.environ.get(
        "LIBERTY_UPLOAD_FOLDER", "uploads"
    )
    # Resolve DB path the same way helpers use (cwd film_analysis.db)
    db_path = Path(current_app.root_path) / "film_analysis.db"
    if not db_path.is_file():
        db_path = Path("film_analysis.db")

    try:
        report = digitize_play_steps(
            db_path,
            play_id,
            upload_root=upload_root,
            write=not dry_run,
            force=force,
            min_markers=min_markers,
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

    status = 200 if report.get("ok") else 404
    return jsonify(report), status


@playbook_bp.route("/api/playbook/digitize-all", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_digitize_all():
    """Batch digitize image-only plays (optional limit)."""
    import os
    from pathlib import Path

    from playbook_digitize import digitize_play_steps, list_image_only_play_ids

    data = request.get_json(silent=True) or {}
    force = bool(data.get("force"))
    dry_run = bool(data.get("dry_run"))
    limit = int(data.get("limit") or 0)
    min_markers = int(data.get("min_markers") or 3)

    upload_root = current_app.config.get("UPLOAD_FOLDER") or os.environ.get(
        "LIBERTY_UPLOAD_FOLDER", "uploads"
    )
    db_path = Path(current_app.root_path) / "film_analysis.db"
    if not db_path.is_file():
        db_path = Path("film_analysis.db")

    ids = list_image_only_play_ids(db_path)
    if limit > 0:
        ids = ids[:limit]

    reports = []
    accepted_plays = 0
    for pid in ids:
        report = digitize_play_steps(
            db_path,
            pid,
            upload_root=upload_root,
            write=not dry_run,
            force=force,
            min_markers=min_markers,
        )
        reports.append(
            {
                "play_id": pid,
                "name": report.get("name"),
                "accepted_steps": report.get("accepted_steps", 0),
                "ok": report.get("ok"),
                "error": report.get("error"),
            }
        )
        if report.get("accepted_steps", 0) > 0:
            accepted_plays += 1

    return jsonify(
        {
            "ok": True,
            "play_count": len(ids),
            "accepted_plays": accepted_plays,
            "dry_run": dry_run,
            "plays": reports,
        }
    )


@playbook_bp.route("/api/playbook/categories")
@require_feature("ENABLE_PRACTICES")
def playbook_categories_api():
    db = get_db()
    from playbook_taxonomy import build_category_tree, list_categories_flat

    tree = _load_playbook_taxonomy(db)
    return jsonify({"tree": tree, "flat": list_categories_flat(db)})


@playbook_bp.route("/api/playbook/categories", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_categories_create():
    from playbook_taxonomy import build_category_tree, create_category

    data = request.get_json(force=True) or {}
    db = get_db()
    try:
        category_id = create_category(
            db,
            parent_id=data.get("parent_id"),
            name=data.get("name"),
        )
        db.commit()
        return jsonify({"id": category_id, "tree": build_category_tree(db)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@playbook_bp.route("/api/playbook/categories/<int:category_id>", methods=["PUT"])
@require_feature("ENABLE_PRACTICES")
def playbook_categories_update(category_id):
    from playbook_taxonomy import build_category_tree, rename_category

    data = request.get_json(force=True) or {}
    db = get_db()
    try:
        rename_category(db, category_id, data.get("name"))
        db.commit()
        return jsonify({"ok": True, "tree": build_category_tree(db)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@playbook_bp.route("/api/playbook/categories/<int:category_id>/move", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_categories_move(category_id):
    from playbook_taxonomy import build_category_tree, move_category

    data = request.get_json(force=True) or {}
    db = get_db()
    try:
        move_category(
            db,
            category_id,
            parent_id=data.get("parent_id"),
            sort_order=data.get("sort_order"),
        )
        db.commit()
        return jsonify({"ok": True, "tree": build_category_tree(db)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@playbook_bp.route("/api/playbook/categories/<int:category_id>", methods=["DELETE"])
@require_feature("ENABLE_PRACTICES")
def playbook_categories_delete(category_id):
    from playbook_taxonomy import build_category_tree, delete_category

    data = request.get_json(force=True) or {}
    db = get_db()
    try:
        delete_category(db, category_id, reassign_to=data.get("reassign_to"))
        db.commit()
        return jsonify({"ok": True, "tree": build_category_tree(db)})
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


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


# ── Plays Import ──────────────────────────────────────────────

@playbook_bp.route("/playbook/import")
@require_feature("ENABLE_PRACTICES")
def playbook_import():
    """Plays import page — upload PDF or image for diagram extraction."""
    db = get_db()
    from playbook_taxonomy import build_category_tree, ensure_playbook_taxonomy

    ensure_playbook_taxonomy(db)
    playbooks = db.execute("SELECT * FROM playbooks ORDER BY name").fetchall()
    return render_template(
        "playbook_import.html",
        playbooks=[dict(p) for p in playbooks],
        categories=PLAYBOOK_CATEGORIES,
        category_tree=build_category_tree(db),
    )


@playbook_bp.route("/playbook/import/parse", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_import_parse():
    """Extract diagram from uploaded PDF/image and return preview data.

    For PDFs: extracts embedded images or renders page images with PyMuPDF.
    For images: returns the uploaded image for preview.
    Returns JSON with extracted image path and suggested player positions.
    """
    import os
    import uuid

    from playbook_pdf import pdf_page_count, pymupdf_available, render_pdf_pages

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"error": "No file selected"}), 400

    filename = uploaded.filename.lower()
    upload_dir = os.path.join(current_app.config.get("UPLOAD_FOLDER", "uploads"), "play_imports")
    os.makedirs(upload_dir, exist_ok=True)

    ext = os.path.splitext(filename)[1]
    safe_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(upload_dir, safe_name)
    uploaded.save(save_path)

    result = {
        "file_path": save_path,
        "file_url": f"/uploads/play_imports/{safe_name}",
        "filename": uploaded.filename,
        "is_pdf": filename.endswith(".pdf"),
        "extracted_images": [],
        "suggested_positions": _default_positions(),
        "page_count": 0,
        "recommend_bulk_import": False,
        "message": None,
    }

    if filename.endswith(".pdf"):
        if not pymupdf_available():
            return jsonify({
                "error": "PyMuPDF is required to import playbook PDFs. Install with: pip install pymupdf",
            }), 400

        try:
            result["page_count"] = pdf_page_count(save_path)
        except Exception as exc:
            return jsonify({"error": f"Could not read PDF: {exc}"}), 400

        max_preview_pages = 1 if result["page_count"] > 1 else None
        extracted = _extract_images_from_pdf(save_path, upload_dir, max_pages=max_preview_pages)
        result["extracted_images"] = extracted
        if extracted:
            result["file_url"] = extracted[0]["url"]

        if result["page_count"] > 1:
            result["recommend_bulk_import"] = True
            result["message"] = (
                f"This PDF has {result['page_count']} pages. "
                "Use Playbook → Bulk Import to bring in the full scout playbook at once."
            )

    return jsonify(result)


@playbook_bp.route("/playbook/import/save", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_import_save():
    """Save an imported play (from extracted diagram) to the playbook."""
    data = request.get_json(force=True) if request.is_json else request.form

    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    category = (data.get("category") or "offense").strip()
    category_id_raw = (data.get("category_id") or "").strip()
    tags = (data.get("tags") or "").strip()
    playbook_id = (data.get("playbook_id") or "").strip()
    diagram_json = (data.get("diagram_json") or "{}").strip()
    steps_json = (data.get("steps_json") or "[]").strip()
    source_image = (data.get("source_image") or "").strip()

    if not name:
        return jsonify({"error": "Play name is required"}), 400

    db = get_db()
    from playbook_taxonomy import ensure_playbook_taxonomy, legacy_category_from_id, resolve_category_id_by_path

    ensure_playbook_taxonomy(db)
    category_id = None
    if category_id_raw:
        try:
            category_id = int(category_id_raw)
        except ValueError:
            category_id = None
    if not category_id:
        category_id = resolve_category_id_by_path(db, "offense/man/plays")
    category = legacy_category_from_id(db, category_id)

    cur = db.execute(
        """INSERT INTO plays (name, description, category, category_id, tags, playbook_id, diagram_json)
           VALUES (?,?,?,?,?,?,?)""",
        (
            name, description, category, category_id, tags,
            int(playbook_id) if playbook_id else None,
            diagram_json,
        ),
    )
    play_db_id = cur.lastrowid

    # Insert steps
    try:
        steps = json.loads(steps_json) if isinstance(steps_json, str) else steps_json
        for i, step in enumerate(steps):
            positions = json.dumps(step.get("positions", {}))
            movements = json.dumps(step.get("movements", []))
            label = step.get("label", "")
            notes = step.get("notes", "")
            source_image = step.get("source_image", "") or source_image
            db.execute(
                """INSERT INTO play_steps (play_id, step_number, label, positions_json, movements_json, notes, source_image)
                   VALUES (?,?,?,?,?,?,?)""",
                (play_db_id, i, label, positions, movements, notes, source_image),
            )
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    db.commit()
    return jsonify({
        "id": play_db_id,
        "message": f"Play '{name}' imported successfully",
        "redirect": url_for("playbook.playbook_edit", play_id=play_db_id),
    })


def _extract_images_from_pdf(pdf_path, output_dir, max_pages=None):
    """Extract diagram images from a PDF file.

    Tries embedded images first, then renders each page with PyMuPDF.
    """
    import os
    import uuid

    from playbook_pdf import render_pdf_pages

    images = []

    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                if hasattr(page, 'images') and page.images:
                    for img_idx, img in enumerate(page.images):
                        try:
                            x0, y0, x1, y1 = img['x0'], img['top'], img['x1'], img['bottom']
                            cropped = page.within_bbox((x0, y0, x1, y1))
                            img_name = f"{uuid.uuid4().hex}.png"
                            img_path = os.path.join(output_dir, img_name)
                            im = cropped.to_image(resolution=150)
                            im.save(img_path)
                            images.append({
                                "file_path": img_path,
                                "url": f"/uploads/play_imports/{img_name}",
                                "page": page_num + 1,
                                "index": img_idx,
                            })
                        except Exception:
                            continue
    except (ImportError, Exception):
        pass

    if not images:
        try:
            import fitz
            doc = fitz.open(pdf_path)
            for page_num in range(len(doc)):
                page = doc[page_num]
                for img_idx, img_info in enumerate(page.get_images(full=True)):
                    try:
                        xref = img_info[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        image_ext = base_image.get("ext", "png")
                        img_name = f"{uuid.uuid4().hex}.{image_ext}"
                        img_path = os.path.join(output_dir, img_name)
                        with open(img_path, "wb") as f:
                            f.write(image_bytes)
                        images.append({
                            "file_path": img_path,
                            "url": f"/uploads/play_imports/{img_name}",
                            "page": page_num + 1,
                            "index": img_idx,
                        })
                    except Exception:
                        continue
            doc.close()
        except (ImportError, Exception):
            pass

    if not images:
        images = render_pdf_pages(
            pdf_path,
            output_dir,
            url_prefix="/uploads/play_imports",
            max_pages=max_pages,
        )

    return images


def _default_positions():
    """Return default basketball positions for a half-court diagram.

    5 players positioned in a standard offensive set.
    """
    return {
        "1": {"x": 250, "y": 380, "label": "PG"},   # Point guard (top of key)
        "2": {"x": 150, "y": 320, "label": "SG"},   # Shooting guard (left wing)
        "3": {"x": 350, "y": 320, "label": "SF"},   # Small forward (right wing)
        "4": {"x": 120, "y": 200, "label": "PF"},   # Power forward (left block)
        "5": {"x": 380, "y": 200, "label": "C"},    # Center (right block)
    }
