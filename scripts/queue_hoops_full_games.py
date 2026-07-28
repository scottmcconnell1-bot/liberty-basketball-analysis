#!/usr/bin/env python3
"""Queue full-game Hoopsalytics AI analyses one at a time (accuracy teaching).

Starts the next game that has no completed analysis yet. Designed to be
called repeatedly (or left looping) while the teach/compare cycle runs.

Usage:
  py -3.12 scripts/queue_hoops_full_games.py           # start next pending
  py -3.12 scripts/queue_hoops_full_games.py --status
  py -3.12 scripts/queue_hoops_full_games.py --loop     # wait + chain until all done
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "film_analysis.db"
BASE = "http://127.0.0.1:8080"

# Games with no analysis first (build multi-game keep_clf), Grace full last.
GAMES = [
    (17, "hoopsalytics_marsing_2025-12-02", "Marsing"),
    (16, "hoopsalytics_nyssa_2025-12-04", "Nyssa"),
    (15, "hoopsalytics_harper_or_2025-12-05", "Harper"),
    (13, "hoopsalytics_burns_or_2025-12-06", "Burns"),
    (12, "hoopsalytics_melba_2025-12-09", "Melba"),
    (14, "hoopsalytics_camas_county_2025-12-13", "Camas County"),
    (20, "hoopsalytics_idaho_city_2026-01-05", "Idaho City"),
    (18, "hoopsalytics_north_star_charter_2026-01-08", "North Star"),
    (19, "hoopsalytics_grace_2026-01-10", "Grace"),
]


def _get(url: str):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_status(conn: sqlite3.Connection) -> list[dict]:
    out = []
    for vid, gid, name in GAMES:
        det = conn.execute(
            "SELECT COUNT(1), COALESCE(MAX(timestamp_ms),0) FROM detections WHERE game_id=?",
            (gid,),
        ).fetchone()
        ev = conn.execute(
            "SELECT COUNT(1) FROM events WHERE game_id=? AND COALESCE(source_type,'ai')='ai'",
            (gid,),
        ).fetchone()[0]
        run = conn.execute(
            """SELECT id, status, progress_pct, progress_step, run_kind, analysis_key, started_at, completed_at, error_message
               FROM analysis_runs
               WHERE source_video_id=? OR analysis_key=? OR base_game_id=?
               ORDER BY id DESC LIMIT 1""",
            (vid, gid, gid),
        ).fetchone()
        out.append(
            {
                "video_id": vid,
                "name": name,
                "game_id": gid,
                "detections": det[0] if det else 0,
                "max_ms": det[1] if det else 0,
                "events": ev,
                "run": None
                if not run
                else {
                    "id": run[0],
                    "status": run[1],
                    "pct": run[2],
                    "step": run[3],
                    "kind": run[4],
                    "key": run[5],
                    "started": run[6],
                    "completed": run[7],
                    "error": run[8],
                },
            }
        )
    return out


def anything_running(rows: list[dict]) -> dict | None:
    for row in rows:
        run = row.get("run") or {}
        if run.get("status") == "running":
            return row
    return None


def next_to_queue(rows: list[dict]) -> dict | None:
    """Queue games that have never completed a full-ish detection pass."""
    for row in rows:
        run = row.get("run") or {}
        status = run.get("status")
        if status == "running":
            return None
        # Need a completed run with substantial detections ( > 30 min of film ).
        if status == "completed" and int(row.get("detections") or 0) > 50000:
            continue
        if status == "failed":
            return row
        if not run:
            return row
        # Grace Q1-only (~241k dets at 980s) — still queue a full rerun.
        if row["game_id"].endswith("grace_2026-01-10") and int(row.get("max_ms") or 0) < 1_500_000:
            return row
        if status == "completed":
            continue
        return row
    return None


def start_analyze(video_id: int, label: str) -> dict:
    # Full game — no end_ms window.
    return _post(
        f"{BASE}/api/videos/{video_id}/analyze",
        {"run_label": label},
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--loop", action="store_true", help="Chain games until all complete")
    ap.add_argument("--poll-sec", type=int, default=120)
    args = ap.parse_args()

    conn = sqlite3.connect(str(DB_PATH))
    rows = run_status(conn)
    if args.status or not args.loop:
        for row in rows:
            run = row.get("run") or {}
            print(
                f"{row['name']:16} vid={row['video_id']} dets={row['detections']:7} "
                f"max_ms={int(row['max_ms'])} ev={row['events']:5} "
                f"status={run.get('status') or 'none'} pct={run.get('pct')} "
                f"{(run.get('step') or '')[:50]}"
            )
        if args.status and not args.loop:
            conn.close()
            return 0

    def tick():
        nonlocal rows
        conn2 = sqlite3.connect(str(DB_PATH))
        rows = run_status(conn2)
        conn2.close()
        running = anything_running(rows)
        if running:
            run = running["run"]
            print(
                f"[wait] {running['name']} running {run.get('pct')}% — {run.get('step')}",
                flush=True,
            )
            return "waiting"
        nxt = next_to_queue(rows)
        if not nxt:
            print("[done] All Hoopsalytics games have substantial completed analyses.", flush=True)
            return "done"
        label = f"hoops full teach — {nxt['name']}"
        print(f"[start] {nxt['name']} video_id={nxt['video_id']} ({label})", flush=True)
        try:
            resp = start_analyze(nxt["video_id"], label)
            print(json.dumps(resp, indent=2), flush=True)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(f"HTTP {exc.code}: {body}", flush=True)
            return "error"
        except Exception as exc:
            print(f"start failed: {exc}", flush=True)
            return "error"
        return "started"

    if not args.loop:
        result = tick()
        conn.close()
        return 0 if result in {"started", "waiting", "done"} else 1

    while True:
        result = tick()
        if result == "done":
            break
        if result == "error":
            time.sleep(30)
            continue
        time.sleep(max(15, args.poll_sec))

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
