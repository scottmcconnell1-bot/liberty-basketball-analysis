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
from pathlib import Path

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    jsonify,
    flash,
    current_app,
    session,
)

from helpers import get_db, require_feature, get_default_team_id
from module_entitlements import enforce_module_access
from module_keys import PLAYBOOK_RECOGNITION

playbook_bp = Blueprint("playbook", __name__)

_PUBLIC_ENDPOINTS = frozenset({
    "playbook.playbook_share",
})

# Liberty program playbooks (separate from opponent scout playbooks).
# Stored on plays.team_key via runtime ALTER — schema.sql gate deferred.
PLAYBOOK_TEAMS = (
    {"key": "hs_boys", "label": "High School Boys"},
    {"key": "hs_girls", "label": "High School Girls"},
    {"key": "jh_boys", "label": "Jr High Boys"},
    {"key": "jh_girls", "label": "Jr High Girls"},
)
DEFAULT_PLAYBOOK_TEAM = "hs_boys"
PLAYBOOK_TEAM_KEYS = frozenset(t["key"] for t in PLAYBOOK_TEAMS)
_PLAYBOOK_TEAM_LABELS = {t["key"]: t["label"] for t in PLAYBOOK_TEAMS}
_SESSION_TEAM_KEY = "playbook_team"


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


def normalize_playbook_team(raw):
    key = (raw or "").strip()
    if key in PLAYBOOK_TEAM_KEYS:
        return key
    return DEFAULT_PLAYBOOK_TEAM


def playbook_team_label(team_key):
    return _PLAYBOOK_TEAM_LABELS.get(
        normalize_playbook_team(team_key),
        _PLAYBOOK_TEAM_LABELS[DEFAULT_PLAYBOOK_TEAM],
    )


def resolve_playbook_team(*, persist=False):
    """Resolve active team from query → form → session → default."""
    raw = request.args.get("team")
    if raw is None and request.method in ("POST", "PUT", "PATCH"):
        raw = request.form.get("team_key") or request.form.get("team")
    if raw is None:
        raw = session.get(_SESSION_TEAM_KEY)
    team_key = normalize_playbook_team(raw)
    if persist:
        session[_SESSION_TEAM_KEY] = team_key
    return team_key


def _team_template_kwargs(team_key=None):
    team = normalize_playbook_team(team_key)
    return {
        "playbook_teams": list(PLAYBOOK_TEAMS),
        "selected_team": team,
        "selected_team_label": playbook_team_label(team),
    }


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


def _plays_query(db, team_key=None):
    _ensure_play_progression_columns(db)
    team_key = normalize_playbook_team(team_key)
    return db.execute(
        """SELECT p.*, pb.name as playbook_name,
                  pc.name as category_name,
                  pc.slug_path as category_path,
                  (SELECT COUNT(*) FROM play_steps ps WHERE ps.play_id = p.id) as step_count,
                  (SELECT COUNT(*) FROM plays child WHERE child.parent_play_id = p.id) as progression_count
           FROM plays p
           LEFT JOIN playbooks pb ON pb.id = p.playbook_id
           LEFT JOIN play_categories pc ON pc.id = p.category_id
           WHERE COALESCE(p.team_key, ?) = ?
             AND COALESCE(pb.kind, 'team') != 'opponent'
           ORDER BY p.name COLLATE NOCASE ASC, p.id ASC""",
        (DEFAULT_PLAYBOOK_TEAM, team_key),
    ).fetchall()


def _ensure_play_team_key_column(db):
    """Additive team playbook column — does not edit schema.sql (Scott gate)."""
    cols = {row[1] for row in db.execute("PRAGMA table_info(plays)").fetchall()}
    if "team_key" not in cols:
        # DEFAULT must be a literal in SQLite ALTER; key is a fixed constant.
        db.execute(
            "ALTER TABLE plays ADD COLUMN team_key TEXT NOT NULL DEFAULT 'hs_boys'"
        )
    # Existing rows / empty values land on HS Boys so nothing disappears.
    db.execute(
        """UPDATE plays
              SET team_key = ?
            WHERE team_key IS NULL OR TRIM(COALESCE(team_key, '')) = ''""",
        (DEFAULT_PLAYBOOK_TEAM,),
    )


def _ensure_play_progression_columns(db):
    cols = {row[1] for row in db.execute("PRAGMA table_info(plays)").fetchall()}
    if "parent_play_id" not in cols:
        db.execute(
            "ALTER TABLE plays ADD COLUMN parent_play_id INTEGER REFERENCES plays(id) ON DELETE SET NULL"
        )
    if "progression_order" not in cols:
        db.execute(
            "ALTER TABLE plays ADD COLUMN progression_order INTEGER NOT NULL DEFAULT 0"
        )
    if "list_order" not in cols:
        db.execute("ALTER TABLE plays ADD COLUMN list_order INTEGER")
    _ensure_play_team_key_column(db)
    # Backfill top-level list_order once so drag-reorder has a stable baseline.
    missing = db.execute(
        """SELECT COUNT(*) AS c FROM plays
            WHERE (parent_play_id IS NULL OR parent_play_id = 0)
              AND list_order IS NULL"""
    ).fetchone()["c"]
    if missing:
        rows = db.execute(
            """SELECT id FROM plays
                WHERE parent_play_id IS NULL OR parent_play_id = 0
                ORDER BY updated_at DESC, id DESC"""
        ).fetchall()
        for index, row in enumerate(rows):
            db.execute("UPDATE plays SET list_order = ? WHERE id = ?", (index, row["id"]))
        db.commit()


