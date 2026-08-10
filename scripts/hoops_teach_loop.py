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


def _retry_locked(op, *, retries: int = 5, label: str = "db"):
    """Retry on transient SQLite 'database is locked' (Flask/GPU writers compete)."""
    last = None
    for attempt in range(retries + 1):
        try:
            return op()
        except sqlite3.OperationalError as exc:
            last = exc
            if "locked" not in str(exc).lower() or attempt >= retries:
                raise
            wait = min(30.0, 2.0 * (attempt + 1))
            print(
                f"[{label}] database is locked; retry {attempt + 1}/{retries} in {wait:.0f}s",
                flush=True,
            )
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
PANEL_SCRIPT = ROOT / "scripts" / "score_full_film_panel.py"
PANEL_LATEST = ROOT / "data" / "hoopsalytics" / "full_film_panel_latest.json"
# Full-film panel cadence: every teach for Hoops; every N teaches for HUDL (default 2)
PANEL_EVERY_HOOPS = int(os.environ.get("LIBERTY_PANEL_EVERY_HOOPS", "1"))
PANEL_EVERY_HUDL = int(os.environ.get("LIBERTY_PANEL_EVERY_HUDL", "2"))
# No progress_step/pct change for this long while a worker is alive → hung (kill + re-queue)
HUNG_STALE_SEC = int(os.environ.get("LIBERTY_HUNG_STALE_SEC", str(45 * 60)))

# Fixed full-film panel bases (Scott gates). Prefer these over HUDL when queueing.
PANEL_BASE_KEYS = {
    "hoopsalytics_idaho_city_2026-01-05",
    "hoopsalytics_harper_or_2025-12-05",
    "hoopsalytics_burns_or_2025-12-06",
    "hoopsalytics_nyssa_2025-12-04",
    "hoopsalytics_melba_2025-12-09",
    "hoopsalytics_camas_county_2025-12-13",
}


def _base_analysis_key(gid: str) -> str:
    return str(gid or "").split("__rerun_", 1)[0]


def panel_queue_rank(gid: str, *, fail_scores: dict[str, float] | None = None) -> tuple:
    """Lower sort key = teach/analyze sooner. Panel failures beat HUDL FIFO."""
    base = _base_analysis_key(gid)
    is_panel = 0 if base in PANEL_BASE_KEYS else 1
    # Worse recall (or missing) → earlier among panel games
    score = 1.0
    if fail_scores is not None and base in fail_scores:
        score = float(fail_scores[base])
    elif is_panel == 0:
        score = -1.0  # unknown panel → ahead of HUDL, behind scored failures
    return (is_panel, score if is_panel == 0 else 0.0)


