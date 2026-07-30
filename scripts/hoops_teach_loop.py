#!/usr/bin/env python3
"""After each Hoopsalytics game completes: teach → regenerate → score → queue next.

Run alongside (or instead of) queue_hoops_full_games --loop.
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

# Hide console flashes from PowerShell/tasklist child processes on Windows
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "film_analysis.db"
PY = sys.executable
BASE = "http://127.0.0.1:8080"


def _connect_db() -> sqlite3.Connection:
    """Open film DB with a long busy timeout so Flask/workers do not kill the loop."""
    conn = sqlite3.connect(str(DB), timeout=60.0)
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def _retry_locked(op, *, retries: int = 2, label: str = "db"):
    """Retry once/twice on transient SQLite 'database is locked'."""
    last = None
    for attempt in range(retries + 1):
        try:
            return op()
        except sqlite3.OperationalError as exc:
            last = exc
            if "locked" not in str(exc).lower() or attempt >= retries:
                raise
            wait = 2.0 * (attempt + 1)
            print(f"[{label}] database is locked; retry {attempt + 1}/{retries} in {wait:.0f}s", flush=True)
            time.sleep(wait)
    raise last  # pragma: no cover

GAMES = [
    (17, "hoopsalytics-marsing-2025-12-02", "hoopsalytics_marsing_2025-12-02", "Marsing"),
    (16, "hoopsalytics-nyssa-2025-12-04", "hoopsalytics_nyssa_2025-12-04", "Nyssa"),
    (15, "hoopsalytics-harper_or-2025-12-05", "hoopsalytics_harper_or_2025-12-05", "Harper"),
    (13, "hoopsalytics-burns_or-2025-12-06", "hoopsalytics_burns_or_2025-12-06", "Burns"),
    (12, "hoopsalytics-melba-2025-12-09", "hoopsalytics_melba_2025-12-09", "Melba"),
    (14, "hoopsalytics-camas_county-2025-12-13", "hoopsalytics_camas_county_2025-12-13", "Camas"),
    (20, "hoopsalytics-idaho_city-2026-01-05", "hoopsalytics_idaho_city_2026-01-05", "Idaho City"),
    (18, "hoopsalytics-north_star_charter-2026-01-08", "hoopsalytics_north_star_charter_2026-01-08", "North Star"),
    (19, "hoopsalytics-grace-2026-01-10", "hoopsalytics_grace_2026-01-10", "Grace"),
]


def _load_hudl_games(conn: sqlite3.Connection) -> list[tuple]:
    """Append imported HUDL videos after Hoopsalytics set."""
    rows = conn.execute(
        """SELECT id, game_id, opponent FROM videos
           WHERE game_id LIKE 'hudl_%'
           ORDER BY id"""
    ).fetchall()
    out = []
    for vid, gid, opp in rows:
        film = f"hudl-{gid[5:]}" if gid.startswith("hudl_") else f"hudl-{gid}"
        # Prefer Film Tool client id if present
        ft = conn.execute(
            "SELECT client_game_id FROM film_tool_games WHERE analysis_key=? LIMIT 1",
            (gid,),
        ).fetchone()
        film_id = ft[0] if ft else film
        name = f"HUDL {opp or gid}"
        out.append((int(vid), film_id, gid, name))
    return out


def all_games(conn: sqlite3.Connection) -> list[tuple]:
    return list(GAMES) + _load_hudl_games(conn)

TAUGHT = set()
STATE_PATH = ROOT / "data" / "hoopsalytics" / "teach_loop_state.json"


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"taught_keys": [], "scores": []}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def run(cmd: list[str]) -> int:
    print("+", " ".join(cmd), flush=True)
    kwargs = {"cwd": str(ROOT)}
    if CREATE_NO_WINDOW:
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.call(cmd, **kwargs)


def post_analyze(video_id: int, label: str) -> dict:
    data = json.dumps({"run_label": label}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/videos/{video_id}/analyze",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def latest_run(conn: sqlite3.Connection, video_id: int, gid: str):
    return conn.execute(
        """SELECT id, status, progress_pct, progress_step, analysis_key, error_message
           FROM analysis_runs
           WHERE source_video_id=? OR analysis_key=? OR base_game_id=?
           ORDER BY id DESC LIMIT 1""",
        (video_id, gid, gid),
    ).fetchone()


def det_max_ms(conn: sqlite3.Connection, analysis_key: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(timestamp_ms),0) FROM detections WHERE game_id=?",
        (analysis_key,),
    ).fetchone()
    return int(row[0] or 0)


def det_max_ms_for_base(conn: sqlite3.Connection, gid: str) -> int:
    """Best coverage across primary + any __rerun_* keys for this game."""
    row = conn.execute(
        """SELECT COALESCE(MAX(timestamp_ms),0) FROM detections
           WHERE game_id = ? OR game_id LIKE ?""",
        (gid, f"{gid}__rerun_%"),
    ).fetchone()
    return int(row[0] or 0)


def analysis_worker_alive() -> bool:
    """True if an analysis_launcher (or ai_analyzer) process is running."""
    try:
        # tasklist CSV has no CommandLine; use CIM so we can see script names.
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" "
                "| Select-Object -ExpandProperty CommandLine",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
            creationflags=CREATE_NO_WINDOW,
        )
        out = (r.stdout or "").lower()
        return "analysis_launcher" in out or "ai_analyzer" in out
    except Exception:
        return False


def reclaim_zombie_runs(conn: sqlite3.Connection, *, stale_minutes: int = 20) -> int:
    """Clear 'running' rows when no worker is alive (or run is ancient).

    Prevents the teach loop from waiting forever after reboot / crashed workers.
    """
    def _once() -> int:
        return _reclaim_zombie_runs_once(conn, stale_minutes=stale_minutes)

    return _retry_locked(_once, retries=2, label="zombie")


def _reclaim_zombie_runs_once(conn: sqlite3.Connection, *, stale_minutes: int = 20) -> int:
    rows = conn.execute(
        """SELECT id, analysis_key, progress_step, progress_pct, started_at
           FROM analysis_runs WHERE status='running'"""
    ).fetchall()
    if not rows:
        return 0

    worker = analysis_worker_alive()
    fixed = 0
    for run_id, key, step, pct, started_at in rows:
        mx = det_max_ms(conn, key or "")
        step_l = (step or "").lower()
        age_row = conn.execute(
            """SELECT (julianday('now') - julianday(COALESCE(?, 'now'))) * 24 * 60""",
            (started_at,),
        ).fetchone()
        age_min = float(age_row[0] or 0)

        is_zombie = (not worker) or (age_min >= stale_minutes and not worker)
        # Also treat long-stuck regenerate with no worker as zombie immediately
        if (not worker) and ("regenerat" in step_l or "event" in step_l):
            is_zombie = True
        if worker and age_min < stale_minutes:
            continue
        if not is_zombie and worker:
            continue

        if mx >= 50_000:
            conn.execute(
                """UPDATE analysis_runs
                   SET status='completed',
                       progress_pct=100,
                       progress_step='Reclaimed zombie run (detections kept)',
                       completed_at=CURRENT_TIMESTAMP,
                       error_message=NULL
                   WHERE id=?""",
                (run_id,),
            )
        else:
            conn.execute(
                """UPDATE analysis_runs
                   SET status='failed',
                       progress_step='Failed',
                       error_message=COALESCE(error_message,'') || ' | zombie: no analysis worker',
                       completed_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (run_id,),
            )
        fixed += 1
        print(
            f"[zombie] id={run_id} key={key} worker={worker} age_min={age_min:.0f} mx={mx} -> fixed",
            flush=True,
        )
    if fixed:
        conn.commit()
    return fixed


