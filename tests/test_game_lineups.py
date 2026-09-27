"""Starting five storage and bench-point roles."""

from game_boxscore import apply_starter_roles, bench_points, starter_points
from game_lineups import parse_starter_entry


def test_parse_roster_label():
    parsed = parse_starter_entry("40 - Dayley")
    assert parsed["jersey"] == "40"
    assert parsed["name"] == "Dayley"
    parsed = parse_starter_entry({"jersey": "02", "name": "Colman"})
    assert parsed["jersey"] == "2"


def test_save_requires_five_or_empty(tmp_path, monkeypatch):
    import game_lineups as gl

    monkeypatch.setattr(gl, "LINEUPS_ROOT", tmp_path)
    try:
        gl.save_starters("game1", {"liberty": [{"jersey": "1"}], "opponent": []})
        assert False, "expected ValueError"
    except ValueError:
        pass
    saved = gl.save_starters("game1", {
        "liberty": [{"jersey": n, "name": f"P{n}"} for n in range(1, 6)],
        "opponent": [],
        "source": "coach",
    })
    assert saved["complete"]["liberty"] is True
    assert saved["complete"]["opponent"] is False
    loaded = gl.load_starters("game1")
    assert [row["jersey"] for row in loaded["liberty"]] == ["1", "2", "3", "4", "5"]


def test_starter_roles_and_bench_points():
    players = [
        {"jersey": "40", "name": "Dayley", "pts": 26},
        {"jersey": "15", "name": "Colman", "pts": 11},
        {"jersey": "24", "name": "Bench", "pts": 8},
    ]
    apply_starter_roles(players, {"40", "15", "2", "10", "11"})
    assert players[0]["role"] == "starter"
    assert players[-1]["role"] == "bench"
    assert bench_points(players) == 8
    assert starter_points(players) == 37


def test_starters_api_roundtrip(client, tmp_path, monkeypatch):
    import game_lineups as gl

    monkeypatch.setattr(gl, "LINEUPS_ROOT", tmp_path)
    response = client.post("/api/games/demo_game/starters", json={
        "liberty": [{"jersey": str(n), "name": f"P{n}"} for n in range(1, 6)],
        "opponent": [],
    })
    assert response.status_code == 200
    body = response.get_json()
    assert body["complete"]["liberty"] is True
    assert body["complete"]["opponent"] is False
    loaded = client.get("/api/games/demo_game/starters")
    assert loaded.status_code == 200
    assert [row["jersey"] for row in loaded.get_json()["liberty"]] == ["1", "2", "3", "4", "5"]
