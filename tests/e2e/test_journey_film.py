"""Film journeys: upload -> analysis runs -> event generation -> results -> clips/trim, plus NFHS.

Every test drives the real HTTP routes with the Flask test client and asserts exact DB rows,
statuses and JSON fields. The analysis worker is never spawned: `start_analysis_subprocess`
is recorded, and the worker's own DB writes are replayed in-process (analysis_launcher's
`_mark_running`, the ai_analyzer progress/completion UPDATEs, and the real
`event_generator.main` over synthetic detections).

Tests marked ``xfail(strict=True, reason="BUG: ...")`` assert the *correct* behaviour and
currently fail because of a real defect in the app.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime as _real_datetime
from pathlib import Path
from urllib.parse import quote

import pytest

from tests.e2e import data as td

pytestmark = pytest.mark.e2e

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None
needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not installed")

VIDEO_BYTES = bytes(range(256)) * 64  # 16 KiB of deterministic "film"
XHR = {"X-Requested-With": "XMLHttpRequest"}


# ── fixtures / helpers ──────────────────────────────────────────────────────


class Env:
    def __init__(self, app, client, tmp_path):
        self.app = app
        self.client = client
        self.tmp = tmp_path
        self.db_path = app.config["DATABASE"]
        self.uploads = Path(app.config["UPLOAD_FOLDER"])
        self.spawned: list[tuple[str, str]] = []

    def conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def q(self, sql, params=()):
        c = self.conn()
        try:
            return [dict(r) for r in c.execute(sql, params).fetchall()]
        finally:
            c.close()

    def one(self, sql, params=()):
        rows = self.q(sql, params)
        assert len(rows) == 1, f"expected one row for {sql!r} {params}: {rows}"
        return rows[0]

    def execute(self, sql, params=()):
        c = self.conn()
        try:
            c.execute(sql, params)
            c.commit()
        finally:
            c.close()

    def setting(self, key, value):
        self.execute("INSERT OR REPLACE INTO app_settings(key, value) VALUES (?, ?)", (key, str(value)))

    def json(self, path, status=200):
        r = self.client.get(path)
        assert r.status_code == status, f"GET {path} -> {r.status_code}: {r.data[:300]!r}"
        return r.get_json()

    def post_json(self, path, payload=None):
        return self.client.post(path, data=json.dumps(payload or {}), content_type="application/json")

    # uploads
    def upload(self, filename="clip.mp4", opponent="Eagle Ridge", content=VIDEO_BYTES):
        r = self.client.post(
            "/upload",
            data={"video": (io.BytesIO(content), filename), "opponent": opponent},
            content_type="multipart/form-data",
            headers=XHR,
        )
        assert r.status_code == 200, r.data[:300]
        payload = r.get_json()
        video = self.one("SELECT * FROM videos WHERE stored_filename=?", (payload["stored_filename"],))
        return payload, video

    def chunked_upload(self, blob, filename, *, opponent="Chunk Opp", n=3, order=None, mode="analyze", upload_id="u1"):
        size = -(-len(blob) // n)
        chunks = [blob[i * size:(i + 1) * size] for i in range(n)]
        responses = []
        for i in order or range(n):
            r = self.client.post(
                "/api/upload_chunk",
                data={
                    "file": (io.BytesIO(chunks[i]), "blob"),
                    "upload_id": upload_id,
                    "chunk_index": str(i),
                    "total_chunks": str(n),
                    "filename": filename,
                    "opponent": opponent,
                    "upload_mode": mode,
                },
                content_type="multipart/form-data",
            )
            assert r.status_code == 200, r.data[:300]
            responses.append(r.get_json())
        return responses

    # simulated worker (mirrors analysis_launcher.py / ai_analyzer.py DB writes)
    def worker_start(self, key):
        import analysis_launcher

        analysis_launcher._mark_running(self.db_path, key)

    def worker_progress(self, key, current, total):
        self.execute(
            "UPDATE analysis_runs SET progress_pct=?, progress_step=? WHERE analysis_key=? AND status='running'",
            (int(current / total * 100), f"Detecting objects: frame {current}/{total}", key),
        )

    def worker_finish(self, key, *, frames=300, relational_game_id=None, seed=7):
        import event_generator

        rows = td.synthetic_detections(key, frames=frames, seed=seed)
        c = self.conn()
        c.executemany(
            """INSERT INTO detections (game_id, relational_game_id, frame_number, timestamp_ms, object_class,
                                       confidence, x_center, y_center, width, height, tracker_id)
               VALUES (:game_id, :rel, :frame_number, :timestamp_ms, :object_class, :confidence,
                       :x_center, :y_center, :width, :height, :tracker_id)""",
            [{**r, "game_id": key, "rel": relational_game_id} for r in rows],
        )
        c.commit()
        c.close()
        assert event_generator.main(key, self.db_path, relational_game_id=relational_game_id) is True
        self.execute(
            """UPDATE analysis_runs SET status='completed', progress_pct=100, progress_step='Done',
               completed_at=CURRENT_TIMESTAMP WHERE analysis_key=? AND status='running'""",
            (key,),
        )
        return len(rows)

    def run_worker(self, key, **kw):
        self.worker_start(key)
        return self.worker_finish(key, **kw)


@pytest.fixture
def env(app, client, tmp_path, monkeypatch):
    import blueprints.ai as ai_mod
    import event_calibrator
    import film_tool_calibrator
    import film_tool_tags

    e = Env(app, client, tmp_path)
    monkeypatch.setattr(ai_mod, "ai_runtime_available", lambda: True)
    monkeypatch.setattr(ai_mod, "validate_video_for_analysis", lambda _p: (True, None))
    monkeypatch.setattr(ai_mod, "validate_ai_models_for_analysis", lambda _s=None: (True, None))
    monkeypatch.setattr(ai_mod, "start_analysis_subprocess", lambda key, path: e.spawned.append((key, path)))
    # conftest redirects helpers.ai_analysis_log_path; blueprints.ai holds its own reference
    import helpers

    monkeypatch.setattr(ai_mod, "ai_analysis_log_path", helpers.ai_analysis_log_path)
    # chunk staging dir + Film Tool sidecars/calibrators stay inside tmp_path
    monkeypatch.setattr(ai_mod.tempfile, "gettempdir", lambda: str(tmp_path / "systmp"))
    monkeypatch.setattr(film_tool_tags, "TAGS_ROOT", tmp_path / "film_tags")
    monkeypatch.setattr(film_tool_calibrator, "ROOT", tmp_path / "calib")
    monkeypatch.setattr(event_calibrator, "ROOT", tmp_path / "calib")  # film_tool_model_path()
    # deterministic drafts: no auto-accept unless a test opts in
    e.setting("ai.auto_accept_event_confidence", "0")
    return e


def _frozen_datetime(module, monkeypatch, stamp="2026-01-10 19:00:00"):
    fixed = _real_datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")

    class Frozen(_real_datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

        @classmethod
        def utcnow(cls):
            return fixed

    monkeypatch.setattr(module, "datetime", Frozen)


def _post_catching(fn):
    """TESTING=True propagates app exceptions; turn them into a failed response marker."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - we want the defect surfaced as an assertion
        return exc


def _event_signature(row):
    return (row["event_type"], row["timestamp_ms"], row["player"], row["shot_result"])