def load_panel_fail_scores(path: Path = PANEL_LATEST) -> dict[str, float]:
    """Map panel base analysis_key → recall (lower = worse). Empty if unavailable."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}
    out: dict[str, float] = {}
    for g in data.get("games") or []:
        if not isinstance(g, dict):
            continue
        key = _base_analysis_key(str(g.get("analysis_key") or ""))
        if not key:
            continue
        rec = g.get("recall")
        try:
            out[key] = float(rec) if rec is not None else -1.0
        except (TypeError, ValueError):
            out[key] = -1.0
    return out


def games_panel_first(games: list[tuple], *, fail_scores: dict[str, float] | None = None) -> list[tuple]:
    """Stable panel-priority order: worst panel recall first, then non-panel by video id."""
    indexed = list(enumerate(games))

    def _key(item: tuple[int, tuple]) -> tuple:
        idx, row = item
        gid = row[2] if len(row) > 2 else ""
        rank = panel_queue_rank(gid, fail_scores=fail_scores)
        return (*rank, idx)

    return [row for _, row in sorted(indexed, key=_key)]


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


def det_coverage_ok(conn: sqlite3.Connection, analysis_key: str, *, min_ms: int = 50_000) -> bool:
    """Fast keep/fail gate for reclaim — avoids full-table MAX under write load."""
    row = conn.execute(
        """SELECT 1 FROM detections
           WHERE game_id=? AND timestamp_ms >= ? LIMIT 1""",
        (analysis_key, min_ms),
    ).fetchone()
    return row is not None


def det_max_ms_for_base(conn: sqlite3.Connection, gid: str) -> int:
    """Best coverage across primary + any __rerun_* keys for this game."""
    row = conn.execute(
        """SELECT COALESCE(MAX(timestamp_ms),0) FROM detections
           WHERE game_id = ? OR game_id LIKE ?""",
        (gid, f"{gid}__rerun_%"),
    ).fetchone()
    return int(row[0] or 0)


def _extract_analysis_key_from_cmdline(cmdline: str) -> str | None:
    """Parse analysis_key from analysis_launcher / ai_analyzer argv (last token)."""
    if not cmdline:
        return None
    low = cmdline.lower()
    marker = None
    for name in ("analysis_launcher.py", "ai_analyzer.py"):
        if name in low:
            marker = name
            break
    if not marker:
        return None
    idx = low.index(marker)
    rest = cmdline[idx + len(marker) :].strip()
    if not rest:
        return None
    # Windows paths may contain spaces; launcher argv is: db video game_id
    parts = rest.split()
    if not parts:
        return None
    return parts[-1].strip() or None


def list_live_analysis_workers() -> dict:
    """Probe live analysis_launcher / ai_analyzer processes and their keys.

    Returns:
      {
        "ok": bool,
        "any_worker": bool,
        "keys": set[str],          # parsed analysis_keys
        "pid_by_key": dict[str, int],
        "unkeyed_workers": int,    # workers present but key unparseable
        "unkeyed_pids": list[int],
      }
    """
    empty = {
        "ok": False,
        "any_worker": False,
        "keys": set(),
        "pid_by_key": {},
        "unkeyed_workers": 0,
        "unkeyed_pids": [],
    }
    try:
        # tasklist CSV has no CommandLine; use CIM so we can see script names + PID.
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" "
                "| ForEach-Object { '{0}|{1}' -f $_.ProcessId, $_.CommandLine }",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
            creationflags=CREATE_NO_WINDOW,
        )
        lines = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
        keys: set[str] = set()
        pid_by_key: dict[str, int] = {}
        unkeyed_pids: list[int] = []
        unkeyed = 0
        any_worker = False
        for line in lines:
            pid = None
            cmdline = line
            if "|" in line:
                left, right = line.split("|", 1)
                try:
                    pid = int(left.strip())
                except ValueError:
                    pid = None
                cmdline = right.strip()
            low = cmdline.lower()
            if "analysis_launcher" not in low and "ai_analyzer" not in low:
                continue
            # Ignore this teach loop itself if somehow matched
            if "hoops_teach_loop" in low:
                continue
            any_worker = True
            key = _extract_analysis_key_from_cmdline(cmdline)
            if key:
                keys.add(key)
                if pid is not None:
                    pid_by_key[key] = pid
            else:
                unkeyed += 1
                if pid is not None:
                    unkeyed_pids.append(pid)
        return {
            "ok": True,
            "any_worker": any_worker,
            "keys": keys,
            "pid_by_key": pid_by_key,
            "unkeyed_workers": unkeyed,
            "unkeyed_pids": unkeyed_pids,
        }
    except Exception:
        return empty


def analysis_worker_alive() -> bool:
    """True if an analysis_launcher (or ai_analyzer) process is running."""
    info = list_live_analysis_workers()
    return bool(info.get("any_worker"))


def live_analysis_keys() -> set[str]:
    """Analysis keys currently owned by a live launcher/analyzer."""
    return set(list_live_analysis_workers().get("keys") or set())


def wait_progress_fingerprint(pct, step) -> str:
    """Fingerprint for hung detection — frame text in step usually advances when healthy."""
    return f"{pct}|{step or ''}"


def hung_wait_due(
    snap: dict | None,
    *,
    key: str,
    fingerprint: str,
    now: float,
    stale_sec: int = HUNG_STALE_SEC,
) -> bool:
    """True when the same wait fingerprint has been stuck longer than stale_sec."""
    if not snap or not key or stale_sec <= 0:
        return False
    if snap.get("key") != key:
        return False
    if snap.get("fingerprint") != fingerprint:
        return False
    try:
        since = float(snap.get("since") or 0)
    except (TypeError, ValueError):
        return False
    if since <= 0:
        return False
    return (now - since) >= float(stale_sec)


def update_wait_progress_snap(
    snap: dict | None,
    *,
    key: str,
    fingerprint: str,
    now: float,
) -> dict:
    """Refresh or reset the wait-progress snapshot used for hung detection."""
    if (
        snap
        and snap.get("key") == key
        and snap.get("fingerprint") == fingerprint
        and snap.get("since")
    ):
        return {
            "key": key,
            "fingerprint": fingerprint,
            "since": snap["since"],
            "last_seen": now,
        }
    return {"key": key, "fingerprint": fingerprint, "since": now, "last_seen": now}


def kill_analysis_pids(pids: list[int]) -> list[int]:
    """taskkill listed PIDs. Returns PIDs we attempted to kill."""
    killed: list[int] = []
    for pid in pids:
        if not pid:
            continue
        try:
            subprocess.run(
                ["taskkill", "/PID", str(int(pid)), "/F"],
                check=False,
                capture_output=True,
                creationflags=CREATE_NO_WINDOW,
            )
            killed.append(int(pid))
        except Exception as exc:
            print(f"[hung] taskkill pid={pid} failed: {exc}", flush=True)
    return killed


def mark_run_failed_hung(conn: sqlite3.Connection, run_id: int, *, detail: str) -> None:
    conn.execute(
        """UPDATE analysis_runs
           SET status='failed',
               progress_step='Failed',
               error_message=COALESCE(error_message,'') || ?,
               completed_at=CURRENT_TIMESTAMP
           WHERE id=? AND status='running'""",
        (f" | hung: {detail}", run_id),
    )
    conn.commit()


def restart_hung_analysis(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    key: str,
    fingerprint: str,
    stale_sec: int = HUNG_STALE_SEC,
) -> bool:
    """Kill live worker for key (if any) and fail the run so teach can re-queue."""
    workers = list_live_analysis_workers()
    pid_by_key = dict(workers.get("pid_by_key") or {})
    pids = []
    if key and key in pid_by_key:
        pids.append(int(pid_by_key[key]))
    killed = kill_analysis_pids(pids)
    detail = f"no progress for >={stale_sec}s ({fingerprint}); killed={killed or 'none'}"
    mark_run_failed_hung(conn, run_id, detail=detail)
    print(f"[hung] key={key} run_id={run_id} {detail}", flush=True)
    return True


def reclaim_zombie_runs(conn: sqlite3.Connection, *, stale_minutes: int = 20) -> int:
    """Clear 'running' rows that are not backed by a live worker for that key.

    Per-game: a live North Star launcher must NOT block reclaim of other games'
    zombie rows. When worker key cannot be parsed, stay conservative (skip).
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

    workers = list_live_analysis_workers()
    live_keys: set[str] = set(workers.get("keys") or set())
    any_worker = bool(workers.get("any_worker"))
    unkeyed = int(workers.get("unkeyed_workers") or 0)
    # Cannot tell which game the live process owns → do not reclaim while it lives.
    if any_worker and not live_keys and unkeyed > 0:
        print(
            "[zombie] live worker(s) with unparseable key; skipping reclaim (conservative)",
            flush=True,
        )
        return 0

    fixed = 0
    for run_id, key, step, pct, started_at in rows:
        key_s = key or ""
        step_l = (step or "").lower()
        age_row = conn.execute(
            """SELECT (julianday('now') - julianday(COALESCE(?, 'now'))) * 24 * 60""",
            (started_at,),
        ).fetchone()
        age_min = float(age_row[0] or 0)

        # Live worker owns this exact key → leave alone.
        if key_s and key_s in live_keys:
            continue

        # Another game's worker is alive, and this row is not that game → zombie now.
        other_live = bool(live_keys) and (not key_s or key_s not in live_keys)
        no_worker = not any_worker
        stuck_regen = no_worker and ("regenerat" in step_l or "event" in step_l)
        aged_out = no_worker and age_min >= stale_minutes

        if not (other_live or no_worker or stuck_regen or aged_out):
            continue
        # When no worker: still honor stale_minutes unless regenerate-stuck or stale_minutes==0
        if no_worker and not stuck_regen and stale_minutes > 0 and age_min < stale_minutes:
            continue

        # Cheap coverage gate (full MAX() blocks for minutes under concurrent YOLO writes).
        keep = det_coverage_ok(conn, key_s, min_ms=50_000) if key_s else False
        # Mid-film detection zombies must not become "completed" on thin coverage —
        # teach treats completed as done and will never re-queue the rest of the film.
        pct_f = float(pct or 0)
        if keep and "detect" in step_l and "regenerat" not in step_l:
            if pct_f < 95.0 or not det_coverage_ok(conn, key_s, min_ms=1_200_000):
                keep = False
        if keep:
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
        # Commit each row so a slow later key cannot roll back earlier reclaim work.
        conn.commit()
        fixed += 1
        print(
            f"[zombie] id={run_id} key={key_s} live_keys={sorted(live_keys) or '-'} "
            f"age_min={age_min:.0f} keep={keep} -> fixed",
            flush=True,
        )
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


