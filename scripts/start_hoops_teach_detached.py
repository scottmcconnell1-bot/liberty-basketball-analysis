#!/usr/bin/env python3
"""Start Liberty + Hoops teach loop fully detached from Cursor/terminal.

Uses Windows CREATE_BREAKAWAY_FROM_JOB so closing Cursor does not kill the
GPU analysis or teach chain.

Usage:
  py -3.12 scripts/start_hoops_teach_detached.py
  py -3.12 scripts/start_hoops_teach_detached.py --status
  py -3.12 scripts/start_hoops_teach_detached.py --stop-loop
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "data" / "hoopsalytics"
PID_PATH = LOG_DIR / "detached_pids.json"
PORT = 8080

# Windows process-creation flags
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
CREATE_NO_WINDOW = 0x08000000


def _flags() -> int:
    if os.name != "nt":
        return 0
    return DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB | CREATE_NO_WINDOW


def _port_open(port: int = PORT) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


def _spawn(args: list[str], log_name: str) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    out = open(LOG_DIR / f"{log_name}.out.log", "a", encoding="utf-8")
    err = open(LOG_DIR / f"{log_name}.err.log", "a", encoding="utf-8")
    out.write(f"\n--- spawn {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    out.flush()
    creationflags = _flags()
    popen_kwargs: dict = {
        "cwd": str(ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": out,
        "stderr": err,
        "close_fds": True,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = creationflags
    else:
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(args, **popen_kwargs)
    return int(proc.pid)


def _load_pids() -> dict:
    if PID_PATH.exists():
        try:
            return json.loads(PID_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_pids(data: dict) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PID_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        # tasklist is reliable without psutil
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
        return str(pid) in (r.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def ensure_server(pids: dict) -> dict:
    if _port_open():
        print(f"[detached] Liberty already listening on :{PORT}")
        return pids
    print("[detached] Starting Liberty server (no browser)…")
    pid = _spawn(
        [sys.executable, str(ROOT / "scripts" / "launch_liberty.py"), "--no-browser"],
        "detached_liberty",
    )
    pids["liberty_pid"] = pid
    for _ in range(60):
        if _port_open():
            print(f"[detached] Liberty up (pid={pid})")
            return pids
        time.sleep(1)
    print("[detached] WARNING: server did not open :8080 within 60s — check logs")
    return pids


def ensure_teach_loop(pids: dict, *, restart: bool = False) -> dict:
    old = pids.get("teach_loop_pid")
    if old and _pid_alive(old) and not restart:
        print(f"[detached] Teach loop already running (pid={old})")
        return pids
    if old and _pid_alive(old) and restart:
        print(f"[detached] Stopping old teach loop pid={old}")
        subprocess.run(["taskkill", "/PID", str(old), "/F"], check=False, capture_output=True)
        time.sleep(1)
    print("[detached] Starting Hoops teach loop…")
    pid = _spawn([sys.executable, str(ROOT / "scripts" / "hoops_teach_loop.py")], "detached_teach_loop")
    pids["teach_loop_pid"] = pid
    print(f"[detached] Teach loop pid={pid}")
    print(f"[detached] Logs: {LOG_DIR / 'detached_teach_loop.out.log'}")
    return pids


def status() -> int:
    pids = _load_pids()
    print(f"port 8080 open: {_port_open()}")
    for key in ("liberty_pid", "teach_loop_pid"):
        pid = pids.get(key)
        print(f"{key}: {pid} alive={_pid_alive(pid)}")
    # Show analysis worker if present (no wmic — removed on some Windows builds)
    r = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq python.exe", "/V", "/FO", "CSV"],
        capture_output=True,
        text=True,
        check=False,
    )
    analysis_running = "analysis_launcher" in (r.stdout or "")
    # Fallback: check DB for running analysis
    if not analysis_running:
        try:
            import sqlite3

            conn = sqlite3.connect(str(ROOT / "film_analysis.db"))
            row = conn.execute(
                "SELECT analysis_key, progress_pct FROM analysis_runs WHERE status='running' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            conn.close()
            if row:
                print(f"analysis_launcher: running in DB ({row[0]} @ {row[1]}%)")
            else:
                print("analysis_launcher: not found (may be between games)")
        except Exception:
            print("analysis_launcher: unknown")
    else:
        print("analysis_launcher: running")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--restart-loop", action="store_true")
    ap.add_argument("--stop-loop", action="store_true")
    args = ap.parse_args()

    if args.status:
        return status()

    pids = _load_pids()
    if args.stop_loop:
        pid = pids.get("teach_loop_pid")
        if pid and _pid_alive(pid):
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False)
            print(f"[detached] stopped teach loop {pid}")
        pids["teach_loop_pid"] = None
        _save_pids(pids)
        return 0

    pids = ensure_server(pids)
    pids = ensure_teach_loop(pids, restart=args.restart_loop)
    pids["started_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _save_pids(pids)
    print("[detached] Safe to close Cursor — Marsing/analysis + teach loop keep going.")
    print(f"[detached] Status anytime: py -3.12 scripts/start_hoops_teach_detached.py --status")
    print(f"[detached] Queue status:   py -3.12 scripts/queue_hoops_full_games.py --status")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