# ── 1. upload -> run -> worker progress -> completion -> results ─────────────


def test_whole_upload_runs_through_progress_to_results(env):
    payload, video = env.upload("clip.mp4", "Eagle Ridge")
    key = payload["game_id"]

    # upload response + videos row + file on disk
    assert payload["status"] == "uploaded"
    assert key.startswith("eagle_ridge_clip_") and key == video["game_id"]
    assert payload["stored_filename"].startswith("clip_") and payload["stored_filename"].endswith(".mp4")
    stored = env.uploads / payload["stored_filename"]
    assert stored.read_bytes() == VIDEO_BYTES
    assert video["original_filename"] == "clip.mp4"
    assert video["file_size_bytes"] == len(VIDEO_BYTES)
    assert video["file_path"] == str(stored)
    assert video["is_duplicate"] == 0 and video["relational_game_id"] is None

    # queued primary run + spawn call
    run = env.one("SELECT * FROM analysis_runs")
    assert (run["status"], run["run_kind"], run["run_label"]) == ("pending", "primary", "Original upload")
    assert run["analysis_key"] == key and run["base_analysis_key"] == key
    assert run["source_video_id"] == video["id"] and run["video_path"] == str(stored)
    assert run["started_at"] is None
    assert env.spawned == [(key, str(stored))]

    p = env.json(f"/api/analysis_progress/{key}")
    assert (p["status"], p["progress_pct"], p["detection_count"], p["event_count"]) == ("pending", 0, None, None)

    # worker picks it up
    env.worker_start(key)
    p = env.json(f"/api/analysis_progress/{key}")
    assert (p["status"], p["progress_step"]) == ("running", "Loading AI models…")
    assert p["started_at"] is not None

    env.worker_progress(key, 150, 300)
    p = env.json(f"/api/analysis_progress/{key}")
    assert (p["status"], p["progress_pct"], p["current_frame"], p["total_frames"]) == ("running", 50, 150, 300)
    assert p["detection_count"] is None  # no COUNT(*) while running

    jobs = env.json("/api/analysis_jobs")["jobs"]
    assert [(j["analysis_key"], j["status"], j["display_game"], j["video_id"]) for j in jobs] == [
        (key, "running", "Liberty vs Eagle Ridge", video["id"])
    ]
    lib = env.json("/api/videos")
    assert [(v["id"], v["analysis_status"], v["analysis_key"], v["current_frame"]) for v in lib] == [
        (video["id"], "running", key, 150)
    ]

    # worker finishes: detections + events + completed
    n_det = env.worker_finish(key)
    n_ev = env.one("SELECT COUNT(*) AS c FROM events WHERE game_id=?", (key,))["c"]
    assert n_ev > 0

    p = env.json(f"/api/analysis_progress/{key}")
    assert (p["status"], p["progress_pct"], p["progress_step"]) == ("completed", 100, "Done")
    assert (p["detection_count"], p["event_count"], p["error_message"]) == (n_det, n_ev, None)

    s = env.json(f"/api/analysis_status/{key}")
    assert (s["status"], s["detection_count"], s["event_count"], s["analysis_key"]) == ("completed", n_det, n_ev, key)

    res = env.json(f"/api/analysis/{key}")
    assert res["game_id"] == key and res["analysis_key"] == key
    assert res["video_id"] == video["id"]
    assert res["stored_filename"] == payload["stored_filename"]
    assert (res["detection_count"], res["event_count"]) == (n_det, n_ev)
    by_type = {r["event_type"]: r["cnt"] for r in env.q(
        "SELECT event_type, COUNT(*) AS cnt FROM events WHERE game_id=? GROUP BY event_type", (key,))}
    assert {r["event_type"]: r["cnt"] for r in res["events_summary"]} == by_type
    assert len(res["recent_events"]) == n_ev

    detail = env.json(f"/api/videos/{video['id']}")
    assert (detail["analysis_status"], detail["analysis_key"]) == ("completed", key)
    assert (detail["detection_count"], detail["event_count"]) == (n_det, n_ev)
    dbg = env.json(f"/api/videos/{video['id']}/analysis-debug")
    assert dbg["run"]["id"] == run["id"] and dbg["needs_event_regeneration"] is False
    assert env.json("/api/analysis_jobs")["jobs"][0]["status"] == "completed"  # recent completion still listed


def test_chunked_upload_out_of_order_reassembles_and_queues(env, monkeypatch):
    import blueprints.ai as ai_mod

    _frozen_datetime(ai_mod, monkeypatch, "2026-01-10 19:00:00")
    blob = bytes((i * 7) % 251 for i in range(10_000))
    responses = env.chunked_upload(blob, "chunky film.mp4", order=[2, 0, 1], upload_id="abc123")

    assert [r["status"] for r in responses] == ["chunk_received", "chunk_received", "complete"]
    assert [r.get("received") for r in responses[:2]] == [1, 2]
    final = responses[-1]
    video = env.one("SELECT * FROM videos")
    assert video["original_filename"] == "chunky_film.mp4"
    assert final["filename"] == video["stored_filename"] and final["game_id"] == video["game_id"]
    assert video["game_id"].startswith("chunk_opp_chunky_film_")
    assert Path(video["file_path"]).read_bytes() == blob
    assert video["file_size_bytes"] == len(blob)
    assert not (env.tmp / "systmp" / "liberty_uploads" / "abc123").exists()  # staging cleaned

    run = env.one("SELECT * FROM analysis_runs")
    assert (run["status"], run["run_kind"], run["run_label"], run["analysis_key"]) == (
        "pending", "primary", "Original upload", video["game_id"])
    assert env.spawned == [(video["game_id"], video["file_path"])]

    # same filename again (a minute later) -> flagged duplicate; tag_only queues nothing
    _frozen_datetime(ai_mod, monkeypatch, "2026-01-10 19:01:00")
    env.chunked_upload(blob, "chunky film.mp4", mode="tag_only", upload_id="def456")
    dup = env.q("SELECT * FROM videos ORDER BY id")[1]
    assert (dup["is_duplicate"], dup["duplicate_of_id"]) == (1, video["id"])
    assert env.one("SELECT COUNT(*) AS c FROM analysis_runs")["c"] == 1
    assert len(env.spawned) == 1
    dup_check = env.json("/api/check_duplicate?filename=chunky film.mp4")
    assert dup_check["is_duplicate"] is True and len(dup_check["previous_uploads"]) == 2


def test_chunked_upload_without_ai_runtime_does_not_strand_pending_run(env, monkeypatch):
    # Regression: the chunked path queued a run but never marked it failed.
    import blueprints.ai as ai_mod

    monkeypatch.setattr(ai_mod, "ai_runtime_available", lambda: False)
    final = env.chunked_upload(b"x" * 3000, "noai.mp4")[-1]
    run = env.one("SELECT * FROM analysis_runs")
    assert env.spawned == []
    # /upload in the same situation marks the run failed immediately
    assert (run["status"], run["error_message"]) == ("failed", "Missing AI packages (cv2/ultralytics)"), run
    assert run["completed_at"] is not None
    assert env.json(f"/api/analysis_progress/{final['game_id']}")["status"] == "failed"
    assert env.json("/api/analysis_jobs")["jobs"][0]["status"] == "failed"