def _group_plays_for_list(db, plays):
    """Nest progression children under their parent; hide orphans' children from top level."""
    _ensure_play_progression_columns(db)
    play_dicts = [dict(p) for p in plays]
    by_id = {p["id"]: p for p in play_dicts}
    for p in play_dicts:
        p["progressions"] = []
        p["search_blob"] = (p.get("name") or "").lower()

    for p in play_dicts:
        parent_id = p.get("parent_play_id")
        if parent_id and parent_id in by_id:
            by_id[parent_id]["progressions"].append(p)
            by_id[parent_id]["search_blob"] += " " + (p.get("name") or "").lower()

    for p in play_dicts:
        if p["progressions"]:
            p["progressions"].sort(
                key=lambda child: (
                    child.get("progression_order") or 0,
                    child.get("name") or "",
                )
            )

    top = [
        p
        for p in play_dicts
        if not p.get("parent_play_id") or p.get("parent_play_id") not in by_id
    ]
    # Browse list is always A–Z by name (case-insensitive). list_order remains
    # for drag-reorder API / progressions; it does not drive the main index.
    top.sort(key=lambda p: ((p.get("name") or "").lower(), p.get("id") or 0))
    return top


def reorder_plays(db, *, ordered_ids, parent_play_id=None):
    """Persist a new order for top-level plays or progressions under one parent."""
    _ensure_play_progression_columns(db)
    ids = []
    for raw in ordered_ids or []:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        raise ValueError("No plays to reorder")

    if parent_play_id in ("", None):
        parent_play_id = None
    else:
        parent_play_id = int(parent_play_id)

    for index, play_id in enumerate(ids):
        if parent_play_id is None:
            row = db.execute(
                "SELECT id, parent_play_id FROM plays WHERE id = ?",
                (play_id,),
            ).fetchone()
            if not row or row["parent_play_id"]:
                raise ValueError("Top-level reorder includes a progression play")
            db.execute(
                "UPDATE plays SET list_order = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (index, play_id),
            )
        else:
            row = db.execute(
                "SELECT id, parent_play_id FROM plays WHERE id = ?",
                (play_id,),
            ).fetchone()
            if not row or row["parent_play_id"] != parent_play_id:
                raise ValueError("Progression reorder includes a play from another group")
            db.execute(
                """UPDATE plays
                      SET progression_order = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?""",
                (index, play_id),
            )
    db.commit()
    return ids


