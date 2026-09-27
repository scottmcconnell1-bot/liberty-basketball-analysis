"""Film Tool top bar and settings cleanup tests."""

from pathlib import Path


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


def test_film_tool_manual_tagging_overlays_film(client):
    html = client.get("/film").data.decode("utf-8")
    film_at = html.find('id="filmReviewGrid"')
    video_at = html.find('<video id="video"')
    overlay_at = html.find('id="ftTagOverlay"')
    bar_at = html.find('class="ft-video-bar"')
    panel_at = html.find('id="ftManualTagPanel"')
    box_at = html.find('id="ftProgramStep1"')
    game_info_at = html.find('id="ftGameInfoDetails"')
    assert film_at > 0
    assert video_at > film_at
    assert overlay_at > video_at
    assert bar_at > overlay_at
    assert panel_at > overlay_at
    assert 'hidden' in html[panel_at:panel_at + 80]
    assert box_at > 0 and box_at < film_at
    assert game_info_at > 0 and game_info_at < film_at
    assert 'id="ftManualTagDetails"' not in html
    assert 'id="ftManualTagToggle"' in html
    assert 'id="ftTagGameBtn"' in html
    assert 'id="ftGameTeamsDialog"' in html
    assert 'class="ft-quick-tag"' in html
    assert html.find('id="startersBtn"') > overlay_at
    assert html.find('id="startersBtn"') < html.find('data-tag-tab="offense"')
    assert html.find("</details>", game_info_at) < film_at
    score_at = html.find('class="ft-scoreboard"')
    assert game_info_at < score_at < film_at
    assert 'id="loadTagsBtn"' in html
    assert 'id="ftScoreHint"' in html
    assert 'id="ftQ1EndBtn"' in html
    assert "Score updates from tagged makes" in html
    hide_css = html.split("#film-tool-root.ft-manual-tagging-on .ft-program-section", 1)[1].split("}", 1)[0]
    assert "ft-vid-controls" not in hide_css
    assert "ft-scoreboard" not in hide_css
    assert 'aria-label="Video transport controls"' in html
    assert 'data-tag-tab="offense"' in html
    assert 'data-tag-tab="defense"' in html
    assert 'data-tag-tab="flow"' in html
    assert 'id="ftTagPaneOffense"' in html
    assert 'id="ftTagPaneDefense"' in html
    assert 'id="ftTagPaneFlow"' in html


def test_settings_includes_film_tool_section(client):
    response = client.get("/settings")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert 'id="film-tool"' in html
    assert "Tagging vocabulary" in html
    assert "filmToolThemeSetting" in html
    assert '/film?open=terms' in html


def test_film_tool_quick_tag_uses_game_roster_flow():
    js = (Path(__file__).resolve().parents[1] / "static/js/film-tool.js").read_text(encoding="utf-8")
    css = (Path(__file__).resolve().parents[1] / "static/css/film-tool.css").read_text(encoding="utf-8")
    jump = js.split("{ id: 'jumpball'", 1)[1].split("{ id:", 1)[0]
    assert "teamMode: 'team-player'" in jump
    assert "Who won the jump?" in js
    assert "function appendAddPlayerRow" in js
    assert "function loadGameTeamRosters" in js
    assert "prompt(" not in js
    assert "#film-tool-root #quickTagDialog" in css
    assert "calc(100vw - 4.5rem)" in css
    blob = js.split("{ id: 'blob'", 1)[1].split("{ id:", 1)[0]
    slob = js.split("{ id: 'slob'", 1)[1].split("{ id:", 1)[0]
    timeout = js.split("{ id: 'timeout'", 1)[1].split("{ id:", 1)[0]
    turnover = js.split("{ id: 'turnover'", 1)[1].split("{ id:", 1)[0]
    assert "teamMode: 'team-only'" in blob
    assert "teamMode: 'team-only'" in slob
    assert "teamMode: 'team-only'" in timeout
    assert "teamMode: 'team-only'" in turnover
    assert "function askAssistAfterMake" in js
    assert "Did an assist occur?" in js
    assert "function playersOnFloor" in js
    assert "Only the five in the game. SUB if this is a replacement." in js
    assert "function isOurTaggedTeam" in js
    assert "function knownQ1EndSeconds" in js
    assert "15 * 60 + 58" in js
    assert "Q1 ends at 15:58" in js
    assert "ENDQTR" in js.split("function currentQuarter()", 1)[1].split("function ", 1)[0]
    assert "function repairEmptyTeams" in js
    assert "if (selected && !terms.includes(selected))" in js
    assert "function autosaveStorageKey" in js
    assert "function autosaveMatchesOpenFilm" in js
    assert "analysisGameId: openAnalysisGameId()" in js
    assert "function teachManualTagsToAi" in js
    assert "/teach-manual" in js
    assert "function pullServerTagsForOpenFilm" in js
    assert "/manual-tags" in js
    assert 'id="teachAiBtn"' in (Path(__file__).resolve().parents[1] / "templates" / "film_tool.html").read_text(encoding="utf-8")
