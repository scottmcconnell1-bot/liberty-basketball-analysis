"""Trim saved game film with ffmpeg (background jobs)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from copy import deepcopy
from datetime import datetime

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_JOB_TTL_SECONDS = 60 * 60


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffprobe_duration_ms(video_path: str) -> int | None:
    """Return video duration in milliseconds using ffprobe or OpenCV."""
    if shutil.which("ffprobe"):
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    video_path,
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(float(result.stdout.strip()) * 1000)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            pass

    try:
        import cv2

        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        cap.release()
        if frames > 0 and fps > 0:
            return int(frames / fps * 1000)
    except Exception:
        pass
    return None


def trim_video_file(input_path: str, output_path: str, start_ms: int, end_ms: int) -> None:
    """Fast trim using stream copy (keyframe-aligned)."""
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg is not installed. Install ffmpeg and restart the app.")

    start_sec = max(0, start_ms) / 1000.0
    duration_sec = max(0, end_ms - start_ms) / 1000.0
    if duration_sec <= 0:
        raise ValueError("Trim end must be after trim start")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_sec:.3f}",
        "-i",
        input_path,
        "-t",
        f"{duration_sec:.3f}",
        "-c",
        "copy",
        "-avoid_negative_ts",
        "make_zero",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60 * 60 * 4)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "ffmpeg failed")[-500:]
        raise RuntimeError(tail)
    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise RuntimeError("ffmpeg produced an empty output file")


def _now() -> float:
    return time.time()


def _prune_old_jobs() -> None:
    cutoff = _now() - _JOB_TTL_SECONDS
    stale = [job_id for job_id, job in _jobs.items() if job.get("updated_at", 0) < cutoff]
    for job_id in stale:
        _jobs.pop(job_id, None)


def _public_job(job: dict) -> dict:
    payload = {
        "job_id": job["job_id"],
        "status": job["status"],
        "message": job.get("message", ""),
        "error": job.get("error"),
        "source_video_id": job.get("source_video_id"),
    }
    if job.get("status") == "complete":
        payload.update({
            "video_id": job.get("video_id"),
            "stored_filename": job.get("stored_filename"),
            "game_id": job.get("game_id"),
            "file_size": job.get("file_size"),
            "redirect_url": job.get("redirect_url"),
            "videos_url": job.get("videos_url"),
        })
    return payload


def get_trim_job(job_id: str) -> dict | None:
    with _jobs_lock:
        _prune_old_jobs()
        job = _jobs.get(job_id)
        return deepcopy(_public_job(job)) if job else None


def _update_job(job_id: str, **fields) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)
            _jobs[job_id]["updated_at"] = _now()


def start_trim_job(*, app, video_row: dict, start_ms: int, end_ms: int, label: str | None = None) -> str:
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _prune_old_jobs()
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "starting",
            "message": "Starting trim…",
            "source_video_id": video_row["id"],
            "error": None,
            "created_at": _now(),
            "updated_at": _now(),
        }

    thread = threading.Thread(
        target=_run_trim_job,
        args=(job_id, app, dict(video_row), start_ms, end_ms, label),
        daemon=True,
        name=f"video-trim-{job_id[:8]}",
    )
    thread.start()
    return job_id


def _run_trim_job(
    job_id: str,
    app,
    video_row: dict,
    start_ms: int,
    end_ms: int,
    label: str | None,
) -> None:
    try:
        with app.app_context():
            from helpers import film_page_path, get_db, videos_page_path

            input_path = os.path.abspath(video_row["file_path"])
            if not os.path.exists(input_path):
                raise FileNotFoundError(f"Source video not found: {input_path}")

            duration_ms = ffprobe_duration_ms(input_path)
            if duration_ms is not None and end_ms > duration_ms + 1000:
                raise ValueError(f"End time exceeds video duration ({duration_ms // 1000}s)")

            upload_dir = app.config.get("UPLOAD_FOLDER", "uploads")
            stem, ext = os.path.splitext(video_row["stored_filename"])
            if not ext:
                ext = ".mp4"
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            stored_filename = f"{stem}_trim_{ts}{ext}"
            output_path = os.path.join(upload_dir, stored_filename)

            _update_job(job_id, status="trimming", message="Trimming video with ffmpeg…")
            trim_video_file(input_path, output_path, start_ms, end_ms)

            file_size = os.path.getsize(output_path)
            safe_label = (label or "trimmed").strip() or "trimmed"
            original_filename = f"{video_row['original_filename']} ({safe_label})"
            game_id = f"{video_row['game_id']}_trim_{ts}"

            db = get_db()
            video_cur = db.execute(
                """INSERT INTO videos (original_filename, stored_filename, file_path, file_size_bytes,
                                       opponent, game_id, relational_game_id, is_duplicate, duplicate_of_id)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    original_filename,
                    stored_filename,
                    output_path,
                    file_size,
                    video_row.get("opponent"),
                    game_id,
                    video_row.get("relational_game_id"),
                    0,
                    video_row["id"],
                ),
            )
            db.commit()

            film_url = film_page_path(stored_filename, game_id)
            _update_job(
                job_id,
                status="complete",
                message="Trim complete",
                video_id=video_cur.lastrowid,
                stored_filename=stored_filename,
                game_id=game_id,
                file_size=file_size,
                redirect_url=film_url,
                videos_url=videos_page_path(),
            )
    except Exception as exc:
        _update_job(job_id, status="error", error=str(exc), message=str(exc))


def parse_time_input(value: str) -> int | None:
    """Parse hh:mm:ss, mm:ss, or plain seconds into milliseconds."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", raw):
        return int(float(raw) * 1000)
    parts = raw.split(":")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        return None
    if len(nums) == 2:
        minutes, seconds = nums
        return int((minutes * 60 + seconds) * 1000)
    if len(nums) == 3:
        hours, minutes, seconds = nums
        return int((hours * 3600 + minutes * 60 + seconds) * 1000)
    return None
