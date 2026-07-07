"""Hierarchical playbook categories: Offense/Defense/Press/Press Break → Man/Zone → subtypes."""

from __future__ import annotations

DEFAULT_TAXONOMY = [
    {
        "name": "Offense",
        "slug": "offense",
        "is_system": 1,
        "children": [
            {
                "name": "Man",
                "slug": "man",
                "is_system": 1,
                "children": [
                    {"name": "Plays", "slug": "plays", "is_system": 1},
                    {"name": "BLOB", "slug": "blob", "is_system": 1},
                    {"name": "SLOB", "slug": "slob", "is_system": 1},
                ],
            },
            {
                "name": "Zone",
                "slug": "zone",
                "is_system": 1,
                "children": [
                    {"name": "Plays", "slug": "plays", "is_system": 1},
                    {"name": "BLOB", "slug": "blob", "is_system": 1},
                    {"name": "SLOB", "slug": "slob", "is_system": 1},
                ],
            },
        ],
    },
    {
        "name": "Defense",
        "slug": "defense",
        "is_system": 1,
        "children": [
            {
                "name": "Man",
                "slug": "man",
                "is_system": 1,
                "children": [{"name": "Plays", "slug": "plays", "is_system": 1}],
            },
            {
                "name": "Zone",
                "slug": "zone",
                "is_system": 1,
                "children": [{"name": "Plays", "slug": "plays", "is_system": 1}],
            },
        ],
    },
    {
        "name": "Press",
        "slug": "press",
        "is_system": 1,
        "children": [
            {
                "name": "Man",
                "slug": "man",
                "is_system": 1,
                "children": [{"name": "Plays", "slug": "plays", "is_system": 1}],
            },
            {
                "name": "Zone",
                "slug": "zone",
                "is_system": 1,
                "children": [{"name": "Plays", "slug": "plays", "is_system": 1}],
            },
        ],
    },
    {
        "name": "Press Break",
        "slug": "press_break",
        "is_system": 1,
        "children": [
            {
                "name": "Man",
                "slug": "man",
                "is_system": 1,
                "children": [{"name": "Plays", "slug": "plays", "is_system": 1}],
            },
            {
                "name": "Zone",
                "slug": "zone",
                "is_system": 1,
                "children": [{"name": "Plays", "slug": "plays", "is_system": 1}],
            },
        ],
    },
]

LEAF_SUBTYPES = {"plays", "blob", "slob"}


LEGACY_CATEGORY_MAP = {
    "offense": ("offense", "man", "plays"),
    "defense": ("defense", "man", "plays"),
    "press": ("press", "man", "plays"),
    "transition": ("offense", "man", "plays"),
    "out_of_bounds": ("offense", "man", "blob"),
    "special": ("offense", "man", "plays"),
}


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


def ensure_playbook_taxonomy(db):
    """Seed default taxonomy and backfill play.category_id from legacy category text."""
    row = db.execute("SELECT COUNT(*) AS c FROM play_categories").fetchone()
    if not row or row["c"] == 0:
        for index, node in enumerate(DEFAULT_TAXONOMY):
            _insert_taxonomy_node(db, node, sort_order=index)

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
    db.execute(
        """UPDATE plays
              SET category_id = (
                  SELECT id FROM play_categories WHERE slug_path = 'offense/man/plays' LIMIT 1
              )
            WHERE category_id IS NULL"""
    )


def _category_row_to_dict(row):
    return {
        "id": row["id"],
        "parent_id": row["parent_id"],
        "name": row["name"],
        "slug": row["slug"],
        "slug_path": row["slug_path"],
        "sort_order": row["sort_order"],
        "is_system": bool(row["is_system"]),
        "play_count": row["play_count"] if "play_count" in row.keys() else 0,
    }


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
    """When adding under Plays/BLOB/SLOB, create a sibling under Man/Zone instead."""
    if not parent_id:
        return None, ""
    parent = db.execute(
        "SELECT id, parent_id, slug, slug_path FROM play_categories WHERE id = ?",
        (parent_id,),
    ).fetchone()
    if not parent:
        raise ValueError("Parent category not found")
    if parent["slug"] in LEAF_SUBTYPES and parent["parent_id"]:
        grandparent = db.execute(
            "SELECT id, slug_path FROM play_categories WHERE id = ?",
            (parent["parent_id"],),
        ).fetchone()
        if grandparent:
            return grandparent["id"], grandparent["slug_path"]
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

    if "press break" in combined:
        side = "press_break"
    elif "press" in section_l:
        side = "press"
    elif "defense" in combined:
        side = "defense"
    else:
        side = "offense"

    coverage = "zone" if "zone" in combined else "man"

    if "blob" in section_l:
        subtype = "blob"
    elif "slob" in section_l:
        subtype = "slob"
    else:
        subtype = "plays"

    slug_path = f"{side}/{coverage}/{subtype}"
    category_id = resolve_category_id_by_path(db, slug_path)
    if category_id:
        return category_id, legacy_category_from_id(db, category_id)

    fallback_id = resolve_category_id_by_path(db, "offense/man/plays")
    return fallback_id, "offense"


def leaf_categories(db):
    """Return assignable leaf categories (Plays/BLOB/SLOB and custom siblings)."""
    rows = db.execute(
        """SELECT c.*
             FROM play_categories c
            WHERE NOT EXISTS (
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
    if root in {"offense", "defense", "press"}:
        return root
    if root == "press_break":
        return "press"
    return "offense"
