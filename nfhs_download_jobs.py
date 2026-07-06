"""Background NFHS download jobs with yt-dlp progress tracking."""

from __future__ import annotations

import threading
import time
import uuid
from copy import deepcopy

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
_JOB_TTL_SECONDS = 60 * 60


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
        "percent": job.get("percent", 0),
        "speed": job.get("speed"),
        "eta": job.get("eta"),
        "message": job.get("message", ""),
        "nfhs_game_id": job.get("nfhs_game_id"),
        "error": job.get("error"),
    }
    if job.get("status") == "complete":
        payload.update({
            "file_size": job.get("file_size"),
            "stored_filename": job.get("stored_filename"),
            "game_id": job.get("game_id"),
            "already_saved": job.get("already_saved", False),
            "redirect_url": job.get("redirect_url"),
            "videos_url": job.get("videos_url"),
        })
    return payload


def get_download_job(job_id: str) -> dict | None:
    with _jobs_lock:
        _prune_old_jobs()
        job = _jobs.get(job_id)
        return deepcopy(_public_job(job)) if job else None


def _update_job(job_id: str, **fields) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)
            _jobs[job_id]["updated_at"] = _now()


def start_download_job(
    *,
    app,
    game_id: str,
    email: str,
    password: str,
    output_dir: str,
    watch_url: str | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> str:
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _prune_old_jobs()
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "starting",
            "percent": 0,
            "speed": None,
            "eta": None,
            "message": "Starting download…",
            "nfhs_game_id": game_id,
            "error": None,
            "created_at": _now(),
            "updated_at": _now(),
        }

    thread = threading.Thread(
        target=_run_download_job,
        args=(job_id, app, game_id, email, password, output_dir, watch_url, start_ms, end_ms),
        daemon=True,
        name=f"nfhs-download-{job_id[:8]}",
    )
    thread.start()
    return job_id


def _run_download_job(
    job_id: str,
    app,
    game_id: str,
    email: str,
    password: str,
    output_dir: str,
    watch_url: str | None,
    start_ms: int | None,
    end_ms: int | None,
) -> None:
    from nfhs import download_nfhs_vod, lookup_game, register_nfhs_download

    def on_progress(percent, speed=None, eta=None, message=""):
        _update_job(
            job_id,
            status="downloading",
            percent=percent,
            speed=speed,
            eta=eta,
            message=message or f"Downloading… {percent:.1f}%",
        )

    _update_job(job_id, status="downloading", message="Connecting to NFHS…", percent=0)

    try:
        with app.app_context():
            result = download_nfhs_vod(
                game_id,
                email,
                password,
                output_dir,
                watch_url=watch_url,
                progress_callback=on_progress,
                start_ms=start_ms,
                end_ms=end_ms,
            )
            if not result["success"]:
                _update_job(job_id, status="error", error=result["error"], message=result["error"])
                return

            lookup = lookup_game(game_id, email, password)
            from helpers import film_page_path, get_db, videos_page_path

            db = get_db()
            saved = register_nfhs_download(
                db,
                result["file_path"],
                game_id,
                home_team=lookup.get("home_team") if lookup.get("success") else None,
                away_team=lookup.get("away_team") if lookup.get("success") else None,
                nfhs_url=watch_url,
            )
            db.commit()

            film_url = film_page_path(saved["stored_filename"], saved["game_id"])
            _update_job(
                job_id,
                status="complete",
                percent=100,
                message="Download complete",
                file_size=result["file_size"],
                stored_filename=saved["stored_filename"],
                game_id=saved["game_id"],
                already_saved=saved.get("already_saved", False),
                redirect_url=film_url,
                videos_url=videos_page_path(),
            )
    except Exception as exc:
        _update_job(job_id, status="error", error=str(exc), message=str(exc))
