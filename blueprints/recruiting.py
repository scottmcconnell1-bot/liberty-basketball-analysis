"""
Recruiting Station Blueprint
============================
Coach-facing recruiting profiles + public share links for next-level coaches.

Routes:
  GET    /recruiting                         — list profiles
  GET    /recruiting/new                     — create form
  GET    /recruiting/<id>/edit               — edit form
  GET    /api/recruiting                     — list JSON
  POST   /api/recruiting                     — create
  GET    /api/recruiting/<id>                — get one
  PUT    /api/recruiting/<id>                — update
  DELETE /api/recruiting/<id>                — delete
  POST   /api/recruiting/<id>/share          — ensure share token
  POST   /api/recruiting/<id>/unshare        — revoke share token
  GET    /api/recruiting/player-defaults/<id>— defaults + stats from player
  GET    /recruiting/share/<token>           — public read-only profile
  GET    /recruiting/share/<token>/print     — print-friendly profile
"""

from flask import (
    Blueprint,
    abort,
    jsonify,
    render_template,
    request,
    url_for,
)

from helpers import SCHEDULE_LEVEL_OPTIONS, get_db, require_feature
import recruiting as recruiting_helpers

recruiting_bp = Blueprint("recruiting", __name__)


def _share_url(token: str) -> str:
    return url_for("recruiting.recruiting_share", token=token, _external=True)


def _print_url(token: str) -> str:
    return url_for("recruiting.recruiting_share_print", token=token, _external=True)


def _profile_with_stats(db, profile: dict | None) -> dict | None:
    if not profile:
        return None
    stats = recruiting_helpers.player_stats_summary(
        db,
        profile.get("player_id"),
        profile.get("player_name") or profile.get("display_name"),
    )
    profile = dict(profile)
    profile["stats"] = stats
    profile["stats_blurb"] = recruiting_helpers.format_stats_blurb(stats)
    if profile.get("share_token"):
        profile["share_url"] = _share_url(profile["share_token"])
        profile["print_url"] = _print_url(profile["share_token"])
    else:
        profile["share_url"] = None
        profile["print_url"] = None
    return profile


# ── Coach UI ─────────────────────────────────────────────────

@recruiting_bp.route("/recruiting")
@require_feature("ENABLE_RECRUITING")
def recruiting_page():
    db = get_db()
    level = (request.args.get("level") or "").strip() or None
    profiles = [
        _profile_with_stats(db, p)
        for p in recruiting_helpers.list_profiles(db, program_level=level)
    ]
    players = db.execute(
        "SELECT id, name, jersey_number, position, grade, level, program_name "
        "FROM players ORDER BY name"
    ).fetchall()
    return render_template(
        "recruiting.html",
        profiles=profiles,
        players=players,
        level_options=SCHEDULE_LEVEL_OPTIONS,
        filter_level=level or "",
        message=request.args.get("message"),
        error=request.args.get("error"),
    )


@recruiting_bp.route("/recruiting/new")
@require_feature("ENABLE_RECRUITING")
def recruiting_new_page():
    db = get_db()
    players = db.execute(
        "SELECT id, name, jersey_number, position, grade, level, program_name "
        "FROM players ORDER BY name"
    ).fetchall()
    defaults = {}
    player_id = request.args.get("player_id", type=int)
    if player_id:
        defaults = recruiting_helpers.defaults_from_player(db, player_id)
    return render_template(
        "recruiting_edit.html",
        profile=None,
        defaults=defaults,
        players=players,
        level_options=SCHEDULE_LEVEL_OPTIONS,
        mode="create",
    )


@recruiting_bp.route("/recruiting/<int:profile_id>/edit")
@require_feature("ENABLE_RECRUITING")
def recruiting_edit_page(profile_id):
    db = get_db()
    profile = _profile_with_stats(db, recruiting_helpers.get_profile(db, profile_id))
    if not profile:
        abort(404)
    players = db.execute(
        "SELECT id, name, jersey_number, position, grade, level, program_name "
        "FROM players ORDER BY name"
    ).fetchall()
    return render_template(
        "recruiting_edit.html",
        profile=profile,
        defaults={},
        players=players,
        level_options=SCHEDULE_LEVEL_OPTIONS,
        mode="edit",
    )


