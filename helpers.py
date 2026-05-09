"""
Shared helper functions for the Liberty Basketball Analysis app.

This module contains all utility functions, database helpers, and
business logic that was previously in app.py. Both app.py and the
blueprint modules import from here to avoid circular dependencies.
"""

import os
import importlib.util
import json
import re
import sqlite3
import subprocess
import time
from datetime import datetime
from functools import wraps
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from flask import g, current_app, request, render_template, abort, redirect, url_for, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from config import Config
from settings_store import AI_DEFAULTS, load_all_settings, save_settings

try:
    import psutil
except ImportError:  # pragma: no cover - optional at runtime
    psutil = None

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
POWER_SAMPLE_CACHE = {}

# ── Configuration ─────────────────────────────────────────


def feature_enabled(flag_name):
    return bool(get_runtime_settings()["features"].get(flag_name, False))


def analysis_option_enabled(option_name):
    return bool(get_runtime_settings()["analysis"].get(option_name, False))


def require_feature(flag_name):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not feature_enabled(flag_name):
                abort(404)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator




def get_runtime_settings():
    if "runtime_settings" not in g:
        g.runtime_settings = load_all_settings(
            feature_defaults=current_app.config.get("FEATURES", {}),
            analysis_defaults=current_app.config.get("ANALYSIS_CONFIG", {}),
            ai_defaults=AI_DEFAULTS,
            db=get_db(),
        )
    return g.runtime_settings


def build_process_snapshot(pid, fallback_name=None):
    if not psutil:
        return {
            "pid": pid,
            "name": fallback_name or f"PID {pid}",
            "cpu_percent": None,
            "memory_mb": None,
            "is_self_project": False,
        }

    try:
        proc = psutil.Process(pid)
        try:
            cwd = proc.cwd()
        except (psutil.AccessDenied, psutil.ZombieProcess, FileNotFoundError, OSError):
            cwd = ""
        try:
            cmdline = proc.cmdline()
        except (psutil.AccessDenied, psutil.ZombieProcess):
            cmdline = []
        is_self_project = bool(cwd and cwd.startswith(PROJECT_ROOT)) or any(
            part.startswith(PROJECT_ROOT) or part.endswith(("app.py", "ai_analyzer.py", "event_generator.py"))
            for part in cmdline
        )
        return {
            "pid": pid,
            "name": proc.name() or fallback_name or f"PID {pid}",
            "cpu_percent": proc.cpu_percent(interval=0.0),
            "memory_mb": round(proc.memory_info().rss / (1024 ** 2), 1),
            "is_self_project": is_self_project,
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return {
            "pid": pid,
            "name": fallback_name or f"PID {pid}",
            "cpu_percent": None,
            "memory_mb": None,
            "is_self_project": False,
        }


def parse_optional_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sample_cpu_power_watts():
    base_path = "/sys/class/powercap"
    if not os.path.isdir(base_path):
        return None

    now = time.monotonic()
    package_readings = []
    fallback_readings = []

    for root, _, files in os.walk(base_path):
        if "energy_uj" not in files:
            continue

        energy_path = os.path.join(root, "energy_uj")
        max_energy_path = os.path.join(root, "max_energy_range_uj")
        zone_name_path = os.path.join(root, "name")

        try:
            with open(energy_path, "r", encoding="utf-8") as handle:
                energy_uj = float(handle.read().strip())
            with open(zone_name_path, "r", encoding="utf-8") as handle:
                zone_name = handle.read().strip() or os.path.basename(root)
        except (OSError, ValueError):
            continue

        max_energy_uj = None
        if os.path.exists(max_energy_path):
            try:
                with open(max_energy_path, "r", encoding="utf-8") as handle:
                    max_energy_uj = float(handle.read().strip())
            except (OSError, ValueError):
                max_energy_uj = None

        previous = POWER_SAMPLE_CACHE.get(root)
        POWER_SAMPLE_CACHE[root] = {
            "energy_uj": energy_uj,
            "sample_time": now,
        }
        if not previous:
            continue

        delta_time = now - previous["sample_time"]
        if delta_time <= 0:
            continue

        delta_energy = energy_uj - previous["energy_uj"]
        if delta_energy < 0 and max_energy_uj:
            delta_energy += max_energy_uj
        if delta_energy < 0:
            continue

        watts = (delta_energy / 1_000_000.0) / delta_time
        if watts < 0 or watts > 1000:
            continue

        normalized_name = zone_name.lower()
        rel_depth = os.path.relpath(root, base_path).count(os.sep)
        if normalized_name.startswith("package-"):
            package_readings.append(watts)
        elif rel_depth == 0:
            fallback_readings.append(watts)

    if package_readings:
        return round(sum(package_readings), 1)
    if fallback_readings:
        return round(sum(fallback_readings), 1)
    return None


def build_resource_status():
    app_process = build_process_snapshot(os.getpid(), "Liberty app")
    virtual_memory = psutil.virtual_memory() if psutil else None
    gpu = {
        "available": False,
        "name": "Unavailable",
        "utilization_percent": None,
        "memory_used_mb": None,
        "memory_total_mb": None,
        "power_draw_watts": None,
        "power_limit_watts": None,
        "processes": [],
    }
    cpu_power_watts = sample_cpu_power_watts()

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,power.draw,power.limit",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            name, utilization, memory_used, memory_total, power_draw, power_limit = [
                part.strip() for part in result.stdout.splitlines()[0].split(",", 5)
            ]
            gpu.update({
                "available": True,
                "name": name,
                "utilization_percent": parse_optional_float(utilization),
                "memory_used_mb": parse_optional_float(memory_used),
                "memory_total_mb": parse_optional_float(memory_total),
                "power_draw_watts": parse_optional_float(power_draw),
                "power_limit_watts": parse_optional_float(power_limit),
            })
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        pass

    try:
        process_result = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if process_result.returncode == 0 and process_result.stdout.strip():
            gpu_processes = []
            for line in process_result.stdout.splitlines():
                parts = [part.strip() for part in line.split(",", 2)]
                if len(parts) != 3:
                    continue
                try:
                    pid = int(parts[0])
                    used_gpu_memory = float(parts[2])
                except ValueError:
                    continue
                snapshot = build_process_snapshot(pid, parts[1])
                snapshot["gpu_memory_mb"] = used_gpu_memory
                gpu_processes.append(snapshot)

            gpu["processes"] = sorted(
                gpu_processes,
                key=lambda row: row.get("gpu_memory_mb") or 0,
                reverse=True,
            )
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        pass

    gpu["process_count"] = len(gpu["processes"])
    gpu_power_watts = gpu.get("power_draw_watts")
    total_power_watts = None
    if cpu_power_watts is not None or gpu_power_watts is not None:
        total_power_watts = round(
            sum(value for value in (cpu_power_watts, gpu_power_watts) if value is not None),
            1,
        )

    return {
        "cpu": {
            "system_percent": psutil.cpu_percent(interval=0.0) if psutil else None,
            "process_percent": app_process["cpu_percent"],
        },
        "memory": {
            "system_percent": virtual_memory.percent if virtual_memory else None,
            "used_gb": round((virtual_memory.used / (1024 ** 3)), 2) if virtual_memory else None,
            "total_gb": round((virtual_memory.total / (1024 ** 3)), 2) if virtual_memory else None,
            "process_mb": app_process["memory_mb"],
        },
        "application": app_process,
        "gpu": gpu,
        "power": {
            "cpu_watts": cpu_power_watts,
            "gpu_watts": gpu_power_watts,
            "total_watts": total_power_watts,
        },
    }


