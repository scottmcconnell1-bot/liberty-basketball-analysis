"""Hierarchical playbook categories for Liberty.

Coach taxonomy (v2):
  Offense → Man | Zone
  Defense → Man | Zone
  Press → Man | Zone
  Press Break → Man | Zone
  Transition
  BLOB
  SLOB
  Opponents  (navigates to opponent playbook screen)
"""

from __future__ import annotations

DEFAULT_TAXONOMY = [
    {
        "name": "Offense",
        "slug": "offense",
        "is_system": 1,
        "children": [
            {"name": "Man", "slug": "man", "is_system": 1},
            {"name": "Zone", "slug": "zone", "is_system": 1},
        ],
    },
    {
        "name": "Defense",
        "slug": "defense",
        "is_system": 1,
        "children": [
            {"name": "Man", "slug": "man", "is_system": 1},
            {"name": "Zone", "slug": "zone", "is_system": 1},
        ],
    },
    {
        "name": "Press",
        "slug": "press",
        "is_system": 1,
        "children": [
            {"name": "Man", "slug": "man", "is_system": 1},
            {"name": "Zone", "slug": "zone", "is_system": 1},
        ],
    },
    {
        "name": "Press Break",
        "slug": "press_break",
        "is_system": 1,
        "children": [
            {"name": "Man", "slug": "man", "is_system": 1},
            {"name": "Zone", "slug": "zone", "is_system": 1},
        ],
    },
    {"name": "Transition", "slug": "transition", "is_system": 1},
    {"name": "BLOB", "slug": "blob", "is_system": 1},
    {"name": "SLOB", "slug": "slob", "is_system": 1},
    {
        "name": "Opponents",
        "slug": "opponents",
        "is_system": 1,
        # Special nav target — not a play folder; opens opponent playbooks screen.
        "nav_href": "/playbook/opponents",
    },
]

# Assignable leaves in the new taxonomy (folders that hold plays).
ASSIGNABLE_SLUGS = {
    "offense/man",
    "offense/zone",
    "defense/man",
    "defense/zone",
    "press/man",
    "press/zone",
    "press_break/man",
    "press_break/zone",
    "transition",
    "blob",
    "slob",
}

# Kept for older helpers that treated Plays/BLOB/SLOB as leaf subtypes.
LEAF_SUBTYPES = {"man", "zone", "transition", "blob", "slob"}

LEGACY_CATEGORY_MAP = {
    "offense": ("offense", "man"),
    "defense": ("defense", "man"),
    "press": ("press", "man"),
    "transition": ("transition",),
    "out_of_bounds": ("blob",),
    "special": ("offense", "man"),
}

# Old slug_path → new slug_path for play remapping (v1 leaf Plays → parent Man/Zone).
PATH_REMAP = {
    "offense/man/plays": "offense/man",
    "offense/zone/plays": "offense/zone",
    "offense/man/blob": "blob",
    "offense/zone/blob": "blob",
    "offense/man/slob": "slob",
    "offense/zone/slob": "slob",
    "defense/man/plays": "defense/man",
    "defense/zone/plays": "defense/zone",
    "press/man/plays": "press/man",
    "press/zone/plays": "press/zone",
    "press_break/man/plays": "press_break/man",
    "press_break/zone/plays": "press_break/zone",
}

OBSOLETE_SYSTEM_PATHS = (
    "offense/man/plays",
    "offense/zone/plays",
    "offense/man/blob",
    "offense/zone/blob",
    "offense/man/slob",
    "offense/zone/slob",
    "defense/man/plays",
    "defense/zone/plays",
    "press/man/plays",
    "press/zone/plays",
    "press_break/man/plays",
    "press_break/zone/plays",
)


def _slug_path(parent_path: str, slug: str) -> str:
    return f"{parent_path}/{slug}" if parent_path else slug


