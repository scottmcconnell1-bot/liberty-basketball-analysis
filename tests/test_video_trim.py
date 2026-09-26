"""Tests for video trim API and helpers."""
import os

import pytest

from video_trim import ffmpeg_available, parse_time_input, trim_video_file


@pytest.mark.parametrize("raw,expected", [
    ("0:30", 30000),
    ("1:23:45", 5025000),
    ("90", 90000),
    ("1:30.5", 90500),
])
def test_parse_time_input(raw, expected):
    assert parse_time_input(raw) == expected


def test_parse_time_input_rejects_garbage():
    assert parse_time_input("not-a-time") is None


def test_trim_video_api_requires_ffmpeg(client, db, monkeypatch, tmp_path):
    video_path = tmp_path / "game.mp4"
    video_path.write_bytes(b"not really mp4")
    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("game.mp4", "game.mp4", str(video_path), 16, "Opponent", "game_1"),
    )
    db.commit()

    monkeypatch.setattr("video_trim.ffmpeg_available", lambda: False)
    resp = client.post("/api/videos/1/trim", json={"start_ms": 0, "end_ms": 1000})
    assert resp.status_code == 503
    assert resp.get_json()["code"] == "ffmpeg_missing"


def test_trim_video_api_validates_range(client, db, tmp_path, monkeypatch):
    video_path = tmp_path / "game2.mp4"
    video_path.write_bytes(b"fake")
    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("game2.mp4", "game2.mp4", str(video_path), 16, "Opponent", "game_2"),
    )
    db.commit()
    monkeypatch.setattr("video_trim.ffmpeg_available", lambda: True)
    monkeypatch.setattr("video_trim.ffprobe_duration_ms", lambda _p: 60000)

    resp = client.post("/api/videos/1/trim", json={"start_ms": 5000, "end_ms": 1000})
    assert resp.status_code == 400

    resp = client.post("/api/videos/1/trim", json={"start_ms": 0, "end_ms": 5000})
    assert resp.status_code == 200
    assert resp.get_json()["job_id"]


def test_trim_job_status_missing(client):
    resp = client.get("/api/videos/trim/does-not-exist")
    assert resp.status_code == 404


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
def test_trim_video_file_writes_output(tmp_path):
    import subprocess

    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=160x120:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-shortest", "-c:v", "libx264", "-c:a", "aac", str(input_path),
        ],
        check=True,
    )
    trim_video_file(str(input_path), str(output_path), 500, 2000)
    assert output_path.exists()
    assert os.path.getsize(output_path) > 0


def test_trim_stamp_is_unique_per_job_within_one_second():
    from video_trim import trim_stamp

    a, b = trim_stamp("aaaaaaaa11111111"), trim_stamp("bbbbbbbb22222222")
    assert a != b
    assert a.endswith("_aaaaaaaa") and b.endswith("_bbbbbbbb")


def test_get_trim_job_finds_job_started_by_another_worker(app, tmp_path, monkeypatch):
    """Simulate gunicorn worker B polling a job that worker A started (A's dict is not shared)."""
    import json
    import time

    import video_trim

    monkeypatch.setitem(app.config, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(video_trim, "_jobs", {})  # this process knows nothing about the job
    jobs_dir = tmp_path / ".trim_jobs"
    jobs_dir.mkdir()
    job_id = "0123456789abcdef0123456789abcdef"
    (jobs_dir / f"{job_id}.json").write_text(json.dumps({
        "job_id": job_id, "status": "trimming", "message": "Trimming video with ffmpeg…",
        "error": None, "source_video_id": 7, "created_at": time.time(), "updated_at": time.time(),
    }))
    with app.app_context():
        job = video_trim.get_trim_job(job_id)
    assert job and job["status"] == "trimming" and job["source_video_id"] == 7

    # Expired files are ignored; malformed ids never touch the filesystem
    (jobs_dir / f"{job_id}.json").write_text(json.dumps({"job_id": job_id, "status": "complete", "updated_at": 0}))
    with app.app_context():
        assert video_trim.get_trim_job(job_id) is None
        assert video_trim.get_trim_job("../../etc/passwd") is None


def test_start_trim_job_persists_state_for_other_workers(app, tmp_path, monkeypatch):
    import video_trim

    monkeypatch.setitem(app.config, "UPLOAD_FOLDER", str(tmp_path))
    monkeypatch.setattr(video_trim, "_jobs", {})
    monkeypatch.setattr(video_trim.threading, "Thread", lambda *a, **k: type("T", (), {"start": lambda self: None})())
    video_row = {"id": 3, "stored_filename": "g.mp4", "file_path": str(tmp_path / "g.mp4"),
                 "original_filename": "g.mp4", "game_id": "g", "opponent": "x"}
    job_id = video_trim.start_trim_job(app=app, video_row=video_row, start_ms=0, end_ms=1000)
    persisted = tmp_path / ".trim_jobs" / f"{job_id}.json"
    assert persisted.is_file()
    assert "_jobs_dir" not in persisted.read_text()  # private keys never written
