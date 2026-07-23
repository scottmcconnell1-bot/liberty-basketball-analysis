"""Smoke tests for Recruiting Station MVP."""

import json

from recruiting import (
    create_profile,
    ensure_share_token,
    format_stats_blurb,
    get_profile_by_share_token,
    player_stats_summary,
)


def _seed_player_and_stats(db):
    cur = db.execute(
        """INSERT INTO players (name, jersey_number, position, grade, program_name, gender, level)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("Alex Patriot", 11, "G", 11, "Liberty", "boys", "varsity"),
    )
    player_id = cur.lastrowid
    db.execute(
        """INSERT INTO stats (game_id, player_id, player_name, pts, fgm, fga, threes_made, threes_att, ast, reb, stl, blk, tov, minutes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("g1", player_id, "Alex Patriot", 18, 7, 14, 2, 5, 4, 5, 2, 0, 3, 28.0),
    )
    db.execute(
        """INSERT INTO stats (game_id, player_id, player_name, pts, fgm, fga, threes_made, threes_att, ast, reb, stl, blk, tov, minutes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("g2", player_id, "Alex Patriot", 12, 4, 10, 1, 4, 6, 3, 1, 1, 2, 24.0),
    )
    db.commit()
    return player_id


def test_create_share_and_public_page(client, db):
    player_id = _seed_player_and_stats(db)
    resp = client.post(
        "/api/recruiting",
        data=json.dumps(
            {
                "player_id": player_id,
                "display_name": "Alex Patriot",
                "grad_year": 2027,
                "position": "G",
                "height": "5'11\"",
                "school_program": "Liberty Charter",
                "program_level": "varsity",
                "contact_email": "coach@example.com",
                "highlight_url": "https://example.com/highlight",
                "film_links": [{"url": "https://example.com/game1", "label": "Game 1"}],
                "bio": "Floor general.",
                "season_summary": "",
                "is_published": True,
            }
        ),
        content_type="application/json",
    )
    assert resp.status_code == 201
    profile = json.loads(resp.data)
    assert profile["display_name"] == "Alex Patriot"
    assert profile["stats"]["games"] == 2
    assert profile["stats"]["ppg"] == 15.0

    share = client.post(f"/api/recruiting/{profile['id']}/share")
    assert share.status_code == 200
    share_data = json.loads(share.data)
    assert share_data["token"]
    assert "/recruiting/share/" in share_data["url"]

    page = client.get(f"/recruiting/share/{share_data['token']}")
    assert page.status_code == 200
    assert b"Alex Patriot" in page.data
    assert b"Class of 2027" in page.data
    assert b"Floor general" in page.data

    print_page = client.get(f"/recruiting/share/{share_data['token']}/print")
    assert print_page.status_code == 200
    assert b"Print" in print_page.data


def test_recruiting_list_page_and_nav(client, db):
    create_profile(
        db,
        {
            "display_name": "Jordan Scout",
            "program_level": "jv",
            "grad_year": 2028,
        },
    )
    page = client.get("/recruiting")
    assert page.status_code == 200
    assert b"Recruiting Station" in page.data
    assert b"Jordan Scout" in page.data

    home = client.get("/")
    assert home.status_code == 200
    assert b'href="/recruiting"' in home.data
    assert b"Recruiting" in home.data


def test_share_token_helpers(db):
    profile = create_profile(db, {"display_name": "Share Me", "program_level": "jr_high"})
    token1 = ensure_share_token(db, profile["id"])
    token2 = ensure_share_token(db, profile["id"])
    assert token1 == token2
    loaded = get_profile_by_share_token(db, token1)
    assert loaded is not None
    assert loaded["display_name"] == "Share Me"


def test_player_stats_summary_and_blurb(db):
    player_id = _seed_player_and_stats(db)
    summary = player_stats_summary(db, player_id, "Alex Patriot")
    assert summary["games"] == 2
    assert summary["pts"] == 30
    blurb = format_stats_blurb(summary)
    assert "2 GP" in blurb
    assert "15.0 PPG" in blurb


def test_update_and_delete(client, db):
    create = client.post(
        "/api/recruiting",
        data=json.dumps({"display_name": "Temp Athlete", "program_level": "varsity"}),
        content_type="application/json",
    )
    profile_id = json.loads(create.data)["id"]
    upd = client.put(
        f"/api/recruiting/{profile_id}",
        data=json.dumps({"display_name": "Temp Athlete", "height": "6'2\"", "program_level": "varsity"}),
        content_type="application/json",
    )
    assert upd.status_code == 200
    assert json.loads(upd.data)["height"] == "6'2\""

    deleted = client.delete(f"/api/recruiting/{profile_id}")
    assert deleted.status_code == 200
    missing = client.get(f"/api/recruiting/{profile_id}")
    assert missing.status_code == 404


def test_public_share_404(client):
    resp = client.get("/recruiting/share/does-not-exist")
    assert resp.status_code == 404
