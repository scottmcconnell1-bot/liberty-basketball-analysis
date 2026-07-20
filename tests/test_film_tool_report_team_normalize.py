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


def test_film_tool_template_cache_bust_bumped():
    text = Path("templates/film_tool.html").read_text(encoding="utf-8")
    assert "js/film-tool.js" in text
    assert "?v=20260720filmOpen" in text
