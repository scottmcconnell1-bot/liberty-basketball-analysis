"""Jr High player app, Stage 1 (plan .team/specs/10_jrhigh_player_app_plan_v7.md).

The static site is playbook.html rendered in share view with player_build=True.
Everything is written under tmp_path; the repo's data/ and dist/ are not touched.
"""

import json

from blueprints.playbook import _build_player_site


def _setup(tmp_path, db):
    hidden_text = "SECRET coach note do not ship"
    visible = db.execute(
        "INSERT INTO plays (name, category, description, tags) VALUES (?, ?, ?, ?)",
        ("Visible Play", "offense", hidden_text, "zone,press"),
    ).lastrowid
    hidden = db.execute(
        "INSERT INTO plays (name, category) VALUES (?, ?)",
        ("Hidden Play", "offense"),
    ).lastrowid
    for pid in (visible, hidden):
        db.execute(
            "INSERT INTO play_steps (play_id, step_number, label, positions_json, movements_json, notes, source_image) "
            "VALUES (?, 1, 'Start', '{}', '[]', ?, '/uploads/bulk_imports/x/page_0001.png')",
            (pid, hidden_text),
        )
    db.commit()
    data = tmp_path / "data" / "playbook"
    (data / "choreography").mkdir(parents=True)
    (data / "jrhigh_player_visibility.json").write_text(json.dumps({str(visible): True, str(hidden): False}))
    (data / "choreography" / f"{visible}.json").write_text(json.dumps({
        "version": 1, "play_id": visible, "source": "auto_extract", "court_mode": "full",
        "steps": [{
            "step_index": 0, "source_image": "/uploads/bulk_imports/x/page_0001.png",
            "court_frac": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8},
            "positions": {"o1": {"x": 250, "y": 300}}, "coachOrder": True, "movements": [],
            "ink": {"paths": {}, "marks": {}, "passes": [], "actions": []},
        }],
    }))
    return visible, hidden, hidden_text


def test_player_site_has_only_visible_plays_and_no_private_fields(app, db, tmp_path):
    visible, hidden, hidden_text = _setup(tmp_path, db)
    out = tmp_path / "dist" / "player"
    with app.test_request_context():
        result = _build_player_site(db, data_root=tmp_path, out_dir=out)
    assert result["ok"] and result["count"] == 1
    assert (out / "plays" / str(visible) / "index.html").is_file()
    assert not (out / "plays" / str(hidden)).exists()

    choreo = json.loads((out / "plays" / str(visible) / "choreography").read_text())
    assert choreo["ok"] and choreo["sticky"]
    doc = choreo["choreography"]
    assert doc["source"] == "auto_extract" and doc["court_mode"] == "full"
    assert set(doc["steps"][0]) == {"step_index", "positions", "coachOrder", "movements", "ink"}

    page = (out / "plays" / str(visible) / "index.html").read_text(encoding="utf-8")
    index = (out / "player.html").read_text(encoding="utf-8")
    for text in (page, index, json.dumps(choreo)):
        # The page's code mentions '/uploads/' in sheetImageSrc; no real sheet path ships.
        assert "/uploads/bulk_imports" not in text and "page_0001.png" not in text
        assert hidden_text not in text
    assert "court_frac" not in json.dumps(choreo)  # the page's code names it; the data must not
    assert "zone,press" not in page
    assert "Hidden Play" not in index and "Visible Play" in index


def test_player_page_plays_from_its_own_folder(app, db, tmp_path):
    visible, _hidden, _text = _setup(tmp_path, db)
    out = tmp_path / "dist" / "player"
    with app.test_request_context():
        _build_player_site(db, data_root=tmp_path, out_dir=out)
    page = (out / "plays" / str(visible) / "index.html").read_text(encoding="utf-8")
    assert 'const shareAssetBase = ".";' in page
    assert "const playerBuild = true;" in page
    assert 'src="../../man_defense.js"' in page and 'href="../../playbook.css"' in page
    # No main-app chrome: no job poller, no Google font, no service worker.
    assert "analysis_jobs" not in page and "fonts.googleapis" not in page and "serviceWorker" not in page
    # Plan v7: the page header (title, back link) is not in the player page.
    assert 'class="page-header"' not in page
    # Previous / Next work in the player app.
    assert 'onclick="prevStep()" disabled' not in page and 'onclick="nextStep()" disabled' not in page


def test_share_view_is_unchanged_by_player_build(client, db):
    db.execute(
        "INSERT INTO plays (name, category, share_token) VALUES (?, ?, ?)",
        ("Shared Only", "offense", "tok-player-build-check"),
    )
    db.commit()
    page = client.get("/play/share/tok-player-build-check").data.decode()
    assert "const playerBuild = false;" in page
    assert 'onclick="prevStep()" disabled' in page
    assert "Shared play" in page


def test_playbook_page_keeps_one_main_script(client, db):
    """The old v5 edit closed the main <script> early, so ~7000 lines rendered as text."""
    db.execute(
        "INSERT INTO plays (name, category, share_token) VALUES (?, ?, ?)",
        ("Script Check", "offense", "tok-script-check"),
    )
    db.commit()
    page = client.get("/play/share/tok-script-check").data.decode()
    main = page[page.index("async function togglePlayVisibility"):]
    assert main.index("async function playAnimation") < main.index("</script>")