def test_whole_upload_without_ai_runtime_marks_run_failed(env, monkeypatch):
    import blueprints.ai as ai_mod

    monkeypatch.setattr(ai_mod, "ai_runtime_available", lambda: False)
    payload, _ = env.upload("noai.mp4")
    run = env.one("SELECT * FROM analysis_runs")
    assert (run["status"], run["error_message"]) == ("failed", "Missing AI packages (cv2/ultralytics)")
    assert env.json(f"/api/analysis_progress/{payload['game_id']}")["status"] == "failed"
    assert env.json("/api/analysis_jobs")["jobs"][0]["status"] == "failed"


def test_chunk_upload_id_cannot_escape_staging_dir(env):
    # Regression: upload_id was joined raw into the staging path.
    escape = env.tmp / "outside" / "evil"
    for bad in (str(escape), "../../outside/evil", "..", "a/b"):
        r = env.client.post(
            "/api/upload_chunk",
            data={"file": (io.BytesIO(b"payload"), "blob"), "upload_id": bad, "chunk_index": "0",
                  "total_chunks": "2", "filename": "x.mp4"},
            content_type="multipart/form-data",
        )
        assert r.status_code == 400 and r.get_json()["error"] == "Invalid upload_id", bad
    assert not escape.exists(), "chunk written outside <tmp>/liberty_uploads"
    assert not (env.tmp / "outside").exists()
    assert env.q("SELECT * FROM videos") == []
    # the film tool's real id shape (base36 time + random) is still accepted
    env.chunked_upload(b"z" * 900, "ok.mp4", upload_id="lx3k9a0qz81m2")
    assert env.one("SELECT COUNT(*) AS c FROM videos")["c"] == 1


def test_same_second_duplicate_upload_keeps_both_files(env, monkeypatch):
    # Regression: same filename in the same second used to share stored_filename
    # (first film overwritten on disk, then a UNIQUE-constraint 500).
    import blueprints.ai as ai_mod

    _frozen_datetime(ai_mod, monkeypatch)
    first = b"FIRST" * 1000
    second = b"SECOND" * 1000
    third = b"THIRD" * 1000
    p1, v1 = env.upload("game.mp4", content=first)
    r2 = _post_catching(lambda: env.client.post(
        "/upload", data={"video": (io.BytesIO(second), "game.mp4"), "opponent": "Eagle Ridge"},
        content_type="multipart/form-data", headers=XHR))
    assert Path(v1["file_path"]).read_bytes() == first, "first upload's film was overwritten on disk"
    assert not isinstance(r2, Exception) and r2.status_code == 200, r2
    p2 = r2.get_json()
    v2 = env.one("SELECT * FROM videos WHERE stored_filename=?", (p2["stored_filename"],))
    assert p2["stored_filename"] != p1["stored_filename"] and p2["game_id"] != p1["game_id"]
    assert Path(v2["file_path"]).read_bytes() == second
    assert (v2["is_duplicate"], v2["duplicate_of_id"]) == (1, v1["id"])
    # the chunked path in the same second also gets its own file
    env.chunked_upload(third, "game.mp4", opponent="Eagle Ridge", upload_id="same-sec")
    rows = env.q("SELECT stored_filename, file_path, game_id FROM videos ORDER BY id")
    assert len(rows) == 3 and len({r["stored_filename"] for r in rows}) == 3
    assert len({r["game_id"] for r in rows}) == 3
    assert [Path(r["file_path"]).read_bytes() for r in rows] == [first, second, third]
    runs = env.q("SELECT analysis_key FROM analysis_runs ORDER BY id")
    assert [r["analysis_key"] for r in runs] == [r["game_id"] for r in rows]


# ── 2. event rebuild / regenerate ───────────────────────────────────────────


def _completed_upload(env, mode="expanded", opponent="Eagle Ridge", filename="clip.mp4"):
    env.setting("ai.event_generator_mode", mode)
    payload, video = env.upload(filename, opponent)
    key = payload["game_id"]
    n_det = env.run_worker(key)
    return key, video, n_det


@pytest.mark.parametrize("mode", ["expanded", "precision"])
def test_regenerate_events_is_idempotent_and_tags_generator(env, mode):
    key, video, n_det = _completed_upload(env, mode=mode)
    before = sorted(_event_signature(r) for r in env.q("SELECT * FROM events WHERE game_id=?", (key,)))
    assert before

    for _ in range(2):
        r = env.client.post(f"/api/videos/{video['id']}/regenerate-events")
        assert r.status_code == 200, r.data[:300]
        body = r.get_json()
        rows = env.q("SELECT * FROM events WHERE game_id=?", (key,))
        assert body["status"] == "events_regenerated" and body["analysis_key"] == key
        assert (body["detection_count"], body["event_count"]) == (n_det, len(rows))
        assert sorted(_event_signature(r) for r in rows) == before  # same drafts, no duplicates
        assert all(r["source_type"] == "ai" and r["review_status"] == "pending" for r in rows)

    run = env.one("SELECT * FROM analysis_runs")
    assert (run["status"], run["progress_pct"]) == ("completed", 100)
    assert run["progress_step"] in ("Done", "Events regenerated (enhanced analysis skipped)")
    generators = {json.loads(r["details_json"] or "{}").get("generator") for r in env.q(
        "SELECT details_json FROM events WHERE game_id=? AND event_type='shot'", (key,))}
    if mode == "precision":
        assert generators == {"precision"}
    else:
        assert "precision" not in generators
        types = {r["event_type"] for r in env.q("SELECT event_type FROM events WHERE game_id=?", (key,))}
        assert {"shot", "make"} <= types  # expanded vocabulary


def test_rebuild_keeps_film_tool_manual_tags_without_duplicates(env):
    key, video, _ = _completed_upload(env, mode="expanded")
    rows = [{"eventtype": "2PT", "result": "Make", "player": "12", "team": "Liberty", "start": "00:20"},
            {"eventtype": "Steal", "result": "NA", "player": "5", "team": "Liberty", "start": "00:40"}]
    r = env.post_json(f"/api/film/{quote(key, safe='')}/teach-manual", {"rows": rows})
    assert r.status_code == 200, r.data[:300]
    assert r.get_json()["manual_saved"] == 2
    manual_before = env.q("SELECT id, event_type, timestamp_ms, human_verified FROM events "
                          "WHERE game_id=? AND source_type='manual' ORDER BY id", (key,))
    assert [(m["event_type"], m["timestamp_ms"], m["human_verified"]) for m in manual_before] == [
        ("shot", 20000, 1), ("steal", 40000, 1)]

    def status_counts():
        rows = env.q("SELECT source_type, review_status, COUNT(*) AS c FROM events WHERE game_id=? "
                     "GROUP BY source_type, review_status", (key,))
        return {(r["source_type"], r["review_status"]): r["c"] for r in rows}

    graded = status_counts()
    for _ in range(3):
        assert env.client.post(f"/api/videos/{video['id']}/regenerate-events").status_code == 200
        manual = env.q("SELECT id, event_type, timestamp_ms, human_verified FROM events "
                       "WHERE game_id=? AND source_type='manual' ORDER BY id", (key,))
        assert manual == manual_before
        assert status_counts() == graded  # teach grading is re-derived, not stacked


