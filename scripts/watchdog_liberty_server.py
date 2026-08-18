#!/usr/bin/env python3
"""Keep Liberty Flask listening on PORT (default 8080).

Used by the Windows scheduled-task watchdog so Tailscale Funnel never 502s
because app.py died after reboot/sleep/crash.

Usage:
  py -3.12 scripts/watchdog_liberty_server.py
  py -3.12 scripts/watchdog_liberty_server.py --status
"""
from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "data" / "hoopsalytics"
LOG_FILE = LOG_DIR / "liberty_watchdog.log"

# Import ensure_server from detached launcher (same spawn path + logs).
sys.path.insert(0, str(ROOT / "scripts"))
from start_hoops_teach_detached import (  # noqa: E402
    PORT,
    _load_pids,
    _port_open,
    _save_pids,
    ensure_server,
)


def _log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _http_ok(path: str = "/") -> bool:
    url = f"http://127.0.0.1:{PORT}{path}"
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def server_healthy() -> bool:
    if not _port_open():
        return False
    return _http_ok("/")


def status() -> int:
    print(f"port {PORT} open: {_port_open()}")
    print(f"http GET / ok: {_http_ok('/')}")
    print(f"http GET /coach ok: {_http_ok('/coach')}")
    pids = _load_pids()
    print(f"liberty_pid: {pids.get('liberty_pid')}")
    print(f"log: {LOG_FILE}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", action="store_true", help="Print health and exit")
    args = parser.parse_args()
    if args.status:
        return status()

    _log("=== liberty server watchdog start ===")
    if server_healthy():
        _log("Liberty healthy on :8080 - no action")
        _log("=== liberty server watchdog done ===")
        return 0

    if _port_open():
        _log("Port open but HTTP check failed - restarting app.py")
    else:
        _log("Port :8080 closed - starting Liberty")

    pids = _load_pids()
    pids = ensure_server(pids)
    _save_pids(pids)

    time.sleep(2)
    if server_healthy():
        _log(f"Liberty up after restart (pid={pids.get('liberty_pid')})")
        _log("=== liberty server watchdog done ===")
        return 0

    _log("ERROR: Liberty still unhealthy after restart - check detached_liberty.err.log")
    _log("=== liberty server watchdog failed ===")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
