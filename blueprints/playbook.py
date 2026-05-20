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


# ── Plays Import ──────────────────────────────────────────────

@playbook_bp.route("/playbook/import")
@require_feature("ENABLE_PRACTICES")
def playbook_import():
    """Plays import page — upload PDF or image for diagram extraction."""
    db = get_db()
    playbooks = db.execute("SELECT * FROM playbooks ORDER BY name").fetchall()
    return render_template(
        "playbook_import.html",
        playbooks=[dict(p) for p in playbooks],
        categories=PLAYBOOK_CATEGORIES,
    )


@playbook_bp.route("/playbook/import/parse", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_import_parse():
    """Extract diagram from uploaded PDF/image and return preview data.

    For PDFs: extracts embedded images using pdfplumber/PyMuPDF.
    For images: returns the uploaded image for preview.
    Returns JSON with extracted image path and suggested player positions.
    """
    import os, uuid, tempfile

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"error": "No file selected"}), 400

    filename = uploaded.filename.lower()
    upload_dir = os.path.join(current_app.config.get("UPLOAD_FOLDER", "uploads"), "play_imports")
    os.makedirs(upload_dir, exist_ok=True)

    # Save with unique name
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
    }

    if filename.endswith(".pdf"):
        # Extract images from PDF
        extracted = _extract_images_from_pdf(save_path, upload_dir)
        result["extracted_images"] = extracted
        if extracted:
            result["file_url"] = extracted[0]["url"]

    return jsonify(result)


@playbook_bp.route("/playbook/import/save", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_import_save():
    """Save an imported play (from extracted diagram) to the playbook."""
    data = request.get_json(force=True) if request.is_json else request.form

    name = (data.get("name") or "").strip()
    description = (data.get("description") or "").strip()
    category = (data.get("category") or "offense").strip()
    tags = (data.get("tags") or "").strip()
    playbook_id = (data.get("playbook_id") or "").strip()
    diagram_json = (data.get("diagram_json") or "{}").strip()
    steps_json = (data.get("steps_json") or "[]").strip()
    source_image = (data.get("source_image") or "").strip()

    if not name:
        return jsonify({"error": "Play name is required"}), 400

    db = get_db()
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


def _extract_images_from_pdf(pdf_path, output_dir):
    """Extract embedded images from a PDF file.

    Returns list of dicts with file_path and url for each extracted image.
    """
    import os, uuid
    images = []

    # Try pdfplumber first (good for embedded images)
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                if hasattr(page, 'images') and page.images:
                    for img_idx, img in enumerate(page.images):
                        try:
                            # Extract image bytes from the PDF
                            x0, y0, x1, y1 = img['x0'], img['top'], img['x1'], img['bottom']
                            # Crop the page to the image area and extract
                            cropped = page.within_bbox((x0, y0, x1, y1))
                            # Save as PNG
                            img_name = f"{uuid.uuid4().hex}.png"
                            img_path = os.path.join(output_dir, img_name)
                            # Use page to_image for the cropped area
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

    # Fallback: try PyMuPDF (fitz) for image extraction
    if not images:
        try:
            import fitz  # PyMuPDF
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

    # Last resort: convert entire PDF page to image
    if not images:
        try:
            from pdf2image import convert_from_path
            pages = convert_from_path(pdf_path, dpi=150, first_page=1, last_page=1)
            if pages:
                img_name = f"{uuid.uuid4().hex}.png"
                img_path = os.path.join(output_dir, img_name)
                pages[0].save(img_path, "PNG")
                images.append({
                    "file_path": img_path,
                    "url": f"/uploads/play_imports/{img_name}",
                    "page": 1,
                    "index": 0,
                })
        except (ImportError, Exception):
            pass

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
