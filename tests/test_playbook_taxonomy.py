"""Tests for hierarchical playbook categories."""

from playbook_taxonomy import (
    build_category_tree,
    create_category,
    create_opponent_playbook,
    delete_category,
    ensure_playbook_taxonomy,
    resolve_category_from_section,
    resolve_category_id_by_path,
)


def test_category_tree_rolls_up_play_counts(db):
    """Parent folders (Offense / Man) include descendant play totals."""
    ensure_playbook_taxonomy(db)
    leaf_id = resolve_category_id_by_path(db, "offense/man")
    assert leaf_id is not None
    db.execute(
        "INSERT INTO plays (name, category, category_id) VALUES (?, ?, ?)",
        ("Rollup Test Play", "offense", leaf_id),
    )
    db.commit()
    tree = build_category_tree(db)
    offense = next(node for node in tree if node["name"] == "Offense")
    man = next(child for child in offense["children"] if child["name"] == "Man")
    assert man["play_count"] >= 1
    assert offense["play_count"] >= man["play_count"]
    assert offense["direct_play_count"] == 0


def test_default_taxonomy_seeded(db):
    ensure_playbook_taxonomy(db)
    db.commit()
    tree = build_category_tree(db)
    names = [node["name"] for node in tree]
    assert names[:8] == [
        "Offense",
        "Defense",
        "Press",
        "Press Break",
        "Transition",
        "BLOB",
        "SLOB",
        "Opponents",
    ]
    offense = tree[0]
    assert {c["name"] for c in offense["children"]} == {"Man", "Zone"}
    defense = tree[1]
    assert {c["name"] for c in defense["children"]} == {"Man", "Zone"}
    press = tree[2]
    assert {c["name"] for c in press["children"]} == {"Man", "Zone"}
    press_break = tree[3]
    assert {c["name"] for c in press_break["children"]} == {"Man", "Zone"}
    opponents = next(node for node in tree if node["name"] == "Opponents")
    assert opponents.get("nav_href") == "/playbook/opponents"


def test_resolve_offense_man_category(db):
    ensure_playbook_taxonomy(db)
    db.commit()
    category_id = resolve_category_id_by_path(db, "offense/man")
    assert category_id is not None


def test_create_and_delete_custom_category(db):
    ensure_playbook_taxonomy(db)
    db.commit()
    parent_id = resolve_category_id_by_path(db, "defense/man")
    custom_id = create_category(db, parent_id=parent_id, name="Traps")
    db.commit()
    assert resolve_category_id_by_path(db, "defense/man/traps") == custom_id
    delete_category(db, custom_id)
    db.commit()
    assert resolve_category_id_by_path(db, "defense/man/traps") is None


def test_resolve_category_from_section(db):
    ensure_playbook_taxonomy(db)
    db.commit()
    category_id, legacy = resolve_category_from_section(db, "BLOB", "Offense - Man")
    assert legacy == "out_of_bounds"
    assert resolve_category_id_by_path(db, "blob") == category_id


def test_play_save_with_category_id(client, db):
    ensure_playbook_taxonomy(db)
    db.commit()
    category_id = resolve_category_id_by_path(db, "blob")
    response = client.post(
        "/playbook/save",
        data={
            "name": "Zone BLOB Special",
            "category_id": str(category_id),
            "steps_json": "[]",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    row = db.execute("SELECT category_id FROM plays WHERE name = ?", ("Zone BLOB Special",)).fetchone()
    assert row["category_id"] == category_id


def test_create_page_initializes_category_select(client, db):
    """Category dropdown is filled by JS on create/edit, not only on the list page."""
    ensure_playbook_taxonomy(db)
    db.commit()
    response = client.get("/playbook/create")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'id="playCategoryId"' in html
    assert "getElementById('playCategoryId')" in html
    assert "initPlaybookTaxonomy()" in html


def test_playbook_list_survives_missing_categories_table(client, db):
    """Older databases without play_categories should migrate on first visit."""
    db.execute("DROP TABLE IF EXISTS play_categories")
    db.commit()
    response = client.get("/playbook")
    assert response.status_code == 200
    assert db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='play_categories'"
    ).fetchone() is not None


def test_opponent_playbook_create_and_page(client, db):
    ensure_playbook_taxonomy(db)
    db.commit()
    opp_id = create_opponent_playbook(db, name="Marsing")
    db.commit()
    resp = client.get("/playbook/opponents")
    assert resp.status_code == 200
    assert b"Marsing" in resp.data
    detail = client.get(f"/playbook/opponents/{opp_id}")
    assert detail.status_code == 200
    assert b"Marsing" in detail.data