def module_available(module_name):
    return importlib.util.find_spec(module_name) is not None


def list_ollama_models():
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return []

    if result.returncode != 0:
        return []

    models = []
    for index, line in enumerate(result.stdout.splitlines()):
        if index == 0 or not line.strip():
            continue
        parts = line.split()
        if parts:
            models.append(parts[0])
    return models


def call_ollama(prompt, model=None, timeout=60):
    """Call Ollama to generate a response. Returns (success, text_or_error)."""
    cmd = ["ollama", "run"]
    if model:
        cmd.append(model)
    else:
        cmd.append("llama3")
    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return False, "Ollama is not installed."
    except subprocess.TimeoutExpired:
        return False, "Ollama request timed out."
    except subprocess.SubprocessError as exc:
        return False, f"Ollama error: {exc}"
    if result.returncode != 0:
        return False, result.stderr.strip() or "Ollama returned an error."
    return True, result.stdout.strip()


def generate_practice_ai_notes_llm(practice, settings_snapshot=None):
    """Generate practice AI notes using Ollama LLM.

    Falls back gracefully when Ollama is unavailable.
    Returns (notes_text, source_tag) where source_tag is 'llm' or 'heuristic'.
    """
    if settings_snapshot is None:
        settings_snapshot = get_runtime_settings()
    provider = settings_snapshot.get("ai", {}).get("llm_provider", "none")
    model = settings_snapshot.get("ai", {}).get("llm_model", "")

    if provider != "ollama" or not model:
        return None, "none"

    available_models = list_ollama_models()
    if model not in available_models:
        return None, "none"

    plan_text = practice.get("plan_text") or ""
    coach_notes = practice.get("coach_notes") or ""
    practice_date = practice.get("practice_date", "")
    status = practice.get("status", "")

    prompt = (
        "You are an assistant basketball coach. Summarize this practice session "
        "and suggest what to focus on next.\n\n"
        f"Practice date: {practice_date}\n"
        f"Status: {status}\n"
        f"Practice plan:\n{plan_text or '(none)'}\n\n"
        f"Coach notes:\n{coach_notes or '(none)'}\n\n"
        "Respond in 3-4 sentences. First sentence: summarize the focus. "
        "Second: note any concerns from the coach notes. "
        "Third: recommend the next practice emphasis. "
        "Keep it concise and actionable."
    )

    ok, text = call_ollama(prompt, model=model)
    if ok and text:
        return text, "llm"
    return None, "none"


