"""
Stat Books Blueprint — handwritten spiral scorebook extract / confirm MVP.

Routes under /stat-books/...
"""

from __future__ import annotations

import json
from pathlib import Path

from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from stat_book.checksum import apply_validation
from stat_book.demo import create_sample_draft, ensure_spiral_template
from stat_book.paths import (
    blank_path,
    confirmed_path,
    ensure_dirs,
    list_confirmed,
    list_templates,
    sanitize_game_id,
    sanitize_template_id,
    upload_dir,
)
from stat_book.pipeline import (
    create_manual_draft,
    extract_from_image,
    load_draft,
    load_layout,
    save_draft,
    save_layout,
)
from stat_book.schema import build_confirmed_box, stamp_confirmed, validate_confirmed_box

stat_books_bp = Blueprint("stat_books", __name__)

DEFAULT_TEMPLATE = "liberty_spiral_scorebook"


def _upload_root() -> str:
    return current_app.config.get("UPLOAD_FOLDER", "uploads")


def _parse_game_id(game_id: str) -> str | None:
    try:
        return sanitize_game_id(game_id)
    except ValueError:
        return None


@stat_books_bp.record_once
def _on_register(_state):
    ensure_dirs()
    try:
        ensure_spiral_template()
    except FileNotFoundError:
        pass


@stat_books_bp.route("/stat-books")
def index():
    ensure_dirs()
    return render_template(
        "stat_books/index.html",
        templates=list_templates(),
        confirmed=list_confirmed(),
        default_template=DEFAULT_TEMPLATE,
    )


@stat_books_bp.route("/stat-books/templates/<template_id>", methods=["GET"])
def calibrate(template_id):
    tid = sanitize_template_id(template_id)
    layout = load_layout(tid) if (blank_path(tid).parent / "layout.json").is_file() else {}
    blank = blank_path(tid)
    return render_template(
        "stat_books/calibrate.html",
        template_id=tid,
        layout_json=json.dumps(layout, indent=2),
        has_blank=blank.is_file(),
        blank_name=blank.name if blank.is_file() else "blank.png",
    )


@stat_books_bp.route("/stat-books/templates/<template_id>/blank", methods=["POST"])
def upload_blank(template_id):
    tid = sanitize_template_id(template_id)
    file = request.files.get("blank")
    if not file or not file.filename:
        flash("Choose a blank template image.", "error")
        return redirect(url_for("stat_books.calibrate", template_id=tid))
    ext = Path(file.filename).suffix.lower() or ".png"
    dest_dir = blank_path(tid).parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    for old in dest_dir.glob("blank.*"):
        try:
            old.unlink()
        except OSError:
            pass
    dest = dest_dir / f"blank{ext}"
    file.save(str(dest))
    flash(f"Saved {dest.name}", "ok")
    return redirect(url_for("stat_books.calibrate", template_id=tid))


@stat_books_bp.route("/stat-books/templates/<template_id>/layout", methods=["GET", "POST"])
def layout_api(template_id):
    tid = sanitize_template_id(template_id)
    if request.method == "GET":
        return jsonify(load_layout(tid))
    raw = request.get_json(silent=True)
    if raw is None and request.form.get("layout_json"):
        try:
            raw = json.loads(request.form["layout_json"])
        except json.JSONDecodeError:
            return jsonify({"ok": False, "error": "Invalid JSON"}), 400
    if not isinstance(raw, dict):
        return jsonify({"ok": False, "error": "layout must be object"}), 400
    path = save_layout(tid, raw)
    if request.form.get("layout_json"):
        flash("layout.json saved", "ok")
        return redirect(url_for("stat_books.calibrate", template_id=tid))
    return jsonify({"ok": True, "path": str(path)})


@stat_books_bp.route("/stat-books/templates/<template_id>/blank-file")
def blank_file(template_id):
    path = blank_path(sanitize_template_id(template_id))
    if not path.is_file():
        return jsonify({"error": "no blank"}), 404
    return send_file(path)


