"""Videos → Film Tool must resolve saved manual tags even after analysis_key wipe/reruns."""

from pathlib import Path

from film_tool_games import list_film_tool_games, save_film_tool_game


def test_save_does_not_wipe_existing_analysis_key(db):
    save_film_tool_game(
        db,
        {
            "id": "game-keep-key",
            "gameType": "my",
            "opponent": "Wilder High School",
            "analysisGameId": "nfhs_base__rerun_1",
            "rows": [{"eventtype": "2PT", "result": "Make"}],
            "updatedAt": "2026-07-20T00:00:00+00:00",
        },
    )
    db.commit()

    # Bare /film autosave historically sent empty analysisGameId and wiped the link.
    save_film_tool_game(
        db,
        {
            "id": "game-keep-key",
            "gameType": "my",
            "opponent": "Wilder High School",
            "analysisGameId": "",
            "rows": [{"eventtype": "2PT", "result": "Make"}, {"eventtype": "3PT", "result": "Make"}],
            "updatedAt": "2026-07-20T01:00:00+00:00",
        },
    )
    db.commit()

    games = list_film_tool_games(db, analysis_key="nfhs_base__rerun_1")
    assert len(games) == 1
    assert games[0]["id"] == "game-keep-key"
    assert games[0]["analysisGameId"] == "nfhs_base__rerun_1"
    assert len(games[0]["rows"]) == 2


def test_list_film_tool_games_matches_rerun_family(db):
    save_film_tool_game(
        db,
        {
            "id": "game-family",
            "gameType": "my",
            "opponent": "Wilder High School",
            "analysisGameId": "nfhs_stem_base__rerun_old",
            "rows": [{"eventtype": "2PT", "result": "Make"}] * 3,
            "updatedAt": "2026-07-20T00:00:00+00:00",
        },
    )
    db.commit()

    games = list_film_tool_games(db, analysis_key="nfhs_stem_base__rerun_new")
    assert len(games) == 1
    assert games[0]["id"] == "game-family"


def test_film_tool_js_preserves_linked_analysis_key():
    text = Path("static/js/film-tool.js").read_text(encoding="utf-8")
    assert "let linkedAnalysisGameId" in text
    assert "fromContext || linkedAnalysisGameId" in text
    assert "FILM_TOOL_CLIENT_GAME_ID" in text
    assert "FILM_TOOL_VIDEO_OPPONENT" in text


def test_film_tool_template_bootstraps_client_game_and_opponent():
    text = Path("templates/film_tool.html").read_text(encoding="utf-8")
    assert "FILM_TOOL_CLIENT_GAME_ID" in text
    assert "FILM_TOOL_VIDEO_OPPONENT" in text
    assert "js/film-tool.js') }}?v=20260720filmOpen" in text


def test_film_route_injects_client_game_for_opponent(client, app, db):
    save_film_tool_game(
        db,
        {
            "id": "game-1784304093435",
            "gameType": "my",
            "date": "2026-01-30",
            "ourTeam": "Liberty",
            "opponent": "Wilder High School",
            "analysisGameId": "",
            "rows": [{"eventtype": "2PT", "result": "Make"}] * 5,
            "updatedAt": "2026-07-20T00:00:00+00:00",
        },
    )
    db.execute(
        """INSERT INTO videos (original_filename, stored_filename, file_path, file_size_bytes,
           opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            "wilder.mp4",
            "nfhs_gam_test_open.mp4",
            "uploads/nfhs_gam_test_open.mp4",
            100,
            "Wilder High School",
            "nfhs_gam_test_open_base",
        ),
    )
    db.commit()

    resp = client.get("/film/nfhs_gam_test_open.mp4?game_id=nfhs_gam_test_open_base__rerun_x&focus=1")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "game-1784304093435" in html
    assert "Wilder High School" in html
    assert "FILM_TOOL_CLIENT_GAME_ID" in html
