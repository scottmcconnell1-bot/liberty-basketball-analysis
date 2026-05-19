"""
Bulk Playbook Import Blueprint
===============================

Handles uploading a large PDF playbook and extracting individual plays
with automatic categorization based on page headers.

Routes:
- /playbook/bulk_import     — Upload page
- /api/playbook/bulk/parse   — Parse PDF, extract pages with categories
- /api/playbook/bulk/save    — Save selected plays to playbook
"""

import json
import os
import uuid

from flask import Blueprint, render_template, request, jsonify, current_app

from helpers import get_db, require_feature

bulk_import_bp = Blueprint("bulk_import", __name__)


def _extract_pages_with_categories(pdf_path):
    """Extract all pages from a PDF with category detection from headers.

    Returns a list of dicts:
    {
        "page_number": int,
        "section": str,       # e.g. "BLOB", "Defense", "Offense"
        "play_name": str,     # e.g. "Box 1", "Cross"
        "image_url": str,
        "image_path": str,
        "page_count": int     # pages in this play (for multi-page plays)
    }
    """
    import fitz

    doc = fitz.open(pdf_path)
    upload_dir = os.path.join(current_app.config.get("UPLOAD_FOLDER", "uploads"), "bulk_imports")
    os.makedirs(upload_dir, exist_ok=True)

    pages = []
    current_section = ""
    current_play = ""
    play_start = 0

    for i, page in enumerate(doc):
        page_num = i + 1
        text = page.get_text().strip()
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        # Detect section from header line
        for line in lines:
            if "Liberty Charter Patriots" in line and " - " in line:
                parts = line.split(" - ")
                if len(parts) >= 3:
                    new_section = parts[2].strip()
                    # Clean up section name
                    for suffix in [" - Plays", " - Building Blocks", " - "]:
                        if new_section.endswith(suffix):
                            new_section = new_section[:-len(suffix)]
                    current_section = new_section.strip()
                break

        # Detect play name (line index 2, after header and section repeat)
        detected_play = ""
        if len(lines) >= 3:
            candidate = lines[2] if len(lines) > 2 else ""
            # Skip if it's just numbers/player positions
            if (candidate and
                not candidate.startswith("21-22") and
                candidate != current_section and
                candidate not in ("1", "2", "3", "4", "5", "x1", "x2", "x3", "x4", "x5") and
                len(candidate) > 1):
                detected_play = candidate

        # If play name changed, record the previous play's page range
        if detected_play and detected_play != current_play:
            if current_play and pages:
                # Update page count for the previous play group
                for p in pages[play_start:]:
                    p["page_count"] = len([pp for pp in pages[play_start:]
                                          if pp["play_name"] == current_play
                                          and pp["section"] == current_section])
            current_play = detected_play
            play_start = len(pages)

        # Render page to image
        pix = page.get_pixmap(dpi=150)
        img_name = f"page_{page_num:04d}.png"
        img_path = os.path.join(upload_dir, img_name)
        pix.save(img_path)

        pages.append({
            "page_number": page_num,
            "section": current_section or "Unknown",
            "play_name": current_play or f"Page {page_num}",
            "image_url": f"/uploads/bulk_imports/{img_name}",
            "image_path": img_path,
            "page_count": 1,
        })

    doc.close()

    # Group consecutive pages with same section+play into plays
    plays = []
    if pages:
        current = {
            "section": pages[0]["section"],
            "play_name": pages[0]["play_name"],
            "start_page": pages[0]["page_number"],
            "end_page": pages[0]["page_number"],
            "page_count": 1,
            "pages": [pages[0]],
        }
        for p in pages[1:]:
            if p["section"] == current["section"] and p["play_name"] == current["play_name"]:
                current["end_page"] = p["page_number"]
                current["page_count"] += 1
                current["pages"].append(p)
            else:
                plays.append(current)
                current = {
                    "section": p["section"],
                    "play_name": p["play_name"],
                    "start_page": p["page_number"],
                    "end_page": p["page_number"],
                    "page_count": 1,
                    "pages": [p],
                }
        plays.append(current)

    return plays


