"""Tests for NFHS download registration and upload behavior."""
import io
import os

import pytest

from nfhs import (
    _yt_dlp_available,
    _yt_dlp_command,
    extract_nfhs_game_id,
    parse_nfhs_input,
    register_nfhs_download,
)


@pytest.mark.parametrize("raw,expected", [
    ("gamfad8d650d0", "gamfad8d650d0"),
    (
        "https://www.nfhsnetwork.com/events/caldwell-high-school-caldwell-id/gamfad8d650d0",
        "gamfad8d650d0",
    ),
    (
        "https://www.nfhsnetwork.com/events/liberty-charter-school/gam12d9559efc?autoplay=true",
        "gam12d9559efc",
    ),
    ("www.nfhsnetwork.com/events/some-school/gamabc1234567", "gamabc1234567"),
    ("https://www.nfhsnetwork.com/game/gamabc1234567", "gamabc1234567"),
])
def test_extract_nfhs_game_id_supports_events_urls(raw, expected):
    assert extract_nfhs_game_id(raw) == expected


def test_parse_nfhs_input_preserves_watch_url():
    url = "https://www.nfhsnetwork.com/events/caldwell-high-school-caldwell-id/gamfad8d650d0"
    parsed = parse_nfhs_input(url)
    assert parsed["game_id"] == "gamfad8d650d0"
    assert parsed["watch_url"] == url


def test_extract_nfhs_game_id_rejects_garbage():
    assert extract_nfhs_game_id("https://example.com/not-nfhs") is None


def test_register_nfhs_download_creates_video_record(app, tmp_path):
    video_path = tmp_path / "nfhs_gam123.mp4"
    video_path.write_bytes(b"fake video bytes")

    with app.app_context():
        from helpers import get_db

        db = get_db()
        saved = register_nfhs_download(
            db,
            str(video_path),
            "gam123",
            home_team="Liberty Charter",
            away_team="Riverside",
        )
        db.commit()

        row = db.execute(
            "SELECT * FROM videos WHERE id=?",
            (saved["video_id"],),
        ).fetchone()
        game_row = db.execute(
            "SELECT * FROM games WHERE id=?",
            (saved["relational_game_id"],),
        ).fetchone()
        source_row = db.execute(
            "SELECT * FROM sources WHERE game_id=? AND source_type='nfhs_vod'",
            (saved["relational_game_id"],),
        ).fetchone()

    assert saved["already_saved"] is False
    assert row is not None
    assert row["stored_filename"] == "nfhs_gam123.mp4"
    assert row["opponent"] == "Riverside"
    assert row["game_id"].startswith("nfhs_gam123_")
    assert game_row is not None
    assert game_row["nfhs_game_id"] == "gam123"
    assert source_row is not None
    assert source_row["source_path"] == str(video_path)


def test_register_nfhs_download_is_idempotent(app, tmp_path):
    video_path = tmp_path / "nfhs_gam456.mp4"
    video_path.write_bytes(b"fake video bytes")

    with app.app_context():
        from helpers import get_db

        db = get_db()
        first = register_nfhs_download(db, str(video_path), "gam456", opponent_name="Opponent")
        db.commit()
        second = register_nfhs_download(db, str(video_path), "gam456", opponent_name="Opponent")

    assert first["video_id"] == second["video_id"]
    assert second["already_saved"] is True


def test_upload_chunk_tag_only_skips_analysis(client, app):
    """Chunked tag-only uploads should save the video without queueing AI analysis."""
    import uuid

    chunk = io.BytesIO(b"x" * 1024)
    data = {
        "upload_id": f"testupload{uuid.uuid4().hex}",
        "chunk_index": 0,
        "total_chunks": 1,
        "filename": "game.mp4",
        "opponent": "Riverside",
        "upload_mode": "tag_only",
        "file": (chunk, "chunk.bin"),
    }
    resp = client.post("/api/upload_chunk", data=data, content_type="multipart/form-data")
    if resp.status_code != 200:
        pytest.fail(resp.get_data(as_text=True))
    payload = resp.get_json()
    assert payload["status"] == "complete"
    assert "redirect_url" in payload

    with app.app_context():
        from helpers import get_db

        db = get_db()
        video = db.execute("SELECT * FROM videos ORDER BY id DESC LIMIT 1").fetchone()
        runs = db.execute("SELECT COUNT(*) AS c FROM analysis_runs").fetchone()["c"]
    assert video is not None
    assert runs == 0


def test_yt_dlp_command_prefers_module_fallback():
    cmd = _yt_dlp_command()
    assert cmd
    assert cmd[-1] != ""


def test_yt_dlp_available_after_install():
    """yt-dlp should be listed in requirements-dev and importable in CI."""
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        pytest.skip("yt-dlp not installed in this environment yet")
    assert _yt_dlp_available() is True


