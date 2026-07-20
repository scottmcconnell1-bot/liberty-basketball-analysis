"""Regression: blank/Select team must count as Liberty in Film Tool reports."""

from pathlib import Path


def test_film_tool_js_normalizes_blank_team_in_stat_accumulator():
    """Box score / team totals must use same team remap as Manual vs AI."""
    text = Path("static/js/film-tool.js").read_text(encoding="utf-8")
    assert "function normalizeManualTeamForCompare" in text
    assert "const team = normalizeManualTeamForCompare(r.team, our, opp)" in text
    assert "const team = r.team || 'Unknown'" not in text


def test_film_tool_js_score_state_uses_team_normalize():
    text = Path("static/js/film-tool.js").read_text(encoding="utf-8")
    assert "normalizeManualTeamForCompare(r.team, liberty, opponent)" in text


def test_film_tool_js_syncs_team_dropdown_to_liberty_names():
    """Team select must include Liberty (not only 'Our Team') so tags don't show Select."""
    text = Path("static/js/film-tool.js").read_text(encoding="utf-8")
    assert "function syncTeamVocabulary" in text
    assert "function resolveTeamSelectValue" in text
    assert "function repairRowTeamFields" in text
    assert "EVENT_TYPES_ALLOW_BLANK_TEAM" in text
    assert "Which team? — who did this action?" not in text  # old copy
    assert "Team</strong> — who did this action?" in text


def test_film_tool_js_reloads_hosted_video_with_game():
    text = Path("static/js/film-tool.js").read_text(encoding="utf-8")
    assert "function ensureHostedVideoLoaded" in text
    assert "loadHostedVideo(hostedUrl" in text
    assert "preload', 'auto'" in text or 'preload", "auto"' in text


def test_film_tool_template_cache_bust_bumped():
    text = Path("templates/film_tool.html").read_text(encoding="utf-8")
    assert "js/film-tool.js" in text
    assert "?v=20260720filmVideoTeam" in text
    assert 'preload="auto"' in text