@bulk_import_bp.route("/playbook/bulk_import")
@require_feature("ENABLE_PRACTICES")
def bulk_import_page():
    """Bulk playbook import page — upload a large PDF and extract plays."""
    db = get_db()
    playbooks = db.execute("SELECT * FROM playbooks ORDER BY name").fetchall()
    return render_template(
        "playbook_bulk_import.html",
        playbooks=[dict(p) for p in playbooks],
    )


@bulk_import_bp.route("/api/playbook/bulk/parse", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def bulk_import_parse():
    """Parse uploaded PDF and return extracted plays with categories."""
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    uploaded = request.files["file"]
    if not uploaded.filename:
        return jsonify({"error": "No file selected"}), 400

    filename = uploaded.filename.lower()
    if not filename.endswith(".pdf"):
        return jsonify({"error": "Only PDF files are supported"}), 400

    # Save PDF temporarily
    upload_dir = os.path.join(current_app.config.get("UPLOAD_FOLDER", "uploads"), "bulk_imports")
    os.makedirs(upload_dir, exist_ok=True)
    pdf_name = f"{uuid.uuid4().hex}.pdf"
    pdf_path = os.path.join(upload_dir, pdf_name)
    uploaded.save(pdf_path)

    try:
        plays = _extract_pages_with_categories(pdf_path)
    except Exception as e:
        return jsonify({"error": f"Failed to parse PDF: {str(e)}"}), 400

    # Build summary
    sections = {}
    for play in plays:
        sec = play["section"]
        if sec not in sections:
            sections[sec] = {"count": 0, "pages": 0}
        sections[sec]["count"] += 1
        sections[sec]["pages"] += play["page_count"]

    return jsonify({
        "filename": uploaded.filename,
        "total_pages": sum(p["page_count"] for p in plays),
        "total_plays": len(plays),
        "sections": sections,
        "plays": plays,
    })


@bulk_import_bp.route("/api/playbook/bulk/save", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def bulk_import_save():
    """Save selected plays from bulk import to the playbook."""
    data = request.get_json(force=True)
    plays = data.get("plays", [])
    default_playbook_id = data.get("playbook_id", "")

    if not plays:
        return jsonify({"error": "No plays to save"}), 400

    db = get_db()
    saved = []
    errors = []

    for i, play_data in enumerate(plays):
        name = (play_data.get("play_name") or "").strip()
        section = (play_data.get("section") or "").strip()
        playbook_id = (play_data.get("playbook_id") or default_playbook_id).strip()
        category = _section_to_category(section)
        tags = play_data.get("tags", "")
        pages = play_data.get("pages", [])

        if not name:
            errors.append(f"Play {i+1}: missing name")
            continue

        try:
            # Create the play
            cur = db.execute(
                """INSERT INTO plays (name, description, category, tags, playbook_id, diagram_json, created_by)
                   VALUES (?,?,?,?,?,?,?)""",
                (
                    name,
                    f"Imported from bulk PDF — {section}",
                    category,
                    tags,
                    int(playbook_id) if playbook_id else None,
                    json.dumps({"section": section, "source": "bulk_import"}),
                    "bulk_import",
                ),
            )
            play_db_id = cur.lastrowid

            # Create steps from pages
            for j, page in enumerate(pages):
                source_image = page.get("image_url", "")
                db.execute(
                    """INSERT INTO play_steps (play_id, step_number, label, positions_json, movements_json, notes, source_image)
                       VALUES (?,?,?,?,?,?,?)""",
                    (
                        play_db_id,
                        j,
                        f"Step {j+1} (Page {page.get('page_number', '?')})",
                        "{}",
                        "[]",
                        "",
                        source_image,
                    ),
                )

            saved.append({"id": play_db_id, "name": name, "section": section})
        except Exception as e:
            errors.append(f"Play '{name}': {str(e)}")

    db.commit()

    return jsonify({
        "saved": saved,
        "saved_count": len(saved),
        "errors": errors,
    })


def _section_to_category(section):
    """Map PDF section names to playbook categories."""
    section_lower = section.lower().strip()
    mapping = {
        "offense": "offense",
        "defense": "defense",
        "blob": "out_of_bounds",
        "slob": "out_of_bounds",
        "press break": "press",
        "transition": "transition",
        "drills": "special",
    }
    for key, cat in mapping.items():
        if key in section_lower:
            return cat
    return "offense"  # default
