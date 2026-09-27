"""Regression tests for the analysis slowdown found on the live server (2026-09-27).

The frame loop reads each frame's detections back with
``WHERE game_id = ? AND frame_number = ?``. With no index that query scans the whole
detections table every frame, so analysis slowed as the table grew (benchmark:
11.2 fps empty, 7.7 fps at 1M rows, 5.0 fps at 3M; live ~1 fps). See
docs/validation/analysis_speed.md.
"""
from __future__ import annotations

import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRAME_LOOKUP = (
    "SELECT id, x_center, y_center, width, height, confidence FROM detections "
    "WHERE game_id = ? AND frame_number = ? AND object_class = 'person' ORDER BY id"
)


def _plan(conn, sql, params):
    return " ".join(str(r[-1]) for r in conn.execute("EXPLAIN QUERY PLAN " + sql, params))


def test_new_database_indexes_the_per_frame_detection_lookup(app):
    conn = sqlite3.connect(app.config["DATABASE"])
    plan = _plan(conn, FRAME_LOOKUP, ("g", 1))
    conn.close()
    assert "USING INDEX" in plan and "SCAN detections" not in plan, plan


def test_existing_database_gets_the_index_at_startup(app):
    import helpers

    conn = sqlite3.connect(app.config["DATABASE"])
    conn.execute("DROP INDEX IF EXISTS idx_detections_game_frame")
    conn.commit()
    assert "SCAN detections" in _plan(conn, FRAME_LOOKUP, ("g", 1))  # the old, unindexed state
    conn.close()
    with app.app_context():
        helpers.ensure_db()
    conn = sqlite3.connect(app.config["DATABASE"])
    assert "USING INDEX" in _plan(conn, FRAME_LOOKUP, ("g", 1))
    conn.close()


def test_analyzer_adds_the_index_before_its_frame_loop(tmp_path):
    """The teach loop starts analyses in separate processes, before any app restart."""
    pytest.importorskip("cv2")
    pytest.importorskip("ultralytics")
    import ai_analyzer

    db_path = tmp_path / "live.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE detections (id INTEGER PRIMARY KEY, game_id TEXT, frame_number INTEGER,
                                    object_class TEXT, x_center INTEGER, y_center INTEGER,
                                    width INTEGER, height INTEGER, confidence REAL)"""
    )
    conn.commit()
    ai_analyzer.ensure_detection_indexes(conn)
    assert "USING INDEX" in _plan(conn, FRAME_LOOKUP, ("g", 1))
    conn.close()


def test_detection_index_helper_is_shared_and_idempotent(tmp_path):
    import helpers

    conn = sqlite3.connect(tmp_path / "x.db")
    conn.execute("CREATE TABLE detections (id INTEGER PRIMARY KEY, game_id TEXT, frame_number INTEGER)")
    helpers.ensure_detection_indexes(conn)
    helpers.ensure_detection_indexes(conn)  # second call is a no-op
    names = {r[1] for r in conn.execute("PRAGMA index_list(detections)")}
    assert "idx_detections_game_frame" in names
    # a database without the table (fresh install before schema) is left alone
    empty = sqlite3.connect(tmp_path / "empty.db")
    helpers.ensure_detection_indexes(empty)
    empty.close()
    conn.close()


# ── Jersey OCR ran on the CPU even on a CUDA machine ─────────────────────────

def test_jersey_ocr_uses_the_gpu_when_cuda_is_available(monkeypatch):
    import types

    import jersey_ocr

    created = []

    class FakeReader:
        def __init__(self, langs, gpu=False, verbose=True):
            created.append(gpu)

    monkeypatch.setitem(sys.modules, "easyocr", types.SimpleNamespace(Reader=FakeReader))
    fake_torch = types.SimpleNamespace(cuda=types.SimpleNamespace(is_available=lambda: True))
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(jersey_ocr, "_OCR_ENGINE", None)
    monkeypatch.setattr(jersey_ocr, "_OCR_UNAVAILABLE", False)
    assert jersey_ocr._get_ocr_engine() is not None
    assert created == [True]

    fake_torch.cuda.is_available = lambda: False
    monkeypatch.setattr(jersey_ocr, "_OCR_ENGINE", None)
    jersey_ocr._get_ocr_engine()
    assert created == [True, False]


# ── Docker image could not build ─────────────────────────────────────────────

def test_dockerfile_copies_every_requirements_file_it_installs():
    dockerfile = (ROOT / "Dockerfile").read_text()
    copied = set()
    for line in dockerfile.splitlines():
        if line.startswith("COPY ") and "requirements" in line:
            copied.update(part for part in line.split()[1:-1])
    needed = {"requirements.docker.txt"}
    todo = ["requirements.docker.txt"]
    while todo:
        text = (ROOT / todo.pop()).read_text()
        for inc in re.findall(r"^-r\s+(\S+)", text, re.M):
            if inc not in needed:
                needed.add(inc)
                todo.append(inc)
    assert needed <= copied, f"Dockerfile installs {sorted(needed)} but copies only {sorted(copied)}"


# ── /sw.js 404 on the live server (started with `python app.py`) ─────────────

def test_service_worker_is_served_when_app_runs_as_a_script(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = dict(os.environ, PORT=str(port), LIBERTY_DATABASE=str(tmp_path / "app.db"),
               LIBERTY_UPLOAD_FOLDER=str(tmp_path / "uploads"), FLASK_DEBUG="0")
    proc = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import urllib.request

        deadline = time.time() + 30
        status = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/sw.js", timeout=2) as resp:
                    status = resp.status
                    body = resp.read()
                break
            except urllib.error.HTTPError as exc:
                status = exc.code
                break
            except OSError:
                time.sleep(0.3)
        assert status == 200, f"/sw.js returned {status}"
        assert b"CACHE_NAME" in body
    finally:
        proc.terminate()
        proc.wait(timeout=10)
