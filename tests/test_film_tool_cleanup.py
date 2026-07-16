"""Film Tool top bar and settings cleanup tests."""


def test_film_tool_top_bar_is_simplified(client):
    response = client.get("/film")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert 'class="btn tab-btn active"' in html or 'class="btn tab-btn' in html
    assert "⚙ Setup" in html
    assert 'href="/settings#film-tool"' in html
    assert 'id="manageTermsBtn"' not in html
    assert 'data-theme-toggle' not in html
    assert 'id="exportBtn"' in html
    assert 'id="manualTagFocusBtn"' in html
    assert 'id="undoBtnBar"' in html
    assert 'id="vidPlayPauseBtn"' in html
    assert 'id="ftTagDrawerToggle"' in html
    assert 'data-skip="-5"' in html
    assert 'data-skip="-10"' in html
    assert 'data-skip="5"' in html
    assert 'Focus FS' in html
    assert 'ft-tag-drawer-toggle' in html
    assert 'data-skip="-30"' not in html
    assert 'manual-tag-focus' in html


def test_settings_includes_film_tool_section(client):
    response = client.get("/settings")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert 'id="film-tool"' in html
    assert "Tagging vocabulary" in html
    assert "filmToolThemeSetting" in html
    assert '/film?open=terms' in html
