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
