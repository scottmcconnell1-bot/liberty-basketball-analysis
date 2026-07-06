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


def test_nfhs_download_status_missing_job(client):
    resp = client.get("/api/scouting/nfhs/download/does-not-exist")
    assert resp.status_code == 404
