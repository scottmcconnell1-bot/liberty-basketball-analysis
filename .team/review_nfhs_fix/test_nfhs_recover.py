"""Tests for recovering a finished NFHS download when yt-dlp's last step fails."""
import shutil
import subprocess
import sys

import pytest

import nfhs
from nfhs import _is_good_mp4, _probe_video, _recover_finished_download

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="needs ffmpeg + ffprobe"
)


def _make(path, fmt):
    """3 s test video with AAC audio, as MP4 ('mp4') or raw HLS-style MPEG-TS ('mpegts')."""
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=25",
         "-f", "lavfi", "-i", "sine=frequency=440", "-t", "3", "-c:v", "libx264", "-c:a", "aac",
         "-f", fmt, str(path)],
        check=True,
    )


def test_good_mp4_is_accepted_unchanged(tmp_path):
    out = tmp_path / "nfhs_gamtest.mp4"
    _make(out, "mp4")
    before = out.read_bytes()
    ok, done = _recover_finished_download(str(out))
    assert ok and "complete" in done
    assert out.read_bytes() == before


def test_unrepaired_stream_is_remuxed_to_mp4(tmp_path):
    out = tmp_path / "nfhs_gamtest.mp4"
    _make(out, "mpegts")  # what yt-dlp leaves when its fixup step fails
    assert "mpegts" in _probe_video(str(out))["format"]
    ok, done = _recover_finished_download(str(out))
    assert ok and "repaired" in done
    assert _is_good_mp4(str(out))
    assert not (tmp_path / "nfhs_gamtest.filmtool_fix.mp4").exists()


def test_leftover_fixup_output_is_used(tmp_path):
    out = tmp_path / "nfhs_gamtest.mp4"
    _make(out, "mpegts")
    _make(tmp_path / "nfhs_gamtest.temp.mp4", "mp4")  # fixup finished, rename failed
    ok, done = _recover_finished_download(str(out))
    assert ok and "interrupted" in done
    assert _is_good_mp4(str(out))
    assert not (tmp_path / "nfhs_gamtest.temp.mp4").exists()


def test_garbage_file_is_rejected(tmp_path):
    out = tmp_path / "nfhs_gamtest.mp4"
    out.write_bytes(b"not a video" * 1000)
    ok, _ = _recover_finished_download(str(out))
    assert not ok


def test_cut_off_mp4_is_rejected(tmp_path):
    good = tmp_path / "good.mp4"
    _make(good, "mp4")
    out = tmp_path / "nfhs_gamtest.mp4"
    out.write_bytes(good.read_bytes()[: good.stat().st_size // 2])
    ok, _ = _recover_finished_download(str(out))
    assert not ok


def test_download_succeeds_with_warning_when_ytdlp_fails_at_the_end(tmp_path, monkeypatch):
    """Full download_nfhs_vod path: fake yt-dlp writes a raw stream, then exits 1."""
    src = tmp_path / "src.ts"
    _make(src, "mpegts")
    fake = tmp_path / "fake_ytdlp.py"
    fake.write_text(
        "import shutil, sys\n"
        "out = sys.argv[sys.argv.index('-o') + 1]\n"
        f"shutil.copy({str(src)!r}, out)\n"
        "print('ERROR: Postprocessing: Conversion failed!')\n"
        "sys.exit(1)\n"
    )
    monkeypatch.setattr(nfhs, "get_nfhs_token", lambda e, p: "SECRET_TOKEN_123")
    monkeypatch.setattr(nfhs, "_yt_dlp_available", lambda: True)
    monkeypatch.setattr(nfhs, "_yt_dlp_command", lambda: [sys.executable, str(fake)])
    monkeypatch.setattr(nfhs, "_NFHS_LOG_DIR", str(tmp_path / "logs"))

    res = nfhs.download_nfhs_vod("gamtest12345", "e", "p", str(tmp_path / "up"))
    assert res["success"], res
    assert "warning" in res and "repaired" in res["warning"]
    assert _is_good_mp4(res["file_path"])
    log = open(res["log_path"], encoding="utf-8").read()
    assert "Conversion failed" in log and "SECRET_TOKEN_123" not in log


def test_download_still_fails_when_no_usable_file(tmp_path, monkeypatch):
    fake = tmp_path / "fake_ytdlp.py"
    fake.write_text("import sys\nprint('ERROR: HTTP Error 403')\nsys.exit(1)\n")
    monkeypatch.setattr(nfhs, "get_nfhs_token", lambda e, p: "SECRET_TOKEN_123")
    monkeypatch.setattr(nfhs, "_yt_dlp_available", lambda: True)
    monkeypatch.setattr(nfhs, "_yt_dlp_command", lambda: [sys.executable, str(fake)])
    monkeypatch.setattr(nfhs, "_NFHS_LOG_DIR", str(tmp_path / "logs"))

    res = nfhs.download_nfhs_vod("gamtest12345", "e", "p", str(tmp_path / "up"))
    assert not res["success"]
    assert "403" in res["error"] and "Full log" in res["error"]
    assert "SECRET_TOKEN_123" not in res["error"]
