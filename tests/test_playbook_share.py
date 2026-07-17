"""Tests for shareable playbook links."""

import json

from playbook_sharing import ensure_share_token, get_play_by_share_token


def test_ensure_share_token_creates_and_reuses(db):
    cur = db.execute(
        "INSERT INTO plays (name, category) VALUES (?, ?)",
        ("Share Test", "offense"),
    )
    play_id = cur.lastrowid
    token1 = ensure_share_token(db, play_id)
    db.commit()
    assert token1
    token2 = ensure_share_token(db, play_id)
    assert token2 == token1


def test_get_play_by_share_token(db):
    token = "test-share-token-abc"
    cur = db.execute(
        "INSERT INTO plays (name, category, share_token) VALUES (?, ?, ?)",
        ("Shared Play", "offense", token),
    )
    play_id = cur.lastrowid
    db.commit()
    row = get_play_by_share_token(db, token)
    assert row is not None
    assert row["id"] == play_id


def test_share_api_and_public_page(client, db):
    cur = db.execute(
        "INSERT INTO plays (name, category) VALUES (?, ?)",
        ("Public Share Play", "offense"),
    )
    play_id = cur.lastrowid
    db.commit()

    resp = client.post(f"/api/playbook/play/{play_id}/share")
    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert data["token"]
    assert "/play/share/" in data["url"]

    page = client.get(f"/play/share/{data['token']}")
    assert page.status_code == 200
    assert b"Public Share Play" in page.data
    assert b"Shared play" in page.data


def test_share_page_not_found(client):
    resp = client.get("/play/share/does-not-exist")
    assert resp.status_code == 404
