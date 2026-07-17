"""Tests for server-side Film Tool manual tag persistence."""

from film_tool_games import (
    delete_film_tool_game,
    get_film_tool_game,
    import_exported_events,
    list_film_tool_games,
    save_film_tool_game,
)


def _sample_game(client_game_id="game-1001", analysis_key="liberty_vs_test"):
    return {
        "id": client_game_id,
        "gameType": "my",
        "date": "2026-01-10",
        "ourTeam": "Liberty",
        "opponent": "Test High",
        "analysisGameId": analysis_key,
        "rows": [
            {
                "label": "2PT MAKE",
                "player": "12 - Smith",
                "quarter": "Q1",
                "team": "Liberty",
                "side": "off",
                "category": "shot",
                "eventtype": "2PT",
                "result": "MAKE",
                "start": "1:23",
                "duration": "0:03",
                "notes": "",
            }
        ],
        "currentStarters": None,
        "quarterStarters": {"Q1": None, "Q2": None, "Q3": None, "Q4": None},
        "updatedAt": "2026-01-10T12:00:00+00:00",
    }


def test_save_and_get_film_tool_game(db):
    payload = _sample_game()
    result = save_film_tool_game(db, payload)
    db.commit()

    assert result["client_game_id"] == "game-1001"
    assert result["tag_count"] == 1

    loaded = get_film_tool_game(db, "game-1001")
    assert loaded is not None
    assert loaded["opponent"] == "Test High"
    assert len(loaded["rows"]) == 1
    assert loaded["rows"][0]["eventtype"] == "2PT"


def test_list_film_tool_games_by_analysis_key(db):
    save_film_tool_game(db, _sample_game("game-a", "alpha_game"))
    save_film_tool_game(db, _sample_game("game-b", "beta_game"))
    db.commit()

    alpha_games = list_film_tool_games(db, analysis_key="alpha_game")
    assert len(alpha_games) == 1
    assert alpha_games[0]["id"] == "game-a"


def test_import_exported_events_json(db):
    export_payload = {
        "mode": "my",
        "gametype": "my",
        "events": [
            {
                "label": "3PT MISS",
                "player": "5",
                "quarter": "Q1",
                "team": "Liberty",
                "eventtype": "3PT",
                "result": "MISS",
                "start": 83,
                "duration": 2,
            }
        ],
        "analysisGameId": "imported_game",
    }
    import_exported_events(db, export_payload)
    db.commit()

    games = list_film_tool_games(db, analysis_key="imported_game")
    assert len(games) == 1
    assert games[0]["rows"][0]["start"] == "1:23"


def test_delete_film_tool_game(db):
    save_film_tool_game(db, _sample_game())
    db.commit()
    assert delete_film_tool_game(db, "game-1001") is True
    db.commit()
    assert get_film_tool_game(db, "game-1001") is None


def test_api_film_tool_games_round_trip(client, db):
    payload = _sample_game("game-api", "api_game_key")
    resp = client.put("/api/film-tool-games", json=payload)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["tag_count"] == 1

    listed = client.get("/api/film-tool-games?analysis_key=api_game_key")
    assert listed.status_code == 200
    games = listed.get_json()["games"]
    assert len(games) == 1
    assert games[0]["rows"][0]["result"] == "MAKE"

    one = client.get("/api/film-tool-games/game-api")
    assert one.status_code == 200
    assert one.get_json()["analysisGameId"] == "api_game_key"

    imported = client.post(
        "/api/film-tool-games/import?analysis_key=import_route_game",
        json={"events": payload["rows"], "gametype": "my", "opponent": "Import Opp"},
    )
    assert imported.status_code == 200

    deleted = client.delete("/api/film-tool-games/game-api")
    assert deleted.status_code == 200