@stat_books_bp.route("/stat-books/games/<game_id>/upload", methods=["POST"])
def upload_game(game_id):
    gid = _parse_game_id(game_id)
    if not gid:
        flash("Invalid Game ID. Use letters, numbers, and . _ - , only.", "error")
        return redirect(url_for("stat_books.index"))
    try:
        tid = sanitize_template_id(request.form.get("template_id") or DEFAULT_TEMPLATE)
    except ValueError:
        flash("Invalid template.", "error")
        return redirect(url_for("stat_books.index"))
    file = request.files.get("scan") or request.files.get("file")
    if not file or not file.filename:
        flash("Choose a photo/scan.", "error")
        return redirect(url_for("stat_books.index"))
    work = upload_dir(gid, _upload_root())
    ext = Path(file.filename).suffix.lower() or ".png"
    original = work / f"original{ext}"
    file.save(str(original))
    corners = None
    if request.form.get("corners"):
        try:
            corners = json.loads(request.form["corners"])
        except json.JSONDecodeError:
            corners = None
    try:
        payload = extract_from_image(
            original, tid, gid, corners=corners, upload_folder=_upload_root()
        )
    except Exception as exc:  # noqa: BLE001 — always land on review UI
        current_app.logger.exception("stat-book extract failed for %s", gid)
        payload = create_manual_draft(
            gid, tid, _upload_root(), reason=str(exc), image_path=original
        )
    if (payload.get("meta") or {}).get("manual_fill"):
        flash(
            f"Upload saved for {gid}. OCR/align incomplete — fill stats on the review screen.",
            "ok",
        )
    else:
        flash(f"Draft extracted for {gid} — review before confirming.", "ok")
    return redirect(url_for("stat_books.review", game_id=gid))


@stat_books_bp.route("/stat-books/games/<game_id>/align", methods=["POST"])
def align_game(game_id):
    gid = _parse_game_id(game_id)
    if not gid:
        return jsonify({"ok": False, "error": "Invalid game_id"}), 400
    draft = load_draft(gid, _upload_root())
    work = upload_dir(gid, _upload_root())
    originals = list(work.glob("original.*"))
    if not originals:
        return jsonify({"ok": False, "error": "No original upload"}), 404
    body = request.get_json(silent=True) or {}
    tid = body.get("template_id") or (draft or {}).get("box", {}).get("template_id") or DEFAULT_TEMPLATE
    try:
        payload = extract_from_image(
            originals[0], tid, gid, corners=body.get("corners"), upload_folder=_upload_root()
        )
    except Exception as exc:  # noqa: BLE001
        current_app.logger.exception("stat-book align failed for %s", gid)
        payload = create_manual_draft(
            gid, tid, _upload_root(), reason=str(exc), image_path=originals[0]
        )
    return jsonify({"ok": True, "draft": payload})


@stat_books_bp.route("/stat-books/games/<game_id>/review")
def review(game_id):
    gid = _parse_game_id(game_id)
    if not gid:
        flash("Invalid Game ID.", "error")
        return redirect(url_for("stat_books.index"))
    draft = load_draft(gid, _upload_root())
    if not draft:
        flash(f"No draft for {gid}.", "error")
        return redirect(url_for("stat_books.index"))
    box = apply_validation(draft.get("box") or {})
    draft["box"] = box
    work = upload_dir(gid, _upload_root())
    # Prefer the coach upload over aligned.png — a failed/identity align can
    # overwrite the sheet view with the blank template and hide the real scan.
    image_name = None
    for name in ("original.jpeg", "original.jpg", "original.webp", "original.png", "aligned.png"):
        if (work / name).is_file():
            image_name = name
            break
    if image_name is None:
        found = list(work.glob("original.*")) + list(work.glob("aligned.*"))
        if found:
            image_name = found[0].name
    aligned_name = "aligned.png" if (work / "aligned.png").is_file() else None
    return render_template(
        "stat_books/review.html",
        game_id=gid,
        box=box,
        meta=draft.get("meta") or {},
        image_name=image_name,
        aligned_name=aligned_name,
    )