def test_parse_yt_dlp_progress_line():
    from nfhs import _parse_yt_dlp_progress

    parsed = _parse_yt_dlp_progress("[download]  45.2% of ~  2.50GiB at  5.00MiB/s ETA 05:30")
    assert parsed is not None
    assert parsed["percent"] == 45.2
    assert parsed["speed"] == "5.00MiB/s"
    assert parsed["eta"] == "05:30"


def test_format_section_time():
    from nfhs import _format_section_time

    assert _format_section_time(0) == "0:00"
    assert _format_section_time(90_000) == "1:30"
    assert _format_section_time(3_705_000) == "1:01:45"


def test_hls_segment_index_from_log_line():
    from nfhs import _hls_segment_index

    assert _hls_segment_index(
        "[https @ 0000] Opening 'https://d1.cloudfront.net/hd116.ts' for reading"
    ) == 116
    assert _hls_segment_index("[download]  12.0% of 1.00GiB at 5.00MiB/s ETA 02:00") is None


def test_friendly_download_phase_hides_technical_logs():
    from nfhs import _friendly_download_phase, _parse_yt_dlp_progress

    assert _friendly_download_phase("[NFHSNetwork] Extracting URL: https://example.com/game/gam123") == "Connecting to NFHS…"
    assert _friendly_download_phase("[download]  12.0% of 1.00GiB at 5.00MiB/s ETA 02:00") is None
    assert _friendly_download_phase(
        "[https @ 0000] Opening 'https://d1.cloudfront.net/hd116.ts' for reading"
    ) is None
    parsed = _parse_yt_dlp_progress("[download]  12.0% of 1.00GiB at 5.00MiB/s ETA 02:00")
    assert parsed["message"] == "Downloading… 12.0%"


def test_film_page_path_without_request_context():
    from helpers import film_page_path

    assert film_page_path("nfhs_gam1.mp4", "nfhs_gam1_abc") == "/film/nfhs_gam1.mp4?game_id=nfhs_gam1_abc"


def test_nfhs_download_status_missing_job(client):
    resp = client.get("/api/scouting/nfhs/download/does-not-exist")
    assert resp.status_code == 404


def test_nfhs_download_cancel_missing_job(client):
    resp = client.post("/api/scouting/nfhs/download/does-not-exist/cancel")
    assert resp.status_code == 409


def test_nfhs_download_cancel_marks_job_cancelled():
    import nfhs_download_jobs as jobs
    from nfhs import NfhsDownloadControl

    job_id = "testjob123"
    with jobs._jobs_lock:
        jobs._jobs[job_id] = {
            "job_id": job_id,
            "status": "downloading",
            "percent": 10,
            "message": "Downloading",
            "updated_at": jobs._now(),
        }
        jobs._controls[job_id] = NfhsDownloadControl()

    ok, message = jobs.cancel_download_job(job_id)
    assert ok is True
    job = jobs.get_download_job(job_id)
    assert job["status"] == "cancelled"


def test_start_video_analysis_for_library_video(client, db, monkeypatch, tmp_path):
    import blueprints.ai as ai_module

    video_path = tmp_path / "nfhs_gam999.mp4"
    video_path.write_bytes(b"fake video")
    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("nfhs_gam999.mp4", "nfhs_gam999.mp4", str(video_path), 16, "Opponent", "nfhs_gam999_20260101"),
    )
    db.commit()

    monkeypatch.setattr(ai_module, "ai_runtime_available", lambda: True)
    monkeypatch.setattr(ai_module, "validate_video_for_analysis", lambda _path: (True, None))
    monkeypatch.setattr(ai_module, "validate_ai_models_for_analysis", lambda _settings=None: (True, None))
    started = []
    monkeypatch.setattr(ai_module, "start_analysis_subprocess", lambda *args, **kwargs: started.append(args))

    resp = client.post("/api/videos/1/analyze")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "started"
    assert payload["game_id"] == "nfhs_gam999_20260101"
    assert started

    row = db.execute("SELECT analysis_key, run_kind, status FROM analysis_runs").fetchone()
    assert row["analysis_key"] == "nfhs_gam999_20260101"
    assert row["run_kind"] == "primary"
    assert row["status"] == "pending"