def recover_interrupted_runs(conn: sqlite3.Connection) -> int:
    """After reboot / stuck wait: reclaim zombies, then finish interrupted regenerates."""
    fixed = reclaim_zombie_runs(conn, stale_minutes=15)
    rows = conn.execute(
        "SELECT id, analysis_key, progress_step FROM analysis_runs WHERE status='running'"
    ).fetchall()
    for run_id, key, step in rows:
        # If somehow still running with a live worker, leave alone
        if analysis_worker_alive():
            break
        mx = det_max_ms(conn, key or "")
        step_l = (step or "").lower()
        if mx >= 50_000 and (
            "regenerat" in step_l or "event" in step_l or mx >= 1_200_000
        ):
            conn.execute(
                """UPDATE analysis_runs
                   SET status='completed',
                       progress_pct=100,
                       progress_step='Recovered after interrupt (detections kept)',
                       completed_at=CURRENT_TIMESTAMP,
                       error_message=NULL
                   WHERE id=?""",
                (run_id,),
            )
            fixed += 1
        else:
            conn.execute(
                """UPDATE analysis_runs
                   SET status='failed',
                       error_message=COALESCE(error_message,'') || ' | interrupted (insufficient detections to keep)',
                       completed_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (run_id,),
            )
            fixed += 1
    if fixed:
        conn.commit()
    return fixed


def needs_full(conn: sqlite3.Connection, video_id: int, gid: str) -> bool:
    """True only when we lack usable film coverage — do NOT re-queue after reboot thrash."""
    mx = det_max_ms_for_base(conn, gid)
    # Grace: need ~25+ minutes (full game), not Q1-only
    if gid.endswith("grace_2026-01-10"):
        return mx < 1_500_000
    # Idaho City was thin (~9 min) — keep requesting full coverage
    if "idaho_city" in gid and mx < 1_200_000:
        return True
    # ~20 minutes of detections = keep; skip re-analyze
    if mx >= 1_200_000:
        return False
    run = latest_run(conn, video_id, gid)
    if not run:
        return True
    if run[1] == "running":
        return False
    # Thin/partial coverage may need another pass
    if mx < 50_000:
        return True
    # Partial but present — don't auto-burn another full GPU night unless never completed
    if run[1] == "completed":
        return False
    return mx < 1_200_000


def teach_and_score(analysis_key: str, film_id: str, name: str, state: dict) -> None:
    print(f"\n=== TEACH after {name} ({analysis_key}) ===", flush=True)
    is_hudl = str(analysis_key).startswith("hudl_")
    if is_hudl:
        run([PY, "scripts/teach_from_boxscore.py", "--write-model"])
    else:
        run([PY, "scripts/teach_from_hoops_pbp.py", "--write-model"])
    # Regenerate every game that has detections so new keep_clf / caps apply.
    conn = _connect_db()
    keys = [
        r[0]
        for r in conn.execute(
            """SELECT DISTINCT game_id FROM detections
               WHERE game_id LIKE 'hoopsalytics%' OR game_id LIKE 'hudl_%'"""
        )
    ]
    conn.close()
    for key in keys:
        run([PY, "scripts/regenerate_events.py", key])

    score: dict = {"mode": "hudl_boxscore" if is_hudl else "hoops_pbp"}
    if not is_hudl:
        run(
            [
                PY,
                "scripts/compare_ai_to_hoops_pbp.py",
                "--film-id",
                film_id,
                "--analysis-key",
                analysis_key,
            ]
        )
        score_path = ROOT / "data" / "hoopsalytics" / f"compare_{film_id.replace('-', '_')}.json"
        if score_path.exists():
            score = {**score, **json.loads(score_path.read_text(encoding="utf-8"))}
    else:
        # Team-total compare via boxscore model vs AI event counts
        run([PY, "scripts/teach_from_boxscore.py", "--write-model", "--compare-ai"])
        report = ROOT / "data" / "hoopsalytics" / "boxscore_teach_report.json"
        if report.exists():
            data = json.loads(report.read_text(encoding="utf-8"))
            games = data.get("games") or data.get("by_game") or {}
            if isinstance(games, dict) and analysis_key in games:
                score = {**score, **games[analysis_key]}

    state["taught_keys"] = sorted(set(state.get("taught_keys") or []) | {analysis_key})
    state.setdefault("scores", []).append({"name": name, "key": analysis_key, **score})
    save_state(state)
    print(
        f"SCORE {name}: prec={score.get('precision')} rec={score.get('recall')} "
        f"exact={score.get('exact')} extra={score.get('extra')} miss={score.get('miss')} "
        f"mode={score.get('mode')}",
        flush=True,
    )


def main() -> int:
    state = load_state()
    print("Hoops+HUDL teach loop starting…", flush=True)
    conn0 = _connect_db()
    try:
        nfix = _retry_locked(lambda: recover_interrupted_runs(conn0), retries=2, label="recover")
    finally:
        conn0.close()
    if nfix:
        print(f"[recover] adjusted {nfix} interrupted analysis_runs", flush=True)
    while True:
        conn = _connect_db()
        # Every cycle: never wait on dead workers
        n_z = reclaim_zombie_runs(conn, stale_minutes=15)
        if n_z:
            print(f"[zombie] reclaimed {n_z} stuck run(s)", flush=True)
        games = all_games(conn)
        running = None
        for vid, film, gid, name in games:
            runrow = latest_run(conn, vid, gid)
            if runrow and runrow[1] == "running":
                running = (name, runrow)
                break
        if running:
            name, runrow = running
            # If no worker, reclaim again immediately instead of sleeping forever
            if not analysis_worker_alive():
                reclaim_zombie_runs(conn, stale_minutes=0)
                conn.close()
                time.sleep(5)
                continue
            print(
                f"[wait] {name} {runrow[2]}% — {runrow[3]}",
                flush=True,
            )
            conn.close()
            time.sleep(90)
            continue

        # Teach any newly completed game not yet in state
        for vid, film, gid, name in games:
            runrow = latest_run(conn, vid, gid)
            if not runrow or runrow[1] != "completed":
                continue
            key = runrow[4] or gid
            if det_max_ms(conn, key) < 50_000:
                continue
            if key in (state.get("taught_keys") or []):
                continue
            conn.close()
            teach_and_score(key, film, name, state)
            conn = _connect_db()
            games = all_games(conn)

        # Queue next needed full game
        nxt = None
        for vid, film, gid, name in games:
            if needs_full(conn, vid, gid):
                nxt = (vid, film, gid, name)
                break
        conn.close()
        if not nxt:
            print("[done] All Hoops + HUDL games analyzed + taught at least once.", flush=True)
            run([PY, "scripts/teach_from_hoops_pbp.py", "--write-model"])
            run([PY, "scripts/teach_from_boxscore.py", "--write-model"])
            break

        vid, film, gid, name = nxt
        label = f"full teach — {name}"
        print(f"[start] {name} video={vid}", flush=True)
        try:
            resp = post_analyze(vid, label)
            print(json.dumps(resp, indent=2), flush=True)
        except Exception as exc:
            print(f"start failed: {exc}", flush=True)
            time.sleep(60)
            continue
        time.sleep(90)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
