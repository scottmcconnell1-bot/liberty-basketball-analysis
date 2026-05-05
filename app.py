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

from flask import (
    Flask, abort, g, redirect, render_template, request,
    send_from_directory, jsonify, current_app, url_for,
)
from werkzeug.utils import secure_filename

from config import Config
from settings_store import AI_DEFAULTS, load_all_settings, save_settings

try:
    import psutil
except ImportError:  # pragma: no cover - optional at runtime
    psutil = None

app = Flask(__name__)
app.config.from_object(Config)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
POWER_SAMPLE_CACHE = {}

# ── Configuration ─────────────────────────────────────────
app.config.setdefault("DATABASE", "film_analysis.db")
app.config.setdefault("UPLOAD_FOLDER", "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


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


@app.context_processor
def inject_feature_flags():
    runtime_settings = get_runtime_settings()
    return {
        "features": runtime_settings["features"],
        "analysis_config": runtime_settings["analysis"],
    }


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


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql", mode="r") as f:
        db.executescript(f.read())
    db.commit()
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


@app.cli.command("init-db")
def init_db_command():
    with app.app_context():
        init_db()
    print("Initialized the database.")


@app.before_request
def ensure_db():
    if not os.path.exists(current_app.config["DATABASE"]):
        init_db()
    else:
        # Run migrations on every startup to pick up new tables/columns
        db = get_db()
        _ensure_migration_columns(db)


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
        "gender": edit_game["gender"] if edit_game else "boys",
        "level": edit_game["level"] if edit_game else "jr_high",
        "game_date": edit_game["game_date"] if edit_game else "",
        "game_time": edit_game["game_time"] if edit_game else "",
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


def build_practice_ai_notes(practice):
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

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/schedule")
@require_feature("ENABLE_SEASONS_SCHEDULE")
def schedule():
    return render_schedule_page(
        message=request.args.get("message"),
        error=request.args.get("error"),
        edit_game_id=request.args.get("edit_game_id", type=int),
        edit_season_id=request.args.get("edit_season_id", type=int),
    )


@app.route("/schedule/seasons/save", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def schedule_save_season():
    form = request.form
    season_id = form.get("season_id", "").strip()
    name = (form.get("name") or "").strip()
    start_date = (form.get("start_date") or "").strip()
    end_date = (form.get("end_date") or "").strip()

    if not name or not start_date or not end_date:
        return render_schedule_page(
            error="Season name, start date, and end date are required.",
            edit_season_id=int(season_id) if season_id else None,
            season_form_data={
                "id": season_id,
                "name": name,
                "start_date": start_date,
                "end_date": end_date,
            },
        ), 400

    db = get_db()
    try:
        if season_id:
            db.execute(
                "UPDATE seasons SET name=?, start_date=?, end_date=? WHERE id=?",
                (name, start_date, end_date, int(season_id)),
            )
            message = "Season updated."
        else:
            db.execute(
                "INSERT INTO seasons (name, start_date, end_date) VALUES (?,?,?)",
                (name, start_date, end_date),
            )
            message = "Season created."
        db.commit()
    except sqlite3.IntegrityError:
        return render_schedule_page(
            error="Season name already exists.",
            edit_season_id=int(season_id) if season_id else None,
            season_form_data={
                "id": season_id,
                "name": name,
                "start_date": start_date,
                "end_date": end_date,
            },
        ), 409

    return redirect(url_for("schedule", message=message))


@app.route("/schedule/seasons/<int:season_id>/delete", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def schedule_delete_season(season_id):
    db = get_db()
    db.execute("DELETE FROM scheduled_games WHERE season_id=?", (season_id,))
    db.execute("DELETE FROM seasons WHERE id=?", (season_id,))
    db.commit()
    return redirect(url_for("schedule", message="Season deleted."))


@app.route("/schedule/games/save", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def schedule_save_game():
    form = request.form
    filters = {
        "season_id": int(form["filter_season_id"]) if form.get("filter_season_id") else None,
        "level": (form.get("filter_level") or "").strip(),
        "gender": (form.get("filter_gender") or "").strip(),
        "status": (form.get("filter_status") or "").strip(),
    }
    game_id = form.get("game_id", "").strip()
    season_id = form.get("season_id", "").strip()
    game_date = (form.get("game_date") or "").strip()
    opponent_name = (form.get("opponent_name") or "").strip()

    if not season_id or not game_date or not opponent_name:
        return render_schedule_page(
            error="Season, date, and opponent are required.",
            filters=filters,
            edit_game_id=int(game_id) if game_id else None,
            game_form_data={
                "id": game_id,
                "season_id": season_id,
                "program_name": (form.get("program_name") or "Liberty").strip(),
                "gender": (form.get("gender") or "boys").strip(),
                "level": (form.get("level") or "jr_high").strip(),
                "game_date": game_date,
                "game_time": (form.get("game_time") or "").strip(),
                "location_type": (form.get("location_type") or "home").strip(),
                "opponent_name": opponent_name,
                "tournament_name": (form.get("tournament_name") or "").strip(),
                "status": (form.get("status") or "scheduled").strip(),
                "notes": (form.get("notes") or "").strip(),
            },
        ), 400

    db = get_db()
    values = (
        int(season_id),
        (form.get("program_name") or "Liberty").strip() or "Liberty",
        (form.get("gender") or "boys").strip() or "boys",
        (form.get("level") or "jr_high").strip() or "jr_high",
        game_date,
        (form.get("game_time") or "").strip() or None,
        (form.get("location_type") or "home").strip() or "home",
        opponent_name,
        (form.get("tournament_name") or "").strip() or None,
        (form.get("status") or "scheduled").strip() or "scheduled",
        (form.get("notes") or "").strip() or None,
    )

    if game_id:
        db.execute(
            """UPDATE scheduled_games SET
               season_id=?, program_name=?, gender=?, level=?, game_date=?, game_time=?,
               location_type=?, opponent_name=?, tournament_name=?, status=?, notes=?,
               updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            values + (int(game_id),),
        )
        message = "Scheduled game updated."
    else:
        db.execute(
            """INSERT INTO scheduled_games
               (season_id, program_name, gender, level, game_date, game_time,
                location_type, opponent_name, tournament_name, status, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
        message = "Scheduled game created."
    db.commit()

    return redirect(
        url_for(
            "schedule",
            season_id=filters["season_id"],
            level=filters["level"] or None,
            gender=filters["gender"] or None,
            status=filters["status"] or None,
            message=message,
        )
    )


@app.route("/schedule/games/<int:game_id>/delete", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def schedule_delete_game(game_id):
    filters = {
        "season_id": request.form.get("filter_season_id", type=int),
        "level": (request.form.get("filter_level") or "").strip(),
        "gender": (request.form.get("filter_gender") or "").strip(),
        "status": (request.form.get("filter_status") or "").strip(),
    }
    db = get_db()
    db.execute("DELETE FROM scheduled_games WHERE id=?", (game_id,))
    db.commit()
    return redirect(
        url_for(
            "schedule",
            season_id=filters["season_id"],
            level=filters["level"] or None,
            gender=filters["gender"] or None,
            status=filters["status"] or None,
            message="Scheduled game deleted.",
        )
    )


@app.route("/videos")
@require_feature("ENABLE_AUTO_STATS_M1")
def videos_page():
    return render_template("videos.html")


@app.route("/film")
@app.route("/film/<filename>")
@require_feature("ENABLE_MANUAL_TAG_MVP")
def film(filename=None):
    game_id = (request.args.get("game_id") or "").strip() or None
    if filename and not game_id:
        db = get_db()
        # Find the most recent analysis run for this video file
        row = db.execute(
            "SELECT game_id FROM analysis_runs WHERE video_path LIKE ? ORDER BY id DESC LIMIT 1",
            (f"%{filename}",),
        ).fetchone()
        if row:
            game_id = row["game_id"]
    return render_template(
        "film_tool.html",
        filename=filename,
        game_id=game_id,
        uploaded_video_url=url_for("uploaded_file", filename=filename) if filename else None,
    )


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)


@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    db = get_db()
    catalog = build_settings_catalog()
    runtime_settings = get_runtime_settings()

    if request.method == "POST":
        detector_values = {option["value"] for option in catalog["detector_options"]}
        device_values = {option["value"] for option in catalog["device_options"]}
        event_generator_mode_values = {option["value"] for option in catalog["event_generator_mode_options"]}
        llm_provider_values = {option["value"] for option in catalog["llm_provider_options"]}
        llm_model_values = {option["value"] for option in catalog["llm_model_options"]}

        updates = {}
        for flag_name in current_app.config.get("FEATURES", {}):
            updates[f"feature.{flag_name}"] = bool(request.form.get(f"feature_{flag_name}"))
        for option_name in current_app.config.get("ANALYSIS_CONFIG", {}):
            updates[f"analysis.{option_name}"] = bool(request.form.get(f"analysis_{option_name}"))

        detector_model = (request.form.get("ai_detector_model") or AI_DEFAULTS["detector_model"]).strip()
        updates["ai.detector_model"] = detector_model if detector_model in detector_values else AI_DEFAULTS["detector_model"]
        custom_detector_model = (request.form.get("ai_custom_detector_model") or "").strip()
        updates["ai.custom_detector_model"] = custom_detector_model

        inference_device = (request.form.get("ai_inference_device") or AI_DEFAULTS["inference_device"]).strip()
        if inference_device not in device_values:
            inference_device = AI_DEFAULTS["inference_device"]
        updates["ai.inference_device"] = inference_device

        event_generator_mode = (request.form.get("ai_event_generator_mode") or AI_DEFAULTS["event_generator_mode"]).strip()
        if event_generator_mode not in event_generator_mode_values:
            event_generator_mode = AI_DEFAULTS["event_generator_mode"]
        updates["ai.event_generator_mode"] = event_generator_mode

        try:
            frame_stride = max(1, int(request.form.get("ai_frame_stride", AI_DEFAULTS["frame_stride"])))
        except ValueError:
            frame_stride = AI_DEFAULTS["frame_stride"]
        updates["ai.frame_stride"] = frame_stride

        try:
            tracker_distance = max(1, int(request.form.get("ai_tracker_max_distance", AI_DEFAULTS["tracker_max_distance"])))
        except ValueError:
            tracker_distance = AI_DEFAULTS["tracker_max_distance"]
        updates["ai.tracker_max_distance"] = tracker_distance

        try:
            tracker_gap = max(1, int(request.form.get("ai_tracker_max_frame_gap", AI_DEFAULTS["tracker_max_frame_gap"])))
        except ValueError:
            tracker_gap = AI_DEFAULTS["tracker_max_frame_gap"]
        updates["ai.tracker_max_frame_gap"] = tracker_gap

        llm_provider = (request.form.get("ai_llm_provider") or "none").strip()
        if llm_provider not in llm_provider_values:
            llm_provider = "none"
        updates["ai.llm_provider"] = llm_provider

        llm_model = (request.form.get("ai_llm_model") or "").strip()
        if llm_provider == "ollama" and llm_model not in llm_model_values:
            llm_model = catalog["llm_model_options"][0]["value"] if catalog["llm_model_options"] else ""
        if llm_provider == "none":
            llm_model = ""
        updates["ai.llm_model"] = llm_model

        save_settings(db, updates)
        g.pop("runtime_settings", None)
        return redirect(url_for("settings_page", message="Settings saved."))

    return render_template(
        "settings.html",
        message=request.args.get("message"),
        runtime_settings=runtime_settings,
        catalog=catalog,
    )


@app.route("/settings/custom-weights")
def custom_weights_guide_page():
    return render_template("custom_weights_guide.html")


@app.route("/settings/ollama/pull", methods=["POST"])
def pull_ollama_model():
    model_name = (request.form.get("model_name") or "").strip()
    if not model_name or not re.fullmatch(r"[A-Za-z0-9._:-]+", model_name):
        return redirect(url_for("settings_page", message="Invalid Ollama model name."))

    log_slug = re.sub(r"[^A-Za-z0-9._-]+", "-", model_name)
    log_path = f"/tmp/liberty-basketball-ollama-pull-{log_slug}.log"
    try:
        with open(log_path, "ab") as log_file:
            subprocess.Popen(
                ["ollama", "pull", model_name],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except FileNotFoundError:
        return redirect(url_for("settings_page", message="Ollama is not installed in the current environment."))
    return redirect(
        url_for(
            "settings_page",
            message=f"Started pulling {model_name}. Refresh settings later to see it in the installed models list. Log: {log_path}",
        )
    )


@app.route("/debug")
def debug_page():
    db = get_db()
    entry_type = (request.args.get("entry_type") or "all").strip()
    entry_status = (request.args.get("entry_status") or "all").strip()
    query = (request.args.get("q") or "").strip()
    log_query = (request.args.get("log_query") or "").strip()

    sql_query = "SELECT * FROM issue_reports WHERE 1=1"
    params = []
    if entry_type != "all":
        sql_query += " AND entry_type = ?"
        params.append(entry_type)
    if entry_status != "all":
        sql_query += " AND status = ?"
        params.append(entry_status)
    if query:
        sql_query += " AND (title LIKE ? OR details LIKE ? OR COALESCE(source_path, '') LIKE ? OR COALESCE(browser_console, '') LIKE ?)"
        wildcard = f"%{query}%"
        params.extend([wildcard, wildcard, wildcard, wildcard])
    sql_query += " ORDER BY CASE WHEN status = 'open' THEN 0 ELSE 1 END, created_at DESC, id DESC"

    issue_reports = db.execute(sql_query, params).fetchall()
    recent_failures = db.execute(
        """SELECT id, game_id, error_message, started_at, completed_at
           FROM analysis_runs
           WHERE error_message IS NOT NULL AND TRIM(error_message) != ''
           ORDER BY id DESC
           LIMIT 20"""
    ).fetchall()
    app_log_lines = read_filtered_app_logs(log_query, limit=250)

    return render_template(
        "debug_issues.html",
        issue_reports=issue_reports,
        recent_failures=recent_failures,
        app_log_lines=app_log_lines,
        filters={
            "entry_type": entry_type,
            "entry_status": entry_status,
            "q": query,
            "log_query": log_query,
        },
        compose_source=(
            extract_local_path(request.args.get("source"))
            or extract_local_path(request.referrer)
            or request.path
        ),
        message=request.args.get("message"),
    )


@app.route("/debug/issues", methods=["POST"])
def create_issue_report():
    db = get_db()
    wants_json = request.headers.get("X-Requested-With") == "XMLHttpRequest"
    entry_type = (request.form.get("entry_type") or "issue").strip()
    if entry_type not in {"bug", "issue", "recommendation", "note"}:
        entry_type = "issue"

    title = (request.form.get("title") or "").strip() or f"{entry_type.title()} report"
    details = (request.form.get("details") or "").strip()
    return_to = safe_return_path(request.form.get("return_to"))
    source_path = extract_local_path(request.form.get("source_path")) or return_to
    browser_console = (request.form.get("browser_console") or "").strip() or None

    if not details:
        message = "Details are required before submitting a report."
        if wants_json:
            return jsonify({"status": "error", "message": message}), 400
        return redirect(append_query_params(return_to, message=message))

    cursor = db.execute(
        """INSERT INTO issue_reports (entry_type, title, details, source_path, browser_console, status)
           VALUES (?, ?, ?, ?, ?, 'open')""",
        (entry_type, title, details, source_path, browser_console),
    )
    db.commit()
    if wants_json:
        return jsonify({
            "status": "ok",
            "message": "Report saved.",
            "report_id": cursor.lastrowid,
            "source_path": source_path,
        })
    return redirect(append_query_params(return_to, message="Report saved."))


@app.route("/debug/issues/<int:issue_id>/complete", methods=["POST"])
def complete_issue_report(issue_id):
    db = get_db()
    db.execute(
        "UPDATE issue_reports SET status='completed', completed_at=CURRENT_TIMESTAMP WHERE id=?",
        (issue_id,),
    )
    db.commit()
    return redirect(safe_return_path(request.form.get("return_to")))


# ── API: Dashboard ────────────────────────────────────────

@app.route("/api/dashboard")
def api_dashboard():
    db = get_db()
    seasons   = db.execute("SELECT COUNT(*) FROM seasons").fetchone()[0]
    scheduled = db.execute("SELECT COUNT(*) FROM scheduled_games").fetchone()[0]
    events    = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    players   = db.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    upcoming  = db.execute(
        """SELECT * FROM scheduled_games
           WHERE game_date >= date('now') AND status != 'cancelled'
           ORDER BY game_date, game_time LIMIT 5"""
    ).fetchall()
    recent    = db.execute(
        "SELECT * FROM events ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    return jsonify({
        "seasons":       seasons,
        "scheduled":     scheduled,
        "events":        events,
        "players":       players,
        "upcoming_games": [dict(r) for r in upcoming],
        "recent_events":  [dict(r) for r in recent],
    })


@app.route("/api/resource-status")
def api_resource_status():
    return jsonify(build_resource_status())


# ── API: Seasons ──────────────────────────────────────────

@app.route("/api/seasons", methods=["GET"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_seasons_list():
    db = get_db()
    rows = db.execute("SELECT * FROM seasons ORDER BY start_date DESC").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/seasons", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_seasons_create():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    start = data.get("start_date", "")
    end   = data.get("end_date", "")
    if not name or not start or not end:
        return jsonify({"error": "name, start_date, end_date required"}), 400
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO seasons (name, start_date, end_date) VALUES (?,?,?)",
            (name, start, end),
        )
        db.commit()
        row = db.execute("SELECT * FROM seasons WHERE id=?", (cur.lastrowid,)).fetchone()
        return jsonify(dict(row)), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Season name already exists"}), 409


@app.route("/api/seasons/<int:season_id>", methods=["GET"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_season_get(season_id):
    db = get_db()
    row = db.execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@app.route("/api/seasons/<int:season_id>", methods=["PUT"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_season_update(season_id):
    data = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    name  = data.get("name", row["name"])
    start = data.get("start_date", row["start_date"])
    end   = data.get("end_date", row["end_date"])
    db.execute(
        "UPDATE seasons SET name=?, start_date=?, end_date=? WHERE id=?",
        (name, start, end, season_id),
    )
    db.commit()
    return jsonify(dict(db.execute("SELECT * FROM seasons WHERE id=?", (season_id,)).fetchone()))


@app.route("/api/seasons/<int:season_id>", methods=["DELETE"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_season_delete(season_id):
    db = get_db()
    db.execute("DELETE FROM scheduled_games WHERE season_id=?", (season_id,))
    db.execute("DELETE FROM seasons WHERE id=?", (season_id,))
    db.commit()
    return jsonify({"deleted": True})


# ── API: Scheduled Games ──────────────────────────────────

@app.route("/api/scheduled_games", methods=["GET"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_scheduled_games_list():
    db = get_db()
    rows = fetch_scheduled_games(
        db,
        season_id=request.args.get("season_id", type=int),
        level=(request.args.get("level") or "").strip(),
        gender=(request.args.get("gender") or "").strip(),
        status=(request.args.get("status") or "").strip(),
    )
    return jsonify([dict(r) for r in rows])


@app.route("/api/scheduled_games", methods=["POST"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_scheduled_games_create():
    data = request.get_json(force=True)
    required = ("season_id", "game_date", "opponent_name")
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    db = get_db()
    cur = db.execute(
        """INSERT INTO scheduled_games
           (season_id, program_name, gender, level, game_date, game_time,
            location_type, opponent_name, tournament_name, status, notes)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["season_id"],
            data.get("program_name", "Liberty"),
            data.get("gender", "boys"),
            data.get("level", "jr_high"),
            data["game_date"],
            data.get("game_time"),
            data.get("location_type", "home"),
            data["opponent_name"],
            data.get("tournament_name"),
            data.get("status", "scheduled"),
            data.get("notes"),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM scheduled_games WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/scheduled_games/<int:game_id>", methods=["GET"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_scheduled_game_get(game_id):
    db = get_db()
    row = db.execute("SELECT * FROM scheduled_games WHERE id=?", (game_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@app.route("/api/scheduled_games/<int:game_id>", methods=["PUT"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_scheduled_game_update(game_id):
    data = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT * FROM scheduled_games WHERE id=?", (game_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    db.execute(
        """UPDATE scheduled_games SET
           season_id=?, program_name=?, gender=?, level=?, game_date=?, game_time=?,
           location_type=?, opponent_name=?, tournament_name=?, status=?, notes=?,
           updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (
            data.get("season_id", row["season_id"]),
            data.get("program_name", row["program_name"]),
            data.get("gender", row["gender"]),
            data.get("level", row["level"]),
            data.get("game_date", row["game_date"]),
            data.get("game_time", row["game_time"]),
            data.get("location_type", row["location_type"]),
            data.get("opponent_name", row["opponent_name"]),
            data.get("tournament_name", row["tournament_name"]),
            data.get("status", row["status"]),
            data.get("notes", row["notes"]),
            game_id,
        ),
    )
    db.commit()
    return jsonify(dict(db.execute("SELECT * FROM scheduled_games WHERE id=?", (game_id,)).fetchone()))


@app.route("/api/scheduled_games/<int:game_id>", methods=["DELETE"])
@require_feature("ENABLE_SEASONS_SCHEDULE")
def api_scheduled_game_delete(game_id):
    db = get_db()
    db.execute("DELETE FROM scheduled_games WHERE id=?", (game_id,))
    db.commit()
    return jsonify({"deleted": True})


# ── API: Games (completed games) ───────────────────────────

@app.route("/api/games", methods=["GET"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_games_list():
    db = get_db()
    rows = fetch_games_with_context(db)
    return jsonify([dict(r) for r in rows])


@app.route("/api/games", methods=["POST"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_games_create():
    data = request.get_json(force=True)
    required = ("source_type", "source_key")
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    db = get_db()
    cur = db.execute(
        """INSERT INTO games
           (scheduled_game_id, start_time, end_time, source_type, source_key,
            nfhs_game_id, nfhs_url, home_score, away_score, result, is_conference)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data.get("scheduled_game_id"),
            data.get("start_time"),
            data.get("end_time"),
            data["source_type"],
            data["source_key"],
            data.get("nfhs_game_id"),
            data.get("nfhs_url"),
            data.get("home_score"),
            data.get("away_score"),
            data.get("result"),
            int(bool(data.get("is_conference", False))),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM games WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/games/<int:game_id>", methods=["GET"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_games_get(game_id):
    db = get_db()
    row = db.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@app.route("/api/games/<int:game_id>", methods=["PUT"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_games_update(game_id):
    data = request.get_json(force=True)
    db = get_db()
    existing = db.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
    if not existing:
        return jsonify({"error": "Not found"}), 404
    db.execute(
        """UPDATE games SET
           scheduled_game_id=?, start_time=?, end_time=?, source_type=?, source_key=?,
           nfhs_game_id=?, nfhs_url=?, home_score=?, away_score=?, result=?, is_conference=?,
           updated_at=CURRENT_TIMESTAMP
           WHERE id=?""",
        (
            data.get("scheduled_game_id", existing["scheduled_game_id"]),
            data.get("start_time", existing["start_time"]),
            data.get("end_time", existing["end_time"]),
            data.get("source_type", existing["source_type"]),
            data.get("source_key", existing["source_key"]),
            data.get("nfhs_game_id", existing["nfhs_game_id"]),
            data.get("nfhs_url", existing["nfhs_url"]),
            data.get("home_score", existing["home_score"]),
            data.get("away_score", existing["away_score"]),
            data.get("result", existing["result"]),
            int(data.get("is_conference", bool(existing["is_conference"]))),
            game_id,
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
    return jsonify(dict(row))


@app.route("/api/games/<int:game_id>", methods=["DELETE"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_games_delete(game_id):
    db = get_db()
    db.execute("DELETE FROM games WHERE id=?", (game_id,))
    db.commit()
    return jsonify({"deleted": True})


# ── API: Sources (film sources per game) ────────────────────

@app.route("/api/sources", methods=["GET"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_sources_list():
    db = get_db()
    rows = fetch_sources_with_context(db, game_id=request.args.get("game_id", type=int))
    return jsonify([dict(r) for r in rows])


@app.route("/api/sources", methods=["POST"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_sources_create():
    data = request.get_json(force=True)
    required = ("game_id", "source_type", "source_path")
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    db = get_db()
    cur = db.execute(
        """INSERT INTO sources (game_id, source_type, source_path)
           VALUES (?,?,?)""",
        (data["game_id"], data["source_type"], data["source_path"]),
    )
    db.commit()
    row = db.execute("SELECT * FROM sources WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/sources/<int:source_id>", methods=["GET"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_sources_get(source_id):
    db = get_db()
    row = db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@app.route("/api/sources/<int:source_id>", methods=["DELETE"])
@require_feature("ENABLE_GAMES_SOURCES")
def api_sources_delete(source_id):
    db = get_db()
    db.execute("DELETE FROM sources WHERE id=?", (source_id,))
    db.commit()
    return jsonify({"deleted": True})


# ── API: NFHS Matches ──────────────────────────────────────

@app.route("/api/nfhs_matches", methods=["GET"])
@require_feature("ENABLE_NFHS_MATCHING")
def api_nfhs_matches_list():
    db = get_db()
    rows = fetch_nfhs_matches_with_context(db)
    return jsonify([dict(r) for r in rows])


@app.route("/api/nfhs_matches", methods=["POST"])
@require_feature("ENABLE_NFHS_MATCHING")
def api_nfhs_matches_create():
    data = request.get_json(force=True)
    required = ("scheduled_game_id", "nfhs_game_id", "nfhs_url")
    missing = [k for k in required if not data.get(k)]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400
    db = get_db()
    cur = db.execute(
        """INSERT INTO nfhs_matches
           (scheduled_game_id, nfhs_game_id, nfhs_url, match_status, confidence)
           VALUES (?,?,?,?,?)""",
        (
            data["scheduled_game_id"],
            data["nfhs_game_id"],
            data["nfhs_url"],
            data.get("match_status", "candidate"),
            data.get("confidence"),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM nfhs_matches WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


@app.route("/api/nfhs_matches/<int:match_id>/confirm", methods=["POST"])
@require_feature("ENABLE_NFHS_MATCHING")
def api_nfhs_matches_confirm(match_id):
    db = get_db()
    payload = confirm_nfhs_match(db, match_id)
    if not payload:
        return jsonify({"error": "Not found"}), 404
    return jsonify(payload)


@app.route("/api/nfhs_matches/<int:match_id>/reject", methods=["POST"])
@require_feature("ENABLE_NFHS_MATCHING")
def api_nfhs_matches_reject(match_id):
    db = get_db()
    row = db.execute("SELECT * FROM nfhs_matches WHERE id=?", (match_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    db.execute("UPDATE nfhs_matches SET match_status='rejected' WHERE id=?", (match_id,))
    db.commit()
    row = db.execute("SELECT * FROM nfhs_matches WHERE id=?", (match_id,)).fetchone()
    return jsonify(dict(row))


# ── API: Events (film tagger) ─────────────────────────────

@app.route("/api/save_event", methods=["POST"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def save_event():
    data = request.get_json(force=True)
    if not data or "timestamp_ms" not in data:
        return jsonify({"status": "error", "message": "timestamp_ms required"}), 400
    db = get_db()
    cur = db.execute(
        """INSERT INTO events
           (game_id, player, event_type, shot_result, timestamp_ms, details_json,
            source_video, source_frame, human_verified, confidence)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            data.get("game_id", "default_game"),
            data.get("player"),
            data.get("event_type"),
            data.get("shot_result"),
            data["timestamp_ms"],
            data.get("details_json"),
            data.get("source_video"),
            data.get("source_frame"),
            int(bool(data.get("human_verified", True))),
            data.get("confidence"),
        ),
    )
    db.commit()
    refresh_game_stats(db, data.get("game_id", "default_game"))
    return jsonify({"status": "success", "id": cur.lastrowid})


@app.route("/api/events/<game_id>", methods=["GET"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def get_events(game_id):
    db = get_db()
    event_type = (request.args.get("event_type") or "").strip()
    if event_type:
        rows = db.execute(
            "SELECT * FROM events WHERE game_id=? AND event_type=? ORDER BY timestamp_ms ASC",
            (game_id, event_type),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM events WHERE game_id=? ORDER BY timestamp_ms ASC",
            (game_id,),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/events/<int:event_id>", methods=["PUT"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def update_event(event_id):
    data = request.get_json(force=True)
    db = get_db()
    row = db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    db.execute(
        """UPDATE events SET player=?, event_type=?, shot_result=?,
           timestamp_ms=?, details_json=?, human_verified=?, confidence=?
           WHERE id=?""",
        (
            data.get("player", row["player"]),
            data.get("event_type", row["event_type"]),
            data.get("shot_result", row["shot_result"]),
            data.get("timestamp_ms", row["timestamp_ms"]),
            data.get("details_json", row["details_json"]),
            int(bool(data.get("human_verified", row["human_verified"]))),
            data.get("confidence", row["confidence"]),
            event_id,
        ),
    )
    db.commit()
    refresh_game_stats(db, row["game_id"])
    return jsonify(dict(db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()))


@app.route("/api/events/<int:event_id>", methods=["DELETE"])
@require_feature("ENABLE_MANUAL_TAG_MVP")
def delete_event(event_id):
    db = get_db()
    row = db.execute("SELECT game_id FROM events WHERE id=?", (event_id,)).fetchone()
    db.execute("DELETE FROM events WHERE id=?", (event_id,))
    db.commit()
    if row:
        refresh_game_stats(db, row["game_id"])
    return jsonify({"deleted": True})


# ── API: Players ──────────────────────────────────────────

@app.route("/api/players", methods=["GET"])
def api_players_list():
    db = get_db()
    season_id = request.args.get("season_id")
    if season_id:
        rows = db.execute(
            "SELECT * FROM players WHERE season_id=? ORDER BY jersey_number", (season_id,)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM players ORDER BY jersey_number").fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/players", methods=["POST"])
def api_players_create():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    db = get_db()
    cur = db.execute(
        """INSERT INTO players (name, jersey_number, position, grade,
           program_name, gender, level, season_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            name,
            data.get("jersey_number"),
            data.get("position"),
            data.get("grade"),
            data.get("program_name", "Liberty"),
            data.get("gender", "boys"),
            data.get("level", "jr_high"),
            data.get("season_id"),
        ),
    )
    db.commit()
    row = db.execute("SELECT * FROM players WHERE id=?", (cur.lastrowid,)).fetchone()
    return jsonify(dict(row)), 201


# ── API: Analysis ─────────────────────────────────────────

@app.route("/api/analysis_status/<game_id>")
@require_feature("ENABLE_AUTO_STATS_M1")
def get_analysis_status(game_id):
    db = get_db()
    row = db.execute(
        """SELECT status, started_at, completed_at, error_message, settings_json,
                  (SELECT COUNT(*) FROM detections WHERE game_id = analysis_runs.game_id) AS detection_count,
                  (SELECT COUNT(*) FROM events WHERE game_id = analysis_runs.game_id) AS event_count
           FROM analysis_runs WHERE game_id=? ORDER BY id DESC LIMIT 1""",
        (game_id,),
    ).fetchone()
    if row is None:
        return jsonify({
            "status": "not_started",
            "detection_count": 0,
            "event_count": 0,
            "event_generation_summary": "AI analysis has not started yet.",
            "auto_event_persistence_enabled": analysis_option_enabled("USE_DRIBBLE_EVENTS"),
        })

    payload = dict(row)
    settings_snapshot = {}
    if payload.get("settings_json"):
        try:
            settings_snapshot = json.loads(payload["settings_json"])
        except json.JSONDecodeError:
            settings_snapshot = {}
    generator_mode = settings_snapshot.get("ai", {}).get("event_generator_mode", AI_DEFAULTS["event_generator_mode"])
    if generator_mode == "expanded":
        payload["event_generation_summary"] = (
            "YOLO currently detects players and the ball. The expanded heuristic generator tries to "
            "derive possession changes, shots, makes, misses, rebounds, assists, steals, turnovers, "
            "blocks, fouls, and dribbles from those detections."
        )
    else:
        payload["event_generation_summary"] = (
            "YOLO currently detects players and the ball. Auto-tagged events come from the legacy "
            "dribble-only heuristic, so a completed upload can still show zero tagged events."
        )
    payload["auto_event_persistence_enabled"] = analysis_option_enabled("USE_DRIBBLE_EVENTS")
    return jsonify(payload)


# ── API: Stats ────────────────────────────────────────────

@app.route("/api/stats/<game_id>")
@require_feature("ENABLE_AUTO_STATS_M1")
def get_stats(game_id):
    from stats import refresh_stats
    db = get_db()
    return jsonify(refresh_stats(db, game_id))


# ── API: Upload video ─────────────────────────────────────

@app.route("/api/upload_video", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def upload_video():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400
    filename = secure_filename(f.filename)
    dest = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    f.save(dest)
    return jsonify({"status": "uploaded", "filename": filename})


@app.route("/api/videos")
@require_feature("ENABLE_AUTO_STATS_M1")
def api_videos():
    """Return all videos from the DB with their analysis status."""
    db = get_db()
    rows = db.execute("""
        SELECT v.*, ar.status as analysis_status, ar.error_message,
               (SELECT COUNT(*) FROM detections d WHERE d.game_id = v.game_id) as detection_count,
               (SELECT COUNT(*) FROM events e WHERE e.game_id = v.game_id) as event_count,
               (SELECT COUNT(*) FROM analysis_runs ar2 WHERE ar2.source_video_id = v.id OR ar2.base_game_id = v.game_id OR ar2.video_path = v.file_path) as analysis_run_count
        FROM videos v
        LEFT JOIN analysis_runs ar ON ar.game_id = v.game_id
                                   AND ar.id = (SELECT MAX(id) FROM analysis_runs WHERE game_id = v.game_id)
        ORDER BY v.id DESC
    """).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/videos/<int:vid_id>/compare")
@require_feature("ENABLE_AUTO_STATS_M1")
def compare_video_analysis(vid_id):
    db = get_db()
    video = db.execute("SELECT * FROM videos WHERE id=?", (vid_id,)).fetchone()
    if not video:
        abort(404)

    ensure_primary_run_metadata(db, video)
    rows = db.execute(
        """SELECT ar.*,
                  (SELECT COUNT(*) FROM detections d WHERE d.game_id = ar.game_id) AS detection_count,
                  (SELECT COUNT(*) FROM events e WHERE e.game_id = ar.game_id) AS event_count
           FROM analysis_runs ar
           WHERE ar.source_video_id = ?
              OR ar.base_game_id = ?
              OR ar.game_id = ?
              OR ar.video_path = ?
           ORDER BY ar.id DESC""",
        (vid_id, video["game_id"], video["game_id"], video["file_path"]),
    ).fetchall()
    runs = [build_run_summary(row) for row in rows]
    primary_run = next((run for run in runs if run.get("run_kind") == "primary"), runs[-1] if runs else None)
    baseline_detection_count = primary_run["detection_count"] if primary_run else 0
    baseline_event_count = primary_run["event_count"] if primary_run else 0
    current_ai_settings = get_runtime_settings()["ai"]
    for run in runs:
        run["detection_delta"] = run["detection_count"] - baseline_detection_count
        run["event_delta"] = run["event_count"] - baseline_event_count

    return render_template(
        "analysis_compare.html",
        video=video,
        runs=runs,
        primary_run=primary_run,
        current_ai_settings=current_ai_settings,
        current_detector_model=display_detector_model(current_ai_settings),
        message=request.args.get("message"),
    )


@app.route("/videos/<int:vid_id>/rerun", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def rerun_video_analysis(vid_id):
    db = get_db()
    video = db.execute("SELECT * FROM videos WHERE id=?", (vid_id,)).fetchone()
    if not video:
        abort(404)

    runtime_settings = get_runtime_settings()
    ensure_primary_run_metadata(db, video, build_analysis_settings_snapshot(runtime_settings))
    run_payload = queue_analysis_run(
        db,
        video,
        runtime_settings,
        run_kind="rerun",
        run_label=request.form.get("run_label"),
    )

    if ai_runtime_available():
        start_analysis_subprocess(run_payload["game_id"], video["file_path"])
        message = f"Queued rerun '{run_payload['run_label']}'."
    else:
        db.execute(
            "UPDATE analysis_runs SET status='failed', error_message=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
            ("Missing AI packages (cv2/ultralytics)", run_payload["id"]),
        )
        db.commit()
        message = "Rerun saved, but AI packages are unavailable in the current runtime."

    return redirect(url_for("compare_video_analysis", vid_id=vid_id, message=message))


@app.route("/api/check_duplicate")
@require_feature("ENABLE_AUTO_STATS_M1")
def api_check_duplicate():
    """Check if a filename has been uploaded before."""
    original_filename = request.args.get("filename", "")
    if not original_filename:
        return jsonify({"is_duplicate": False})
    db = get_db()
    rows = db.execute(
        "SELECT id, stored_filename, opponent, upload_timestamp FROM videos WHERE original_filename=? ORDER BY id DESC",
        (secure_filename(original_filename),),
    ).fetchall()
    if rows:
        return jsonify({
            "is_duplicate": True,
            "previous_uploads": [dict(r) for r in rows],
        })
    return jsonify({"is_duplicate": False})


@app.route("/api/videos/<int:vid_id>", methods=["DELETE"])
@require_feature("ENABLE_AUTO_STATS_M1")
def delete_video(vid_id):
    """Delete a video record, its file on disk, and all related analysis data."""
    db = get_db()
    row = db.execute("SELECT * FROM videos WHERE id=?", (vid_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404

    game_id = row["game_id"]
    file_path = row["file_path"]
    run_game_ids = [
        run["game_id"]
        for run in db.execute(
            "SELECT game_id FROM analysis_runs WHERE source_video_id=? OR base_game_id=? OR video_path=?",
            (vid_id, game_id, file_path),
        ).fetchall()
    ] or [game_id]

    # Delete file from disk
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            pass  # Don't fail if file already gone

    # Delete all related analysis data
    for run_game_id in run_game_ids:
        db.execute("DELETE FROM events WHERE game_id=?", (run_game_id,))
        db.execute("DELETE FROM detections WHERE game_id=?", (run_game_id,))
        db.execute("DELETE FROM stats WHERE game_id=?", (run_game_id,))
    db.execute("DELETE FROM analysis_runs WHERE source_video_id=? OR base_game_id=? OR video_path=?", (vid_id, game_id, file_path))
    db.execute("DELETE FROM videos WHERE id=?", (vid_id,))
    db.commit()

    return jsonify({"success": True, "deleted_game_id": game_id})


@app.route("/api/admin/reset", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def admin_reset():
    """Wipe all video uploads, analysis data, and uploaded files. Fresh start."""
    db = get_db()

    # Collect file paths before deleting
    rows = db.execute("SELECT file_path FROM videos").fetchall()
    for row in rows:
        fp = row["file_path"]
        if fp and os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass

    # Clear all analysis/video data (preserve seasons, games, players)
    db.executescript("""
        DELETE FROM events;
        DELETE FROM detections;
        DELETE FROM analysis_runs;
        DELETE FROM stats;
        DELETE FROM videos;
    """)
    db.commit()

    return jsonify({"success": True, "message": "All video data cleared."})


@app.route("/upload", methods=["POST"])
@require_feature("ENABLE_AUTO_STATS_M1")
def upload_and_analyze():
    """Handle the film tool's 'Upload and Analyze' form (posts to /upload)."""
    if "video" not in request.files:
        return "No video file provided", 400
    f = request.files["video"]
    if not f.filename:
        return "Empty filename", 400

    opponent = request.form.get("opponent", "unknown").strip() or "unknown"
    original_filename = secure_filename(f.filename)
    stem, ext = os.path.splitext(original_filename)

    # ── Timestamped stored filename ───────────────────────────
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stored_filename = f"{stem}_{ts}{ext}"
    dest = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_filename)
    f.save(dest)
    file_size = os.path.getsize(dest)

    # ── Duplicate detection ───────────────────────────────────
    db = get_db()
    prior = db.execute(
        "SELECT id, stored_filename, upload_timestamp FROM videos WHERE original_filename=? ORDER BY id DESC LIMIT 1",
        (original_filename,),
    ).fetchone()
    is_dup = prior is not None
    dup_of_id = prior["id"] if prior else None
    dup_msg = ""
    if is_dup:
        dup_msg = (
            f"<p style='background:#fef3c7;border:1px solid #f59e0b;border-radius:6px;"
            f"padding:10px 14px;margin-top:12px;'>⚠️ <strong>Duplicate detected</strong> — "
            f"<em>{original_filename}</em> was previously uploaded as "
            f"<code>{prior['stored_filename']}</code> on {prior['upload_timestamp']}. "
            f"This upload has been saved with a new timestamp.</p>"
        )

    # ── game_id & DB records ─────────────────────────────────
    game_id = f"{opponent.lower().replace(' ', '_')}_{stem}_{ts}"

    video_cur = db.execute(
        """INSERT INTO videos (original_filename, stored_filename, file_path, file_size_bytes,
                               opponent, game_id, is_duplicate, duplicate_of_id)
           VALUES (?,?,?,?,?,?,?,?)""",
        (original_filename, stored_filename, dest, file_size,
         opponent, game_id, int(is_dup), dup_of_id),
    )
    video_row = db.execute(
        "SELECT * FROM videos WHERE id=?",
        (video_cur.lastrowid,),
    ).fetchone()
    runtime_settings = get_runtime_settings()
    run_payload = queue_analysis_run(
        db,
        video_row,
        runtime_settings,
        run_kind="primary",
        run_label="Original upload",
    )
    run_id = run_payload["id"]

    # ── Launch AI subprocess ──────────────────────────────────
    if ai_runtime_available():
        start_analysis_subprocess(game_id, dest)
        ai_msg = "✅ AI analysis running in background — check <a href='/status'>Status page</a> for progress."
    else:
        db.execute(
            "UPDATE analysis_runs SET status='failed', error_message=?, completed_at=CURRENT_TIMESTAMP WHERE id=?",
            ("Missing AI packages (cv2/ultralytics)", run_id),
        )
        db.commit()
        ai_msg = "⚠️ AI analysis unavailable — missing opencv-python or ultralytics."

    film_url = url_for("film", filename=stored_filename, game_id=game_id)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({
            "status": "uploaded",
            "stored_filename": stored_filename,
            "game_id": game_id,
            "redirect_url": film_url,
            "analysis_message": ai_msg,
        })

    return f"""<!DOCTYPE html>
    <html><head>
    <meta http-equiv="refresh" content="4;url={film_url}">
    <style>
      body{{font-family:sans-serif;padding:40px;background:#f7f6f2;max-width:640px;margin:auto;}}
      .card{{background:#fff;border:1px solid #e2e0da;border-radius:8px;padding:28px;margin-top:24px;}}
      code{{background:#f3f4f6;padding:2px 6px;border-radius:4px;font-size:.9em;}}
      .nav a{{margin-right:16px;color:#01696f;text-decoration:none;font-weight:500;}}
      .report-link{{display:inline-block;padding:8px 12px;border-radius:999px;background:linear-gradient(135deg,#f59e0b,#ef4444,#ec4899);color:#fff !important;font-weight:700;box-shadow:0 8px 20px rgba(239,68,68,.25);}}
    </style>
    </head><body>
    <div class="nav"><a href="/">⬅ Dashboard</a><a href="/videos">📹 All Videos</a><a href="/status">📊 Status</a><a href="/debug">🛠 Debug / Issues</a><a href="/debug?compose=1&source=/upload" class="report-link">Report Bug / Idea</a></div>
    <div class="card">
      <h2>📹 Upload complete</h2>
      <p><strong>Original filename:</strong> {original_filename}</p>
      <p><strong>Stored as:</strong> <code>{stored_filename}</code></p>
      <p><strong>Opponent:</strong> {opponent}</p>
      <p><strong>Game ID:</strong> <code>{game_id}</code></p>
      <p><strong>File size:</strong> {file_size/1_000_000:.1f} MB</p>
      {dup_msg}
      <p style="margin-top:16px;">{ai_msg}</p>
      <p style="margin-top:20px;color:#6b7280;font-size:.9em;">
        Redirecting to film tool in 4 seconds…
        <a href="{film_url}">click here</a> to go now.
      </p>
      <p><a href="/videos">📹 View all uploaded videos</a> &nbsp;|&nbsp; <a href="/status">📊 Analysis status</a></p>
    </div>
    </body></html>
    """


@app.route("/status")
@require_feature("ENABLE_AUTO_STATS_M1")
def status_page():
    """Live status page showing all analysis runs."""
    db = get_db()
    runs = db.execute(
        "SELECT * FROM analysis_runs ORDER BY id DESC"
    ).fetchall()

    # Count detections and events per game
    det_counts = {r[0]: r[1] for r in db.execute(
        "SELECT game_id, COUNT(*) FROM detections GROUP BY game_id"
    ).fetchall()}
    evt_counts = {r[0]: r[1] for r in db.execute(
        "SELECT game_id, COUNT(*) FROM events GROUP BY game_id"
    ).fetchall()}

    return render_template(
        "status.html",
        runs=[dict(row) for row in runs],
        detection_rows=[
            {
                "game_id": game_id,
                "detections": det_counts.get(game_id, 0),
                "events": evt_counts.get(game_id, 0),
            }
            for game_id in sorted(set(list(det_counts) + list(evt_counts)))
        ],
    )

# ── Additional Page Routes ─────────────────────────────────────
@app.route("/games")
@require_feature("ENABLE_GAMES_SOURCES")
def games_page():
    return render_games_page(
        message=request.args.get("message"),
        error=request.args.get("error"),
        edit_game_id=request.args.get("edit_game_id", type=int),
    )


@app.route("/games/save", methods=["POST"])
@require_feature("ENABLE_GAMES_SOURCES")
def games_save():
    form = request.form
    game_id = form.get("game_id", "").strip()
    source_type = (form.get("source_type") or "").strip()
    source_key = (form.get("source_key") or "").strip()

    if not source_type or not source_key:
        return render_games_page(
            error="Source type and source key are required for each game.",
            edit_game_id=int(game_id) if game_id else None,
            game_form_data={
                "id": game_id,
                "scheduled_game_id": form.get("scheduled_game_id", "").strip(),
                "start_time": (form.get("start_time") or "").strip(),
                "end_time": (form.get("end_time") or "").strip(),
                "source_type": source_type,
                "source_key": source_key,
                "nfhs_game_id": (form.get("nfhs_game_id") or "").strip(),
                "nfhs_url": (form.get("nfhs_url") or "").strip(),
                "home_score": (form.get("home_score") or "").strip(),
                "away_score": (form.get("away_score") or "").strip(),
                "result": (form.get("result") or "").strip(),
                "is_conference": bool(form.get("is_conference")),
            },
        ), 400

    db = get_db()
    values = (
        int(form["scheduled_game_id"]) if form.get("scheduled_game_id") else None,
        (form.get("start_time") or "").strip() or None,
        (form.get("end_time") or "").strip() or None,
        source_type,
        source_key,
        (form.get("nfhs_game_id") or "").strip() or None,
        (form.get("nfhs_url") or "").strip() or None,
        int(form["home_score"]) if form.get("home_score") else None,
        int(form["away_score"]) if form.get("away_score") else None,
        (form.get("result") or "").strip() or None,
        int(bool(form.get("is_conference"))),
    )

    if game_id:
        db.execute(
            """UPDATE games SET
               scheduled_game_id=?, start_time=?, end_time=?, source_type=?, source_key=?,
               nfhs_game_id=?, nfhs_url=?, home_score=?, away_score=?, result=?, is_conference=?,
               updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            values + (int(game_id),),
        )
        message = "Game updated."
    else:
        db.execute(
            """INSERT INTO games
               (scheduled_game_id, start_time, end_time, source_type, source_key,
                nfhs_game_id, nfhs_url, home_score, away_score, result, is_conference)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            values,
        )
        message = "Game created."
    db.commit()
    return redirect(url_for("games_page", message=message))


@app.route("/games/<int:game_id>/delete", methods=["POST"])
@require_feature("ENABLE_GAMES_SOURCES")
def games_delete(game_id):
    db = get_db()
    db.execute("DELETE FROM sources WHERE game_id=?", (game_id,))
    db.execute("DELETE FROM games WHERE id=?", (game_id,))
    db.commit()
    return redirect(url_for("games_page", message="Game deleted."))


@app.route("/games/sources/save", methods=["POST"])
@require_feature("ENABLE_GAMES_SOURCES")
def games_save_source():
    form = request.form
    game_id = form.get("game_id", "").strip()
    source_type = (form.get("source_type") or "").strip()
    source_path = (form.get("source_path") or "").strip()

    if not game_id or not source_type or not source_path:
        return render_games_page(
            error="Game, source type, and source path are required to link a source.",
            source_form_data={
                "game_id": game_id,
                "source_type": source_type,
                "source_path": source_path,
            },
        ), 400

    db = get_db()
    db.execute(
        "INSERT INTO sources (game_id, source_type, source_path) VALUES (?,?,?)",
        (int(game_id), source_type, source_path),
    )
    db.commit()
    return redirect(url_for("games_page", message="Source linked to game."))


@app.route("/games/sources/<int:source_id>/delete", methods=["POST"])
@require_feature("ENABLE_GAMES_SOURCES")
def games_delete_source(source_id):
    db = get_db()
    db.execute("DELETE FROM sources WHERE id=?", (source_id,))
    db.commit()
    return redirect(url_for("games_page", message="Source removed."))

@app.route("/nfhs-matches")
@require_feature("ENABLE_NFHS_MATCHING")
def nfhs_matches_page():
    return render_nfhs_matches_page(
        message=request.args.get("message"),
        error=request.args.get("error"),
    )


@app.route("/nfhs-matches/add", methods=["POST"])
@require_feature("ENABLE_NFHS_MATCHING")
def nfhs_matches_add():
    form = request.form
    scheduled_game_id = form.get("scheduled_game_id", "").strip()
    nfhs_game_id = (form.get("nfhs_game_id") or "").strip()
    nfhs_url = (form.get("nfhs_url") or "").strip()
    confidence = (form.get("confidence") or "").strip()

    if not scheduled_game_id or not nfhs_game_id or not nfhs_url:
        return render_nfhs_matches_page(
            error="Scheduled game, NFHS game ID, and NFHS URL are required.",
            form_data={
                "scheduled_game_id": scheduled_game_id,
                "nfhs_game_id": nfhs_game_id,
                "nfhs_url": nfhs_url,
                "confidence": confidence,
            },
        ), 400

    db = get_db()
    db.execute(
        """INSERT INTO nfhs_matches
           (scheduled_game_id, nfhs_game_id, nfhs_url, match_status, confidence)
           VALUES (?,?,?,?,?)""",
        (
            int(scheduled_game_id),
            nfhs_game_id,
            nfhs_url,
            "candidate",
            float(confidence) if confidence else None,
        ),
    )
    db.commit()
    return redirect(url_for("nfhs_matches_page", message="NFHS candidate added."))


@app.route("/nfhs-matches/<int:match_id>/confirm", methods=["POST"])
@require_feature("ENABLE_NFHS_MATCHING")
def nfhs_matches_confirm_page(match_id):
    payload = confirm_nfhs_match(get_db(), match_id)
    if not payload:
        abort(404)
    return redirect(url_for("nfhs_matches_page", message="NFHS match confirmed and linked."))


@app.route("/nfhs-matches/<int:match_id>/reject", methods=["POST"])
@require_feature("ENABLE_NFHS_MATCHING")
def nfhs_matches_reject_page(match_id):
    db = get_db()
    row = db.execute("SELECT * FROM nfhs_matches WHERE id=?", (match_id,)).fetchone()
    if not row:
        abort(404)
    db.execute("UPDATE nfhs_matches SET match_status='rejected' WHERE id=?", (match_id,))
    db.commit()
    return redirect(url_for("nfhs_matches_page", message="NFHS match rejected."))


@app.route("/practices")
@require_feature("ENABLE_PRACTICES")
def practices_page():
    return render_practices_page(
        message=request.args.get("message"),
        error=request.args.get("error"),
        edit_practice_id=request.args.get("edit_practice_id", type=int),
    )


@app.route("/practices/save", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def practices_save():
    form = request.form
    filters = {
        "season_id": request.form.get("filter_season_id", type=int),
        "level": (request.form.get("filter_level") or "").strip(),
        "status": (request.form.get("filter_status") or "").strip(),
    }
    practice_id = form.get("practice_id", "").strip()
    season_id = form.get("season_id", "").strip()
    practice_date = (form.get("practice_date") or "").strip()

    if not season_id or not practice_date:
        return render_practices_page(
            error="Season and practice date are required.",
            filters=filters,
            edit_practice_id=int(practice_id) if practice_id else None,
            form_data={
                "id": practice_id,
                "season_id": season_id,
                "level": (form.get("level") or "jr_high").strip(),
                "practice_date": practice_date,
                "status": (form.get("status") or "planned").strip(),
                "plan_source": (form.get("plan_source") or "manual").strip(),
                "plan_text": (form.get("plan_text") or "").strip(),
                "coach_notes": (form.get("coach_notes") or "").strip(),
            },
        ), 400

    db = get_db()
    values = (
        int(season_id),
        (form.get("level") or "jr_high").strip() or "jr_high",
        practice_date,
        (form.get("status") or "planned").strip() or "planned",
        (form.get("plan_source") or "manual").strip() or "manual",
        (form.get("plan_text") or "").strip() or None,
        (form.get("coach_notes") or "").strip() or None,
    )
    if practice_id:
        db.execute(
            """UPDATE practices SET
               season_id=?, level=?, practice_date=?, status=?, plan_source=?,
               plan_text=?, coach_notes=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            values + (int(practice_id),),
        )
        message = "Practice updated."
    else:
        db.execute(
            """INSERT INTO practices
               (season_id, level, practice_date, status, plan_source, plan_text, coach_notes)
               VALUES (?,?,?,?,?,?,?)""",
            values,
        )
        message = "Practice created."
    db.commit()
    return redirect(
        url_for(
            "practices_page",
            season_id=filters["season_id"],
            level=filters["level"] or None,
            status=filters["status"] or None,
            message=message,
        )
    )


@app.route("/practices/<int:practice_id>/delete", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def practices_delete(practice_id):
    filters = {
        "season_id": request.form.get("filter_season_id", type=int),
        "level": (request.form.get("filter_level") or "").strip(),
        "status": (request.form.get("filter_status") or "").strip(),
    }
    db = get_db()
    db.execute("DELETE FROM practices WHERE id=?", (practice_id,))
    db.commit()
    return redirect(
        url_for(
            "practices_page",
            season_id=filters["season_id"],
            level=filters["level"] or None,
            status=filters["status"] or None,
            message="Practice deleted.",
        )
    )


@app.route("/practices/<int:practice_id>/generate", methods=["POST"])
@require_feature("ENABLE_PRACTICES")
def practice_generate_notes(practice_id):
    db = get_db()
    practice = db.execute("SELECT * FROM practices WHERE id=?", (practice_id,)).fetchone()
    if not practice:
        abort(404)
    ai_notes = build_practice_ai_notes(practice)
    combined_summary = build_practice_combined_summary(practice, ai_notes)
    db.execute(
        "UPDATE practices SET ai_notes=?, combined_summary=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (ai_notes, combined_summary, practice_id),
    )
    db.commit()
    return redirect(url_for("practice_report_page", practice_id=practice_id, message="Practice report refreshed."))


@app.route("/practices/<int:practice_id>/report")
@require_feature("ENABLE_PRACTICES")
def practice_report_page(practice_id):
    db = get_db()
    practice = db.execute(
        """
        SELECT p.*, s.name AS season_name
        FROM practices p
        LEFT JOIN seasons s ON s.id = p.season_id
        WHERE p.id=?
        """,
        (practice_id,),
    ).fetchone()
    if not practice:
        abort(404)
    return render_template(
        "practice_report.html",
        practice=practice,
        show_plan=request.args.get("show_plan", "1") != "0",
        show_coach=request.args.get("show_coach", "1") != "0",
        show_ai=request.args.get("show_ai", "1") != "0",
        show_combined=request.args.get("show_combined", "1") != "0",
        message=request.args.get("message"),
    )


@app.route("/practice-summary")
@require_feature("ENABLE_PRACTICES")
def practice_summary_page():
    db = get_db()
    filters = {
        "season_id": request.args.get("season_id", type=int),
        "level": (request.args.get("level") or "").strip(),
        "status": (request.args.get("status") or "").strip(),
        "start_date": (request.args.get("start_date") or "").strip(),
        "end_date": (request.args.get("end_date") or "").strip(),
    }
    seasons = db.execute("SELECT * FROM seasons ORDER BY start_date DESC, id DESC").fetchall()
    practices = fetch_practices_with_context(
        db,
        season_id=filters["season_id"],
        level=filters["level"],
        status=filters["status"],
        start_date=filters["start_date"] or None,
        end_date=filters["end_date"] or None,
    )
    range_summary = build_practice_range_summary(practices)
    return render_template(
        "practice_summary.html",
        seasons=seasons,
        practices=practices,
        filters=filters,
        range_summary=range_summary,
        level_options=SCHEDULE_LEVEL_OPTIONS,
        practice_status_options=PRACTICE_STATUS_OPTIONS,
    )

@app.route("/dashboard")
def dashboard_page():
    return render_template("dashboard.html")

@app.route("/users")
def users_page():
    return render_template("users.html")

if __name__ == "__main__":
    with app.app_context():
        init_db()
    debug_mode = os.environ.get("LIBERTY_DEBUG", "1").strip().lower() in {"1", "true", "yes", "on"}
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