def test_rebuild_does_not_duplicate_accepted_ai_events(env):
    # Regression: rebuild kept human_verified AI rows AND re-inserted them as new drafts.
    key, video, _ = _completed_upload(env, mode="expanded")
    initial = env.q("SELECT * FROM events WHERE game_id=? ORDER BY timestamp_ms, id", (key,))
    total_before = len(initial)
    shot = [e for e in initial if e["event_type"] == "shot"][0]
    others = [e for e in initial if e["id"] != shot["id"]]
    to_reject, to_correct = others[0], others[1]

    r = env.client.post(f"/api/review/events/{shot['id']}/accept", data="{}", content_type="application/json")
    assert r.status_code == 200 and r.get_json()["review_status"] == "accepted"
    r = env.client.post(f"/api/review/events/{to_reject['id']}/reject", data="{}", content_type="application/json")
    assert r.status_code == 200 and r.get_json()["review_status"] == "rejected"
    r = env.post_json(f"/api/review/events/{to_correct['id']}/correct",
                      {"event_type": "block", "player": "44", "timestamp_ms": to_correct["timestamp_ms"] + 700})
    assert r.status_code == 200 and r.get_json()["review_status"] == "corrected"

    def snapshot():
        rows = env.q("SELECT id, event_type, timestamp_ms, player, review_status FROM events "
                     "WHERE game_id=? ORDER BY id", (key,))
        return {r["id"]: r for r in rows}

    decided_before = {i: r for i, r in snapshot().items() if i in (shot["id"], to_reject["id"], to_correct["id"])}
    for _ in range(3):
        body = env.client.post(f"/api/videos/{video['id']}/regenerate-events").get_json()
        assert body["status"] == "events_regenerated"
        after = snapshot()
        assert len(after) == total_before  # one row per generated play, every rebuild
        assert {i: after[i] for i in decided_before} == decided_before  # same ids, same decisions
        # no fresh draft for any play a person already decided on
        for ev in (shot, to_reject, to_correct):
            dupes = [r for r in after.values() if r["id"] != ev["id"]
                     and (r["event_type"], r["timestamp_ms"]) == (ev["event_type"], ev["timestamp_ms"])]
            assert dupes == [], (ev["event_type"], ev["timestamp_ms"], dupes)
    assert env.one("SELECT review_status FROM events WHERE id=?", (shot["id"],))["review_status"] == "accepted"


def test_rebuild_with_default_auto_accept_is_idempotent(env):
    # Regression: each rebuild added another auto-accepted copy (4 -> 8 -> 12).
    env.setting("ai.auto_accept_event_confidence", "0.85")  # shipped default
    key, video, _ = _completed_upload(env, mode="precision")

    def counts():
        rows = env.q("SELECT review_status, COUNT(*) AS c FROM events WHERE game_id=? GROUP BY review_status", (key,))
        return {r["review_status"]: r["c"] for r in rows}

    before = counts()
    assert before.get("accepted", 0) > 0
    auto = env.q("SELECT review_notes, reviewed_by_user_id FROM events WHERE game_id=? AND review_status='accepted'", (key,))
    assert {(a["review_notes"], a["reviewed_by_user_id"]) for a in auto} == {("Auto-accepted (high confidence)", None)}
    for _ in range(3):
        assert env.client.post(f"/api/videos/{video['id']}/regenerate-events").status_code == 200
        assert counts() == before
    res = env.json(f"/api/analysis/{key}")
    assert res["event_count"] == sum(before.values())


def test_regenerate_without_detections_is_rejected_and_run_untouched(env):
    payload, video = env.upload("empty.mp4")
    r = env.client.post(f"/api/videos/{video['id']}/regenerate-events")
    assert r.status_code == 400 and r.get_json()["code"] == "no_detections"
    assert env.one("SELECT status FROM analysis_runs")["status"] == "pending"
    assert env.client.post("/api/videos/999999/regenerate-events").status_code == 404


def test_interrupted_rebuild_is_reconciled(env):
    # Regression: reconcile skipped in-process rebuild steps, so a killed rebuild
    # stayed 'running' forever and blocked new analysis.
    key, video, _ = _completed_upload(env)
    # the rebuild request died mid-way (e.g. gunicorn --timeout 120 killed the worker)
    env.execute("UPDATE analysis_runs SET status='running', progress_pct=35, "
                "progress_step='Clustering players and rebuilding events…', completed_at=NULL")
    import helpers

    log = Path(helpers.ai_analysis_log_path(key))
    log.write_text("\n[2026-01-10T19:00:00Z] Rebuild events started in web worker.\n")

    # a rebuild that is still within a request's lifetime is left alone
    assert env.json(f"/api/analysis_progress/{key}")["status"] == "running"

    old = time.time() - 3 * 3600
    os.utime(log, (old, old))
    p = env.json(f"/api/analysis_progress/{key}")
    assert (p["status"], p["error_message"]) == ("failed", helpers.EVENT_REBUILD_INTERRUPTED_MESSAGE)
    # Rebuild works again, and so does a new analysis request
    assert env.client.post(f"/api/videos/{video['id']}/regenerate-events").status_code == 200
    assert env.one("SELECT status FROM analysis_runs")["status"] == "completed"
    r = env.client.post(f"/api/videos/{video['id']}/analyze")
    assert r.status_code == 200 and r.get_json()["status"] == "started"


# ── 3. reruns, compare page, superseding ────────────────────────────────────


def _spy_render(monkeypatch):
    import blueprints.ai as ai_mod

    captured = {}
    real = ai_mod.render_template

    def spy(name, **ctx):
        captured[name] = ctx
        return real(name, **ctx)

    monkeypatch.setattr(ai_mod, "render_template", spy)
    return captured


def test_rerun_labels_second_run_keeps_primary_and_compare_lists_both(env, monkeypatch):
    key, video, n_det = _completed_upload(env)
    primary_events = env.one("SELECT COUNT(*) AS c FROM events WHERE game_id=?", (key,))["c"]

    r = env.client.post(f"/videos/{video['id']}/rerun", data={"run_label": "YOLOv8s test"}, follow_redirects=False)
    assert r.status_code == 302 and "Queued+rerun" in r.headers["Location"].replace("%20", "+")
    runs = env.q("SELECT * FROM analysis_runs ORDER BY id")
    assert [(x["run_kind"], x["run_label"], x["status"]) for x in runs] == [
        ("primary", "Original upload", "completed"), ("rerun", "YOLOv8s test", "pending")]
    rerun_key = runs[1]["analysis_key"]
    assert rerun_key.startswith(f"{key}__rerun_") and runs[1]["base_analysis_key"] == key
    assert env.spawned[-1] == (rerun_key, video["file_path"])

    # a second request while the rerun is running is refused
    env.worker_start(rerun_key)
    r = env.client.post(f"/api/videos/{video['id']}/analyze")
    assert r.status_code == 409 and r.get_json()["code"] == "already_running"
    rerun_det = env.worker_finish(rerun_key, frames=150, seed=11)

    captured = _spy_render(monkeypatch)
    assert env.client.get(f"/videos/{video['id']}/compare").status_code == 200
    ctx = captured["analysis_compare.html"]
    listed = {x["analysis_key"]: x for x in ctx["runs"]}
    assert set(listed) == {key, rerun_key}
    assert ctx["primary_run"]["analysis_key"] == key
    assert (listed[key]["detection_count"], listed[key]["event_count"]) == (n_det, primary_events)
    assert listed[rerun_key]["detection_count"] == rerun_det
    assert listed[rerun_key]["detection_delta"] == rerun_det - n_det

    # primary results untouched by the rerun
    res = env.json(f"/api/analysis/{key}")
    assert (res["detection_count"], res["event_count"]) == (n_det, primary_events)
    assert env.json(f"/api/analysis_progress/{rerun_key}")["detection_count"] == rerun_det