# ── Public share (ungated, like playbook share) ───────────────

@recruiting_bp.route("/recruiting/share/<token>")
def recruiting_share(token):
    db = get_db()
    profile = _profile_with_stats(db, recruiting_helpers.get_profile_by_share_token(db, token))
    if not profile:
        abort(404)
    return render_template(
        "recruiting_public.html",
        profile=profile,
        print_mode=False,
        share_url=_share_url(token),
        print_url=_print_url(token),
    )


@recruiting_bp.route("/recruiting/share/<token>/print")
def recruiting_share_print(token):
    db = get_db()
    profile = _profile_with_stats(db, recruiting_helpers.get_profile_by_share_token(db, token))
    if not profile:
        abort(404)
    return render_template(
        "recruiting_public.html",
        profile=profile,
        print_mode=True,
        share_url=_share_url(token),
        print_url=_print_url(token),
    )


# ── API ──────────────────────────────────────────────────────

@recruiting_bp.route("/api/recruiting", methods=["GET"])
@require_feature("ENABLE_RECRUITING")
def api_recruiting_list():
    db = get_db()
    level = (request.args.get("level") or "").strip() or None
    profiles = [
        _profile_with_stats(db, p)
        for p in recruiting_helpers.list_profiles(db, program_level=level)
    ]
    return jsonify(profiles)


@recruiting_bp.route("/api/recruiting", methods=["POST"])
@require_feature("ENABLE_RECRUITING")
def api_recruiting_create():
    db = get_db()
    data = request.get_json(force=True) if request.is_json else request.form.to_dict()
    if not request.is_json and "film_links" in request.form:
        data["film_links"] = request.form.get("film_links")
    try:
        profile = recruiting_helpers.create_profile(db, data)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_profile_with_stats(db, profile)), 201


@recruiting_bp.route("/api/recruiting/<int:profile_id>", methods=["GET"])
@require_feature("ENABLE_RECRUITING")
def api_recruiting_get(profile_id):
    db = get_db()
    profile = _profile_with_stats(db, recruiting_helpers.get_profile(db, profile_id))
    if not profile:
        abort(404)
    return jsonify(profile)


@recruiting_bp.route("/api/recruiting/<int:profile_id>", methods=["PUT"])
@require_feature("ENABLE_RECRUITING")
def api_recruiting_update(profile_id):
    db = get_db()
    data = request.get_json(force=True) if request.is_json else request.form.to_dict()
    try:
        profile = recruiting_helpers.update_profile(db, profile_id, data)
    except KeyError:
        abort(404)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(_profile_with_stats(db, profile))


@recruiting_bp.route("/api/recruiting/<int:profile_id>", methods=["DELETE"])
@require_feature("ENABLE_RECRUITING")
def api_recruiting_delete(profile_id):
    db = get_db()
    if not recruiting_helpers.get_profile(db, profile_id):
        abort(404)
    recruiting_helpers.delete_profile(db, profile_id)
    return jsonify({"status": "deleted"})


@recruiting_bp.route("/api/recruiting/<int:profile_id>/share", methods=["POST"])
@require_feature("ENABLE_RECRUITING")
def api_recruiting_share(profile_id):
    db = get_db()
    try:
        token = recruiting_helpers.ensure_share_token(db, profile_id)
    except ValueError:
        abort(404)
    return jsonify(
        {
            "token": token,
            "url": _share_url(token),
            "print_url": _print_url(token),
        }
    )


@recruiting_bp.route("/api/recruiting/<int:profile_id>/unshare", methods=["POST"])
@require_feature("ENABLE_RECRUITING")
def api_recruiting_unshare(profile_id):
    db = get_db()
    if not recruiting_helpers.get_profile(db, profile_id):
        abort(404)
    recruiting_helpers.revoke_share_token(db, profile_id)
    return jsonify({"status": "unshared"})


@recruiting_bp.route("/api/recruiting/player-defaults/<int:player_id>", methods=["GET"])
@require_feature("ENABLE_RECRUITING")
def api_recruiting_player_defaults(player_id):
    db = get_db()
    defaults = recruiting_helpers.defaults_from_player(db, player_id)
    if not defaults:
        abort(404)
    return jsonify(defaults)
