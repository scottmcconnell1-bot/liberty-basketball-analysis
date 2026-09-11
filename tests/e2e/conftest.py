"""End-to-end fixtures.

Two targets, same tests:

* default        - Flask test client against a temporary DB + upload dir (CI-safe, ~1 min)
* live server    - set LIBERTY_E2E_BASE_URL=http://127.0.0.1:8090 (+ LIBERTY_E2E_DB=<its db>,
                   LIBERTY_E2E_UPLOADS=<its uploads>); see scripts/run_e2e_live.sh

Analysis:
* default        - the app's "spawn analysis" call is stubbed; the test seeds synthetic
                   detections + AI drafts so every downstream feature has data
* LIBERTY_E2E_REAL_ANALYSIS=1 (default target) - the stub runs ai_analyzer in-process on
                   the uploaded clip (needs the CV stack; ~40 s for the 12 s real clip)
* live server    - the server spawns the real worker; the test polls until it completes
"""
from __future__ import annotations

import io
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.e2e import data as td  # noqa: E402

LIVE_URL = os.environ.get("LIBERTY_E2E_BASE_URL", "").rstrip("/")
REAL_ANALYSIS = os.environ.get("LIBERTY_E2E_REAL_ANALYSIS") == "1"


PENDING_REAL: list[tuple[str, str]] = []  # (game_id, video_path) recorded by the spawn stub


class _Resp:
    def __init__(self, r):
        self.status_code = r.status_code
        self.data = r.content
        self.headers = r.headers
        self._r = r

    def get_json(self, silent=True):
        try:
            return self._r.json()
        except ValueError:
            return None


class LiveClient:
    """requests-backed twin of the Flask test client for the subset of calls the suite uses."""

    def __init__(self, base_url: str):
        import requests

        self.base = base_url
        self.s = requests.Session()

    def _call(self, method, path, data=None, json=None, content_type=None, headers=None, follow_redirects=True, **kw):
        files = None
        form = None
        if content_type == "multipart/form-data" and isinstance(data, dict):
            files, form = {}, {}
            for k, v in data.items():
                if isinstance(v, tuple):
                    fh, name = v[0], v[1]
                    files[k] = (name, fh.read() if hasattr(fh, "read") else fh)
                else:
                    form[k] = v
        elif isinstance(data, (str, bytes)) and content_type == "application/json":
            json = __import__("json").loads(data)
        else:
            form = data
        r = self.s.request(method, self.base + path, data=form, files=files, json=json,
                           headers=headers, allow_redirects=follow_redirects, timeout=600)
        return _Resp(r)

    def get(self, path, **kw): return self._call("GET", path, **kw)
    def post(self, path, **kw): return self._call("POST", path, **kw)
    def put(self, path, **kw): return self._call("PUT", path, **kw)
    def delete(self, path, **kw): return self._call("DELETE", path, **kw)