def test_new_request_supersedes_pending_rerun(env, monkeypatch):
    import helpers

    key, video, _ = _completed_upload(env)
    stamps = iter(["2026-01-10 19:00:00", "2026-01-10 19:00:05"])

    def next_stamp():
        _frozen_datetime(helpers, monkeypatch, next(stamps))

    next_stamp()
    first = env.client.post(f"/api/videos/{video['id']}/analyze").get_json()
    next_stamp()
    second = env.client.post(f"/api/videos/{video['id']}/analyze").get_json()
    assert first["status"] == second["status"] == "started"
    runs = env.q("SELECT analysis_key, status, run_kind, progress_step FROM analysis_runs ORDER BY id")
    assert [(r["status"], r["run_kind"]) for r in runs] == [
        ("completed", "primary"), ("cancelled", "rerun"), ("pending", "rerun")]
    assert runs[1]["progress_step"] == "Superseded by new analysis request"

    # the cancelled key's progress view follows the replacement run
    p = env.json(f"/api/analysis_progress/{first['analysis_key']}")
    assert (p["status"], p["analysis_key"], p["error_message"]) == ("pending", second["analysis_key"], None)
    lib = env.json("/api/videos")
    assert lib[0]["analysis_status"] == "pending" and lib[0]["analysis_key"] == second["analysis_key"]


def test_same_second_reruns_get_distinct_keys(env, monkeypatch):
    # Regression: rerun keys had 1-second resolution, so the replacement reused the
    # cancelled run's key.
    import helpers

    key, video, _ = _completed_upload(env)
    _frozen_datetime(helpers, monkeypatch)
    a = env.client.post(f"/api/videos/{video['id']}/analyze").get_json()
    b = env.client.post(f"/api/videos/{video['id']}/analyze").get_json()
    assert a["analysis_key"] != b["analysis_key"]
    assert a["analysis_key"].startswith(f"{key}__rerun_") and b["analysis_key"].startswith(f"{key}__rerun_")
    runs = env.q("SELECT analysis_key, status FROM analysis_runs ORDER BY id")
    assert [(r["analysis_key"], r["status"]) for r in runs] == [
        (key, "completed"), (a["analysis_key"], "cancelled"), (b["analysis_key"], "pending")]
    assert env.spawned[-1][0] == b["analysis_key"]
    # the cancelled key's progress view follows the replacement run
    p = env.json(f"/api/analysis_progress/{a['analysis_key']}")
    assert (p["status"], p["analysis_key"]) == ("pending", b["analysis_key"])


# NFHS / library videos carry videos.relational_game_id, so the worker stamps detections
# and events with it.
def _nfhs_video(env, nfhs_id="gamabc12345678"):
    from nfhs import register_nfhs_download

    path = env.uploads / f"nfhs_{nfhs_id}.mp4"
    path.write_bytes(VIDEO_BYTES)
    with env.app.app_context():
        from helpers import get_db

        db = get_db()
        saved = register_nfhs_download(db, str(path), nfhs_id, home_team="Liberty", away_team="Riverside")
        db.commit()
    return saved


def _nfhs_primary_and_rerun(env):
    env.setting("ai.event_generator_mode", "expanded")
    saved = _nfhs_video(env)
    vid, rel = saved["video_id"], saved["relational_game_id"]
    first = env.client.post(f"/api/videos/{vid}/analyze").get_json()
    assert first["run_kind"] == "primary"
    primary_key = first["analysis_key"]
    n_primary = env.run_worker(primary_key, relational_game_id=rel)
    r = env.client.post(f"/videos/{vid}/rerun", data={"run_label": "second pass"})
    assert r.status_code == 302
    rerun_key = env.q("SELECT analysis_key FROM analysis_runs WHERE run_kind='rerun'")[0]["analysis_key"]
    n_rerun = env.run_worker(rerun_key, frames=150, relational_game_id=rel, seed=11)
    return vid, rel, primary_key, n_primary, rerun_key, n_rerun


def test_nfhs_primary_run_uses_relational_game(env):
    saved = _nfhs_video(env)
    r = env.client.post(f"/api/videos/{saved['video_id']}/analyze")
    body = r.get_json()
    assert r.status_code == 200 and (body["run_kind"], body["run_label"]) == ("primary", "NFHS / library video")
    run = env.one("SELECT * FROM analysis_runs")
    assert (run["game_id"], run["analysis_key"], run["status"]) == (
        saved["relational_game_id"], saved["game_id"], "pending")


def test_compare_counts_detections_for_nfhs_runs(env, monkeypatch):
    # Regression: the subquery used games.game_id (no such column), so NFHS runs showed 0.
    # an earlier game already exists (normal season), so the NFHS game is not games.id=1
    r = env.post_json("/api/games", {"source_type": "manual", "source_key": "earlier-game"})
    assert r.status_code in (200, 201), r.data[:200]
    vid, rel, primary_key, n_primary, rerun_key, n_rerun = _nfhs_primary_and_rerun(env)
    captured = _spy_render(monkeypatch)
    assert env.client.get(f"/videos/{vid}/compare").status_code == 200
    runs = {x["analysis_key"]: x for x in captured["analysis_compare.html"]["runs"]}
    assert {k: x["detection_count"] for k, x in runs.items()} == {primary_key: n_primary, rerun_key: n_rerun}
    assert runs[rerun_key]["detection_delta"] == n_rerun - n_primary


def test_nfhs_rerun_rebuild_uses_only_its_own_detections(env, monkeypatch):
    # Regression: rebuilding a rerun also loaded the primary run's detections
    # through the shared relational_game_id.
    import event_generator

    vid, rel, primary_key, n_primary, rerun_key, n_rerun = _nfhs_primary_and_rerun(env)
    loaded = []
    real = event_generator.get_detections

    def spy(*a, **kw):
        df = real(*a, **kw)
        loaded.append(set(df["game_id"]))
        return df

    monkeypatch.setattr(event_generator, "get_detections", spy)
    body = env.client.post(f"/api/videos/{vid}/regenerate-events").get_json()
    assert body["analysis_key"] == rerun_key
    assert body["detection_count"] == n_rerun
    assert loaded == [{rerun_key}]
    assert env.json(f"/api/videos/{vid}/analysis-debug")["detection_count"] == n_rerun


