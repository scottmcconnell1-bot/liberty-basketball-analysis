"""Tests for season-scoped Film Tool rosters."""

import io


from film_roster import delete_film_roster, list_film_roster_players, save_film_roster

SAMPLE_CSV = """POS,#,NAME,GRADE
PG,0,Carter Sullivan,8
SG,3,Jonathan Kariuki,8
C,45,Jasper Musgrave,8
"""


def _create_season(db, name="2025-26"):
    return db.execute(
        "INSERT INTO seasons (name, start_date, end_date) VALUES (?, ?, ?)",
        (name, "2025-11-01", "2026-03-01"),
    ).lastrowid


def test_save_and_list_film_roster(db):
    season_id = _create_season(db)
    result = save_film_roster(
        db,
        season_id=season_id,
        level="varsity",
        gender="boys",
        side="our",
        players=[
            {"label": "0 - Carter Sullivan, 8", "jersey_number": "0", "name": "Carter Sullivan"},
            {"label": "45 - Jasper Musgrave, 8", "jersey_number": "45", "name": "Jasper Musgrave"},
        ],
        replace=True,
    )
    db.commit()

    assert result["count"] == 2
    players = list_film_roster_players(
        db, season_id=season_id, level="varsity", gender="boys", side="our"
    )
    assert len(players) == 2
    assert players[0]["label"] == "0 - Carter Sullivan, 8"


def test_merge_film_roster_keeps_existing_players(db):
    season_id = _create_season(db)
    save_film_roster(
        db,
        season_id=season_id,
        level="jv",
        gender="girls",
        side="our",
        players=[{"label": "1 - Alex Smith"}],
        replace=True,
    )
    save_film_roster(
        db,
        season_id=season_id,
        level="jv",
        gender="girls",
        side="our",
        players=[{"label": "2 - Bailey Jones"}],
        replace=False,
    )
    db.commit()

    players = list_film_roster_players(
        db, season_id=season_id, level="jv", gender="girls", side="our"
    )
    labels = {player["label"] for player in players}
    assert labels == {"1 - Alex Smith", "2 - Bailey Jones"}


def test_delete_film_roster(db):
    season_id = _create_season(db)
    save_film_roster(
        db,
        season_id=season_id,
        level="jrhigh",
        gender="boys",
        side="opp",
        players=[{"label": "12 - Opponent Player"}],
        replace=True,
    )
    db.commit()

    deleted = delete_film_roster(
        db, season_id=season_id, level="jrhigh", gender="boys", side="opp"
    )
    db.commit()
    assert deleted == 1
    assert not list_film_roster_players(
        db, season_id=season_id, level="jrhigh", gender="boys", side="opp"
    )


def test_api_film_rosters_import_with_season(client, db):
    season_id = _create_season(db)
    db.commit()
    data = {
        "file": (io.BytesIO(SAMPLE_CSV.encode("utf-8")), "roster.csv"),
        "file_type": "csv",
        "season_id": str(season_id),
        "level": "varsity",
        "gender": "boys",
        "side": "our",
        "replace": "true",
    }
    resp = client.post("/api/film-rosters/import", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["count"] == 3
    assert payload["season_id"] == season_id

    list_resp = client.get(
        f"/api/film-rosters?season_id={season_id}&level=varsity&gender=boys&side=our"
    )
    assert list_resp.status_code == 200
    assert list_resp.get_json()["count"] == 3


def test_api_film_rosters_delete(client, db):
    season_id = _create_season(db)
    save_film_roster(
        db,
        season_id=season_id,
        level="varsity",
        gender="boys",
        side="our",
        players=[{"label": "5 - Test Player"}],
        replace=True,
    )
    db.commit()

    resp = client.delete(
        f"/api/film-rosters?season_id={season_id}&level=varsity&gender=boys&side=our"
    )
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == 1


def test_api_film_rosters_import_requires_season(client):
    data = {
        "file": (io.BytesIO(SAMPLE_CSV.encode("utf-8")), "roster.csv"),
        "file_type": "csv",
        "level": "varsity",
        "gender": "boys",
        "side": "our",
    }
    resp = client.post("/api/film-rosters/import", data=data, content_type="multipart/form-data")
    assert resp.status_code == 400
    assert "season_id" in resp.get_json()["error"].lower()