def _panel_due(state: dict, *, is_hudl: bool) -> bool:
    """Return True when the fixed full-film panel should run after this teach."""
    every = PANEL_EVERY_HUDL if is_hudl else PANEL_EVERY_HOOPS
    every = max(1, int(every or 1))
    n = int(state.get("teaches_since_panel") or 0) + 1
    state["teaches_since_panel"] = n
    return n >= every


def run_full_film_panel(state: dict) -> None:
    """Compare-only panel scorecard (minutes, not hours). Never blocks forever."""
    if not PANEL_SCRIPT.exists():
        print(f"PANEL skip — missing {PANEL_SCRIPT}", flush=True)
        return
    print("PANEL running full-film evaluation…", flush=True)
    # Soft timeout via wall clock logging only; script itself is compare-only.
    rc = run([PY, str(PANEL_SCRIPT.relative_to(ROOT))])
    latest = ROOT / "data" / "hoopsalytics" / "full_film_panel_latest.json"
    if latest.exists():
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            ev = data.get("evaluation") or {}
            overall = "PASS" if ev.get("overall_pass") else "FAIL"
            print(
                f"PANEL overall={overall}  "
                f"mean_prec={ev.get('mean_precision')}  mean_rec={ev.get('mean_recall')}  "
                f"script_rc={rc}",
                flush=True,
            )
            for key, gate in (ev.get("gates") or {}).items():
                status = "PASS" if gate.get("pass") else "FAIL"
                print(
                    f"PANEL [{status}] {key}: actual={gate.get('actual')} "
                    f"required={gate.get('required')}",
                    flush=True,
                )
            for g in data.get("games") or []:
                print(
                    f"PANEL game {g.get('name')}: prec={g.get('precision')} "
                    f"rec={g.get('recall')} final_exact={g.get('final_score_exact')} "
                    f"player_exact={g.get('player_points_exact')} "
                    f"status_final={g.get('final_score_status')} "
                    f"status_player={g.get('player_points_status')}",
                    flush=True,
                )
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            print(f"PANEL could not parse latest results: {exc}", flush=True)
    else:
        print(f"PANEL no results file after rc={rc}", flush=True)
    state["teaches_since_panel"] = 0
    state["last_panel_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_state(state)


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
    if _panel_due(state, is_hudl=is_hudl):
        run_full_film_panel(state)
    else:
        save_state(state)
        print(
            f"PANEL deferred (teaches_since_panel={state.get('teaches_since_panel')} "
            f"hudl={is_hudl})",
            flush=True,
        )


def main() -> int:
    state = load_state()
    print("Hoops+HUDL teach loop starting...", flush=True)
    try:
        conn0 = _connect_db()
        try:
            nfix = _retry_locked(
                lambda: recover_interrupted_runs(conn0), retries=5, label="recover"
            )
        finally:
            conn0.close()
        if nfix:
            print(f"[recover] adjusted {nfix} interrupted analysis_runs", flush=True)
    except Exception as exc:
        # Never die at startup — watchdog / next cycle will keep going.
        print(f"[recover] skipped after error: {exc}", flush=True)

    consecutive_errors = 0
    while True:
        try:
            conn = _connect_db()
            # Every cycle: never wait on dead workers
            n_z = reclaim_zombie_runs(conn, stale_minutes=15)
            if n_z:
                print(f"[zombie] reclaimed {n_z} stuck run(s)", flush=True)
            fail_scores = load_panel_fail_scores()
            games = games_panel_first(all_games(conn), fail_scores=fail_scores)
            running = None
            for vid, film, gid, name in games:
                runrow = latest_run(conn, vid, gid)
                if runrow and runrow[1] == "running":
                    running = (name, runrow)
                    break
            if running:
                name, runrow = running
                wait_key = (runrow[4] or "") if len(runrow) > 4 else ""
                live_keys = live_analysis_keys()
                # Waiting on a different game's zombie while another launcher is
                # alive — reclaim others immediately; do not sleep 90s forever.
                if wait_key and live_keys and wait_key not in live_keys:
                    print(
                        f"[wait-skip] {name} key={wait_key} not in live {sorted(live_keys)}; reclaiming",
                        flush=True,
                    )
                    reclaim_zombie_runs(conn, stale_minutes=0)
                    state.pop("wait_progress", None)
                    save_state(state)
                    conn.close()
                    time.sleep(5)
                    consecutive_errors = 0
                    continue
                # If no worker, reclaim again immediately instead of sleeping forever
                if not analysis_worker_alive():
                    reclaim_zombie_runs(conn, stale_minutes=0)
                    state.pop("wait_progress", None)
                    save_state(state)
                    conn.close()
                    time.sleep(5)
                    consecutive_errors = 0
                    continue
                fp = wait_progress_fingerprint(runrow[2], runrow[3])
                now = time.time()
                snap = update_wait_progress_snap(
                    state.get("wait_progress"),
                    key=wait_key or name,
                    fingerprint=fp,
                    now=now,
                )
                state["wait_progress"] = snap
                save_state(state)
                if hung_wait_due(
                    snap,
                    key=wait_key or name,
                    fingerprint=fp,
                    now=now,
                    stale_sec=HUNG_STALE_SEC,
                ):
                    restart_hung_analysis(
                        conn,
                        run_id=int(runrow[0]),
                        key=wait_key,
                        fingerprint=fp,
                        stale_sec=HUNG_STALE_SEC,
                    )
                    state.pop("wait_progress", None)
                    save_state(state)
                    conn.close()
                    consecutive_errors = 0
                    time.sleep(5)
                    continue
                stuck_for = int(now - float(snap.get("since") or now))
                print(
                    f"[wait] {name} {runrow[2]}% - {runrow[3]} "
                    f"(same_progress={stuck_for}s/{HUNG_STALE_SEC}s)",
                    flush=True,
                )
                conn.close()
                consecutive_errors = 0
                time.sleep(90)
                continue

            state.pop("wait_progress", None)

            # Teach any newly completed game not yet in state (panel failures first)
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
                games = games_panel_first(all_games(conn), fail_scores=load_panel_fail_scores())

            # Queue next needed full game — worst panel recall before HUDL FIFO
            nxt = None
            for vid, film, gid, name in games:
                if needs_full(conn, vid, gid):
                    nxt = (vid, film, gid, name)
                    break
            conn.close()
            if not nxt:
                print(
                    "[done] All Hoops + HUDL games analyzed + taught at least once.",
                    flush=True,
                )
                run([PY, "scripts/teach_from_hoops_pbp.py", "--write-model"])
                run([PY, "scripts/teach_from_boxscore.py", "--write-model"])
                break

            vid, film, gid, name = nxt
            label = f"full teach - {name}"
            print(f"[start] {name} video={vid}", flush=True)
            try:
                resp = post_analyze(vid, label)
                print(json.dumps(resp, indent=2), flush=True)
            except Exception as exc:
                print(f"start failed: {exc}", flush=True)
                time.sleep(60)
                consecutive_errors = 0
                continue
            consecutive_errors = 0
            time.sleep(90)
        except sqlite3.OperationalError as exc:
            consecutive_errors += 1
            wait = min(120, 15 * consecutive_errors)
            print(
                f"[loop] SQLite error (survive, retry in {wait}s): {exc}",
                flush=True,
            )
            time.sleep(wait)
        except Exception as exc:
            consecutive_errors += 1
            wait = min(180, 30 * consecutive_errors)
            print(
                f"[loop] unexpected error (survive, retry in {wait}s): {exc}",
                flush=True,
            )
            time.sleep(wait)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