def test_nfhs_rerun_generation_keeps_primary_run_events(env):
    # Regression: persist_events deleted every unverified event of the relational
    # game, so generating a rerun wiped the primary run's drafts.
    env.setting("ai.event_generator_mode", "expanded")
    saved = _nfhs_video(env)
    vid, rel = saved["video_id"], saved["relational_game_id"]
    primary_key = env.client.post(f"/api/videos/{vid}/analyze").get_json()["analysis_key"]
    env.run_worker(primary_key, relational_game_id=rel)
    primary_rows = env.q("SELECT id FROM events WHERE game_id=? ORDER BY id", (primary_key,))
    assert primary_rows
    env.client.post(f"/videos/{vid}/rerun", data={})
    rerun_key = env.q("SELECT analysis_key FROM analysis_runs WHERE run_kind='rerun'")[0]["analysis_key"]
    env.run_worker(rerun_key, frames=150, relational_game_id=rel, seed=11)
    assert env.q("SELECT id FROM events WHERE game_id=? ORDER BY id", (primary_key,)) == primary_rows
    rerun_events = env.one("SELECT COUNT(*) AS c FROM events WHERE game_id=?", (rerun_key,))["c"]
    assert rerun_events > 0
    # rebuilding the rerun (latest run) leaves the primary's events alone as well
    body = env.client.post(f"/api/videos/{vid}/regenerate-events").get_json()
    assert body["analysis_key"] == rerun_key
    assert env.q("SELECT id FROM events WHERE game_id=? ORDER BY id", (primary_key,)) == primary_rows
    assert env.one("SELECT COUNT(*) AS c FROM events WHERE game_id=?", (rerun_key,))["c"] == rerun_events


# ── 4. highlights / clips / trim ────────────────────────────────────────────


def _real_video_upload(env, seconds=10):
    path = td.make_synthetic_video(env.tmp / "src.mp4", seconds=seconds)
    payload, video = env.upload("src.mp4", "Highlight Opp", content=path.read_bytes())
    return payload["game_id"], video


def _accept(env, event_id):
    r = env.client.post(f"/api/review/events/{event_id}/accept", data="{}", content_type="application/json")
    assert r.status_code == 200, r.data[:200]


def test_highlights_only_use_accepted_events_and_save_clips(env):
    env.setting("ai.event_generator_mode", "expanded")
    payload, video = env.upload("hl.mp4", "Highlight Opp")
    key = payload["game_id"]
    env.run_worker(key)
    events = env.q("SELECT * FROM events WHERE game_id=? ORDER BY timestamp_ms, id", (key,))
    chosen, pending = events[:2], events[2]
    for ev in chosen:
        _accept(env, ev["id"])

    m = env.json(f"/api/highlights/moments?game_id={quote(key)}")
    assert m["reviewed_event_count"] == 2
    assert [x["id"] for x in m["moments"]] == [e["id"] for e in chosen]
    for mom, ev in zip(m["moments"], chosen):
        assert mom["clip_start_ms"] == max(0, ev["timestamp_ms"] - 3000)
        assert mom["clip_end_ms"] == ev["timestamp_ms"] + 5000
        assert mom["seek_url"] == f"/film/{video['stored_filename']}?game_id={quote(key, safe='')}&t={ev['timestamp_ms']}"
    assert m["video"]["id"] == video["id"]

    r = env.post_json("/api/highlights/generate", {
        "game_id": key, "event_ids": [chosen[0]["id"], chosen[1]["id"], pending["id"]], "cut_video": False})
    assert r.status_code == 201, r.data[:300]
    out = r.get_json()
    assert out["missing_event_ids"] == [pending["id"]]
    assert [x["event_id"] for x in out["export"]] == [e["id"] for e in chosen]
    assert out["trim_jobs"] == [] and out["cut_mode"] == "seek_export"
    dev = env.q("SELECT event_id, clip_category, clip_start_ms, clip_end_ms, canonical_clip_id FROM player_development_clips ORDER BY id")
    assert [(d["event_id"], d["clip_category"]) for d in dev] == [(e["id"], "highlight") for e in chosen]
    canon = env.q("SELECT id, event_id, clip_type FROM clips ORDER BY id")
    assert [(c["event_id"], c["clip_type"]) for c in canon] == [(e["id"], "highlight") for e in chosen]
    assert [d["canonical_clip_id"] for d in dev] == [c["id"] for c in canon]


@needs_ffmpeg
def test_highlight_generation_cuts_ffmpeg_clips(env):
    env.setting("ai.event_generator_mode", "expanded")
    key, video = _real_video_upload(env)
    env.run_worker(key)
    ev = env.q("SELECT * FROM events WHERE game_id=? AND timestamp_ms BETWEEN 1000 AND 4000 ORDER BY timestamp_ms", (key,))[0]
    _accept(env, ev["id"])
    out = env.post_json("/api/highlights/generate", {"game_id": key, "event_ids": [ev["id"]], "pad_after_ms": 2000}).get_json()
    assert out["cut_mode"] == "ffmpeg" and len(out["trim_jobs"]) == 1
    st = _wait_trim(env, out["trim_jobs"][0]["job_id"])
    assert st["status"] == "complete", st
    new = env.one("SELECT * FROM videos WHERE id=?", (st["video_id"],))
    assert new["duplicate_of_id"] == video["id"] and Path(new["file_path"]).exists()


