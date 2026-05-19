"""
Bulk Playbook Import Blueprint
===============================

Handles uploading a large PDF playbook and extracting individual plays
with automatic categorization based on page headers.

Two modes:
1. AUTO — Parse PDF headers, auto-detect sections/plays, bulk save
2. SPLIT — Extract pages, present review grid, user renames/categorizes each play

Routes:
- /playbook/bulk_import          — Upload page (both modes)
- /api/playbook/bulk/parse        — Parse PDF, extract pages with categories (AUTO)
- /api/playbook/bulk/split        — Split PDF into individual play PDFs (SPLIT)
- /api/playbook/bulk/save         — Save selected plays to playbook
"""

import json
import os
import uuid

from flask import Blueprint, render_template, request, jsonify, current_app, send_file

from helpers import get_db, require_feature

bulk_import_bp = Blueprint("bulk_import", __name__)


def _detect_section(lines):
    """Detect the main section from page header lines.

    Format: "21-22 - Liberty Charter Patriots - {Section} - [{Subsection}]"
    Returns the {Section} part (e.g. "BLOB", "Defense", "Offense", "Drills")
    """
    for line in lines:
        if "Liberty Charter Patriots" in line and " - " in line:
            parts = line.split("Liberty Charter Patriots - ")
            if len(parts) >= 2:
                remainder = parts[1].strip()
                if " - " in remainder:
                    section = remainder.split(" - ")[0].strip()
                else:
                    section = remainder
                section = section.rstrip(" -").strip()
                if section:
                    return section
    return ""


def _detect_subsection(lines, section):
    """Detect subsection from line 1 (for Drills section).

    In Drills, line 1 is the sub-category like "Defense", "Offense - Man", etc.
    """
    if len(lines) < 2:
        return ""
    line1 = lines[1].strip()
    # Skip if it's just the section name repeated
    if line1 == section:
        return ""
    # Skip "Plays", "Building Blocks" etc
    if line1 in ("Plays", "Building Blocks"):
        return ""
    return line1


def _detect_play_name(lines, section, subsection):
    """Detect the play name from page lines.

    Skips: header (line 0), section/sub-section (line 1), player positions,
    page numbers, description text.
    """
    skip_values = {"1", "2", "3", "4", "5", "x1", "x2", "x3", "x4", "x5",
                   "Plays", "Building Blocks"}

    for candidate in lines[2:]:
        c = candidate.strip()
        if not c:
            continue
        if c == section:
            continue
        if c == subsection:
            continue
        if c in skip_values:
            continue
        # Skip pure single-digit numbers (player positions)
        if c.isdigit() and len(c) <= 1:
            continue
        # Skip very short single chars
        if len(c) <= 1:
            continue
        # Skip description text (long sentences)
        if len(c) > 60:
            continue
        # Skip section+sub patterns like "Offense - Man" (but NOT "BLOB - Hand Up")
        if " - " in c and any(c.startswith(s + " -") for s in
            ("Offense", "Defense", "Press Break", "Transition")):
            continue
        return c
    return ""