def _insert_taxonomy_node(db, node, parent_id=None, parent_path="", sort_order=0):
    slug_path = _slug_path(parent_path, node["slug"])
    cur = db.execute(
        """INSERT INTO play_categories (parent_id, name, slug, slug_path, sort_order, is_system)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            parent_id,
            node["name"],
            node["slug"],
            slug_path,
            sort_order,
            int(node.get("is_system", 0)),
        ),
    )
    category_id = cur.lastrowid
    for index, child in enumerate(node.get("children") or []):
        _insert_taxonomy_node(db, child, category_id, slug_path, index)
    return category_id


def ensure_play_categories_table(db):
    """Create taxonomy table on older databases that predate playbook categories."""
    db.execute(
        """CREATE TABLE IF NOT EXISTS play_categories (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id       INTEGER REFERENCES play_categories(id) ON DELETE CASCADE,
            name            TEXT NOT NULL,
            slug            TEXT NOT NULL,
            slug_path       TEXT NOT NULL UNIQUE,
            sort_order      INTEGER NOT NULL DEFAULT 0,
            is_system       INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    cols = {row[1] for row in db.execute("PRAGMA table_info(plays)").fetchall()}
    if "category_id" not in cols:
        db.execute(
            "ALTER TABLE plays ADD COLUMN category_id INTEGER REFERENCES play_categories(id)"
        )
    if "share_token" not in cols:
        db.execute("ALTER TABLE plays ADD COLUMN share_token TEXT UNIQUE")


def ensure_playbooks_opponent_columns(db):
    """Opponent playbooks live in playbooks with kind='opponent'."""
    db.execute(
        """CREATE TABLE IF NOT EXISTS playbooks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            description     TEXT,
            created_by      TEXT,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    cols = {row[1] for row in db.execute("PRAGMA table_info(playbooks)").fetchall()}
    if "kind" not in cols:
        db.execute("ALTER TABLE playbooks ADD COLUMN kind TEXT NOT NULL DEFAULT 'team'")
    if "opponent_name" not in cols:
        db.execute("ALTER TABLE playbooks ADD COLUMN opponent_name TEXT")


def _ensure_node(db, *, name, slug, slug_path, parent_id, sort_order, is_system=1):
    row = db.execute(
        "SELECT id FROM play_categories WHERE slug_path = ?",
        (slug_path,),
    ).fetchone()
    if row:
        db.execute(
            """UPDATE play_categories
                  SET parent_id = ?, name = ?, slug = ?, sort_order = ?, is_system = ?
                WHERE id = ?""",
            (parent_id, name, slug, sort_order, is_system, row["id"]),
        )
        return row["id"]
    cur = db.execute(
        """INSERT INTO play_categories (parent_id, name, slug, slug_path, sort_order, is_system)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (parent_id, name, slug, slug_path, sort_order, is_system),
    )
    return cur.lastrowid


def _migrate_taxonomy_v2(db):
    """Bring an existing taxonomy up to Offense/Defense/Press/Press Break + flat buckets."""
    offense_id = _ensure_node(
        db, name="Offense", slug="offense", slug_path="offense", parent_id=None, sort_order=0
    )
    defense_id = _ensure_node(
        db, name="Defense", slug="defense", slug_path="defense", parent_id=None, sort_order=1
    )
    press_id = _ensure_node(
        db, name="Press", slug="press", slug_path="press", parent_id=None, sort_order=2
    )
    press_break_id = _ensure_node(
        db,
        name="Press Break",
        slug="press_break",
        slug_path="press_break",
        parent_id=None,
        sort_order=3,
    )
    man_o = _ensure_node(
        db, name="Man", slug="man", slug_path="offense/man", parent_id=offense_id, sort_order=0
    )
    zone_o = _ensure_node(
        db, name="Zone", slug="zone", slug_path="offense/zone", parent_id=offense_id, sort_order=1
    )
    man_d = _ensure_node(
        db, name="Man", slug="man", slug_path="defense/man", parent_id=defense_id, sort_order=0
    )
    zone_d = _ensure_node(
        db, name="Zone", slug="zone", slug_path="defense/zone", parent_id=defense_id, sort_order=1
    )
    man_p = _ensure_node(
        db, name="Man", slug="man", slug_path="press/man", parent_id=press_id, sort_order=0
    )
    zone_p = _ensure_node(
        db, name="Zone", slug="zone", slug_path="press/zone", parent_id=press_id, sort_order=1
    )
    man_pb = _ensure_node(
        db,
        name="Man",
        slug="man",
        slug_path="press_break/man",
        parent_id=press_break_id,
        sort_order=0,
    )
    zone_pb = _ensure_node(
        db,
        name="Zone",
        slug="zone",
        slug_path="press_break/zone",
        parent_id=press_break_id,
        sort_order=1,
    )
    transition_id = _ensure_node(
        db,
        name="Transition",
        slug="transition",
        slug_path="transition",
        parent_id=None,
        sort_order=4,
    )
    blob_id = _ensure_node(
        db, name="BLOB", slug="blob", slug_path="blob", parent_id=None, sort_order=5
    )
    slob_id = _ensure_node(
        db, name="SLOB", slug="slob", slug_path="slob", parent_id=None, sort_order=6
    )
    _ensure_node(
        db,
        name="Opponents",
        slug="opponents",
        slug_path="opponents",
        parent_id=None,
        sort_order=7,
    )

    path_to_id = {
        "offense/man": man_o,
        "offense/zone": zone_o,
        "defense/man": man_d,
        "defense/zone": zone_d,
        "press/man": man_p,
        "press/zone": zone_p,
        "press_break/man": man_pb,
        "press_break/zone": zone_pb,
        "transition": transition_id,
        "blob": blob_id,
        "slob": slob_id,
    }

    slug_to_id = {
        row["slug_path"]: row["id"]
        for row in db.execute("SELECT id, slug_path FROM play_categories").fetchall()
    }

    for old_path, new_path in PATH_REMAP.items():
        old_id = slug_to_id.get(old_path)
        new_id = path_to_id.get(new_path) or slug_to_id.get(new_path)
        if old_id and new_id and old_id != new_id:
            db.execute(
                "UPDATE plays SET category_id = ? WHERE category_id = ?",
                (new_id, old_id),
            )

    # Delete obsolete system nodes deepest-first.
    for old_path in sorted(OBSOLETE_SYSTEM_PATHS, key=lambda p: p.count("/"), reverse=True):
        row = db.execute(
            "SELECT id FROM play_categories WHERE slug_path = ?",
            (old_path,),
        ).fetchone()
        if not row:
            continue
        db.execute(
            "UPDATE plays SET category_id = ? WHERE category_id = ?",
            (man_o, row["id"]),
        )
        child = db.execute(
            "SELECT id FROM play_categories WHERE parent_id = ? LIMIT 1",
            (row["id"],),
        ).fetchone()
        if not child:
            db.execute("DELETE FROM play_categories WHERE id = ?", (row["id"],))


def ensure_playbook_taxonomy(db):
    """Seed default taxonomy and backfill play.category_id from legacy category text."""
    ensure_play_categories_table(db)
    ensure_playbooks_opponent_columns(db)
    row = db.execute("SELECT COUNT(*) AS c FROM play_categories").fetchone()
    if not row or row["c"] == 0:
        for index, node in enumerate(DEFAULT_TAXONOMY):
            _insert_taxonomy_node(db, node, sort_order=index)
    else:
        _migrate_taxonomy_v2(db)

    slug_to_id = {
        row["slug_path"]: row["id"]
        for row in db.execute("SELECT id, slug_path FROM play_categories").fetchall()
    }
    for legacy, path_parts in LEGACY_CATEGORY_MAP.items():
        slug_path = "/".join(path_parts)
        category_id = slug_to_id.get(slug_path)
        if category_id:
            db.execute(
                "UPDATE plays SET category_id = ? WHERE category = ? AND (category_id IS NULL OR category_id = 0)",
                (category_id, legacy),
            )
    default_id = slug_to_id.get("offense/man")
    if default_id:
        db.execute(
            "UPDATE plays SET category_id = ? WHERE category_id IS NULL",
            (default_id,),
        )


def _category_row_to_dict(row):
    slug_path = row["slug_path"]
    data = {
        "id": row["id"],
        "parent_id": row["parent_id"],
        "name": row["name"],
        "slug": row["slug"],
        "slug_path": slug_path,
        "sort_order": row["sort_order"],
        "is_system": bool(row["is_system"]),
        "play_count": row["play_count"] if "play_count" in row.keys() else 0,
        "assignable": slug_path in ASSIGNABLE_SLUGS,
    }
    if slug_path == "opponents":
        data["nav_href"] = "/playbook/opponents"
        data["assignable"] = False
    return data


def list_categories_flat(db):
    rows = db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM plays p WHERE p.category_id = c.id) AS play_count
             FROM play_categories c
            ORDER BY c.sort_order ASC, c.name ASC"""
    ).fetchall()
    return [_category_row_to_dict(row) for row in rows]


def build_category_tree(db):
    flat = list_categories_flat(db)
    by_id = {item["id"]: {**item, "children": []} for item in flat}
    roots = []
    for item in flat:
        node = by_id[item["id"]]
        parent_id = item["parent_id"]
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(node)
        else:
            roots.append(node)
    for node in by_id.values():
        node["children"].sort(key=lambda child: (child["sort_order"], child["name"].lower()))
    roots.sort(key=lambda child: (child["sort_order"], child["name"].lower()))

    def _rollup(node):
        direct = int(node.get("play_count") or 0)
        node["direct_play_count"] = direct
        total = direct
        for child in node.get("children") or []:
            total += _rollup(child)
        if node.get("slug_path") == "opponents":
            try:
                opp = db.execute(
                    "SELECT COUNT(*) AS c FROM playbooks WHERE kind = 'opponent'"
                ).fetchone()
                total = int(opp["c"] if opp else 0)
            except Exception:
                total = 0
            node["direct_play_count"] = 0
        node["play_count"] = total
        return total

    for root in roots:
        _rollup(root)
    return roots


def category_breadcrumb(db, category_id):
    parts = []
    current_id = category_id
    seen = set()
    while current_id and current_id not in seen:
        seen.add(current_id)
        row = db.execute(
            "SELECT id, parent_id, name FROM play_categories WHERE id = ?",
            (current_id,),
        ).fetchone()
        if not row:
            break
        parts.append(row["name"])
        current_id = row["parent_id"]
    return list(reversed(parts))


def category_path_label(db, category_id):
    return " · ".join(category_breadcrumb(db, category_id))


def resolve_category_id_by_path(db, slug_path):
    row = db.execute(
        "SELECT id FROM play_categories WHERE slug_path = ?",
        (slug_path,),
    ).fetchone()
    return row["id"] if row else None


def resolve_category_id_from_parts(db, side, coverage, subtype):
    slug_path = "/".join(
        part.strip().lower().replace(" ", "_")
        for part in (side, coverage, subtype)
        if part
    )
    return resolve_category_id_by_path(db, slug_path)


def _next_sort_order(db, parent_id):
    row = db.execute(
        "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_order FROM play_categories WHERE parent_id IS ?",
        (parent_id,),
    ).fetchone()
    return int(row["next_order"] or 0)


def _effective_parent_for_new_category(db, parent_id):
    """Custom categories nest under the selected folder (Offense/Defense/Man/Zone/…)."""
    if not parent_id:
        return None, ""
    parent = db.execute(
        "SELECT id, parent_id, slug, slug_path FROM play_categories WHERE id = ?",
        (parent_id,),
    ).fetchone()
    if not parent:
        raise ValueError("Parent category not found")
    if parent["slug"] == "opponents":
        raise ValueError("Add opponent playbooks from the Opponents screen")
    return parent["id"], parent["slug_path"]


def create_category(db, *, parent_id, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("Category name is required")
    parent_id, parent_path = _effective_parent_for_new_category(db, parent_id)
    slug = name.lower().replace(" ", "_").replace("-", "_")
    slug_path = _slug_path(parent_path, slug)
    existing = db.execute(
        "SELECT id FROM play_categories WHERE slug_path = ?",
        (slug_path,),
    ).fetchone()
    if existing:
        raise ValueError("A category with that name already exists here")
    sort_order = _next_sort_order(db, parent_id)
    cur = db.execute(
        """INSERT INTO play_categories (parent_id, name, slug, slug_path, sort_order, is_system)
           VALUES (?, ?, ?, ?, ?, 0)""",
        (parent_id, name, slug, slug_path, sort_order),
    )
    return cur.lastrowid


def rename_category(db, category_id, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("Category name is required")
    row = db.execute(
        "SELECT id, parent_id, slug_path FROM play_categories WHERE id = ?",
        (category_id,),
    ).fetchone()
    if not row:
        raise ValueError("Category not found")
    parent_path = ""
    if row["parent_id"]:
        parent = db.execute(
            "SELECT slug_path FROM play_categories WHERE id = ?",
            (row["parent_id"],),
        ).fetchone()
        parent_path = parent["slug_path"] if parent else ""
    slug = name.lower().replace(" ", "_").replace("-", "_")
    slug_path = _slug_path(parent_path, slug)
    conflict = db.execute(
        "SELECT id FROM play_categories WHERE slug_path = ? AND id != ?",
        (slug_path, category_id),
    ).fetchone()
    if conflict:
        raise ValueError("A category with that name already exists here")
    db.execute(
        "UPDATE play_categories SET name = ?, slug = ?, slug_path = ? WHERE id = ?",
        (name, slug, slug_path, category_id),
    )


def move_category(db, category_id, *, parent_id=None, sort_order=None):
    row = db.execute(
        "SELECT id, parent_id, name, is_system FROM play_categories WHERE id = ?",
        (category_id,),
    ).fetchone()
    if not row:
        raise ValueError("Category not found")
    if row["is_system"] and parent_id != row["parent_id"]:
        raise ValueError("System categories cannot change parents")
    new_parent_id = parent_id if parent_id is not None else row["parent_id"]
    parent_path = ""
    if new_parent_id:
        parent = db.execute(
            "SELECT id, slug_path FROM play_categories WHERE id = ?",
            (new_parent_id,),
        ).fetchone()
        if not parent:
            raise ValueError("Parent category not found")
        parent_path = parent["slug_path"]
    slug = row["name"].lower().replace(" ", "_").replace("-", "_")
    slug_path = _slug_path(parent_path, slug)
    new_sort = sort_order if sort_order is not None else _next_sort_order(db, new_parent_id)
    db.execute(
        """UPDATE play_categories
              SET parent_id = ?, slug_path = ?, sort_order = ?
            WHERE id = ?""",
        (new_parent_id, slug_path, new_sort, category_id),
    )


def delete_category(db, category_id, *, reassign_to=None):
    row = db.execute(
        "SELECT id, is_system FROM play_categories WHERE id = ?",
        (category_id,),
    ).fetchone()
    if not row:
        raise ValueError("Category not found")
    if row["is_system"]:
        raise ValueError("System categories cannot be deleted")
    child = db.execute(
        "SELECT id FROM play_categories WHERE parent_id = ? LIMIT 1",
        (category_id,),
    ).fetchone()
    if child:
        raise ValueError("Delete or move child categories first")
    play_count = db.execute(
        "SELECT COUNT(*) AS c FROM plays WHERE category_id = ?",
        (category_id,),
    ).fetchone()["c"]
    if play_count:
        if not reassign_to:
            raise ValueError("Category has plays — choose another category to move them to")
        db.execute(
            "UPDATE plays SET category_id = ? WHERE category_id = ?",
            (reassign_to, category_id),
        )
    db.execute("DELETE FROM play_categories WHERE id = ?", (category_id,))


def leaf_category_ids(db, category_id):
    """Return category id and all descendant ids (for filtering plays in a branch)."""
    ids = [category_id]
    children = db.execute(
        "SELECT id FROM play_categories WHERE parent_id = ?",
        (category_id,),
    ).fetchall()
    for child in children:
        ids.extend(leaf_category_ids(db, child["id"]))
    return ids


def resolve_category_from_section(db, section, subsection=""):
    """Map scout PDF section headers to a taxonomy category_id."""
    section_l = (section or "").lower()
    subsection_l = (subsection or "").lower()
    combined = f"{section_l} {subsection_l}"

    if "blob" in section_l or "blob" in combined:
        category_id = resolve_category_id_by_path(db, "blob")
        if category_id:
            return category_id, "out_of_bounds"
    if "slob" in section_l or "slob" in combined:
        category_id = resolve_category_id_by_path(db, "slob")
        if category_id:
            return category_id, "out_of_bounds"
    if "transition" in combined:
        category_id = resolve_category_id_by_path(db, "transition")
        if category_id:
            return category_id, "transition"

    if "press break" in combined:
        side = "press_break"
    elif "press" in section_l or "press" in combined:
        side = "press"
    elif "defense" in combined:
        side = "defense"
    else:
        side = "offense"
    coverage = "zone" if "zone" in combined else "man"
    slug_path = f"{side}/{coverage}"
    category_id = resolve_category_id_by_path(db, slug_path)
    if category_id:
        return category_id, legacy_category_from_id(db, category_id)

    fallback_id = resolve_category_id_by_path(db, "offense/man")
    return fallback_id, "offense"


def leaf_categories(db):
    """Return assignable leaf categories (Man/Zone/Transition/BLOB/SLOB and custom leaves)."""
    rows = db.execute(
        """SELECT c.*
             FROM play_categories c
            WHERE c.slug_path != 'opponents'
              AND NOT EXISTS (
                  SELECT 1 FROM play_categories child WHERE child.parent_id = c.id
              )
            ORDER BY c.slug_path ASC"""
    ).fetchall()
    return [_category_row_to_dict(row) for row in rows]


def legacy_category_from_id(db, category_id):
    row = db.execute(
        "SELECT slug_path FROM play_categories WHERE id = ?",
        (category_id,),
    ).fetchone()
    if not row:
        return "offense"
    root = (row["slug_path"] or "").split("/")[0]
    if root in {"offense", "defense", "transition", "press"}:
        return root
    if root == "press_break":
        return "press"
    if root in {"blob", "slob"}:
        return "out_of_bounds"
    return "offense"


def list_opponent_playbooks(db):
    ensure_playbooks_opponent_columns(db)
    rows = db.execute(
        """SELECT pb.*,
                  (SELECT COUNT(*) FROM plays p WHERE p.playbook_id = pb.id) AS play_count
             FROM playbooks pb
            WHERE pb.kind = 'opponent'
            ORDER BY COALESCE(pb.opponent_name, pb.name) COLLATE NOCASE ASC"""
    ).fetchall()
    return [dict(r) for r in rows]


def create_opponent_playbook(db, *, name, description="", created_by=None):
    ensure_playbooks_opponent_columns(db)
    name = (name or "").strip()
    if not name:
        raise ValueError("Opponent name is required")
    cur = db.execute(
        """INSERT INTO playbooks (name, description, created_by, kind, opponent_name, updated_at)
           VALUES (?, ?, ?, 'opponent', ?, CURRENT_TIMESTAMP)""",
        (name, description or "", created_by, name),
    )
    return cur.lastrowid