def _wait_trim(env, job_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = env.json(f"/api/videos/trim/{job_id}")
        if st["status"] in ("complete", "error"):
            return st
        time.sleep(0.1)
    raise AssertionError(f"trim job {job_id} did not finish")


@needs_ffmpeg
def test_trim_job_lifecycle(env):
    from video_trim import ffprobe_duration_ms

    key, video = _real_video_upload(env, seconds=6)
    vid = video["id"]
    assert env.post_json(f"/api/videos/{vid}/trim", {"start_ms": 3000, "end_ms": 3000}).status_code == 400
    assert env.post_json(f"/api/videos/{vid}/trim", {"start_ms": 0, "end_ms": 60_000}).status_code == 400
    assert env.post_json(f"/api/videos/{vid}/trim", {"start": "x", "end": "y"}).status_code == 400
    assert env.post_json("/api/videos/999999/trim", {"start_ms": 0, "end_ms": 1000}).status_code == 404
    assert env.client.get("/api/videos/trim/" + "0" * 32).status_code == 404

    r = env.post_json(f"/api/videos/{vid}/trim", {"start": "0:01", "end": "0:03", "label": "first two"})
    assert r.status_code == 200
    st = _wait_trim(env, r.get_json()["job_id"])
    assert st["status"] == "complete", st
    new = env.one("SELECT * FROM videos WHERE id=?", (st["video_id"],))
    assert new["original_filename"] == "src.mp4 (first two)"
    assert new["duplicate_of_id"] == vid and new["opponent"] == "Highlight Opp"
    assert new["game_id"].startswith(f"{key}_trim_") and new["stored_filename"] == st["stored_filename"]
    # stream copy is keyframe-aligned (documented in trim_video_file), so allow slack
    assert 1500 <= ffprobe_duration_ms(new["file_path"]) <= 3500
    assert env.one("SELECT COUNT(*) AS c FROM analysis_runs WHERE source_video_id=?", (new["id"],))["c"] == 0

    # deleting the source keeps the trimmed copy (duplicate link cleared)
    assert env.client.delete(f"/api/videos/{vid}").get_json()["success"] is True
    assert env.one("SELECT duplicate_of_id FROM videos WHERE id=?", (new["id"],))["duplicate_of_id"] is None
    assert not Path(video["file_path"]).exists() and Path(new["file_path"]).exists()


def test_resaving_film_tool_tags_after_highlight_clip(env):
    # Regression: re-save deleted the old manual events while clips referenced them (FK 500).
    key, video, _ = _completed_upload(env)
    rows = [{"eventtype": "3PT", "result": "Make", "player": "3", "team": "Liberty", "start": "00:05"}]
    path = f"/api/film/{quote(key, safe='')}/teach-manual"
    assert env.post_json(path, {"rows": rows}).status_code == 200
    manual = env.one("SELECT id FROM events WHERE game_id=? AND source_type='manual'", (key,))
    out = env.post_json("/api/highlights/generate", {"game_id": key, "event_ids": [manual["id"]], "cut_video": False})
    assert out.status_code == 201 and len(out.get_json()["saved_clips"]) == 1

    rows[0]["player"] = "33"  # coach corrects the jersey and saves again
    r = _post_catching(lambda: env.post_json(path, {"rows": rows}))
    assert not isinstance(r, Exception), f"teach re-save crashed: {r!r}"
    assert r.status_code == 200 and r.get_json()["replaced"] == 1
    # the clip still points at the (updated) tag
    now = env.one("SELECT id, player FROM events WHERE game_id=? AND source_type='manual'", (key,))
    assert now == {"id": manual["id"], "player": "33"}
    assert [c["event_id"] for c in env.q("SELECT event_id FROM clips")] == [manual["id"]]
    assert [c["event_id"] for c in env.q("SELECT event_id FROM player_development_clips")] == [manual["id"]]

    # dropping that tag and adding another: the clip is detached, not a 500
    rows = [{"eventtype": "Steal", "result": "NA", "player": "5", "team": "Liberty", "start": "00:30"}]
    r = _post_catching(lambda: env.post_json(path, {"rows": rows}))
    assert not isinstance(r, Exception), f"teach re-save crashed: {r!r}"
    assert r.status_code == 200 and (r.get_json()["manual_saved"], r.get_json()["replaced"]) == (1, 1)
    manual_rows = env.q("SELECT event_type, timestamp_ms FROM events WHERE game_id=? AND source_type='manual'", (key,))
    assert manual_rows == [{"event_type": "steal", "timestamp_ms": 30000}]
    assert env.one("SELECT COUNT(*) AS c FROM clips")["c"] == 1


# ── 5. game-id encodings (Jr High keys with commas) ─────────────────────────


def test_comma_game_ids_resolve_under_every_encoding(env):
    payload, video = env.upload("jr.mp4", "Riverside, Eagle")
    key = payload["game_id"]
    assert "," in key and key.startswith("riverside,_eagle_jr_")
    n_det = env.run_worker(key)
    n_ev = env.one("SELECT COUNT(*) AS c FROM events WHERE game_id=?", (key,))["c"]
    for enc in (key, quote(key, safe=""), quote(quote(key, safe=""), safe="")):
        s = env.json(f"/api/analysis_status/{enc}")
        assert (s["status"], s["analysis_key"], s["detection_count"], s["event_count"]) == ("completed", key, n_det, n_ev), enc
        p = env.json(f"/api/analysis_progress/{enc}")
        assert (p["status"], p["analysis_key"], p["detection_count"]) == ("completed", key, n_det), enc
        res = env.json(f"/api/analysis/{enc}")
        assert (res["game_id"], res["video_id"], res["event_count"]) == (key, video["id"], n_ev), enc
        evs = env.json(f"/api/analysis/{enc}/events")
        assert evs["game_id"] == key and len(evs["events"]) == n_ev, enc
    assert env.client.get(f"/analysis/{quote(quote(key, safe=''), safe='')}").status_code == 200


def test_progress_reconciles_stale_run_for_double_encoded_key(env):
    # Regression: /api/analysis_progress reconciled with the still-encoded key.
    import helpers

    payload, _ = env.upload("jr.mp4", "Riverside, Eagle")
    key = payload["game_id"]
    log = Path(helpers.ai_analysis_log_path(key))
    log.write_text(f"[launcher] Started analysis_launcher.py PID=999999 for {key}\n")
    old = time.time() - 600
    os.utime(log, (old, old))
    enc = quote(quote(key, safe=""), safe="")
    p = env.json(f"/api/analysis_progress/{enc}")
    assert (p["status"], p["analysis_key"]) == ("failed", key)
    assert "stopped before processing started" in p["error_message"]
    assert env.one("SELECT status FROM analysis_runs WHERE analysis_key=?", (key,))["status"] == "failed"


def test_plain_key_reconciles_stale_pending_run(env):
    import helpers

    payload, _ = env.upload("plain.mp4", "Riverside")
    key = payload["game_id"]
    log = Path(helpers.ai_analysis_log_path(key))
    log.write_text(f"[launcher] Started analysis_launcher.py PID=999999 for {key}\n")
    old = time.time() - 600
    os.utime(log, (old, old))
    p = env.json(f"/api/analysis_progress/{key}")
    assert p["status"] == "failed" and "stopped before processing started" in p["error_message"]


# ── 6. NFHS credentials + download job (network stubbed) ────────────────────


FAKE_YT_DLP = r"""
import sys
args = sys.argv[1:]
out = args[args.index('-o') + 1]
partial = '--download-sections' in args
size = 400 if partial else 4000
for pct in (10.0, 55.5, 100.0):
    print(f'[download]  {pct}% of 1.00MiB at 2.00MiB/s ETA 00:01', flush=True)
with open(out, 'wb') as fh:
    fh.write((b'P' if partial else b'F') * size)
"""


@pytest.fixture
def nfhs_env(env, monkeypatch):
    import blueprints.scouting as scouting
    import nfhs

    logins = []

    def fake_login(email, password):
        logins.append((email, password))
        ok = password.startswith("good")
        return {"success": ok, "message": "Logged in successfully" if ok else "Login failed (HTTP 401)",
                "session_valid": ok}

    lookup = lambda game_id, email, password: {"success": True, "home_team": "Liberty", "away_team": "Riverside",
                                               "site_url": None}
    monkeypatch.setattr(scouting, "login_nfhs", fake_login)
    monkeypatch.setattr(scouting, "lookup_game", lookup)
    monkeypatch.setattr(nfhs, "lookup_game", lookup)
    monkeypatch.setattr(nfhs, "get_nfhs_token", lambda email, password: "tok-123")
    monkeypatch.setattr(nfhs, "_yt_dlp_available", lambda: True)
    monkeypatch.setattr(nfhs, "_yt_dlp_command", lambda: [sys.executable, "-c", FAKE_YT_DLP])
    monkeypatch.setattr(nfhs.tempfile, "gettempdir", lambda: str(env.tmp / "systmp"))
    (env.tmp / "systmp").mkdir(exist_ok=True)
    env.logins = logins
    return env


def _wait_download(env, job_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = env.json(f"/api/scouting/nfhs/download/{job_id}")
        if st["status"] in ("complete", "error", "cancelled"):
            return st
        time.sleep(0.05)
    raise AssertionError("download did not finish")


def _stored_password(env, email):
    from nfhs import _decrypt_password

    row = env.q("SELECT password_enc FROM nfhs_credentials WHERE email=? AND is_active=1 ORDER BY id DESC", (email,))
    return _decrypt_password(row[0]["password_enc"]) if row else None


def test_nfhs_credentials_download_and_analyze(nfhs_env):
    env = nfhs_env
    r = env.post_json("/api/scouting/nfhs/download", {"game_id": "gamabc12345678"})
    assert r.status_code == 401 and r.get_json()["needs_login"] is True

    r = env.post_json("/api/scouting/nfhs/credentials", {"email": "coach@example.com", "password": "bad"})
    assert r.status_code == 401 and env.q("SELECT * FROM nfhs_credentials") == []
    r = env.post_json("/api/scouting/nfhs/credentials", {"email": "coach@example.com", "password": "good-pw"})
    assert r.status_code == 200 and r.get_json()["status"] == "saved"
    row = env.one("SELECT * FROM nfhs_credentials")
    assert row["password_enc"] != "good-pw" and _stored_password(env, "coach@example.com") == "good-pw"
    info = env.json("/api/scouting/nfhs/credentials")
    assert info == {"has_credentials": True, "email": "coach@example.com",
                    "last_login_at": row["last_login_at"], "last_login_status": "success"}

    url = "https://www.nfhsnetwork.com/events/liberty-charter/gamabc12345678?autoplay=true"
    r = env.post_json("/api/scouting/nfhs/download", {"nfhs_url": url})
    assert r.status_code == 200 and r.get_json()["nfhs_game_id"] == "gamabc12345678"
    st = _wait_download(env, r.get_json()["job_id"])
    assert (st["status"], st["percent"], st["file_size"], st["already_saved"]) == ("complete", 100, 4000, False)
    assert st["stored_filename"] == "nfhs_gamabc12345678.mp4"
    assert st["game_id"].startswith("nfhs_gamabc12345678_")
    video = env.one("SELECT * FROM videos")
    assert (video["stored_filename"], video["file_size_bytes"], video["opponent"], video["game_id"]) == (
        "nfhs_gamabc12345678.mp4", 4000, "Riverside", st["game_id"])
    game = env.one("SELECT * FROM games WHERE id=?", (video["relational_game_id"],))
    assert (game["nfhs_game_id"], game["nfhs_url"]) == ("gamabc12345678", url.split("?")[0])
    assert env.one("SELECT COUNT(*) AS c FROM sources WHERE game_id=? AND source_type='nfhs_vod'", (game["id"],))["c"] == 1
    assert (env.uploads / "nfhs_gamabc12345678.mp4").read_bytes() == b"F" * 4000
    assert not list((env.tmp / "systmp").glob("nfhs_headers_*"))  # bearer-token header file cleaned

    r = env.client.post(f"/api/scouting/nfhs/download/{st['job_id']}/cancel")
    assert r.status_code == 409 and r.get_json()["error"] == "Download already complete"
    assert env.client.get("/api/scouting/nfhs/download/nope").status_code == 404

    body = env.client.post(f"/api/videos/{video['id']}/analyze").get_json()
    assert (body["status"], body["run_kind"], body["analysis_key"]) == ("started", "primary", video["game_id"])
    assert env.one("SELECT game_id FROM analysis_runs")["game_id"] == game["id"]


def test_nfhs_partial_download_does_not_overwrite_full_game(nfhs_env):
    # Regression: a section download reused nfhs_<id>.mp4, replacing the full game on
    # disk while the library row still described the full game.
    env = nfhs_env
    env.post_json("/api/scouting/nfhs/credentials", {"email": "coach@example.com", "password": "good-pw"})
    full = _wait_download(env, env.post_json("/api/scouting/nfhs/download", {"game_id": "gamabc12345678"}).get_json()["job_id"])
    assert full["status"] == "complete"
    full_video = env.one("SELECT * FROM videos")
    part = _wait_download(env, env.post_json("/api/scouting/nfhs/download", {
        "game_id": "gamabc12345678", "start_ms": 0, "end_ms": 60_000}).get_json()["job_id"])
    assert part["status"] == "complete"
    assert Path(full_video["file_path"]).read_bytes() == b"F" * 4000, "full game film replaced by the partial clip"
    assert (part["already_saved"], part["file_size"]) == (False, 400)
    assert part["stored_filename"] != full_video["stored_filename"]
    videos = {v["stored_filename"]: v for v in env.q("SELECT * FROM videos")}
    assert set(videos) == {full_video["stored_filename"], part["stored_filename"]}
    assert videos[full_video["stored_filename"]]["file_size_bytes"] == 4000
    clip = videos[part["stored_filename"]]
    assert clip["file_size_bytes"] == 400 and Path(clip["file_path"]).read_bytes() == b"P" * 400
    assert clip["relational_game_id"] == full_video["relational_game_id"] and clip["game_id"] == part["game_id"]
    # the full game downloaded again maps onto the same library row, refreshed to the new file
    env.execute("UPDATE videos SET file_size_bytes=1 WHERE id=?", (full_video["id"],))
    again =_wait_download(env, env.post_json("/api/scouting/nfhs/download", {"game_id": "gamabc12345678"}).get_json()["job_id"])
    assert (again["status"], again["already_saved"], again["game_id"]) == ("complete", True, full_video["game_id"])
    assert env.one("SELECT COUNT(*) AS c FROM videos")["c"] == 2
    assert env.one("SELECT file_size_bytes FROM videos WHERE id=?", (full_video["id"],))["file_size_bytes"] == 4000


def test_nfhs_login_with_new_password_updates_stored_password(nfhs_env):
    # Regression: a successful login with a new password recorded success but kept
    # the old stored password.
    import blueprints.scouting as scouting

    env = nfhs_env
    env.post_json("/api/scouting/nfhs/credentials", {"email": "coach@example.com", "password": "good-old"})
    r = env.post_json("/api/scouting/nfhs/login", {"email": "coach@example.com", "password": "good-new"})
    assert r.get_json()["success"] is True
    assert env.one("SELECT last_login_status FROM nfhs_credentials")["last_login_status"] == "success"
    assert _stored_password(env, "coach@example.com") == "good-new"
    with env.app.test_request_context():
        assert scouting._get_stored_credentials() == ("coach@example.com", "good-new")
    # logging in again without a password uses the new stored one
    r = env.post_json("/api/scouting/nfhs/login", {"email": "coach@example.com"})
    assert r.get_json()["success"] is True
    assert env.logins[-1] == ("coach@example.com", "good-new")
    # and the download job authenticates with it
    job = env.post_json("/api/scouting/nfhs/download", {"game_id": "gamabc12345678"})
    assert job.status_code == 200
    assert _wait_download(env, job.get_json()["job_id"])["status"] == "complete"


def test_nfhs_failed_login_does_not_replace_working_credentials(nfhs_env):
    # Regression: a failed login stored the bad password as the newest active credential.
    import blueprints.scouting as scouting

    env = nfhs_env
    env.post_json("/api/scouting/nfhs/credentials", {"email": "coach@example.com", "password": "good-pw"})
    saved = env.one("SELECT * FROM nfhs_credentials")
    r = env.post_json("/api/scouting/nfhs/login", {"email": "typo@example.com", "password": "wrong"})
    assert r.get_json()["success"] is False
    r = env.post_json("/api/scouting/nfhs/login", {"email": "coach@example.com", "password": "wrong-too"})
    assert r.get_json()["success"] is False
    with env.app.test_request_context():
        assert scouting._get_stored_credentials() == ("coach@example.com", "good-pw")
    assert env.q("SELECT * FROM nfhs_credentials") == [saved]  # nothing added or re-labelled
    info = env.json("/api/scouting/nfhs/credentials")
    assert (info["email"], info["last_login_status"]) == ("coach@example.com", "success")
