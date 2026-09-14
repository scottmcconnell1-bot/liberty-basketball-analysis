"""End-to-end: every feature, in the order a coach would use them, with real files.

Run:  .venv/bin/python -m pytest tests/e2e -q                     (test client, ~1-2 min)
      LIBERTY_E2E_REAL_ANALYSIS=1 ... pytest tests/e2e -q          (+ real detector on a 12 s clip)
      bash scripts/run_e2e_live.sh                                 (real gunicorn server)
"""
from __future__ import annotations

import pytest

from tests.e2e import scenarios as sc

pytestmark = pytest.mark.e2e


def test_01_no_parameterless_get_route_crashes(e2e):
    results = sc.sweep_get_routes(e2e)
    assert len(results) >= 40


def test_02_settings_and_runtime(e2e): sc.settings_runtime(e2e)
def test_03_seasons_and_schedule(e2e): sc.seasons_and_schedule(e2e)
def test_04_games_sources_nfhs(e2e): sc.games_sources_nfhs(e2e)
def test_05_roster_players_photos(e2e): sc.roster_and_players(e2e)
def test_06_users_messaging_issues(e2e): sc.users_messaging_issues(e2e)


def test_07_video_upload_analysis_trim_rerun(e2e):
    sc.video_upload(e2e, real_film=True)
    assert e2e.state["n_detections"] > 0


def test_08_analysis_pages_and_manual_events(e2e): sc.analysis_pages_and_events(e2e)
def test_09_review_ledger_highlights_clips_playlists(e2e): sc.review_and_highlights(e2e)
def test_10_practices(e2e): sc.practices(e2e)
def test_11_playbook(e2e): sc.playbook(e2e)
def test_12_scouting(e2e): sc.scouting(e2e)
def test_13_stat_books(e2e): sc.stat_books(e2e)
def test_14_assistant(e2e): sc.assistant(e2e)
def test_15_coach_portal(e2e): sc.coach_portal(e2e)
def test_16_regenerate_events_in_both_generator_modes(e2e): sc.regenerate_both_modes(e2e)


def test_17_admin_reset_only_on_temp_db(e2e):
    if e2e.live:
        pytest.skip("admin reset is only exercised against the temporary test-client DB")
    sc.admin_reset(e2e)


def test_18_route_coverage_report(e2e):
    """Every blueprint must have been exercised; print endpoint coverage for the record."""
    import app as app_module

    adapter = app_module.app.url_map.bind("localhost")
    covered, bps = set(), {}
    for rule in app_module.app.url_map.iter_rules():
        if rule.endpoint != "static":
            bps.setdefault(rule.endpoint.split(".")[0], set()).add(rule.endpoint)
    for method, path in e2e.hits:
        try:
            endpoint, _ = adapter.match(path.split("?")[0], method=method)
            covered.add(endpoint)
        except Exception:
            pass
    total = sum(len(v) for v in bps.values())
    per_bp = {bp: (len(eps & covered), len(eps)) for bp, eps in bps.items()}
    print(f"\nendpoint coverage: {len(covered)}/{total} ({100 * len(covered) // total}%)")
    for bp, (c, n) in sorted(per_bp.items()):
        print(f"  {bp:12s} {c:3d}/{n}")
    untouched = [bp for bp, (c, n) in per_bp.items() if c == 0 and bp != "(app)"]
    assert not untouched, f"blueprints never exercised: {untouched}"
    assert len(covered) >= 0.6 * total, f"coverage {len(covered)}/{total} below 60%"