def build_settings_catalog():
    resource_status = build_resource_status()
    gpu = resource_status["gpu"]
    gpu_available = bool(gpu.get("available"))
    gpu_total_mb = gpu.get("memory_total_mb") or 0

    detector_options = [
        {
            "value": "yolov8n.pt",
            "label": "YOLOv8 Nano",
            "note": "Fastest option and the safest default on any hardware.",
        },
        {
            "value": "yolov8s.pt",
            "label": "YOLOv8 Small",
            "note": "Good balance of speed and accuracy on GPU, slower on CPU.",
        },
        {
            "value": "yolov8m.pt",
            "label": "YOLOv8 Medium",
            "note": "Heavier model; best reserved for stronger GPUs or slower offline runs.",
        },
        {
            "value": "yolo11n.pt",
            "label": "YOLO11 Nano",
            "note": "Newer lightweight Ultralytics detector with a similar footprint to YOLOv8 Nano.",
        },
        {
            "value": "yolo11s.pt",
            "label": "YOLO11 Small",
            "note": "Good next step if you want to compare a newer small detector against YOLOv8 Small.",
        },
        {
            "value": "yolo11m.pt",
            "label": "YOLO11 Medium",
            "note": "Higher quality option for slower offline reruns on stronger GPUs.",
        },
        {
            "value": "custom",
            "label": "Custom Ultralytics weights",
            "note": "Use any supported model name or local .pt path, including your own fine-tuned basketball weights.",
        },
    ]
    if gpu_available and gpu_total_mb >= 6000:
        detector_options[1]["recommended"] = True
    else:
        detector_options[0]["recommended"] = True

    device_options = [{"value": "auto", "label": "Auto-select (recommended)"}]
    if gpu_available:
        device_options.append({"value": "cuda", "label": f"GPU ({gpu['name']})"})
    device_options.append({"value": "cpu", "label": "CPU only"})

    ollama_models = list_ollama_models()
    llm_provider_options = [{"value": "none", "label": "Disabled"}]
    if ollama_models:
        llm_provider_options.append({"value": "ollama", "label": "Ollama (local)"})

    llm_model_options = []
    for model_name in ollama_models:
        note = "Lightweight"
        if ":8b" in model_name or "8b" in model_name:
            note = "Heavier"
        llm_model_options.append({"value": model_name, "label": f"{model_name} ({note})"})

    recommended_ollama_models = [
        {
            "value": "qwen2.5:3b",
            "label": "Qwen 2.5 3B",
            "fit": "Best lightweight general-purpose local model on this machine.",
        },
        {
            "value": "llama3.2:3b",
            "label": "Llama 3.2 3B",
            "fit": "Fast local model for summaries and quick prompts.",
        },
        {
            "value": "gemma3:4b",
            "label": "Gemma 3 4B",
            "fit": "Good small-model option if you want a different family than Llama/Qwen.",
        },
        {
            "value": "qwen2.5:7b",
            "label": "Qwen 2.5 7B",
            "fit": "Heavier but still reasonable for this hardware if you want stronger quality.",
        },
        {
            "value": "mistral:7b",
            "label": "Mistral 7B",
            "fit": "Good mid-sized fallback for analysis and comparisons.",
        },
        {
            "value": "llama3.1:8b",
            "label": "Llama 3.1 8B",
            "fit": "Largest practical local model for this setup; already usable but heavier.",
        },
    ]
    for model in recommended_ollama_models:
        model["installed"] = model["value"] in ollama_models
        if gpu_available and gpu_total_mb >= 6000 and model["value"] in {"qwen2.5:3b", "llama3.2:3b", "gemma3:4b"}:
            model["recommended"] = True
        elif not gpu_available and model["value"] in {"qwen2.5:3b", "llama3.2:3b"}:
            model["recommended"] = True

    return {
        "resource_status": resource_status,
        "packages": {
            "cv2": module_available("cv2"),
            "ultralytics": module_available("ultralytics"),
            "torch": module_available("torch"),
        },
        "detector_options": detector_options,
        "device_options": device_options,
        "frame_stride_options": [
            {"value": 1, "label": "Every frame (highest detail)"},
            {"value": 2, "label": "Every 2nd frame"},
            {"value": 4, "label": "Every 4th frame (fastest)"},
        ],
        "event_generator_mode_options": [
            {
                "value": "legacy",
                "label": "Legacy dribble-only generator",
                "note": "Keeps the existing generator behavior and only tries to persist dribble events.",
            },
            {
                "value": "expanded",
                "label": "Expanded heuristic generator",
                "note": "Recommended. Builds on the current detections to emit possession changes, shots, makes, misses, rebounds, assists, steals, turnovers, blocks, fouls, and dribbles.",
            },
        ],
        "llm_provider_options": llm_provider_options,
        "llm_model_options": llm_model_options,
        "recommended_ollama_models": recommended_ollama_models,
    }


def ai_runtime_available():
    return module_available("cv2") and module_available("ultralytics")


def resolve_detector_model(ai_settings):
    selected_model = (ai_settings.get("detector_model") or AI_DEFAULTS["detector_model"]).strip()
    if selected_model == "custom":
        custom_model = (ai_settings.get("custom_detector_model") or "").strip()
        return custom_model or AI_DEFAULTS["detector_model"]
    return selected_model


def display_detector_model(ai_settings):
    selected_model = (ai_settings.get("detector_model") or AI_DEFAULTS["detector_model"]).strip()
    if selected_model == "custom":
        custom_model = (ai_settings.get("custom_detector_model") or "").strip()
        return custom_model or "Custom (not set)"
    return selected_model


def build_analysis_settings_snapshot(runtime_settings):
    return {
        "analysis": runtime_settings["analysis"],
        "ai": runtime_settings["ai"],
    }


def build_rerun_game_id(base_game_id):
    return f"{base_game_id}__rerun_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"


def default_run_label(run_kind, snapshot):
    ai_settings = snapshot.get("ai", {})
    model = display_detector_model(ai_settings)
    device = ai_settings.get("inference_device", "auto")
    if run_kind == "primary":
        return "Original upload"
    return f"Rerun · {model} · {device}"


def ensure_primary_run_metadata(db, video_row, settings_snapshot=None):
    existing = db.execute(
        "SELECT id, run_label FROM analysis_runs WHERE (source_video_id=? OR game_id=? OR video_path=?) ORDER BY id ASC",
        (video_row["id"], video_row["game_id"], video_row["file_path"]),
    ).fetchall()
    if not existing:
        return

    for index, run in enumerate(existing):
        updates = {
            "source_video_id": video_row["id"],
            "base_game_id": video_row["game_id"],
            "run_kind": "primary" if index == 0 else "rerun",
            "run_label": run["run_label"] or ("Original upload" if index == 0 else f"Rerun #{index}"),
        }
        if settings_snapshot and index == 0:
            updates["settings_json"] = json.dumps(settings_snapshot)
        db.execute(
            """UPDATE analysis_runs SET
               source_video_id=COALESCE(source_video_id, :source_video_id),
               base_game_id=COALESCE(base_game_id, :base_game_id),
               run_kind=COALESCE(run_kind, :run_kind),
               run_label=COALESCE(run_label, :run_label),
               settings_json=COALESCE(settings_json, :settings_json)
               WHERE id=:id""",
            {
                "id": run["id"],
                "source_video_id": updates["source_video_id"],
                "base_game_id": updates["base_game_id"],
                "run_kind": updates["run_kind"],
                "run_label": updates["run_label"],
                "settings_json": updates.get("settings_json"),
            },
        )
    db.commit()