@stat_books_bp.route("/stat-books/games/<game_id>/image/<path:filename>")
def game_image(game_id, filename):
    gid = _parse_game_id(game_id)
    if not gid:
        return jsonify({"error": "invalid game_id"}), 400
    work = upload_dir(gid, _upload_root())
    path = (work / filename).resolve()
    if not str(path).startswith(str(work.resolve())) or not path.is_file():
        return jsonify({"error": "not found"}), 404
    return send_file(path)


@stat_books_bp.route("/stat-books/games/<game_id>/draft", methods=["GET", "POST"])
def draft_api(game_id):
    gid = _parse_game_id(game_id)
    if not gid:
        return jsonify({"ok": False, "error": "Invalid game_id"}), 400
    if request.method == "GET":
        draft = load_draft(gid, _upload_root())
        if not draft:
            return jsonify({"ok": False, "error": "no draft"}), 404
        draft["box"] = apply_validation(draft.get("box") or {})
        return jsonify(draft)

    body = request.get_json(silent=True) or {}
    box_in = body.get("box") or body
    box = build_confirmed_box(
        game_id=gid,
        template_id=box_in.get("template_id") or DEFAULT_TEMPLATE,
        players=box_in.get("players") or [],
        home_team=box_in.get("home_team"),
        away_team=box_in.get("away_team"),
        final_score_home=box_in.get("final_score_home"),
        final_score_away=box_in.get("final_score_away"),
        quarters=box_in.get("quarters"),
        checksums=box_in.get("checksums") or {},
    )
    box = apply_validation(box)
    existing = load_draft(gid, _upload_root()) or {"meta": {}}
    payload = {"box": box, "meta": existing.get("meta") or {}}
    save_draft(gid, payload, _upload_root())
    return jsonify({"ok": True, "box": box})


@stat_books_bp.route("/stat-books/games/<game_id>/confirm", methods=["POST"])
def confirm_game(game_id):
    gid = _parse_game_id(game_id)
    if not gid:
        return jsonify({"ok": False, "error": "Invalid game_id"}), 400
    body = request.get_json(silent=True) or {}
    box_in = body.get("box") or body
    confirmed_by = (body.get("confirmed_by") or "coach").strip()
    box = build_confirmed_box(
        game_id=gid,
        template_id=box_in.get("template_id") or DEFAULT_TEMPLATE,
        players=box_in.get("players") or [],
        home_team=box_in.get("home_team") or "Liberty",
        away_team=box_in.get("away_team"),
        final_score_home=box_in.get("final_score_home"),
        final_score_away=box_in.get("final_score_away"),
        quarters=box_in.get("quarters"),
        checksums=box_in.get("checksums") or {},
    )
    box = apply_validation(box)
    box = stamp_confirmed(box, confirmed_by=confirmed_by)
    errors = validate_confirmed_box(box)
    if errors:
        return jsonify({"ok": False, "error": "schema", "details": errors}), 400
    path = confirmed_path(gid)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(box, fh, indent=2)
        fh.write("\n")
    return jsonify({"ok": True, "path": str(path), "box": box})


@stat_books_bp.route("/stat-books/confirmed/<game_id>")
def get_confirmed(game_id):
    gid = _parse_game_id(game_id)
    if not gid:
        return jsonify({"ok": False, "error": "Invalid game_id"}), 400
    path = confirmed_path(gid)
    if not path.is_file():
        return jsonify({"ok": False, "error": "not found"}), 404
    with path.open(encoding="utf-8") as fh:
        return jsonify(json.load(fh))


@stat_books_bp.route("/stat-books/sample", methods=["POST", "GET"])
def sample():
    """Seed HSB/Liberty filled sample into review for pipeline practice."""
    gid = _parse_game_id(request.values.get("game_id") or "sample-hsb-liberty")
    if not gid:
        flash("Invalid Game ID.", "error")
        return redirect(url_for("stat_books.index"))
    create_sample_draft(gid, upload_folder=_upload_root())
    flash(f"Sample draft {gid} ready.", "ok")
    return redirect(url_for("stat_books.review", game_id=gid))
