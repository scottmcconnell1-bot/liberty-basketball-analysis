"""Tests for hierarchical playbook categories."""

from playbook_taxonomy import (
    build_category_tree,
    create_category,
    delete_category,
    ensure_playbook_taxonomy,
    resolve_category_from_section,
    resolve_category_id_by_path,
)


def test_default_taxonomy_seeded(db):
    ensure_playbook_taxonomy(db)
    db.commit()
    tree = build_category_tree(db)
    assert len(tree) == 4
    assert tree[0]["name"] == "Offense"
    offense_man = next(child for child in tree[0]["children"] if child["name"] == "Man")
    subtype_names = {child["name"] for child in offense_man["children"]}
    assert subtype_names == {"Plays", "BLOB", "SLOB"}


def test_resolve_offense_man_plays_category(db):
    ensure_playbook_taxonomy(db)
    db.commit()
    category_id = resolve_category_id_by_path(db, "offense/man/plays")
    assert category_id is not None


def test_create_and_delete_custom_category(db):
    ensure_playbook_taxonomy(db)
    db.commit()
    parent_id = resolve_category_id_by_path(db, "defense/man/plays")
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
    assert legacy == "offense"
    assert resolve_category_id_by_path(db, "offense/man/blob") == category_id


def test_play_save_with_category_id(client, db):
    ensure_playbook_taxonomy(db)
    db.commit()
    category_id = resolve_category_id_by_path(db, "offense/zone/blob")
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