def queue_analysis_run(db, video_row, runtime_settings, run_kind="rerun", run_label=None):
    settings_snapshot = build_analysis_settings_snapshot(runtime_settings)
    game_id = video_row["game_id"] if run_kind == "primary" else build_rerun_game_id(video_row["game_id"])
    run_label = (run_label or "").strip() or default_run_label(run_kind, settings_snapshot)
    run_cur = db.execute(
        """INSERT INTO analysis_runs
           (game_id, video_path, source_video_id, base_game_id, run_label, settings_json, run_kind, status)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            game_id,
            video_row["file_path"],
            video_row["id"],
            video_row["game_id"],
            run_label,
            json.dumps(settings_snapshot),
            run_kind,
            "pending",
        ),
    )
    db.commit()
    return {
        "id": run_cur.lastrowid,
        "game_id": game_id,
        "run_label": run_label,
        "settings_snapshot": settings_snapshot,
    }


def start_analysis_subprocess(game_id, video_path):
    import sys

    subprocess.Popen(
        [sys.executable, "ai_analyzer.py", current_app.config["DATABASE"], video_path, game_id],
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )


def build_run_summary(run_row):
    payload = dict(run_row)
    settings_snapshot = {}
    if payload.get("settings_json"):
        try:
            settings_snapshot = json.loads(payload["settings_json"])
        except json.JSONDecodeError:
            settings_snapshot = {}
    payload["settings_snapshot"] = settings_snapshot
    payload["detector_model"] = display_detector_model(settings_snapshot.get("ai", {}))
    payload["event_generator_mode"] = settings_snapshot.get("ai", {}).get("event_generator_mode")
    payload["inference_device"] = settings_snapshot.get("ai", {}).get("inference_device")
    payload["frame_stride"] = settings_snapshot.get("ai", {}).get("frame_stride")
    payload["llm_provider"] = settings_snapshot.get("ai", {}).get("llm_provider")
    payload["llm_model"] = settings_snapshot.get("ai", {}).get("llm_model")
    return payload

# ── Database helpers ──────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def extract_local_path(value):
    if not value:
        return None

    split_value = urlsplit(value)
    if split_value.netloc and split_value.netloc != request.host:
        return None

    path = split_value.path or value
    if not path.startswith("/") or path.startswith("//"):
        return None

    return urlunsplit(("", "", path, split_value.query, split_value.fragment))


def safe_return_path(value, fallback="debug_page"):
    path = extract_local_path(value)
    if path:
        return path
    return url_for(fallback)


def append_query_params(path, **params):
    split_path = urlsplit(path)
    current_params = dict(parse_qsl(split_path.query, keep_blank_values=True))
    for key, value in params.items():
        if value is not None:
            current_params[key] = value
    return urlunsplit((
        "",
        "",
        split_path.path,
        urlencode(current_params, doseq=True),
        split_path.fragment,
    ))


def read_filtered_app_logs(query="", limit=200):
    log_path = "/tmp/liberty-basketball-app.log"
    if not os.path.exists(log_path):
        return []

    query = (query or "").strip().lower()
    with open(log_path, "r", encoding="utf-8", errors="replace") as handle:
        lines = [line.rstrip() for line in handle.readlines()]
    if query:
        lines = [line for line in lines if query in line.lower()]
    return lines[-limit:]




def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql", mode="r") as f:
        db.executescript(f.read())
    db.commit()
    _ensure_migration_columns(db)


def ensure_db():
    if not os.path.exists(current_app.config["DATABASE"]):
        init_db()
    else:
        db = get_db()
        _ensure_migration_columns(db)


def _ensure_migration_columns(db):
    """Add new columns/tables to existing databases without wiping data."""
    # ── New tables (idempotent) ──────────────────────────────
    db.executescript("""
        CREATE TABLE IF NOT EXISTS videos (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            original_filename TEXT NOT NULL,
            stored_filename   TEXT NOT NULL UNIQUE,
            file_path         TEXT NOT NULL,
            file_size_bytes   INTEGER,
            opponent          TEXT,
            game_id           TEXT,
            upload_timestamp  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_duplicate      INTEGER NOT NULL DEFAULT 0,
            duplicate_of_id   INTEGER REFERENCES videos(id)
        );
        CREATE TABLE IF NOT EXISTS app_settings (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS issue_reports (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_type   TEXT NOT NULL DEFAULT 'issue',
            title        TEXT NOT NULL,
            details      TEXT NOT NULL,
            source_path  TEXT,
            browser_console TEXT,
            status       TEXT NOT NULL DEFAULT 'open',
            created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS player_development_clips (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id       INTEGER REFERENCES players(id),
            game_id         TEXT,
            event_id        INTEGER REFERENCES events(id),
            clip_start_ms   INTEGER NOT NULL,
            clip_end_ms     INTEGER NOT NULL,
            clip_label      TEXT NOT NULL,
            clip_category   TEXT NOT NULL DEFAULT 'general',
            season_id       INTEGER REFERENCES seasons(id),
            notes           TEXT,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS practice_playlists (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            season_id       INTEGER REFERENCES seasons(id),
            level           TEXT NOT NULL DEFAULT 'jr_high',
            status          TEXT NOT NULL DEFAULT 'draft',
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS practice_playlist_clips (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            playlist_id     INTEGER NOT NULL REFERENCES practice_playlists(id) ON DELETE CASCADE,
            clip_id         INTEGER NOT NULL REFERENCES player_development_clips(id) ON DELETE CASCADE,
            sort_order      INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(playlist_id, clip_id)
        );
        CREATE TABLE IF NOT EXISTS playbooks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            description     TEXT,
            created_by      TEXT,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS plays (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            playbook_id     INTEGER REFERENCES playbooks(id) ON DELETE SET NULL,
            name            TEXT NOT NULL,
            description     TEXT,
            category        TEXT NOT NULL DEFAULT 'offense',
            tags            TEXT,
            diagram_json    TEXT,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS play_steps (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            play_id         INTEGER NOT NULL REFERENCES plays(id) ON DELETE CASCADE,
            step_number     INTEGER NOT NULL,
            label           TEXT,
            positions_json  TEXT,
            movements_json  TEXT,
            notes           TEXT,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS playbook_plays (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            playbook_id     INTEGER NOT NULL REFERENCES playbooks(id) ON DELETE CASCADE,
            play_id         INTEGER NOT NULL REFERENCES plays(id) ON DELETE CASCADE,
            sort_order      INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(playbook_id, play_id)
        );
        CREATE TABLE IF NOT EXISTS practice_plan_items (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            practice_id     INTEGER NOT NULL REFERENCES practices(id) ON DELETE CASCADE,
            playlist_id     INTEGER REFERENCES practice_playlists(id),
            item_type       TEXT NOT NULL DEFAULT 'drill',
            title           TEXT NOT NULL,
            description     TEXT,
            duration_min    INTEGER,
            sort_order      INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT NOT NULL UNIQUE,
            email           TEXT NOT NULL UNIQUE,
            password_hash   TEXT NOT NULL,
            is_admin        INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS maxpreps_rankings (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            team_key        TEXT NOT NULL,
            state           TEXT NOT NULL DEFAULT 'Idaho',
            ranking         INTEGER,
            ranking_url     TEXT,
            scraped_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(team_key, state)
        );
    """)
    # ── New columns on existing tables ──────────────────────
    col_migrations = [
        ("analysis_runs", "source_video_id", "ALTER TABLE analysis_runs ADD COLUMN source_video_id INTEGER REFERENCES videos(id)"),
        ("analysis_runs", "base_game_id", "ALTER TABLE analysis_runs ADD COLUMN base_game_id TEXT"),
        ("analysis_runs", "run_label", "ALTER TABLE analysis_runs ADD COLUMN run_label TEXT"),
        ("analysis_runs", "settings_json", "ALTER TABLE analysis_runs ADD COLUMN settings_json TEXT"),
        ("analysis_runs", "run_kind", "ALTER TABLE analysis_runs ADD COLUMN run_kind TEXT DEFAULT 'primary'"),
        ("events", "source_video",   "ALTER TABLE events ADD COLUMN source_video TEXT"),
        ("events", "source_frame",   "ALTER TABLE events ADD COLUMN source_frame INTEGER"),
        ("events", "human_verified", "ALTER TABLE events ADD COLUMN human_verified INTEGER NOT NULL DEFAULT 0"),
        ("events", "confidence",     "ALTER TABLE events ADD COLUMN confidence REAL"),
        ("issue_reports", "browser_console", "ALTER TABLE issue_reports ADD COLUMN browser_console TEXT"),
        ("scheduled_games", "jv_game_time", "ALTER TABLE scheduled_games ADD COLUMN jv_game_time TIME"),
        ("scheduled_games", "frosh_game_time", "ALTER TABLE scheduled_games ADD COLUMN frosh_game_time TIME"),
        ("scheduled_games", "team", "ALTER TABLE scheduled_games ADD COLUMN team TEXT NOT NULL DEFAULT 'boys_hs'"),
        ("practice_plan_items", "sort_order", "ALTER TABLE practice_plan_items ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"),
    ]
    existing = {
        (row[1], row[2]): True
        for row in db.execute(
            "SELECT type, tbl_name, name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for table, col, sql in col_migrations:
        try:
            cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()]
            if col not in cols:
                db.execute(sql)
        except Exception:
            pass
    db.commit()






SCHEDULE_LEVEL_OPTIONS = [
    ("jr_high", "Jr High"),
    ("jv", "JV"),
    ("varsity", "Varsity"),
]
SCHEDULE_GENDER_OPTIONS = [
    ("boys", "Boys"),
    ("girls", "Girls"),
]
SCHEDULE_LOCATION_OPTIONS = [
    ("home", "Home"),
    ("away", "Away"),
    ("neutral", "Neutral"),
]
SCHEDULE_STATUS_OPTIONS = [
    ("scheduled", "Scheduled"),
    ("cancelled", "Cancelled"),
    ("rescheduled", "Rescheduled"),
    ("completed", "Completed"),
]
SCHEDULE_TEAM_OPTIONS = [
    ("boys_hs", "Boys High School"),
    ("girls_hs", "Girls High School"),
    ("jr_boys", "Jr High Boys"),
    ("jr_girls", "Jr High Girls"),
]
GAME_SOURCE_TYPE_OPTIONS = [
    ("manual", "Manual"),
    ("nfhs", "NFHS"),
    ("pixellot", "Pixellot"),
]
GAME_RESULT_OPTIONS = [
    ("", "Not set"),
    ("win", "Win"),
    ("loss", "Loss"),
    ("tie", "Tie"),
]
SOURCE_TYPE_OPTIONS = [
    ("manual_upload", "Manual Upload"),
    ("local_file", "Local File"),
    ("nfhs_vod", "NFHS VOD"),
    ("pixellot_vod", "Pixellot VOD"),
]
PRACTICE_STATUS_OPTIONS = [
    ("planned", "Planned"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
]
PRACTICE_PLAN_SOURCE_OPTIONS = [
    ("manual", "Manual"),
    ("uploaded", "Uploaded"),
    ("auto", "Auto"),
]


def fetch_scheduled_games(db, season_id=None, level=None, gender=None, status=None):
    clauses = []
    params = []

    if season_id:
        clauses.append("sg.season_id = ?")
        params.append(season_id)
    if level:
        clauses.append("sg.level = ?")
        params.append(level)
    if gender:
        clauses.append("sg.gender = ?")
        params.append(gender)
    if status:
        clauses.append("sg.status = ?")
        params.append(status)

    query = """
        SELECT sg.*, s.name AS season_name
        FROM scheduled_games sg
        JOIN seasons s ON s.id = sg.season_id
    """
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY sg.game_date, sg.game_time, sg.id"

    return db.execute(query, params).fetchall()


def render_schedule_page(
    *,
    error=None,
    message=None,
    filters=None,
    edit_game_id=None,
    edit_season_id=None,
    game_form_data=None,
    season_form_data=None,
):
    db = get_db()
    if filters is None:
        filters = {
            "season_id": request.args.get("season_id", type=int),
            "level": (request.args.get("level") or "").strip(),
            "gender": (request.args.get("gender") or "").strip(),
            "status": (request.args.get("status") or "").strip(),
        }

    seasons = db.execute(
        "SELECT * FROM seasons ORDER BY start_date DESC, id DESC"
    ).fetchall()
    games = fetch_scheduled_games(
        db,
        season_id=filters["season_id"],
        level=filters["level"],
        gender=filters["gender"],
        status=filters["status"],
    )

    edit_game = None
    if edit_game_id:
        edit_game = db.execute(
            "SELECT * FROM scheduled_games WHERE id = ?",
            (edit_game_id,),
        ).fetchone()

    edit_season = None
    if edit_season_id:
        edit_season = db.execute(
            "SELECT * FROM seasons WHERE id = ?",
            (edit_season_id,),
        ).fetchone()

    game_form = game_form_data or {
        "id": edit_game["id"] if edit_game else "",
        "season_id": (
            edit_game["season_id"]
            if edit_game
            else (filters["season_id"] or (seasons[0]["id"] if seasons else ""))
        ),
        "program_name": edit_game["program_name"] if edit_game else "Liberty",
        "team": edit_game["team"] if edit_game else "boys_hs",
        "gender": edit_game["gender"] if edit_game else "boys",
        "level": edit_game["level"] if edit_game else "jr_high",
        "game_date": edit_game["game_date"] if edit_game else "",
        "game_time": edit_game["game_time"] if edit_game else "",
        "jv_game_time": edit_game["jv_game_time"] if edit_game else "",
        "frosh_game_time": edit_game["frosh_game_time"] if edit_game else "",
        "location_type": edit_game["location_type"] if edit_game else "home",
        "opponent_name": edit_game["opponent_name"] if edit_game else "",
        "tournament_name": edit_game["tournament_name"] if edit_game else "",
        "status": edit_game["status"] if edit_game else "scheduled",
        "notes": edit_game["notes"] if edit_game else "",
    }

    season_form = season_form_data or {
        "id": edit_season["id"] if edit_season else "",
        "name": edit_season["name"] if edit_season else "",
        "start_date": edit_season["start_date"] if edit_season else "",
        "end_date": edit_season["end_date"] if edit_season else "",
    }

    return render_template(
        "schedule.html",
        seasons=seasons,
        games=games,
        filters=filters,
        error=error,
        message=message,
        game_form=game_form,
        season_form=season_form,
        editing_game=edit_game is not None,
        editing_season=edit_season is not None,
        level_options=SCHEDULE_LEVEL_OPTIONS,
        gender_options=SCHEDULE_GENDER_OPTIONS,
        location_options=SCHEDULE_LOCATION_OPTIONS,
        status_options=SCHEDULE_STATUS_OPTIONS,
        team_options=SCHEDULE_TEAM_OPTIONS,
    )


def fetch_games_with_context(db):
    return db.execute(
        """
        SELECT
            g.*,
            sg.game_date,
            sg.opponent_name,
            sg.program_name,
            sg.gender,
            sg.level,
            s.name AS season_name,
            COUNT(src.id) AS source_count
        FROM games g
        LEFT JOIN scheduled_games sg ON sg.id = g.scheduled_game_id
        LEFT JOIN seasons s ON s.id = sg.season_id
        LEFT JOIN sources src ON src.game_id = g.id
        GROUP BY g.id
        ORDER BY COALESCE(sg.game_date, substr(g.start_time, 1, 10)) DESC, g.id DESC
        """
    ).fetchall()


def fetch_sources_with_context(db, game_id=None):
    query = """
        SELECT
            src.*,
            sg.opponent_name,
            sg.game_date
        FROM sources src
        JOIN games g ON g.id = src.game_id
        LEFT JOIN scheduled_games sg ON sg.id = g.scheduled_game_id
    """
    params = []
    if game_id is not None:
        query += " WHERE src.game_id = ?"
        params.append(game_id)
    query += " ORDER BY src.created_at DESC, src.id DESC"
    return db.execute(query, params).fetchall()


def render_games_page(*, error=None, message=None, edit_game_id=None, game_form_data=None, source_form_data=None):
    db = get_db()
    games = fetch_games_with_context(db)
    scheduled_games = db.execute(
        """
        SELECT sg.*, s.name AS season_name
        FROM scheduled_games sg
        JOIN seasons s ON s.id = sg.season_id
        ORDER BY sg.game_date DESC, sg.id DESC
        """
    ).fetchall()
    sources = fetch_sources_with_context(db)

    edit_game = None
    if edit_game_id:
        edit_game = db.execute("SELECT * FROM games WHERE id = ?", (edit_game_id,)).fetchone()

    game_form = game_form_data or {
        "id": edit_game["id"] if edit_game else "",
        "scheduled_game_id": edit_game["scheduled_game_id"] if edit_game else "",
        "start_time": edit_game["start_time"] if edit_game else "",
        "end_time": edit_game["end_time"] if edit_game else "",
        "source_type": edit_game["source_type"] if edit_game else "manual",
        "source_key": edit_game["source_key"] if edit_game else "",
        "nfhs_game_id": edit_game["nfhs_game_id"] if edit_game else "",
        "nfhs_url": edit_game["nfhs_url"] if edit_game else "",
        "home_score": edit_game["home_score"] if edit_game else "",
        "away_score": edit_game["away_score"] if edit_game else "",
        "result": edit_game["result"] if edit_game else "",
        "is_conference": bool(edit_game["is_conference"]) if edit_game else False,
    }
    source_form = source_form_data or {
        "game_id": edit_game["id"] if edit_game else "",
        "source_type": "manual_upload",
        "source_path": "",
    }

    return render_template(
        "games.html",
        games=games,
        scheduled_games=scheduled_games,
        sources=sources,
        error=error,
        message=message,
        game_form=game_form,
        source_form=source_form,
        editing_game=edit_game is not None,
        game_source_type_options=GAME_SOURCE_TYPE_OPTIONS,
        game_result_options=GAME_RESULT_OPTIONS,
        source_type_options=SOURCE_TYPE_OPTIONS,
    )


def fetch_nfhs_matches_with_context(db):
    return db.execute(
        """
        SELECT
            nm.*,
            sg.game_date,
            sg.opponent_name,
            sg.program_name,
            sg.gender,
            sg.level,
            s.name AS season_name
        FROM nfhs_matches nm
        JOIN scheduled_games sg ON sg.id = nm.scheduled_game_id
        JOIN seasons s ON s.id = sg.season_id
        ORDER BY sg.game_date DESC, nm.id DESC
        """
    ).fetchall()


def confirm_nfhs_match(db, match_id):
    row = db.execute(
        "SELECT * FROM nfhs_matches WHERE id=?",
        (match_id,),
    ).fetchone()
    if not row:
        return None

    game = db.execute(
        "SELECT * FROM games WHERE scheduled_game_id=? ORDER BY id DESC LIMIT 1",
        (row["scheduled_game_id"],),
    ).fetchone()

    if game:
        db.execute(
            """UPDATE games SET
               source_type='nfhs',
               source_key=?,
               nfhs_game_id=?,
               nfhs_url=?,
               updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (row["nfhs_game_id"], row["nfhs_game_id"], row["nfhs_url"], game["id"]),
        )
        game_id = game["id"]
    else:
        cur = db.execute(
            """INSERT INTO games
               (scheduled_game_id, source_type, source_key, nfhs_game_id, nfhs_url)
               VALUES (?,?,?,?,?)""",
            (
                row["scheduled_game_id"],
                "nfhs",
                row["nfhs_game_id"],
                row["nfhs_game_id"],
                row["nfhs_url"],
            ),
        )
        game_id = cur.lastrowid

    existing_source = db.execute(
        "SELECT id FROM sources WHERE game_id=? AND source_type='nfhs_vod' AND source_path=?",
        (game_id, row["nfhs_url"]),
    ).fetchone()
    if not existing_source:
        db.execute(
            "INSERT INTO sources (game_id, source_type, source_path) VALUES (?,?,?)",
            (game_id, "nfhs_vod", row["nfhs_url"]),
        )

    db.execute(
        "UPDATE nfhs_matches SET match_status='confirmed' WHERE id=?",
        (match_id,),
    )
    db.commit()

    confirmed = db.execute(
        "SELECT * FROM nfhs_matches WHERE id=?",
        (match_id,),
    ).fetchone()
    payload = dict(confirmed)
    payload["game_id"] = game_id
    return payload


def render_nfhs_matches_page(*, error=None, message=None, form_data=None):
    db = get_db()
    matches = fetch_nfhs_matches_with_context(db)
    scheduled_games = db.execute(
        """
        SELECT sg.*, s.name AS season_name
        FROM scheduled_games sg
        JOIN seasons s ON s.id = sg.season_id
        ORDER BY sg.game_date DESC, sg.id DESC
        """
    ).fetchall()
    candidate_form = form_data or {
        "scheduled_game_id": "",
        "nfhs_game_id": "",
        "nfhs_url": "",
        "confidence": "",
    }
    return render_template(
        "nfhs_matches.html",
        matches=matches,
        scheduled_games=scheduled_games,
        error=error,
        message=message,
        candidate_form=candidate_form,
    )


def fetch_practices_with_context(db, season_id=None, level=None, status=None, start_date=None, end_date=None):
    clauses = []
    params = []
    if season_id:
        clauses.append("p.season_id = ?")
        params.append(season_id)
    if level:
        clauses.append("p.level = ?")
        params.append(level)
    if status:
        clauses.append("p.status = ?")
        params.append(status)
    if start_date:
        clauses.append("p.practice_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("p.practice_date <= ?")
        params.append(end_date)

    query = """
        SELECT p.*, s.name AS season_name
        FROM practices p
        LEFT JOIN seasons s ON s.id = p.season_id
    """
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY p.practice_date DESC, p.id DESC"
    return db.execute(query, params).fetchall()


def infer_practice_theme(*texts):
    combined = " ".join((text or "").lower() for text in texts)
    themes = {
        "defense": ("defense", "defensive", "closeout", "pressure", "shell"),
        "shooting": ("shoot", "shooting", "shot", "shots"),
        "rebounding": ("rebound", "box out", "boxout"),
        "ball security": ("turnover", "ball security", "handle", "pressure"),
        "transition": ("transition", "fast break", "break"),
        "conditioning": ("conditioning", "sprint", "effort", "energy"),
        "communication": ("communicat", "talk", "voice"),
    }
    scores = {
        theme: sum(combined.count(keyword) for keyword in keywords)
        for theme, keywords in themes.items()
    }
    top_theme = max(scores, key=scores.get, default=None)
    if not top_theme or scores[top_theme] == 0:
        return ""
    return top_theme


def summarize_text_block(text, fallback):
    cleaned = " ".join((text or "").strip().split())
    if not cleaned:
        return fallback
    if len(cleaned) <= 140:
        return cleaned
    return cleaned[:137].rstrip() + "..."


def build_practice_ai_notes(practice, settings_snapshot=None):
    """Generate AI notes for a practice session.

    Uses Ollama LLM when configured and available; falls back to
    heuristic-based generation otherwise.
    """
    # Try LLM first
    llm_notes, source = generate_practice_ai_notes_llm(practice, settings_snapshot)
    if llm_notes:
        return llm_notes

    # Heuristic fallback
    theme = infer_practice_theme(practice["plan_text"], practice["coach_notes"])
    sentences = [
        f"Plan focus: {summarize_text_block(practice['plan_text'], 'No structured plan was entered.')}",
        f"Coach notes: {summarize_text_block(practice['coach_notes'], 'No coach notes were entered.')}",
        "Film context: no film is linked to this practice yet, so this summary is based on the plan and coach notes only.",
    ]
    if theme:
        sentences.append(f"Likely emphasis area: {theme}.")
        if theme == "ball security":
            sentences.append("Recommended next block: add decision-making reps against pressure and track whether live-ball turnovers decrease.")
        elif theme == "shooting":
            sentences.append("Recommended next block: pair shot-volume goals with game-speed finishing and spacing checks.")
        elif theme == "defense":
            sentences.append("Recommended next block: revisit defensive communication and possession-ending habits in the next practice.")
        else:
            sentences.append(f"Recommended next block: keep the {theme} theme visible in the next practice and compare coach notes afterward.")
    else:
        sentences.append("Recommended next block: keep the next practice narrowly focused and record one concrete success metric in the coach notes.")
    return " ".join(sentences)


def build_practice_combined_summary(practice, ai_notes):
    coach_summary = summarize_text_block(practice["coach_notes"], "No coach summary recorded.")
    plan_summary = summarize_text_block(practice["plan_text"], "No practice plan recorded.")
    return (
        f"Plan: {plan_summary}\n"
        f"Coach: {coach_summary}\n"
        f"AI: {ai_notes}\n"
        "Film: No film linked."
    )


def build_practice_range_summary(practices):
    if not practices:
        return "No practices match the selected range."

    completed = sum(1 for practice in practices if practice["status"] == "completed")
    cancelled = sum(1 for practice in practices if practice["status"] == "cancelled")
    with_notes = sum(1 for practice in practices if practice["coach_notes"])
    theme_counts = {}
    for practice in practices:
        theme = infer_practice_theme(practice["plan_text"], practice["coach_notes"], practice["ai_notes"])
        if theme:
            theme_counts[theme] = theme_counts.get(theme, 0) + 1

    ordered_themes = sorted(theme_counts.items(), key=lambda item: (-item[1], item[0]))
    top_themes = ", ".join(f"{theme} ({count})" for theme, count in ordered_themes[:3]) or "No dominant theme captured yet"

    return (
        f"Practices in range: {len(practices)}. "
        f"Completed: {completed}. Cancelled: {cancelled}. "
        f"Coach-note coverage: {with_notes}/{len(practices)}. "
        f"Recurring themes: {top_themes}. "
        "Suggested focus: carry the top recurring theme into the next block and compare future coach notes against it."
    )


def render_practices_page(*, error=None, message=None, filters=None, edit_practice_id=None, form_data=None):
    db = get_db()
    if filters is None:
        filters = {
            "season_id": request.args.get("season_id", type=int),
            "level": (request.args.get("level") or "").strip(),
            "status": (request.args.get("status") or "").strip(),
        }

    seasons = db.execute("SELECT * FROM seasons ORDER BY start_date DESC, id DESC").fetchall()
    practices = fetch_practices_with_context(
        db,
        season_id=filters["season_id"],
        level=filters["level"],
        status=filters["status"],
    )

    edit_practice = None
    if edit_practice_id:
        edit_practice = db.execute("SELECT * FROM practices WHERE id=?", (edit_practice_id,)).fetchone()

    practice_form = form_data or {
        "id": edit_practice["id"] if edit_practice else "",
        "season_id": edit_practice["season_id"] if edit_practice else (filters["season_id"] or (seasons[0]["id"] if seasons else "")),
        "level": edit_practice["level"] if edit_practice else "jr_high",
        "practice_date": edit_practice["practice_date"] if edit_practice else "",
        "status": edit_practice["status"] if edit_practice else "planned",
        "plan_source": edit_practice["plan_source"] if edit_practice else "manual",
        "plan_text": edit_practice["plan_text"] if edit_practice else "",
        "coach_notes": edit_practice["coach_notes"] if edit_practice else "",
    }

    return render_template(
        "practices.html",
        seasons=seasons,
        practices=practices,
        filters=filters,
        error=error,
        message=message,
        practice_form=practice_form,
        editing_practice=edit_practice is not None,
        level_options=SCHEDULE_LEVEL_OPTIONS,
        practice_status_options=PRACTICE_STATUS_OPTIONS,
        practice_plan_source_options=PRACTICE_PLAN_SOURCE_OPTIONS,
    )


def refresh_game_stats(db, game_id):
    if not feature_enabled("ENABLE_AUTO_STATS_M1"):
        return
    from stats import refresh_stats

    refresh_stats(db, game_id)


# ── Page routes ───────────────────────────────────────────
