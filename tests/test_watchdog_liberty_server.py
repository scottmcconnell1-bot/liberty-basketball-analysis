"""scripts/watchdog_liberty_server.py: a hung server holding the port is restarted."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import watchdog_liberty_server as wd  # noqa: E402


@pytest.fixture
def quiet_watchdog(tmp_path, monkeypatch):
    monkeypatch.setattr(wd, "LOG_DIR", tmp_path)
    monkeypatch.setattr(wd, "LOG_FILE", tmp_path / "watchdog.log")
    monkeypatch.setattr(wd.time, "sleep", lambda _s: None)
    monkeypatch.setattr(sys, "argv", ["watchdog_liberty_server.py"])
    saved = {}
    monkeypatch.setattr(wd, "_save_pids", lambda pids: saved.update(pids))
    return saved


def test_hung_server_is_stopped_then_restarted(quiet_watchdog, monkeypatch):
    state = {"port_open": True, "healthy": False, "stopped": None, "started": False}
    monkeypatch.setattr(wd, "_load_pids", lambda: {"liberty_pid": 4242})
    monkeypatch.setattr(wd, "_pid_alive", lambda pid: pid == 4242 and state["stopped"] is None)

    def stop(pid):
        state["stopped"] = pid
        state["port_open"] = False
        return True

    def ensure(pids):
        assert not state["port_open"], "must stop the hung process before starting a new one"
        state["started"] = True
        state["port_open"] = True
        state["healthy"] = True
        return {"liberty_pid": 5555}

    monkeypatch.setattr(wd, "_stop_pid", stop)
    monkeypatch.setattr(wd, "_port_open", lambda: state["port_open"])
    monkeypatch.setattr(wd, "server_healthy", lambda: state["healthy"])
    monkeypatch.setattr(wd, "ensure_server", ensure)

    assert wd.main() == 0
    assert state["stopped"] == 4242
    assert state["started"]
    assert quiet_watchdog["liberty_pid"] == 5555


def test_unknown_listener_is_not_killed(quiet_watchdog, monkeypatch):
    killed = []
    monkeypatch.setattr(wd, "_load_pids", lambda: {"liberty_pid": 4242})
    monkeypatch.setattr(wd, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(wd, "_stop_pid", lambda pid: killed.append(pid) or True)
    monkeypatch.setattr(wd, "_port_open", lambda: True)
    monkeypatch.setattr(wd, "server_healthy", lambda: False)
    monkeypatch.setattr(wd, "ensure_server", lambda pids: pytest.fail("must not start over a foreign listener"))

    assert wd.main() == 1
    assert killed == []


def test_http_4xx_counts_as_alive(monkeypatch):
    import urllib.error

    def raise_401(url, timeout):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(wd.urllib.request, "urlopen", raise_401)
    assert wd._http_ok("/") is True


def test_http_5xx_is_unhealthy(monkeypatch):
    import urllib.error

    def raise_500(url, timeout):
        raise urllib.error.HTTPError(url, 500, "Server Error", {}, None)

    monkeypatch.setattr(wd.urllib.request, "urlopen", raise_500)
    assert wd._http_ok("/") is False