class E2E:
    def __init__(self, client, db_path: str, uploads: str, live: bool, app=None, mp=None):
        self.client = client
        self.db_path = db_path
        self.uploads = uploads
        self.live = live
        self.app = app
        self._mp = mp
        self.state: dict = {}
        self.hits: list[tuple[str, str]] = []
        self.real_analysis = REAL_ANALYSIS or live
        self.workdir = Path(tempfile.mkdtemp(prefix="liberty-e2e-"))

    # thin wrappers that record coverage
    def get(self, path, **kw):
        self.hits.append(("GET", path)); return self.client.get(path, **kw)

    def post(self, path, **kw):
        self.hits.append(("POST", path)); return self.client.post(path, **kw)

    def put(self, path, **kw):
        self.hits.append(("PUT", path)); return self.client.put(path, **kw)

    def delete(self, path, **kw):
        self.hits.append(("DELETE", path)); return self.client.delete(path, **kw)

    def json(self, path, **kw):
        r = self.get(path, **kw)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.data[:200]!r}"
        return r.get_json()

    def db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def upload_file(self, name: str, content: bytes, filename: str, extra: dict | None = None):
        d = {name: (io.BytesIO(content), filename)}
        d.update(extra or {})
        return d

    # analysis strategy
    def ensure_analysis(self, game_id: str) -> dict:
        """Guarantee detections/events exist for game_id and the run is completed."""
        if self.live:
            deadline = time.time() + 25 * 60
            while time.time() < deadline:
                p = self.json(f"/api/analysis_progress/{game_id}")
                if p.get("status") in ("completed", "failed"):
                    assert p["status"] == "completed", p.get("error_message")
                    return p
                time.sleep(5)
            raise AssertionError("analysis did not finish in 25 min")
        if self.real_analysis:
            pytest.importorskip("cv2"); pytest.importorskip("ultralytics")
            from ai_analyzer import run_ai_analysis

            for gid, video_path in [x for x in PENDING_REAL if x[0] == game_id]:
                run_ai_analysis(self.db_path, video_path, gid)  # synchronous, outside any request
                PENDING_REAL.remove((gid, video_path))
        conn = self.db()
        n_det = conn.execute("SELECT COUNT(*) FROM detections WHERE game_id=?", (game_id,)).fetchone()[0]
        if n_det == 0:  # stubbed run: seed synthetic data
            td.insert_detections(conn, game_id, td.synthetic_detections(game_id))
            td.insert_ai_events(conn, game_id, td.ai_events(game_id))
        td.mark_run_completed(conn, game_id, 0, 0)
        conn.close()
        return self.json(f"/api/analysis_progress/{game_id}")


@pytest.fixture(scope="module")
def e2e():
    if LIVE_URL:
        db_path = os.environ.get("LIBERTY_E2E_DB")
        uploads = os.environ.get("LIBERTY_E2E_UPLOADS", "")
        assert db_path, "LIBERTY_E2E_DB must point at the live server's SQLite file"
        yield E2E(LiveClient(LIVE_URL), db_path, uploads, live=True)
        return

    import app as app_module
    from stat_book import paths as sb_paths

    mp = pytest.MonkeyPatch()
    db_fd, db_path = tempfile.mkstemp(suffix="-e2e.db"); os.close(db_fd)
    uploads = tempfile.mkdtemp(prefix="liberty-e2e-uploads-")
    confirmed = Path(tempfile.mkdtemp(prefix="liberty-e2e-confirmed-"))
    app_module.app.config.update({"TESTING": True, "DATABASE": db_path, "UPLOAD_FOLDER": uploads,
                                  "COACH_PASSWORD": "e2e-coach-pass"})
    os.makedirs(os.path.join(uploads, "team_photos"), exist_ok=True)
    mp.setattr(sb_paths, "CONFIRMED_ROOT", confirmed)
    mp.setenv("LIBERTY_COACH_PASSWORD", "e2e-coach-pass")  # blueprints/coach.py reads the env at request time
    with app_module.app.app_context():
        app_module.init_db()

    import blueprints.ai as ai_mod

    def fake_start(game_id, video_path):
        # Never run the detector inside the request: the route has not committed its
        # analysis_runs write yet and an in-process run would collide on the DB. Record the
        # job; ensure_analysis() runs it after the response (REAL_ANALYSIS) or seeds
        # synthetic data instead.
        PENDING_REAL.append((game_id, video_path))

    mp.setattr(ai_mod, "start_analysis_subprocess", fake_start)
    e = E2E(app_module.app.test_client(), db_path, uploads, live=False, app=app_module.app, mp=mp)
    yield e
    mp.undo()
    import shutil

    os.unlink(db_path)
    for d in (uploads, confirmed, e.workdir):  # media, confirmed books, generated clips
        shutil.rmtree(d, ignore_errors=True)
    PENDING_REAL.clear()


def ok(resp, *codes):
    codes = codes or (200,)
    assert resp.status_code in codes, f"{resp.status_code} not in {codes}: {resp.data[:300]!r}"
    return resp
