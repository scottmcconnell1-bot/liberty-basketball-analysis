"""Tests for demo-mode DONE / uninstall helpers."""

from blueprints.demo import demo_mode_enabled


def test_demo_mode_env(monkeypatch, tmp_path):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    assert demo_mode_enabled() is False

    monkeypatch.setenv("DEMO_MODE", "1")
    assert demo_mode_enabled() is True


def test_demo_mode_flag_file(monkeypatch, tmp_path):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    assert demo_mode_enabled() is False

    (tmp_path / ".liberty_demo_mode").write_text("1\n", encoding="ascii")
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
    assert "Uninstalling" in html
    assert "Could not reach the demo uninstall API" in html


def test_done_button_hidden_without_demo_mode(client, monkeypatch):
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setattr("blueprints.demo.demo_mode_enabled", lambda: False)
    page = client.get("/")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'id="demo-done-btn"' not in html


def test_demo_done_returns_200_before_exit(client, monkeypatch, tmp_path):
    """Handler must return JSON ok before scheduling process exit."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.chdir(tmp_path)

    scheduled = []

    def fake_schedule(delay_sec=None):
        scheduled.append(delay_sec if delay_sec is not None else 0.5)

    monkeypatch.setattr("blueprints.demo._schedule_hard_exit", fake_schedule)
    monkeypatch.setattr(
        "blueprints.demo.subprocess.Popen",
        lambda *a, **k: type("P", (), {"pid": 1})(),
    )

    resp = client.post("/api/demo/done")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert "uninstall" in body["message"].lower() or "close" in body["message"].lower()
    # after_this_request runs during the test client response cycle
    assert scheduled == [0.5]
    assert (tmp_path / "LibertyDemo_done.flag").is_file()
    assert (tmp_path / "LibertyDemo_web_cleanup.bat").is_file()