def test_start_video_analysis_rejects_duplicate_running_job(client, db, monkeypatch, tmp_path):
    import blueprints.ai as ai_module

    video_path = tmp_path / "nfhs_gam888.mp4"
    video_path.write_bytes(b"fake video")
    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("nfhs_gam888.mp4", "nfhs_gam888.mp4", str(video_path), 16, "Opponent", "nfhs_gam888_20260101"),
    )
    db.execute(
        "INSERT INTO analysis_runs (analysis_key, video_path, status) VALUES (?, ?, ?)",
        ("nfhs_gam888_20260101", str(video_path), "running"),
    )
    db.commit()

    monkeypatch.setattr(ai_module, "ai_runtime_available", lambda: True)
    monkeypatch.setattr(ai_module, "validate_video_for_analysis", lambda _path: (True, None))
    monkeypatch.setattr(ai_module, "validate_ai_models_for_analysis", lambda _settings=None: (True, None))
    monkeypatch.setattr(ai_module, "start_analysis_subprocess", lambda *args, **kwargs: None)

    resp = client.post("/api/videos/1/analyze")
    assert resp.status_code == 409
    assert "already in progress" in resp.get_json()["error"]


def test_start_video_analysis_requires_ai_packages(client, db, tmp_path):
    video_path = tmp_path / "nfhs_gam777.mp4"
    video_path.write_bytes(b"fake video")
    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("nfhs_gam777.mp4", "nfhs_gam777.mp4", str(video_path), 16, "Opponent", "nfhs_gam777_20260101"),
    )
    db.commit()

    resp = client.post("/api/videos/1/analyze")
    assert resp.status_code == 503
    payload = resp.get_json()
    assert payload["code"] == "ai_packages_unavailable"
    assert "opencv" in payload["error"].lower() or "ultralytics" in payload["error"].lower()
    assert db.execute("SELECT COUNT(*) AS c FROM analysis_runs").fetchone()["c"] == 0


def test_ai_analysis_log_path_uses_project_logs_dir():
    from helpers import ai_analysis_log_path

    path = ai_analysis_log_path("nfhs_gam123_test")
    assert os.path.basename(path).startswith("ai-nfhs_gam123_test")
    assert os.path.basename(os.path.dirname(path)) == "logs"
    assert os.path.isdir(os.path.dirname(path))


def test_start_video_analysis_supersedes_stale_pending(client, db, monkeypatch, tmp_path):
    import blueprints.ai as ai_module

    video_path = tmp_path / "nfhs_gam555.mp4"
    video_path.write_bytes(b"fake video")
    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("nfhs_gam555.mp4", "nfhs_gam555.mp4", str(video_path), 16, "Opponent", "nfhs_gam555_20260101"),
    )
    db.execute(
        "INSERT INTO analysis_runs (analysis_key, video_path, status) VALUES (?, ?, ?)",
        ("nfhs_gam555_20260101", str(video_path), "pending"),
    )
    db.commit()

    monkeypatch.setattr(ai_module, "ai_runtime_available", lambda: True)
    monkeypatch.setattr(ai_module, "validate_video_for_analysis", lambda _path: (True, None))
    monkeypatch.setattr(ai_module, "validate_ai_models_for_analysis", lambda _settings=None: (True, None))
    monkeypatch.setattr(ai_module, "start_analysis_subprocess", lambda *args, **kwargs: None)

    resp = client.post("/api/videos/1/analyze")
    assert resp.status_code == 200

    rows = db.execute("SELECT status, error_message, progress_step FROM analysis_runs ORDER BY id").fetchall()
    assert rows[0]["status"] == "cancelled"
    assert rows[0]["error_message"] is None
    assert "superseded" in (rows[0]["progress_step"] or "").lower()
    assert rows[1]["status"] == "pending"


def test_regenerate_video_events(client, db, monkeypatch, tmp_path):
    video_path = tmp_path / "nfhs_gam444.mp4"
    video_path.write_bytes(b"fake video")
    db.execute(
        """INSERT INTO videos
           (original_filename, stored_filename, file_path, file_size_bytes, opponent, game_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("nfhs_gam444.mp4", "nfhs_gam444.mp4", str(video_path), 16, "Opponent", "nfhs_gam444_20260101"),
    )
    db.execute(
        """INSERT INTO analysis_runs (analysis_key, video_path, status)
           VALUES (?, ?, ?)""",
        ("nfhs_gam444_20260101", str(video_path), "completed"),
    )
    db.execute(
        """INSERT INTO detections
           (game_id, frame_number, timestamp_ms, object_class, confidence, x_center, y_center, width, height)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        ("nfhs_gam444_20260101", 1, 0, "person", 0.9, 10, 10, 5, 5),
    )
    db.execute(
        """INSERT INTO events (game_id, event_type, timestamp_ms)
           VALUES (?, ?, ?)""",
        ("nfhs_gam444_20260101", "possession_change", 100),
    )
    db.commit()

    monkeypatch.setattr("helpers.module_available", lambda name: name == "sklearn")
    monkeypatch.setattr("event_generator.main", lambda *args, **kwargs: True)
    monkeypatch.setattr("film_analysis.run_enhanced_analysis", lambda *args, **kwargs: None)

    resp = client.post("/api/videos/1/regenerate-events")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "events_regenerated"
