"""Tests for Approach A Coach Portal soft gate."""


import pytest


@pytest.fixture
def coach_password(monkeypatch):
    monkeypatch.setenv("LIBERTY_COACH_PASSWORD", "test-coach-secret")
    return "test-coach-secret"


def _login_coach(client, password="test-coach-secret"):
    return client.post("/coach", data={"password": password}, follow_redirects=False)


def test_coach_login_sets_session(client, coach_password):
    resp = _login_coach(client, coach_password)
    assert resp.status_code in (302, 303)
    assert resp.headers["Location"].endswith("/coach/progress")

    with client.session_transaction() as sess:
        assert sess.get("coach_portal") is True
        assert sess.get("user_role") == "coach"


def test_coach_login_rejects_bad_password(client, coach_password):
    resp = _login_coach(client, "wrong")
    assert resp.status_code == 200
    assert b"Incorrect coach password" in resp.data
    with client.session_transaction() as sess:
        assert not sess.get("coach_portal")


def test_coach_setup_when_password_unset(client, monkeypatch):
    monkeypatch.delenv("LIBERTY_COACH_PASSWORD", raising=False)
    resp = client.get("/coach")
    assert resp.status_code == 200
    assert b"LIBERTY_COACH_PASSWORD" in resp.data


def test_coach_ops_routes_denied(client, coach_password):
    assert _login_coach(client, coach_password).status_code in (302, 303)

    for path in ("/settings", "/users", "/debug", "/status", "/preview", "/nfhs-matches"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code in (302, 303), path
        assert "/" == resp.headers["Location"].rstrip("/") or resp.headers["Location"].endswith("/"), path

    api = client.post("/api/admin/reset")
    assert api.status_code == 403


def test_coach_allowed_routes(client, coach_password):
    assert _login_coach(client, coach_password).status_code in (302, 303)

    for path in ("/", "/schedule", "/playbook", "/videos", "/film"):
        resp = client.get(path)
        assert resp.status_code == 200, path


def test_coach_nav_hides_ops(client, coach_password):
    assert _login_coach(client, coach_password).status_code in (302, 303)
    home = client.get("/")
    assert home.status_code == 200
    html = home.data.decode("utf-8")
    assert "Coach view" in html
    assert "read only" in html.lower()
    assert 'href="/settings"' not in html
    assert 'href="/users"' not in html
    assert 'href="/debug"' not in html
    assert 'href="/nfhs-matches"' not in html
    assert "Report Bug" not in html
    assert 'href="/coach/logout"' in html or "/coach/logout" in html


def test_mobile_nav_hamburger_markup(client, coach_password):
    """Hamburger must exist with aria-controls; outside-click JS must treat it as nav chrome."""
    assert _login_coach(client, coach_password).status_code in (302, 303)
    html = client.get("/").data.decode("utf-8")
    assert 'id="nav-hamburger"' in html
    assert 'aria-controls="nav-links"' in html
    assert 'id="nav-links"' in html
    # stopPropagation on hamburger so document click-outside does not instantly close
    assert "stopPropagation" in html
    assert "hamburger.contains" in html


def test_coach_readonly_get_allowed(client, coach_password):
    assert _login_coach(client, coach_password).status_code in (302, 303)
    for path in ("/schedule", "/playbook"):
        resp = client.get(path)
        assert resp.status_code == 200, path


def test_coach_readonly_blocks_mutations(client, coach_password):
    assert _login_coach(client, coach_password).status_code in (302, 303)

    # HTML form POST → flash + redirect (or 403)
    html_post = client.post("/playbook/save", data={}, follow_redirects=False)
    assert html_post.status_code in (302, 303, 403), html_post.status_code
    if html_post.status_code in (302, 303):
        # Must not have reached the real handler as a successful save
        assert html_post.headers.get("Location")

    # Schedule mutating POST
    sched = client.post("/schedule/games/save", data={}, follow_redirects=False)
    assert sched.status_code in (302, 303, 403), sched.status_code

    # JSON API → 403 with explicit error
    api = client.post(
        "/api/playbook/categories",
        json={"name": "CoachShouldNotCreate"},
        headers={"Accept": "application/json"},
    )
    assert api.status_code == 403
    body = api.get_json()
    assert body and body.get("error") == "Coach view is read-only"

    # Messages send blocked
    msg = client.post(
        "/api/messages/send",
        json={"body": "nope"},
        headers={"Accept": "application/json"},
    )
    assert msg.status_code == 403
    assert msg.get_json().get("error") == "Coach view is read-only"


def test_non_coach_can_post_mutations(client):
    """Without coach_portal session, mutating POSTs are not 403'd by the gate."""
    api = client.post(
        "/api/playbook/categories",
        json={"name": "NonCoachCat"},
        headers={"Accept": "application/json"},
    )
    assert api.status_code != 403


def test_coach_logout_clears_session(client, coach_password):
    assert _login_coach(client, coach_password).status_code in (302, 303)
    resp = client.get("/coach/logout", follow_redirects=False)
    assert resp.status_code in (302, 303)
    with client.session_transaction() as sess:
        assert not sess.get("coach_portal")


def test_path_denied_helper():
    from blueprints.coach import path_denied_for_coach

    assert path_denied_for_coach("/settings")
    assert path_denied_for_coach("/settings/custom-weights")
    assert path_denied_for_coach("/api/admin/reset")
    assert path_denied_for_coach("/api/videos/3/analyze")
    assert not path_denied_for_coach("/")
    assert not path_denied_for_coach("/schedule")
    assert not path_denied_for_coach("/playbook")
    assert not path_denied_for_coach("/videos")


def test_coach_mutation_allowlist_helper():
    from blueprints.coach import coach_mutation_allowed

    assert coach_mutation_allowed("/coach")
    assert coach_mutation_allowed("/coach/login")
    assert coach_mutation_allowed("/login")
    assert coach_mutation_allowed("/logout")
    assert not coach_mutation_allowed("/playbook/save")
    assert not coach_mutation_allowed("/api/messages/send")
    assert not coach_mutation_allowed("/schedule/games/save")
