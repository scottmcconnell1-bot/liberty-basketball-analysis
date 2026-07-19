"""Tests for demo-mode DONE / uninstall helpers."""

from blueprints.demo import demo_mode_enabled


def test_demo_mode_env(monkeypatch, tmp_path):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    assert demo_mode_enabled() is False

    monkeypatch.setenv("DEMO_MODE", "1")
    assert demo_mode_enabled() is True


def test_demo_done_forbidden_without_demo_mode(client, monkeypatch):
    monkeypatch.setattr("blueprints.demo.demo_mode_enabled", lambda: False)
    resp = client.post("/api/demo/done")
    assert resp.status_code == 403
    assert resp.get_json()["ok"] is False


def test_demo_status_and_done_button_in_html(client, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    status = client.get("/api/demo/status")
    assert status.status_code == 200
    assert status.get_json()["demo_mode"] is True

    page = client.get("/")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'id="demo-done-btn"' in html
    assert "DONE" in html
    assert "/api/demo/done" in html


def test_done_button_hidden_without_demo_mode(client, monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setattr("blueprints.demo.demo_mode_enabled", lambda: False)
    page = client.get("/")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'id="demo-done-btn"' not in html
