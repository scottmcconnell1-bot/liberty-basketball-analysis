"""Tests for spiral scorebook validation + confirmed JSON shape."""

from __future__ import annotations

import json
from pathlib import Path

from stat_book.checksum import apply_validation, run_validation
from stat_book.demo import LIBERTY_HSB_PLAYERS
from stat_book.paths import TEMPLATES_ROOT
from stat_book.schema import SCHEMA_VERSION, build_confirmed_box, stamp_confirmed, validate_confirmed_box


def test_pts_identity_ok():
    box = build_confirmed_box(
        game_id="g1",
        template_id="liberty_spiral_scorebook",
        players=[{"jersey": "21", "team": "home", "extras": {"fg2": 3, "fg3": 3}, "ftm": 2, "fta": 4, "pts": 17}],
    )
    assert run_validation(box)["ok"] is True


def test_pts_identity_mismatch():
    box = build_confirmed_box(
        game_id="g1",
        template_id="liberty_spiral_scorebook",
        players=[{"jersey": "21", "team": "home", "extras": {"fg2": 3, "fg3": 3}, "ftm": 2, "fta": 4, "pts": 99}],
    )
    result = run_validation(box)
    assert result["ok"] is False
    assert any(i["code"] == "pts_identity" for i in result["issues"])


def test_ftm_gt_fta():
    box = build_confirmed_box(
        game_id="g1",
        template_id="liberty_spiral_scorebook",
        players=[{"jersey": "1", "team": "home", "extras": {"fg2": 1, "fg3": 0}, "ftm": 3, "fta": 1, "pts": 5}],
    )
    assert any(i["code"] == "makes_lte_attempts" for i in run_validation(box)["issues"])


def test_confirmed_shape_matches_foundation():
    box = build_confirmed_box(
        game_id="shape",
        template_id="liberty_spiral_scorebook",
        players=LIBERTY_HSB_PLAYERS,
        home_team="Liberty",
        away_team="HSB",
        final_score_home=48,
        final_score_away=49,
        quarters=[{"period": "F", "home_pts": 48, "away_pts": 49}],
    )
    box = apply_validation(box)
    box = stamp_confirmed(box, "pytest")
    errors = validate_confirmed_box(box)
    assert errors == [], errors
    assert box["schema_version"] == SCHEMA_VERSION
    assert isinstance(box["checksums"], dict)
    assert isinstance(box["quarters"], list)
    assert box["players"][0]["extras"]["fg2"] == 1


def test_spiral_template_assets_exist():
    tdir = TEMPLATES_ROOT / "liberty_spiral_scorebook"
    assert (tdir / "blank.png").is_file()
    assert (tdir / "layout.json").is_file()
    layout = json.loads((tdir / "layout.json").read_text(encoding="utf-8"))
    assert layout["template_id"] == "liberty_spiral_scorebook"
    assert layout["page_count"] == 2
    assert len(layout["cells"]) > 50


def test_example_game_foundation_shape():
    path = Path("data/stat_books/confirmed/example_game.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    # Foundation example may omit optional keys; require core shape
    assert data["schema_version"] == 1
    assert "players" in data and "checksums" in data and "quarters" in data


def test_sanitize_game_id_allows_jrhigh_comma():
    from stat_book.paths import sanitize_game_id

    gid = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
    assert sanitize_game_id(gid) == gid


def test_sanitize_game_id_rejects_path_chars():
    from stat_book.paths import sanitize_game_id
    import pytest

    with pytest.raises(ValueError):
        sanitize_game_id("../evil")
    with pytest.raises(ValueError):
        sanitize_game_id("a/b")


def test_upload_jrhigh_comma_game_id(client, tmp_path, monkeypatch):
    monkeypatch.setitem(client.application.config, "UPLOAD_FOLDER", str(tmp_path))
    sample_png = Path("data/stat_books/templates/liberty_spiral_scorebook/blank.png")
    gid = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
    data = {
        "template_id": "liberty_spiral_scorebook",
        "scan": (sample_png.open("rb"), "scorebook.png"),
    }
    resp = client.post(
        f"/stat-books/games/{gid}/upload",
        data=data,
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303), resp.data
    assert f"/stat-books/games/" in (resp.headers.get("Location") or "")
    draft = tmp_path / "stat_books" / gid / "draft.json"
    assert draft.is_file()
    original = list((tmp_path / "stat_books" / gid).glob("original.*"))
    assert original, "upload should save original image"
    review = client.get(f"/stat-books/games/{gid}/review")
    assert review.status_code == 200


def test_routes_sample_and_confirm(client, tmp_path, monkeypatch):
    monkeypatch.setitem(client.application.config, "UPLOAD_FOLDER", str(tmp_path))
    # Keep the confirmed JSON out of the tracked data/stat_books/confirmed/ tree.
    import stat_book.paths as sb_paths
    confirmed_dir = tmp_path / "confirmed"
    confirmed_dir.mkdir()
    monkeypatch.setattr(sb_paths, "CONFIRMED_ROOT", confirmed_dir)
    resp = client.get("/stat-books")
    assert resp.status_code == 200
    assert b"Stat Books" in resp.data

    sample = client.post("/stat-books/sample", follow_redirects=False)
    assert sample.status_code in (302, 303)

    review = client.get("/stat-books/games/sample-hsb-liberty/review")
    assert review.status_code == 200

    # Confirm a clean single-player box that passes validation + shape
    box = build_confirmed_box(
        game_id="sample-hsb-liberty",
        template_id="liberty_spiral_scorebook",
        players=[
            {"jersey": "21", "name": "H. Coleman", "team": "home", "extras": {"fg2": 3, "fg3": 3}, "fta": 4, "ftm": 2, "pts": 17}
        ],
        home_team="Liberty",
        away_team="HSB",
        final_score_home=17,
        final_score_away=0,
        quarters=[],
        checksums={},
    )
    box = apply_validation(box)
    assert box["validation"]["ok"] is True
    conf = client.post(
        "/stat-books/games/sample-hsb-liberty/confirm",
        json={"box": box, "confirmed_by": "pytest"},
    )
    assert conf.status_code == 200
    payload = conf.get_json()
    assert payload["ok"] is True
    saved = json.loads(Path(payload["path"]).read_text(encoding="utf-8"))
    assert validate_confirmed_box(saved) == []
    assert saved["confirmed_by"] == "pytest"

    api = client.get("/stat-books/confirmed/sample-hsb-liberty")
    assert api.status_code == 200
    assert api.get_json()["game_id"] == "sample-hsb-liberty"
