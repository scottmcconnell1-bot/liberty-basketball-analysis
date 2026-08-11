"""Highlight clips MVP: reviewed ledger → filter → generate/export."""

import json

from highlight_clips import (
    build_seek_url,
    clip_window_ms,
    list_highlight_moments,
)


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


def _create_game(client, source_key="highlight-game"):
    r = post_json(client, "/api/games", {
        "source_type": "manual",
        "source_key": source_key,
    })
    assert r.status_code == 201
    return r.get_json()["id"]


def _save_event(client, game_id, *, player, event_type, timestamp_ms, human_verified=False):
    r = post_json(client, "/api/save_event", {
        "game_id": game_id,
        "player": player,
        "event_type": event_type,
        "timestamp_ms": timestamp_ms,
        "human_verified": human_verified,
        "source_type": "ai" if not human_verified else "manual",
        "confidence": 0.8,
    })
    assert r.status_code == 200
    return r.get_json()["id"]


def test_clip_window_and_seek_helpers():
    assert clip_window_ms(10000, pad_before_ms=3000, pad_after_ms=5000) == (7000, 15000)
    assert clip_window_ms(1000, pad_before_ms=3000, pad_after_ms=5000) == (0, 6000)
    url = build_seek_url("game.mp4", "demo_key", 12345)
    assert url.startswith("/film/game.mp4?")
    assert "game_id=demo_key" in url
    assert "t=12345" in url


def test_highlights_page_renders(client):
    r = client.get("/highlights")
    assert r.status_code == 200
    assert b"Highlight Clips" in r.data
    assert b"/api/highlights/moments" in r.data
    assert b'href="/highlights"' in client.get("/").data or b"/highlights" in client.get("/film").data


def test_moments_exclude_pending_and_empty_state(client, db):
    game_id = _create_game(client, "hl-empty-pending")
    pending_id = _save_event(
        client, game_id, player="23", event_type="made_two", timestamp_ms=5000
    )

    empty = client.get(f"/api/highlights/moments?game_id={game_id}")
    assert empty.status_code == 200
    payload = empty.get_json()
    assert payload["reviewed_event_count"] == 0
    assert payload["empty_reason"] == "no_reviewed_events"
    assert payload["moments"] == []
    assert all(m["id"] != pending_id for m in payload["moments"])


def test_moments_filter_jersey_and_event_type(client, db):
    game_id = _create_game(client, "hl-filter")
    eid23 = _save_event(
        client, game_id, player="23", event_type="made_two", timestamp_ms=10000, human_verified=True
    )
    eid5 = _save_event(
        client, game_id, player="5", event_type="turnover", timestamp_ms=20000, human_verified=True
    )
    eid_named = _save_event(
        client,
        game_id,
        player="Player 23",
        event_type="made_three",
        timestamp_ms=30000,
        human_verified=True,
    )

    all_moments = client.get(f"/api/highlights/moments?game_id={game_id}")
    assert all_moments.status_code == 200
    assert all_moments.get_json()["reviewed_event_count"] == 3

    by_jersey = client.get(f"/api/highlights/moments?game_id={game_id}&jersey=23")
    assert by_jersey.status_code == 200
    ids = {m["id"] for m in by_jersey.get_json()["moments"]}
    assert eid23 in ids
    assert eid_named in ids
    assert eid5 not in ids

    by_type = client.get(f"/api/highlights/moments?game_id={game_id}&event_type=turnover")
    type_ids = {m["id"] for m in by_type.get_json()["moments"]}
    assert type_ids == {eid5}


def test_generate_saves_clips_and_skips_pending(client, db, app):
    game_id = _create_game(client, "hl-generate")
    pending_id = _save_event(
        client, game_id, player="12", event_type="steal", timestamp_ms=1000
    )
    accepted_id = _save_event(
        client,
        game_id,
        player="12",
        event_type="made_two",
        timestamp_ms=8000,
        human_verified=True,
    )

    resp = post_json(
        client,
        "/api/highlights/generate",
        {
            "game_id": game_id,
            "event_ids": [pending_id, accepted_id],
            "save_clips": True,
            "cut_video": False,
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["cut_mode"] == "seek_export"
    assert len(data["export"]) == 1
    assert data["export"][0]["event_id"] == accepted_id
    assert pending_id in data["missing_event_ids"]
    assert len(data["saved_clips"]) == 1
    assert data["saved_clips"][0]["clip_category"] == "highlight"
    assert data["saved_clips"][0]["event_id"] == accepted_id

    clips = client.get("/api/clips").get_json()
    assert any(c["event_id"] == accepted_id for c in clips)


def test_games_endpoint_counts_reviewed(client, db):
    game_id = _create_game(client, "hl-games-count")
    _save_event(client, game_id, player="1", event_type="foul", timestamp_ms=100)
    _save_event(
        client, game_id, player="1", event_type="made_two", timestamp_ms=200, human_verified=True
    )

    r = client.get("/api/highlights/games")
    assert r.status_code == 200
    payload = r.get_json()
    row = next(g for g in payload["games"] if g["id"] == game_id)
    assert row["reviewed_event_count"] == 1


def test_list_highlight_moments_helper_direct(app, db):
    with app.app_context():
        db.execute(
            """INSERT INTO games (source_type, source_key) VALUES ('manual', 'hl-direct')"""
        )
        db.commit()
        game_id = db.execute(
            "SELECT id FROM games WHERE source_key='hl-direct'"
        ).fetchone()["id"]
        db.execute(
            """INSERT INTO events
               (game_id, relational_game_id, player, event_type, timestamp_ms,
                review_status, human_verified, source_type)
               VALUES (?, ?, '7', 'block', 4000, 'accepted', 1, 'manual')""",
            (str(game_id), game_id),
        )
        db.execute(
            """INSERT INTO events
               (game_id, relational_game_id, player, event_type, timestamp_ms,
                review_status, human_verified, source_type)
               VALUES (?, ?, '7', 'steal', 5000, 'pending', 0, 'ai')""",
            (str(game_id), game_id),
        )
        db.commit()

        payload = list_highlight_moments(db, game_id, jersey="7")
        assert payload["reviewed_event_count"] == 1
        assert len(payload["moments"]) == 1
        assert payload["moments"][0]["event_type"] == "block"
        assert payload["moments"][0]["clip_start_ms"] == 1000
        assert payload["moments"][0]["clip_end_ms"] == 9000