def _extract_pages_with_categories(pdf_path):
    """Extract all pages from a PDF with category detection from headers.

    Returns a list of play dicts, each with:
    {
        "section": str,       # e.g. "BLOB", "Defense", "Offense"
        "subsection": str,    # e.g. "Offense - Man" (for Drills)
        "play_name": str,     # e.g. "Box 1", "Cross"
        "start_page": int,
        "end_page": int,
        "page_count": int,
        "pages": [{"page_number": int, "image_url": str, "image_path": str}, ...]
    }
    """
    import fitz

    doc = fitz.open(pdf_path)
    upload_dir = os.path.join(current_app.config.get("UPLOAD_FOLDER", "uploads"), "bulk_imports")
    os.makedirs(upload_dir, exist_ok=True)

    # First pass: extract all page data
    page_data = []
    current_section = ""
    current_subsection = ""

    for i, page in enumerate(doc):
        page_num = i + 1
        text = page.get_text().strip()
        lines = [l.strip() for l in text.split("\n") if l.strip()]

        # Detect section from header
        detected_section = _detect_section(lines)
        if detected_section:
            current_section = detected_section

        # Detect subsection (especially for Drills)
        detected_subsection = _detect_subsection(lines, current_section)
        if detected_subsection:
            current_subsection = detected_subsection

        # Detect play name
        play_name = _detect_play_name(lines, current_section, current_subsection)

        # Skip pages with no detectable play name (divider/blank pages)
        if not play_name:
            play_name = ""

        # Render page to image
        pix = page.get_pixmap(dpi=150)
        img_name = f"page_{page_num:04d}.png"
        img_path = os.path.join(upload_dir, img_name)
        pix.save(img_path)

        page_data.append({
            "page_number": page_num,
            "section": current_section or "Unknown",
            "subsection": current_subsection,
            "play_name": play_name,
            "image_url": f"/uploads/bulk_imports/{img_name}",
            "image_path": img_path,
        })

    doc.close()

    # Second pass: group consecutive pages
    # For Drills section: group by subsection (e.g. all "Defense" drill pages together)
    # For other sections: group by play name
    plays = []
    if not page_data:
        return plays

    current = {
        "section": page_data[0]["section"],
        "subsection": page_data[0]["subsection"],
        "play_name": page_data[0]["play_name"],
        "start_page": page_data[0]["page_number"],
        "end_page": page_data[0]["page_number"],
        "page_count": 1,
        "pages": [page_data[0]],
    }

    for p in page_data[1:]:
        is_drills = p["section"] == "Drills"

        if is_drills:
            # In Drills: group by subsection + play name
            same_group = (
                p["section"] == current["section"]
                and p["subsection"] == current["subsection"]
                and p["play_name"]
                and p["play_name"] == current["play_name"]
            )
        else:
            # In other sections: group by play name
            same_group = (
                p["section"] == current["section"]
                and p["play_name"]
                and p["play_name"] == current["play_name"]
            )

        if same_group:
            current["end_page"] = p["page_number"]
            current["page_count"] += 1
            current["pages"].append(p)
        else:
            plays.append(current)
            current = {
                "section": p["section"],
                "subsection": p["subsection"],
                "play_name": p["play_name"],
                "start_page": p["page_number"],
                "end_page": p["page_number"],
                "page_count": 1,
                "pages": [p],
            }
    plays.append(current)

    # Filter out unnamed divider pages (Building Blocks, etc.)
    plays = [p for p in plays if p["play_name"]]

    # For Drills: rename plays that have no name to use subsection
    for play in plays:
        if play["section"] == "Drills" and not play["play_name"] and play["subsection"]:
            play["play_name"] = f"Drill — {play['subsection']}"

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
    """Parse uploaded PDF and return extracted plays with categories (AUTO mode)."""
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


@bulk_import_bp.route("/api/playbook/bulk/split", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def bulk_import_split():
    """Split uploaded PDF into individual play PDFs for review (SPLIT mode).

    Returns a list of play groups, each with its page images and a downloadable PDF.
    The user reviews each group, renames it, and saves.
    """
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
    session_id = uuid.uuid4().hex
    pdf_path = os.path.join(upload_dir, f"{session_id}.pdf")
    uploaded.save(pdf_path)

    try:
        plays = _extract_pages_with_categories(pdf_path)
    except Exception as e:
        return jsonify({"error": f"Failed to parse PDF: {str(e)}"}), 400

    # For each play, create a mini-PDF from its pages
    import fitz
    source_doc = fitz.open(pdf_path)

    for play in plays:
        # Create a new PDF with just this play's pages
        new_doc = fitz.open()
        for page_info in play["pages"]:
            page_idx = page_info["page_number"] - 1
            new_doc.insert_pdf(source_doc, from_page=page_idx, to_page=page_idx)

        play_pdf_name = f"{session_id}_play_{play['start_page']:04d}.pdf"
        play_pdf_path = os.path.join(upload_dir, play_pdf_name)
        new_doc.save(play_pdf_path)
        new_doc.close()

        play["pdf_url"] = f"/uploads/bulk_imports/{play_pdf_name}"
        play["pdf_path"] = play_pdf_path

    source_doc.close()

    # Build summary
    sections = {}
    for play in plays:
        sec = play["section"]
        if sec not in sections:
            sections[sec] = {"count": 0, "pages": 0}
        sections[sec]["count"] += 1
        sections[sec]["pages"] += play["page_count"]

    return jsonify({
        "session_id": session_id,
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
        category = play_data.get("category") or _section_to_category(section)
        tags = play_data.get("tags", "")
        pages = play_data.get("pages", [])

        if not name:
            errors.append(f"Play {i+1}: missing name")
            continue

        try:
            # Create the play
            cur = db.execute(
                """INSERT INTO plays (name, description, category, tags, playbook_id, diagram_json)
                   VALUES (?,?,?,?,?,?)""",
                (
                    name,
                    f"Imported from bulk PDF — {section}",
                    category,
                    tags,
                    int(playbook_id) if playbook_id else None,
                    json.dumps({"section": section, "source": "bulk_import"}),
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