def move_plays_to_category(db, *, play_ids, category_id):
    """Assign top-level plays (and their progressions) to a leaf category."""
    from playbook_taxonomy import legacy_category_from_id

    _ensure_play_progression_columns(db)
    try:
        category_id = int(category_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid category") from exc

    cat = db.execute(
        "SELECT id, name, slug_path FROM play_categories WHERE id = ?",
        (category_id,),
    ).fetchone()
    if not cat:
        raise ValueError("Category not found")
    if (cat["slug_path"] or "") == "opponents":
        raise ValueError("Opponents is not a play category — open Opponent Playbooks instead")
    has_child = db.execute(
        "SELECT 1 FROM play_categories WHERE parent_id = ? LIMIT 1",
        (category_id,),
    ).fetchone()
    if has_child:
        raise ValueError("Drop onto a specific category (e.g. Man or Zone), not a parent folder")

    ids = []
    for raw in play_ids or []:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        raise ValueError("No plays to move")

    legacy = legacy_category_from_id(db, category_id)
    moved = []
    for play_id in ids:
        row = db.execute(
            "SELECT id, parent_play_id FROM plays WHERE id = ?",
            (play_id,),
        ).fetchone()
        if not row:
            continue
        # Progressions follow their parent; skip direct progression moves.
        if row["parent_play_id"]:
            continue
        db.execute(
            """UPDATE plays
                  SET category_id = ?, category = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
            (category_id, legacy, play_id),
        )
        db.execute(
            """UPDATE plays
                  SET category_id = ?, category = ?, updated_at = CURRENT_TIMESTAMP
                WHERE parent_play_id = ?""",
            (category_id, legacy, play_id),
        )
        moved.append(play_id)

    if not moved:
        raise ValueError("No top-level plays to move")
    db.commit()
    return {
        "moved_ids": moved,
        "category_id": category_id,
        "category_path": cat["slug_path"] or "",
        "category_name": cat["name"] or "",
    }


def _copy_play_row(db, play, *, team_key, name, parent_play_id=None, progression_order=0):
    """Insert a deep-copied play row (no share_token) and return new id."""
    _ensure_play_progression_columns(db)
    cur = db.execute(
        """INSERT INTO plays (
               name, description, category, category_id, tags, playbook_id,
               diagram_json, team_key, parent_play_id, progression_order, list_order
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            name,
            play["description"],
            play["category"],
            play["category_id"],
            play["tags"],
            play["playbook_id"],
            play["diagram_json"],
            normalize_playbook_team(team_key),
            parent_play_id,
            progression_order if progression_order is not None else 0,
            None,
        ),
    )
    return cur.lastrowid


def _copy_play_steps(db, source_play_id, dest_play_id):
    steps = db.execute(
        "SELECT * FROM play_steps WHERE play_id = ? ORDER BY step_number",
        (source_play_id,),
    ).fetchall()
    for step in steps:
        db.execute(
            """INSERT INTO play_steps (
                   play_id, step_number, label, positions_json, movements_json,
                   notes, source_image
               ) VALUES (?,?,?,?,?,?,?)""",
            (
                dest_play_id,
                step["step_number"],
                step["label"],
                step["positions_json"],
                step["movements_json"],
                step["notes"],
                step["source_image"] if "source_image" in step.keys() else None,
            ),
        )


def copy_play_to_team(db, play_id, target_team, *, include_progressions=True):
    """Deep-copy a play (and optional progressions) into another team playbook.

    Edits on the copy do not affect the source. Share tokens are not copied.
    """
    _ensure_play_progression_columns(db)
    target_team = normalize_playbook_team(target_team)
    play = db.execute("SELECT * FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        raise ValueError("Play not found")
    play = dict(play)
    source_team = normalize_playbook_team(play.get("team_key"))
    same_team = source_team == target_team
    new_name = play["name"] + (" (copy)" if same_team else "")

    new_id = _copy_play_row(
        db,
        play,
        team_key=target_team,
        name=new_name,
        parent_play_id=None,
        progression_order=0,
    )
    _copy_play_steps(db, play_id, new_id)

    copied_ids = [new_id]
    if include_progressions and not play.get("parent_play_id"):
        children = db.execute(
            """SELECT * FROM plays
                WHERE parent_play_id = ?
                ORDER BY progression_order ASC, id ASC""",
            (play_id,),
        ).fetchall()
        for index, child in enumerate(children):
            child = dict(child)
            child_name = child["name"] + (" (copy)" if same_team else "")
            child_id = _copy_play_row(
                db,
                child,
                team_key=target_team,
                name=child_name,
                parent_play_id=new_id,
                progression_order=child.get("progression_order") or index,
            )
            _copy_play_steps(db, child["id"], child_id)
            copied_ids.append(child_id)

    db.commit()
    return {
        "new_play_id": new_id,
        "copied_ids": copied_ids,
        "target_team": target_team,
        "source_team": source_team,
        "name": new_name,
    }


def ensure_cycle_spots_progressions(db):
    """One-time: fold PDF-split Cycle Spots sequences under one parent play."""
    _ensure_play_progression_columns(db)
    existing = db.execute(
        "SELECT id FROM plays WHERE name = ? AND (parent_play_id IS NULL OR parent_play_id = 0)",
        ("Cycle Spots",),
    ).fetchone()
    progression_names = [
        "4 Flash",
        "5-1-2",
        "5-1-2-4",
        "5-1-3",
        "Finish the Cycle",
        "Last Leg",
    ]
    children = []
    for name in progression_names:
        row = db.execute(
            """SELECT id, category_id, category, playbook_id, team_key
                 FROM plays
                WHERE name = ?
                  AND (parent_play_id IS NULL OR parent_play_id = 0)
                ORDER BY id
                LIMIT 1""",
            (name,),
        ).fetchone()
        if row:
            children.append(dict(row))
    if len(children) < 2:
        return existing["id"] if existing else None

    if existing:
        parent_id = existing["id"]
    else:
        template = children[0]
        import json as _json

        diagram = _json.dumps(
            {
                "source": "progression_group",
                "group": "cycle_spots",
                "progression_names": progression_names,
            }
        )
        # Ensure team_key is available on child dicts after column ensure.
        if "team_key" not in template:
            template["team_key"] = DEFAULT_PLAYBOOK_TEAM
        cur = db.execute(
            """INSERT INTO plays (
                   name, description, category, category_id, tags, playbook_id,
                   diagram_json, team_key
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "Cycle Spots",
                "Progressions: " + ", ".join(progression_names),
                template.get("category") or "offense",
                template.get("category_id"),
                "cycle spots, progressions",
                template.get("playbook_id"),
                diagram,
                normalize_playbook_team(template.get("team_key")),
            ),
        )
        parent_id = cur.lastrowid

    for index, child in enumerate(children):
        db.execute(
            """UPDATE plays
                  SET parent_play_id = ?, progression_order = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
            (parent_id, index, child["id"]),
        )
    db.commit()
    return parent_id


def ensure_horns_progressions(db):
    """Attach Horns If/Then option pages as progressions of Horns (not Cycle Spots)."""
    _ensure_play_progression_columns(db)
    parent = db.execute(
        """SELECT id FROM plays
            WHERE name = ?
              AND (parent_play_id IS NULL OR parent_play_id = 0)
            ORDER BY id
            LIMIT 1""",
        ("Horns",),
    ).fetchone()
    if not parent:
        return None
    parent_id = parent["id"]

    # Only the Horns option pages — never Cycle Spots sequences.
    progression_names = [
        "If 1 to 2",
        "If 2 to 4",
        "Then 4 to 3",
        "If 2 to 3",
        "Then 2 and 4 exchange",
    ]
    linked = 0
    for index, name in enumerate(progression_names):
        row = db.execute(
            """SELECT id, parent_play_id FROM plays
                WHERE name = ?
                ORDER BY id
                LIMIT 1""",
            (name,),
        ).fetchone()
        if not row:
            continue
        # Skip if already under a different parent (e.g. somehow mis-linked)
        if row["parent_play_id"] and row["parent_play_id"] != parent_id:
            continue
        db.execute(
            """UPDATE plays
                  SET parent_play_id = ?, progression_order = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
            (parent_id, index, row["id"]),
        )
        linked += 1

    if linked:
        db.execute(
            """UPDATE plays
                  SET description = ?,
                      tags = CASE
                        WHEN tags IS NULL OR tags = '' THEN 'horns, progressions'
                        WHEN instr(lower(tags), 'progression') > 0 THEN tags
                        ELSE tags || ', progressions'
                      END,
                      updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
            (
                "Progressions: " + ", ".join(progression_names),
                parent_id,
            ),
        )
        db.commit()
    return parent_id if linked else parent_id


def ensure_zone_23_progressions(db):
    """Defense>Zone teaching pages without a number nest under 2-3 Zone.

    Numbered zone sets (1-2-2, 1-3-1, 2-3 Zone, 3-2 Zone) stay top-level.
    Unnumbered pages (Basic Startup, areas of responsibility, defending cuts, …)
    become progressions of 2-3 Zone.
    """
    import re

    from playbook_taxonomy import resolve_category_id_by_path

    _ensure_play_progression_columns(db)
    zone_id = resolve_category_id_by_path(db, "defense/zone")
    if not zone_id:
        return None

    parent = db.execute(
        """SELECT id FROM plays
            WHERE name = ?
              AND (parent_play_id IS NULL OR parent_play_id = 0)
              AND (category_id = ? OR category_id IS NULL OR category_id = 0)
            ORDER BY id
            LIMIT 1""",
        ("2-3 Zone", zone_id),
    ).fetchone()
    if not parent:
        parent = db.execute(
            """SELECT id FROM plays
                WHERE name = ?
                  AND (parent_play_id IS NULL OR parent_play_id = 0)
                ORDER BY id
                LIMIT 1""",
            ("2-3 Zone",),
        ).fetchone()
    if not parent:
        return None

    parent_id = parent["id"]
    db.execute(
        """UPDATE plays
              SET category_id = ?, category = 'defense', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?""",
        (zone_id, parent_id),
    )

    candidates = db.execute(
        """SELECT id, name FROM plays
            WHERE id != ?
              AND category_id = ?
              AND (
                    parent_play_id IS NULL
                 OR parent_play_id = 0
                 OR parent_play_id = ?
              )
            ORDER BY name COLLATE NOCASE ASC, id ASC""",
        (parent_id, zone_id, parent_id),
    ).fetchall()

    unnumbered = [
        dict(row)
        for row in candidates
        if not re.search(r"\d", row["name"] or "")
    ]
    if not unnumbered:
        db.commit()
        return parent_id

    for index, child in enumerate(unnumbered):
        db.execute(
            """UPDATE plays
                  SET parent_play_id = ?,
                      progression_order = ?,
                      category_id = ?,
                      category = 'defense',
                      updated_at = CURRENT_TIMESTAMP
                WHERE id = ?""",
            (parent_id, index, zone_id, child["id"]),
        )
    db.commit()
    return parent_id


def ensure_known_play_progressions(db):
    """Apply known PDF-split progression groupings."""
    ensure_cycle_spots_progressions(db)
    ensure_horns_progressions(db)
    ensure_zone_23_progressions(db)


def _default_category_id(db):
    from playbook_taxonomy import resolve_category_id_by_path

    return resolve_category_id_by_path(db, "offense/man")


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
    team_key = resolve_playbook_team(persist=True)
    category_tree = _load_playbook_taxonomy(db)
    ensure_known_play_progressions(db)
    plays = _group_plays_for_list(db, _plays_query(db, team_key))
    playbooks = db.execute(
        "SELECT * FROM playbooks WHERE COALESCE(kind, 'team') != 'opponent' ORDER BY name"
    ).fetchall()
    return render_template(
        "playbook.html",
        plays=plays,
        playbooks=[dict(p) for p in playbooks],
        categories=PLAYBOOK_CATEGORIES,
        category_tree=category_tree,
        editing_play=None,
        editing_steps=[],
        view_mode="list",
        selected_category_id=None,
        **_team_template_kwargs(team_key),
    )


@playbook_bp.route("/playbook/opponents")
@require_feature("ENABLE_PRACTICES")
def playbook_opponents():
    """Opponent playbooks — scout what other teams run."""
    db = get_db()
    from playbook_taxonomy import list_opponent_playbooks

    _load_playbook_taxonomy(db)
    opponents = list_opponent_playbooks(db)
    return render_template(
        "playbook_opponents.html",
        opponents=opponents,
        opponent=None,
        plays=[],
    )


@playbook_bp.route("/playbook/opponents", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_opponents_create():
    db = get_db()
    from playbook_taxonomy import create_opponent_playbook

    _load_playbook_taxonomy(db)
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()
    try:
        opp_id = create_opponent_playbook(db, name=name, description=description)
        db.commit()
        flash(f"Opponent playbook created for {name}.", "success")
        return redirect(url_for("playbook.playbook_opponent_detail", playbook_id=opp_id))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("playbook.playbook_opponents"))


@playbook_bp.route("/playbook/opponents/<int:playbook_id>")
@require_feature("ENABLE_PRACTICES")
def playbook_opponent_detail(playbook_id):
    """Plays for one opponent playbook."""
    db = get_db()
    from playbook_taxonomy import ensure_playbooks_opponent_columns, list_opponent_playbooks

    _load_playbook_taxonomy(db)
    ensure_playbooks_opponent_columns(db)
    opponent = db.execute(
        "SELECT * FROM playbooks WHERE id = ? AND kind = 'opponent'",
        (playbook_id,),
    ).fetchone()
    if not opponent:
        flash("Opponent playbook not found.", "error")
        return redirect(url_for("playbook.playbook_opponents"))
    _ensure_play_progression_columns(db)
    plays = db.execute(
        """SELECT p.*,
                  (SELECT COUNT(*) FROM play_steps ps WHERE ps.play_id = p.id) as step_count
             FROM plays p
            WHERE p.playbook_id = ?
            ORDER BY p.name COLLATE NOCASE ASC, p.id ASC""",
        (playbook_id,),
    ).fetchall()
    return render_template(
        "playbook_opponents.html",
        opponents=list_opponent_playbooks(db),
        opponent=dict(opponent),
        plays=[dict(p) for p in plays],
    )


@playbook_bp.route("/playbook/create")
@require_feature("ENABLE_PRACTICES")
def playbook_create():
    """Create new play — opens the canvas editor."""
    db = get_db()
    from playbook_taxonomy import ensure_playbooks_opponent_columns

    team_key = resolve_playbook_team(persist=True)
    category_tree = _load_playbook_taxonomy(db)
    ensure_playbooks_opponent_columns(db)
    playbooks = db.execute(
        "SELECT * FROM playbooks WHERE COALESCE(kind, 'team') != 'opponent' ORDER BY name"
    ).fetchall()
    selected_category_id = request.args.get("category_id", type=int) or _default_category_id(db)
    opponent_playbook_id = request.args.get("playbook_id", type=int)
    editing_play = {
        "id": None,
        "name": "",
        "description": "",
        "category": "offense",
        "category_id": selected_category_id,
        "tags": "",
        "playbook_id": None,
        "diagram_json": "{}",
        "team_key": team_key,
    }
    playbooks_out = [dict(p) for p in playbooks]
    if opponent_playbook_id:
        opp = db.execute(
            "SELECT * FROM playbooks WHERE id = ? AND kind = 'opponent'",
            (opponent_playbook_id,),
        ).fetchone()
        if opp:
            playbooks_out = [dict(opp)] + playbooks_out
            editing_play["playbook_id"] = opponent_playbook_id
    return render_template(
        "playbook.html",
        plays=[],
        playbooks=playbooks_out,
        categories=PLAYBOOK_CATEGORIES,
        category_tree=category_tree,
        editing_play=editing_play,
        editing_steps=[],
        view_mode="editor",
        selected_category_id=selected_category_id,
        **_team_template_kwargs(team_key),
    )


def _progression_nav_context(db, play):
    """Parent/sibling/child progression chips for view + edit screens."""
    _ensure_play_progression_columns(db)
    play = dict(play)
    parent_play = None
    sibling_progressions = []
    child_progressions = [
        dict(r)
        for r in db.execute(
            """SELECT id, name, progression_order,
                      (SELECT COUNT(*) FROM play_steps ps WHERE ps.play_id = plays.id) as step_count
                 FROM plays
                WHERE parent_play_id = ?
                ORDER BY progression_order ASC, name ASC""",
            (play["id"],),
        ).fetchall()
    ]
    if play.get("parent_play_id"):
        parent_play = db.execute(
            "SELECT id, name FROM plays WHERE id = ?",
            (play["parent_play_id"],),
        ).fetchone()
        sibling_progressions = [
            dict(r)
            for r in db.execute(
                """SELECT id, name, progression_order,
                          (SELECT COUNT(*) FROM play_steps ps WHERE ps.play_id = plays.id) as step_count
                     FROM plays
                    WHERE parent_play_id = ?
                    ORDER BY progression_order ASC, name ASC""",
                (play["parent_play_id"],),
            ).fetchall()
        ]
        parent_play = dict(parent_play) if parent_play else None
    return {
        "parent_play": parent_play,
        "sibling_progressions": sibling_progressions,
        "child_progressions": child_progressions,
    }


@playbook_bp.route("/playbook/play/<int:play_id>")
@require_feature("ENABLE_PRACTICES")
def playbook_view(play_id):
    """View a play with step-by-step animation."""
    db = get_db()
    _ensure_play_progression_columns(db)
    play = db.execute("SELECT * FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        flash("Play not found.", "error")
        return redirect(url_for("playbook.playbook_list", team=resolve_playbook_team(persist=True)))

    team_key = normalize_playbook_team(play["team_key"] if "team_key" in play.keys() else None)
    session[_SESSION_TEAM_KEY] = team_key
    nav = _progression_nav_context(db, play)
    # Empty parent shell → open first progression, which still shows the full chip bar.
    step_count = db.execute(
        "SELECT COUNT(*) AS c FROM play_steps WHERE play_id = ?", (play_id,)
    ).fetchone()["c"]
    if nav["child_progressions"] and step_count == 0:
        return redirect(
            url_for("playbook.playbook_view", play_id=nav["child_progressions"][0]["id"])
        )

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
        parent_play=nav["parent_play"],
        sibling_progressions=nav["sibling_progressions"],
        child_progressions=nav["child_progressions"],
        **_team_template_kwargs(team_key),
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
    play = dict(play)  # sqlite3.Row has no .get(); match the other play helpers
    steps = db.execute(
        "SELECT * FROM play_steps WHERE play_id = ? ORDER BY step_number", (play["id"],)
    ).fetchall()
    category_tree = _load_playbook_taxonomy(db)
    team_key = normalize_playbook_team(play.get("team_key"))
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
        **_team_template_kwargs(team_key),
    )


@playbook_bp.route("/playbook/play/<int:play_id>/edit")
@require_feature("ENABLE_PRACTICES")
def playbook_edit(play_id):
    """Edit an existing play."""
    db = get_db()
    _ensure_play_progression_columns(db)
    play = db.execute("SELECT * FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        flash("Play not found.", "error")
        return redirect(url_for("playbook.playbook_list", team=resolve_playbook_team(persist=True)))
    team_key = normalize_playbook_team(play["team_key"] if "team_key" in play.keys() else None)
    session[_SESSION_TEAM_KEY] = team_key
    steps = db.execute(
        "SELECT * FROM play_steps WHERE play_id = ? ORDER BY step_number", (play_id,)
    ).fetchall()
    playbooks = db.execute("SELECT * FROM playbooks ORDER BY name").fetchall()
    category_tree = _load_playbook_taxonomy(db)
    nav = _progression_nav_context(db, play)
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
        parent_play=nav["parent_play"],
        sibling_progressions=nav["sibling_progressions"],
        child_progressions=nav["child_progressions"],
        **_team_template_kwargs(team_key),
    )


@playbook_bp.route("/api/playbook/reorder", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_reorder_api():
    """Reorder top-level plays or progressions (drag-and-drop / multi-move)."""
    db = get_db()
    payload = request.get_json(silent=True) or {}
    ordered_ids = payload.get("ordered_ids") or []
    parent_raw = payload.get("parent_play_id", None)
    try:
        ids = reorder_plays(db, ordered_ids=ordered_ids, parent_play_id=parent_raw)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "ordered_ids": ids})


@playbook_bp.route("/api/playbook/move-category", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_move_category_api():
    """Move one or more top-level plays onto a category (sidebar drop)."""
    from playbook_taxonomy import build_category_tree

    db = get_db()
    payload = request.get_json(silent=True) or {}
    try:
        result = move_plays_to_category(
            db,
            play_ids=payload.get("play_ids") or [],
            category_id=payload.get("category_id"),
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    result["ok"] = True
    result["tree"] = build_category_tree(db)
    return jsonify(result)

@playbook_bp.route("/playbook/play/<int:play_id>/progression-move", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_progression_move(play_id):
    """Move a progression up/down within its parent play."""
    db = get_db()
    _ensure_play_progression_columns(db)
    direction = (request.form.get("direction") or "").strip().lower()
    play = db.execute(
        "SELECT id, parent_play_id, progression_order, name FROM plays WHERE id = ?",
        (play_id,),
    ).fetchone()
    if not play or not play["parent_play_id"]:
        flash("That play is not a progression.", "error")
        return redirect(url_for("playbook.playbook_list"))

    siblings = [
        dict(r)
        for r in db.execute(
            """SELECT id, progression_order, name FROM plays
                WHERE parent_play_id = ?
                ORDER BY progression_order ASC, name ASC""",
            (play["parent_play_id"],),
        ).fetchall()
    ]
    for index, sibling in enumerate(siblings):
        if sibling["progression_order"] != index:
            db.execute(
                "UPDATE plays SET progression_order = ? WHERE id = ?",
                (index, sibling["id"]),
            )
            sibling["progression_order"] = index

    idx = next((i for i, s in enumerate(siblings) if s["id"] == play_id), None)
    if idx is None:
        return redirect(url_for("playbook.playbook_list"))

    swap_with = None
    if direction == "up" and idx > 0:
        swap_with = siblings[idx - 1]
    elif direction == "down" and idx < len(siblings) - 1:
        swap_with = siblings[idx + 1]

    if swap_with:
        db.execute(
            "UPDATE plays SET progression_order = ? WHERE id = ?",
            (swap_with["progression_order"], play_id),
        )
        db.execute(
            "UPDATE plays SET progression_order = ? WHERE id = ?",
            (idx, swap_with["id"]),
        )
        db.commit()
        flash(f"Moved “{play['name']}”.", "success")
    return redirect(url_for("playbook.playbook_list"))


@playbook_bp.route("/playbook/play/<int:play_id>/delete", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_delete(play_id):
    """Delete a play and its steps."""
    db = get_db()
    _ensure_play_progression_columns(db)
    play = db.execute("SELECT team_key FROM plays WHERE id = ?", (play_id,)).fetchone()
    team_key = normalize_playbook_team(play["team_key"] if play else None)
    db.execute("DELETE FROM play_steps WHERE play_id = ?", (play_id,))
    db.execute("DELETE FROM plays WHERE id = ?", (play_id,))
    db.commit()
    flash("Play deleted.", "success")
    return redirect(url_for("playbook.playbook_list", team=team_key))


@playbook_bp.route("/playbook/play/<int:play_id>/duplicate", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_duplicate(play_id):
    """Duplicate a play within the same team playbook."""
    db = get_db()
    _ensure_play_progression_columns(db)
    play = db.execute("SELECT team_key FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        flash("Play not found.", "error")
        return redirect(url_for("playbook.playbook_list", team=resolve_playbook_team(persist=True)))
    source_team = normalize_playbook_team(play["team_key"])
    try:
        result = copy_play_to_team(db, play_id, source_team, include_progressions=True)
    except ValueError:
        flash("Play not found.", "error")
        return redirect(url_for("playbook.playbook_list", team=source_team))
    flash("Play duplicated.", "success")
    return redirect(url_for("playbook.playbook_edit", play_id=result["new_play_id"]))


@playbook_bp.route("/playbook/play/<int:play_id>/copy-to-team", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_copy_to_team(play_id):
    """Deep-copy a play into another (or same) team playbook."""
    db = get_db()
    raw_target = (request.form.get("target_team") or "").strip()
    if not raw_target:
        flash("Pick a team in the Copy to… dropdown, then click Copy to…", "error")
        return redirect(url_for("playbook.playbook_list", team=resolve_playbook_team(persist=True)))
    if raw_target not in PLAYBOOK_TEAM_KEYS:
        flash("Unknown team — pick High School / Jr High Boys or Girls.", "error")
        return redirect(url_for("playbook.playbook_list", team=resolve_playbook_team(persist=True)))
    target_team = normalize_playbook_team(raw_target)
    try:
        result = copy_play_to_team(db, play_id, target_team, include_progressions=True)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("playbook.playbook_list", team=resolve_playbook_team(persist=True)))
    session[_SESSION_TEAM_KEY] = result["target_team"]
    label = playbook_team_label(result["target_team"])
    flash(f"Copied “{result['name']}” to {label}.", "success")
    return redirect(
        url_for(
            "playbook.playbook_list",
            team=result["target_team"],
            copied=result["new_play_id"],
        )
    )


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
    team_key = normalize_playbook_team(
        form.get("team_key") or session.get(_SESSION_TEAM_KEY)
    )

    if not name:
        flash("Play name is required.", "error")
        return redirect(url_for("playbook.playbook_list", team=team_key))

    db = get_db()
    from playbook_taxonomy import legacy_category_from_id, resolve_category_id_by_path

    _load_playbook_taxonomy(db)
    _ensure_play_progression_columns(db)
    category_id = None
    if category_id_raw:
        try:
            category_id = int(category_id_raw)
        except ValueError:
            category_id = None
    if not category_id:
        category_id = resolve_category_id_by_path(db, "offense/man")
    category = legacy_category_from_id(db, category_id)

    if play_id:
        # Update existing play (keep existing team_key unless form overrides)
        existing = db.execute(
            "SELECT team_key FROM plays WHERE id = ?", (int(play_id),)
        ).fetchone()
        if existing and existing["team_key"]:
            team_key = normalize_playbook_team(
                form.get("team_key") or existing["team_key"]
            )
        db.execute(
            """UPDATE plays SET name=?, description=?, category=?, category_id=?, tags=?,
               playbook_id=?, diagram_json=?, team_key=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (
                name, description, category, category_id, tags,
                int(playbook_id) if playbook_id else None,
                diagram_json, team_key, int(play_id),
            ),
        )
        # Delete old steps and re-insert
        db.execute("DELETE FROM play_steps WHERE play_id = ?", (int(play_id),))
        play_db_id = int(play_id)
    else:
        # Create new play
        cur = db.execute(
            """INSERT INTO plays (
                   name, description, category, category_id, tags, playbook_id,
                   diagram_json, team_key
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                name, description, category, category_id, tags,
                int(playbook_id) if playbook_id else None,
                diagram_json, team_key,
            ),
        )
        play_db_id = cur.lastrowid

    session[_SESSION_TEAM_KEY] = team_key

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
    except (json.JSONDecodeError, KeyError, TypeError):
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


@playbook_bp.route("/api/playbook/sheet-align", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_sheet_align_api():
    """Detect court crop + digit positions for a play-sheet source image.

    Prefer FastDraw vector PDF operators when the sibling PDF exists; OCR is
    the draft fallback for raster sheets.

    Body JSON: { \"image_url\": \"/uploads/.../page_XXXX.png\" }
    Returns court_frac (normalized crop) and positions o1..o5 in SVG court space.
    """
    data = request.get_json(force=True, silent=True) or {}
    image_url = (data.get("image_url") or data.get("source_image") or "").strip()
    force_ocr = bool(data.get("force_ocr"))
    if not image_url:
        return jsonify({"error": "image_url required"}), 400
    try:
        if not force_ocr:
            from playbook_vector_extract import extract_sheet_from_image_url

            vec = extract_sheet_from_image_url(
                image_url, app_root=current_app.root_path
            )
            if vec and (vec.get("positions") or {}):
                return jsonify({
                    "ok": True,
                    "image_url": image_url,
                    "source": "vector",
                    "court_frac": vec.get("court_frac"),
                    "positions": vec.get("positions") or {},
                    "ink": vec.get("ink"),
                    "title": vec.get("title"),
                    "page": vec.get("page"),
                })

        from playbook_sheet_align import analyze_sheet_image, resolve_upload_path

        path = resolve_upload_path(image_url, current_app.root_path)
        cache_base = Path(current_app.root_path) / "data" / "playbook"
        result = analyze_sheet_image(path, cache_base=cache_base)
        return jsonify({
            "ok": True,
            "image_url": image_url,
            "source": "ocr",
            "court_frac": result.get("court_frac"),
            "positions": result.get("positions") or {},
            "size": result.get("size"),
        })
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": f"sheet align failed: {exc}"}), 500


@playbook_bp.route("/api/playbook/sheet-extract", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_sheet_extract_api():
    """Stage 1 extract: structured play JSON from vector PDF (OCR fallback).

    Body JSON: {
      \"image_url\": \"/uploads/.../page_XXXX.png\",
      \"to_positions\": {optional next-step tips for path attribution}
    }
    """
    data = request.get_json(force=True, silent=True) or {}
    image_url = (data.get("image_url") or data.get("source_image") or "").strip()
    to_positions = data.get("to_positions") or None
    force_ocr = bool(data.get("force_ocr"))
    if not image_url:
        return jsonify({"error": "image_url required"}), 400
    try:
        if not force_ocr:
            from playbook_vector_extract import extract_sheet_from_image_url

            vec = extract_sheet_from_image_url(
                image_url,
                app_root=current_app.root_path,
                next_positions=to_positions,
            )
            if vec and (vec.get("positions") or {}):
                ink = vec.get("ink") or {}
                return jsonify({
                    "ok": True,
                    "image_url": image_url,
                    "source": "vector",
                    "court_frac": vec.get("court_frac"),
                    "positions": vec.get("positions") or {},
                    "ink": {
                        "paths": ink.get("paths") or {},
                        "marks": ink.get("marks") or {},
                        "passes": ink.get("passes") or [],
                    },
                    "title": vec.get("title"),
                    "page": vec.get("page"),
                })

        from playbook_sheet_align import analyze_sheet_image, resolve_upload_path

        path = resolve_upload_path(image_url, current_app.root_path)
        cache_base = Path(current_app.root_path) / "data" / "playbook"
        result = analyze_sheet_image(path, cache_base=cache_base)
        return jsonify({
            "ok": True,
            "image_url": image_url,
            "source": "ocr",
            "court_frac": result.get("court_frac"),
            "positions": result.get("positions") or {},
            "ink": {"paths": {}, "marks": {}, "passes": []},
            "size": result.get("size"),
        })
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": f"sheet extract failed: {exc}"}), 500


@playbook_bp.route("/api/playbook/sheet-paths", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_sheet_paths_api():
    """Trace ink polylines on a sheet from from_positions → to_positions.

    Prefer vector PDF stroke extraction; OCR/ink-trace is the fallback.

    Body JSON: {
      \"image_url\": \"/uploads/...png\",
      \"from_positions\": {\"o1\": {\"x\":..,\"y\":..}, ...},
      \"to_positions\": {\"o1\": {\"x\":..,\"y\":..}, ...}
    }
    """
    data = request.get_json(force=True, silent=True) or {}
    image_url = (data.get("image_url") or data.get("source_image") or "").strip()
    from_positions = data.get("from_positions") or {}
    to_positions = data.get("to_positions") or {}
    force_ocr = bool(data.get("force_ocr"))
    if not image_url:
        return jsonify({"error": "image_url required"}), 400
    try:
        if not force_ocr:
            from playbook_vector_extract import extract_sheet_from_image_url

            vec = extract_sheet_from_image_url(
                image_url,
                app_root=current_app.root_path,
                next_positions=to_positions or None,
            )
            if vec:
                ink = vec.get("ink") or {}
                if ink.get("paths") or ink.get("passes"):
                    return jsonify({
                        "ok": True,
                        "image_url": image_url,
                        "source": "vector",
                        "paths": ink.get("paths") or {},
                        "marks": ink.get("marks") or {},
                        "passes": ink.get("passes") or [],
                    })

        from playbook_sheet_align import resolve_upload_path, trace_marked_paths_for_transition

        path = resolve_upload_path(image_url, current_app.root_path)
        marked = trace_marked_paths_for_transition(path, from_positions, to_positions)
        return jsonify({
            "ok": True,
            "image_url": image_url,
            "source": "ocr",
            "paths": marked.get("paths") or {},
            "marks": marked.get("marks") or {},
            "passes": marked.get("passes") or [],
        })
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:
        return jsonify({"error": f"sheet paths failed: {exc}"}), 500


def _choreography_base() -> Path:
    return Path(current_app.root_path) / "data" / "playbook"


@playbook_bp.route("/api/playbook/choreography/<int:play_id>", methods=["GET"])
@require_feature("ENABLE_PRACTICES")
def playbook_choreography_get(play_id):
    """Load sticky choreography JSON for a play (positions + ink overrides)."""
    from playbook_choreography import load_choreography

    db = get_db()
    play = db.execute("SELECT id FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        return jsonify({"error": "Play not found"}), 404
    doc = load_choreography(play_id, base=_choreography_base())
    if not doc:
        return jsonify({"ok": True, "sticky": False, "choreography": None})
    return jsonify({"ok": True, "sticky": True, "choreography": doc})


@playbook_bp.route("/api/playbook/choreography/<int:play_id>", methods=["PUT", "POST"])
@require_feature("ENABLE_PRACTICES")
def playbook_choreography_save(play_id):
    """Persist sticky choreography so Play All stops re-guessing OCR/ink."""
    from playbook_choreography import save_choreography

    db = get_db()
    play = db.execute("SELECT id FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        return jsonify({"error": "Play not found"}), 404
    data = request.get_json(force=True, silent=True) or {}
    source = (data.get("source") or "user_save").strip() or "user_save"
    try:
        doc = save_choreography(
            play_id,
            data,
            base=_choreography_base(),
            source=source,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except OSError as exc:
        return jsonify({"error": f"save failed: {exc}"}), 500
    return jsonify({"ok": True, "sticky": True, "choreography": doc})


@playbook_bp.route("/api/playbook/choreography/<int:play_id>", methods=["DELETE"])
@require_feature("ENABLE_PRACTICES")
def playbook_choreography_delete(play_id):
    """Clear sticky choreography — next Play All re-runs OCR + ink trace."""
    from playbook_choreography import delete_choreography

    db = get_db()
    play = db.execute("SELECT id FROM plays WHERE id = ?", (play_id,)).fetchone()
    if not play:
        return jsonify({"error": "Play not found"}), 404
    deleted = delete_choreography(play_id, base=_choreography_base())
    return jsonify({"ok": True, "deleted": deleted, "sticky": False})


@playbook_bp.route("/api/playbook/categories")
@require_feature("ENABLE_PRACTICES")
def playbook_categories_api():
    db = get_db()
    from playbook_taxonomy import list_categories_flat

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

    from playbook_pdf import pdf_page_count, pymupdf_available

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
    _ensure_play_progression_columns(db)
    team_key = normalize_playbook_team(
        data.get("team_key") or session.get(_SESSION_TEAM_KEY)
    )
    category_id = None
    if category_id_raw:
        try:
            category_id = int(category_id_raw)
        except ValueError:
            category_id = None
    if not category_id:
        category_id = resolve_category_id_by_path(db, "offense/man")
    category = legacy_category_from_id(db, category_id)

    cur = db.execute(
        """INSERT INTO plays (
               name, description, category, category_id, tags, playbook_id,
               diagram_json, team_key
           ) VALUES (?,?,?,?,?,?,?,?)""",
        (
            name, description, category, category_id, tags,
            int(playbook_id) if playbook_id else None,
            diagram_json, team_key,
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
