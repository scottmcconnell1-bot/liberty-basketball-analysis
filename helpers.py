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
import threading
import time
from datetime import datetime
from functools import wraps
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from flask import g, current_app, request, render_template, abort, url_for
from flask import jsonify  # noqa: F401  (re-exported: blueprints/ai.py imports it from helpers)

from module_keys import BASE_PLATFORM, SCOUTING, STATS
from settings_store import AI_DEFAULTS, load_all_settings
from settings_store import save_settings  # noqa: F401  (re-exported: blueprints/core.py imports it from helpers)

try:
    import psutil
except ImportError:  # pragma: no cover - optional at runtime
    psutil = None

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
POWER_SAMPLE_CACHE = {}

DEFAULT_TEAM_SEED = {
    "organization_name": "Liberty",
    "team_name": "Liberty",
    "program_name": "Liberty",
    "gender": "boys",
    "level": "jr_high",
}

EVENT_TYPE_SEEDS = [
    ("made_two", "Made 2PT", "shot", 1, 1, 0),
    ("missed_two", "Missed 2PT", "shot", 1, 0, 0),
    ("made_three", "Made 3PT", "shot", 1, 1, 0),
    ("missed_three", "Missed 3PT", "shot", 1, 0, 0),
    ("made_free_throw", "Made free throw", "free_throw", 1, 1, 0),
    ("missed_free_throw", "Missed free throw", "free_throw", 1, 0, 0),
    ("rebound_offensive", "Offensive rebound", "rebound", 1, 0, 0),
    ("rebound_defensive", "Defensive rebound", "rebound", 1, 0, 0),
    ("assist", "Assist", "assist", 1, 0, 0),
    ("steal", "Steal", "defense", 1, 0, 1),
    ("block", "Block", "defense", 1, 0, 0),
    ("turnover", "Turnover", "turnover", 1, 0, 1),
    ("foul_personal", "Personal foul", "foul", 1, 0, 0),
    ("foul_shooting", "Shooting foul", "foul", 1, 0, 0),
    ("substitution", "Substitution", "rotation", 0, 0, 0),
    ("timeout", "Timeout", "game_management", 0, 0, 0),
    ("jump_ball", "Jump ball", "game_management", 0, 0, 1),
    ("period_start", "Period start", "clock", 0, 0, 1),
    ("period_end", "Period end", "clock", 0, 0, 1),
    # Legacy event_type aliases. These bridge pre-taxonomy events so the
    # relational stats derivation (Stage 4C) still aggregates legacy rows.
    ("two_attempt", "Legacy 2PT attempt", "shot", 1, 1, 0),
    ("three_attempt", "Legacy 3PT attempt", "shot", 1, 1, 0),
    ("shot", "Legacy shot", "shot", 1, 1, 0),
    ("2pt", "Legacy 2PT", "shot", 1, 1, 0),
    ("3pt", "Legacy 3PT", "shot", 1, 1, 0),
    ("rebound", "Legacy rebound", "rebound", 1, 0, 0),
    ("make", "Made field goal (AI)", "shot", 1, 1, 0),
    ("miss", "Missed field goal (AI)", "shot", 1, 0, 0),
    ("possession_change", "Possession change (AI)", "possession", 0, 0, 1),
]

BASE_MODULE_ENTITLEMENT = {
    "module_key": BASE_PLATFORM,
    "notes": "Seeded by platform_core_stage_2_backfill; additional modules require Scott approval.",
}

DEMO_MODULE_ENTITLEMENTS = (
    {
        "module_key": STATS,
        "notes": "Seeded demo module entitlement (Stage 8A); stats packaging preview.",
    },
    {
        "module_key": SCOUTING,
        "notes": "Seeded demo module entitlement (Stage 8A); scouting packaging preview.",
    },
)

# ── Configuration ─────────────────────────────────────────


def get_default_team_id(db):
    """Return the default Liberty team id after Stage 2 backfill."""
    return _stage2_default_team_id(db)



def build_review_workflow_summary(db):
    """Aggregate event and review_items counts for coach trust surfaces."""
    event_rows = db.execute(
        """SELECT review_status, COUNT(*) AS count
           FROM events
           GROUP BY review_status"""
    ).fetchall()
    events_by_status = {row["review_status"]: row["count"] for row in event_rows}
    events_total = sum(events_by_status.values())

    item_rows = db.execute(
        """SELECT review_status, COUNT(*) AS count
           FROM review_items
           GROUP BY review_status"""
    ).fetchall()
    items_by_status = {row["review_status"]: row["count"] for row in item_rows}
    items_total = sum(items_by_status.values())

    return {
        "events_total": events_total,
        "events_by_status": events_by_status,
        "events_pending": events_by_status.get("pending", 0),
        "events_accepted": events_by_status.get("accepted", 0),
        "events_corrected": events_by_status.get("corrected", 0),
        "events_rejected": events_by_status.get("rejected", 0),
        "review_items_total": items_total,
        "review_items_by_status": items_by_status,
        "review_items_open": (
            items_by_status.get("pending", 0) + items_by_status.get("needs_review", 0)
        ),
    }


def build_possession_workflow_summary(db, game_id):
    """Aggregate possession linkage counts for film and stats surfaces."""
    from stats import _resolve_relational_game_id, get_possession_summary

    relational_game_id = _resolve_relational_game_id(db, game_id)
    if relational_game_id is not None:
        assign_possessions_for_game(db, relational_game_id)

    summary = get_possession_summary(db, game_id)

    if relational_game_id is not None:
        row = db.execute(
            """SELECT COUNT(*) AS events_total,
                      SUM(CASE WHEN possession_id IS NOT NULL THEN 1 ELSE 0 END) AS events_linked
                 FROM events
                WHERE relational_game_id = ?""",
            (relational_game_id,),
        ).fetchone()
    else:
        row = db.execute(
            """SELECT COUNT(*) AS events_total,
                      SUM(CASE WHEN possession_id IS NOT NULL THEN 1 ELSE 0 END) AS events_linked
                 FROM events
                WHERE game_id = ?""",
            (str(game_id),),
        ).fetchone()

    events_total = row["events_total"] or 0
    events_linked = row["events_linked"] or 0

    return {
        **summary,
        "events_total": events_total,
        "events_linked": events_linked,
        "events_unlinked": events_total - events_linked,
    }


def build_player_minutes_summary(db):
    """Aggregate player_minutes counts for coach stats surfaces."""
    totals = db.execute(
        """SELECT COUNT(*) AS player_rows,
                  COUNT(DISTINCT tracker_id) AS players_tracked,
                  COUNT(DISTINCT COALESCE(CAST(relational_game_id AS TEXT), game_id)) AS games_with_minutes,
                  COALESCE(SUM(minutes_played), 0) AS total_minutes
             FROM player_minutes"""
    ).fetchone()

    top_rows = db.execute(
        """SELECT tracker_id,
                  COALESCE(SUM(minutes_played), 0) AS total_minutes,
                  COUNT(DISTINCT COALESCE(CAST(relational_game_id AS TEXT), game_id)) AS games_played
             FROM player_minutes
            GROUP BY tracker_id
            ORDER BY total_minutes DESC
            LIMIT 5"""
    ).fetchall()

    return {
        "games_with_minutes": totals["games_with_minutes"] or 0,
        "player_rows": totals["player_rows"] or 0,
        "players_tracked": totals["players_tracked"] or 0,
        "total_minutes": round(totals["total_minutes"] or 0, 1),
        "top_players": [
            {
                "tracker_id": row["tracker_id"],
                "total_minutes": round(row["total_minutes"], 1),
                "games_played": row["games_played"],
            }
            for row in top_rows
        ],
    }


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

    ball_detector_options = [
        {
            "value": "models/ball_detector.pt",
            "label": "Fine-tuned basketball detector",
            "note": (
                f"Production default for ball detection: class {AI_DEFAULTS['ball_class_id']} "
                f"at {AI_DEFAULTS['ball_confidence']} confidence (see AGENT_PROTOCOL.md)."
            ),
            "recommended": True,
        },
        {
            "value": "yolov8n.pt",
            "label": "Legacy YOLOv8 sports-ball path",
            "note": "Uses COCO class 32 with legacy filters; benchmarked at 0% precision and 0% recall at conf=0.15.",
        },
        {
            "value": "custom",
            "label": "Custom ball detector weights",
            "note": "Use a local Ultralytics .pt file for future basketball detector candidates.",
        },
    ]

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
        "ball_detector_options": ball_detector_options,
        "device_options": device_options,
        "frame_stride_options": [
            {"value": 1, "label": "Every frame (highest detail)"},
            {"value": 2, "label": "Every 2nd frame"},
            {"value": 4, "label": "Every 4th frame (fastest)"},
        ],
        "event_generator_mode_options": [
            {
                "value": "legacy",
                "label": "Legacy generator",
                "note": "Basic event generation from detections.",
            },
            {
                "value": "expanded",
                "label": "Expanded heuristic generator",
                "note": "Recommended. Builds on the current detections to emit possession changes, shots, makes, misses, rebounds, assists, steals, turnovers, blocks, and fouls.",
            },
            {
                "value": "precision",
                "label": "Precision generator (opt-in)",
                "note": "Fewer, better-supported events for the Review queue; measured with scripts/score_manual_q1_regression.py.",
            },
        ],
        "llm_provider_options": llm_provider_options,
        "llm_model_options": llm_model_options,
        "recommended_ollama_models": recommended_ollama_models,
    }


def ai_runtime_available():
    return (
        module_available("cv2")
        and module_available("ultralytics")
    )


def ai_packages_install_hint() -> str:
    return (
        "AI packages are not installed on this server (opencv-python, ultralytics, scikit-learn). "
        "Install the AI stack, then restart the app. Check Settings → Runtime for status."
    )


def ai_packages_install_commands() -> str:
    return (
        "Windows (PowerShell, from repo root):\n"
        "  .\\.venv\\Scripts\\Activate.ps1\n"
        "  python --version    # must be 3.12.x or 3.13.x\n"
        "  .\\scripts\\install_ai_deps.ps1\n"
        "\n"
        "Or manually (after activating .venv with Python 3.12/3.13):\n"
        "  python -m pip install --upgrade pip\n"
        "  python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu\n"
        "  python -m pip install -r requirements.docker.txt\n"
        "\n"
        "Linux:\n"
        "  pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu\n"
        "  pip install -r requirements.docker.txt"
    )


def resolve_detector_model(ai_settings):
    selected_model = (ai_settings.get("detector_model") or AI_DEFAULTS["detector_model"]).strip()
    if selected_model == "custom":
        custom_model = (ai_settings.get("custom_detector_model") or "").strip()
        return custom_model or AI_DEFAULTS["detector_model"]
    return selected_model


def resolve_ball_detector_model(ai_settings):
    selected_model = (ai_settings.get("ball_detector_model") or AI_DEFAULTS["ball_detector_model"]).strip()
    if selected_model == "custom":
        custom_model = (ai_settings.get("custom_ball_detector_model") or "").strip()
        return custom_model or AI_DEFAULTS["ball_detector_model"]
    return selected_model


def display_detector_model(ai_settings):
    selected_model = (ai_settings.get("detector_model") or AI_DEFAULTS["detector_model"]).strip()
    if selected_model == "custom":
        custom_model = (ai_settings.get("custom_detector_model") or "").strip()
        return custom_model or "Custom (not set)"
    return selected_model


def display_ball_detector_model(ai_settings):
    selected_model = (ai_settings.get("ball_detector_model") or AI_DEFAULTS["ball_detector_model"]).strip()
    if selected_model == "custom":
        custom_model = (ai_settings.get("custom_ball_detector_model") or "").strip()
        return custom_model or "Custom ball detector (not set)"
    return selected_model


def build_analysis_settings_snapshot(runtime_settings):
    return {
        "analysis": runtime_settings["analysis"],
        "ai": runtime_settings["ai"],
    }


def build_rerun_game_id(base_game_id):
    # local time, consistent with upload/trim filenames (DB columns stay UTC)
    return f"{base_game_id}__rerun_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def default_run_label(run_kind, snapshot):
    ai_settings = snapshot.get("ai", {})
    model = display_detector_model(ai_settings)
    device = ai_settings.get("inference_device", "auto")
    if run_kind == "primary":
        return "Original upload"
    return f"Rerun · {model} · {device}"


def ensure_primary_run_metadata(db, video_row, settings_snapshot=None):
    existing = db.execute(
        """SELECT id, run_label FROM analysis_runs
           WHERE (source_video_id=? OR analysis_key=? OR base_analysis_key=? OR video_path=?)
           ORDER BY id ASC""",
        (video_row["id"], video_row["game_id"], video_row["game_id"], video_row["file_path"]),
    ).fetchall()
    if not existing:
        return

    for index, run in enumerate(existing):
        updates = {
            "game_id": video_row["relational_game_id"],
            "source_video_id": video_row["id"],
            "base_game_id": video_row["game_id"],
            "base_analysis_key": video_row["game_id"],
            "run_kind": "primary" if index == 0 else "rerun",
            "run_label": run["run_label"] or ("Original upload" if index == 0 else f"Rerun #{index}"),
        }
        if settings_snapshot and index == 0:
            updates["settings_json"] = json.dumps(settings_snapshot)
        db.execute(
            """UPDATE analysis_runs SET
               game_id=COALESCE(game_id, :game_id),
               source_video_id=COALESCE(source_video_id, :source_video_id),
               base_game_id=COALESCE(base_game_id, :base_game_id),
               base_analysis_key=COALESCE(base_analysis_key, :base_analysis_key),
               run_kind=COALESCE(run_kind, :run_kind),
               run_label=COALESCE(run_label, :run_label),
               settings_json=COALESCE(settings_json, :settings_json)
               WHERE id=:id""",
            {
                "id": run["id"],
                "game_id": updates["game_id"],
                "source_video_id": updates["source_video_id"],
                "base_game_id": updates["base_game_id"],
                "base_analysis_key": updates["base_analysis_key"],
                "run_kind": updates["run_kind"],
                "run_label": updates["run_label"],
                "settings_json": updates.get("settings_json"),
            },
        )
    db.commit()


def queue_analysis_run(db, video_row, runtime_settings, run_kind="rerun", run_label=None):
    settings_snapshot = build_analysis_settings_snapshot(runtime_settings)
    analysis_key = video_row["game_id"] if run_kind == "primary" else build_rerun_game_id(video_row["game_id"])
    run_label = (run_label or "").strip() or default_run_label(run_kind, settings_snapshot)
    run_cur = db.execute(
        """INSERT INTO analysis_runs
           (game_id, analysis_key, video_path, source_video_id, base_game_id, base_analysis_key, run_label, settings_json, run_kind, status, started_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,NULL)""",
        (
            video_row["relational_game_id"],
            analysis_key,
            video_row["file_path"],
            video_row["id"],
            video_row["game_id"],
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
        "game_id": analysis_key,
        "analysis_key": analysis_key,
        "run_label": run_label,
        "settings_snapshot": settings_snapshot,
    }


INTERNAL_SUPERSEDE_MARKERS = (
    "replaced by new request",
    "superseded by new analysis request",
)


def _analysis_run_video_clause(alias=None):
    prefix = f"{alias}." if alias else ""
    return (
        f"({prefix}source_video_id=? OR {prefix}base_analysis_key=? "
        f"OR {prefix}analysis_key=? OR {prefix}video_path=?)"
    )


def _analysis_run_priority_order(alias=None):
    prefix = f"{alias}." if alias else ""
    return f"""CASE {prefix}status
        WHEN 'running' THEN 0
        WHEN 'pending' THEN 1
        WHEN 'completed' THEN 2
        WHEN 'failed' THEN 3
        WHEN 'cancelled' THEN 4
        ELSE 5
    END"""


def latest_analysis_run_id_subquery(video_alias="v", run_alias="ar_latest"):
    clause = (
        f"({run_alias}.source_video_id = {video_alias}.id "
        f"OR {run_alias}.base_analysis_key = {video_alias}.game_id "
        f"OR {run_alias}.analysis_key = {video_alias}.game_id "
        f"OR {run_alias}.video_path = {video_alias}.file_path)"
    )
    return f"""(
        SELECT {run_alias}.id
        FROM analysis_runs {run_alias}
        WHERE {clause}
        ORDER BY {_analysis_run_priority_order(run_alias)}, {run_alias}.id DESC
        LIMIT 1
    )"""


def is_superseded_analysis_run(run_row) -> bool:
    if not run_row:
        return False
    status = run_row["status"] if hasattr(run_row, "keys") else run_row[1]
    if status == "cancelled":
        return True
    if status != "failed":
        return False
    message = (run_row["error_message"] or "").lower()
    return any(marker in message for marker in INTERNAL_SUPERSEDE_MARKERS)


def _analysis_run_video_params(video_row):
    return (
        video_row["id"],
        video_row["game_id"],
        video_row["game_id"],
        video_row["file_path"],
    )


def _analysis_run_row_video_params(run_row):
    return (
        run_row["source_video_id"],
        run_row["base_analysis_key"] or run_row["analysis_key"],
        run_row["base_analysis_key"] or run_row["analysis_key"],
        run_row["video_path"],
    )


def resolve_analysis_run_for_progress(db, game_id: str):
    """Return the analysis run row the progress UI should display."""
    row = db.execute(
        "SELECT * FROM analysis_runs WHERE analysis_key=? ORDER BY id DESC LIMIT 1",
        (game_id,),
    ).fetchone()
    if not row or not is_superseded_analysis_run(row):
        return row

    params = _analysis_run_row_video_params(row)
    replacement = db.execute(
        f"""SELECT * FROM analysis_runs
            WHERE {_analysis_run_video_clause()}
              AND id > ?
              AND status != 'cancelled'
            ORDER BY id DESC
            LIMIT 1""",
        (*params, row["id"]),
    ).fetchone()
    if replacement and not is_superseded_analysis_run(replacement):
        return replacement

    active = db.execute(
        f"""SELECT * FROM analysis_runs
            WHERE {_analysis_run_video_clause()}
              AND status IN ('running', 'pending')
            ORDER BY {_analysis_run_priority_order()}, id DESC
            LIMIT 1""",
        params,
    ).fetchone()
    return active or row


def supersede_pending_analysis_runs(db, video_row, reason="Superseded by new analysis request"):
    """Cancel stuck pending runs so a new analysis can start."""
    clause = _analysis_run_video_clause()
    db.execute(
        f"""UPDATE analysis_runs
               SET status='cancelled',
                   progress_step=?,
                   error_message=NULL,
                   completed_at=CURRENT_TIMESTAMP
             WHERE {clause} AND status='pending'""",
        (reason, *_analysis_run_video_params(video_row)),
    )
    db.commit()


def resolve_relational_game_id_for_analysis(db_path: str, game_id: str) -> int | None:
    """Resolve the relational games.id for an analysis key or legacy numeric id."""
    conn = sqlite3.connect(db_path)
    try:
        try:
            gid_int = int(game_id)
        except (TypeError, ValueError):
            gid_int = None
        if gid_int is not None:
            row = conn.execute("SELECT id FROM games WHERE id = ?", (gid_int,)).fetchone()
            if row:
                return row[0]

        row = conn.execute(
            """SELECT ar.game_id, v.relational_game_id
               FROM analysis_runs ar
               LEFT JOIN videos v ON v.id = ar.source_video_id
               WHERE ar.analysis_key = ?
               ORDER BY ar.id DESC
               LIMIT 1""",
            (game_id,),
        ).fetchone()
        if row:
            if row[0]:
                return row[0]
            if row[1]:
                return row[1]

        row = conn.execute(
            "SELECT relational_game_id FROM videos WHERE game_id = ? ORDER BY id DESC LIMIT 1",
            (game_id,),
        ).fetchone()
        if row and row[0]:
            return row[0]
    finally:
        conn.close()
    return None


def validate_video_for_analysis(video_path: str) -> tuple[bool, str | None]:
    """Return (ok, error_message) for a video before launching AI analysis."""
    video_path = os.path.abspath(video_path)
    if not os.path.exists(video_path):
        return False, f"Video file not found: {video_path}"
    size = os.path.getsize(video_path)
    if size < 1024:
        return False, f"Video file is too small to analyze ({size} bytes): {video_path}"
    try:
        import cv2
    except ImportError:
        return True, None
    cap = cv2.VideoCapture(video_path, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        return False, f"Could not open video for analysis: {video_path}"
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    cap.release()
    if frame_count <= 0 and width <= 0 and height <= 0:
        return False, f"Video has no readable frames: {video_path}"
    return True, None


def is_git_lfs_pointer_file(path: str) -> bool:
    try:
        with open(path, encoding="utf-8", errors="ignore") as handle:
            header = handle.read(120)
        return header.startswith("version https://git-lfs.github.com/spec/v1")
    except OSError:
        return False


def validate_model_weights(model_path: str) -> tuple[bool, str | None]:
    """Return (ok, error_message) for a local model weights file."""
    model_path = (model_path or "").strip()
    if not model_path:
        return True, None

    root = os.path.dirname(os.path.abspath(__file__))
    abs_path = model_path if os.path.isabs(model_path) else os.path.join(root, model_path)
    is_repo_model = model_path.replace("\\", "/").startswith("models/")

    if not os.path.exists(abs_path):
        if is_repo_model:
            return False, f"Model file not found: {model_path}"
        return True, None

    if is_git_lfs_pointer_file(abs_path):
        return False, (
            f"Model file {model_path} is a Git LFS pointer, not the real weights. "
            "Run: git lfs pull"
        )

    if model_path.endswith((".pt", ".pth")) and os.path.getsize(abs_path) < 10_000:
        return False, f"Model file looks too small or corrupt ({os.path.getsize(abs_path)} bytes): {model_path}"
    return True, None


def validate_ai_models_for_analysis(ai_settings=None) -> tuple[bool, str | None]:
    """Validate configured person/ball detector weights before launching analysis."""
    settings = dict(AI_DEFAULTS)
    if ai_settings:
        settings.update(ai_settings)
    for label, path in (
        ("Person detector", resolve_detector_model(settings)),
        ("Ball detector", resolve_ball_detector_model(settings)),
    ):
        ok, message = validate_model_weights(path)
        if not ok:
            return False, f"{label}: {message}"
    return True, None


def ai_analysis_log_path(game_id: str) -> str:
    root = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(root, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    safe_key = re.sub(r"[^\w.\-]+", "_", game_id)[:120]
    return os.path.join(logs_dir, f"ai-{safe_key}.log")


def _read_log_tail(log_path: str, limit: int = 500) -> str:
    try:
        with open(log_path, encoding="utf-8", errors="replace") as handle:
            return handle.read()[-limit:]
    except OSError:
        return ""


def count_detections_for_analysis(
    db,
    *,
    analysis_key=None,
    relational_game_id=None,
    video_game_id=None,
    video_relational_game_id=None,
    base_analysis_key=None,
) -> int:
    """Count detections for a video/analysis run across legacy and relational keys."""
    conditions = []
    params = []
    for rel_id in {relational_game_id, video_relational_game_id} - {None}:
        conditions.append("d.relational_game_id = ?")
        params.append(rel_id)
    for game_id in {analysis_key, video_game_id, base_analysis_key} - {None}:
        conditions.append("d.game_id = ?")
        params.append(game_id)
    if not conditions:
        return 0
    query = f"SELECT COUNT(*) AS c FROM detections d WHERE {' OR '.join(conditions)}"
    return db.execute(query, params).fetchone()["c"]


def count_events_for_analysis(
    db,
    *,
    analysis_key=None,
    relational_game_id=None,
    video_game_id=None,
    base_analysis_key=None,
) -> int:
    """Count events for a video/analysis run across legacy and relational keys."""
    conditions = []
    params = []
    if relational_game_id is not None:
        conditions.append("e.relational_game_id = ?")
        params.append(relational_game_id)
    for game_id in {analysis_key, video_game_id, base_analysis_key} - {None}:
        conditions.append("e.game_id = ?")
        params.append(game_id)
    if not conditions:
        return 0
    query = f"SELECT COUNT(*) AS c FROM events e WHERE {' OR '.join(conditions)}"
    return db.execute(query, params).fetchone()["c"]


def _analysis_log_error_message(content: str) -> str | None:
    if not content:
        return None
    if "No module named 'sklearn'" in content:
        return (
            "Event generation failed while clustering players. Pull the latest code and "
            "click Rebuild again (numpy fallback is used when scikit-learn is unavailable). "
            "For best results on Windows, use Python 3.12 or 3.13."
        )
    if "ERROR: An error occurred in event_generator" in content:
        for line in content.splitlines():
            if "event_generator:" in line:
                return line.strip()[:500]
        return "Event generation failed. See logs for details."
    if "Traceback" in content or "ModuleNotFoundError" in content or "No module named" in content:
        return _read_log_tail_from_content(content, 500)
    return None


def _read_log_tail_from_content(content: str, limit: int = 500) -> str:
    return content[-limit:] if content else ""


def _is_sync_event_rebuild_step(progress_step: str | None) -> bool:
    """True when an in-process Video Library Rebuild is running (not a subprocess)."""
    step = (progress_step or "").lower()
    return any(
        phrase in step
        for phrase in (
            "regenerating events",
            "clustering players",
            "loading detections",
        )
    )


def heal_failed_analysis_run_with_events(db, game_id: str) -> bool:
    """Upgrade failed runs that already produced events (stale watchdog false positive)."""
    columns = {row[1] for row in db.execute("PRAGMA table_info(analysis_runs)").fetchall()}
    select_cols = ["id", "status", "analysis_key"]
    if "game_id" in columns:
        select_cols.append("game_id AS relational_game_id")
    else:
        select_cols.append("NULL AS relational_game_id")
    if "base_analysis_key" in columns:
        select_cols.append("base_analysis_key")
    else:
        select_cols.append("NULL AS base_analysis_key")

    row = db.execute(
        f"""SELECT {", ".join(select_cols)}
           FROM analysis_runs
           WHERE analysis_key=?
           ORDER BY id DESC
           LIMIT 1""",
        (game_id,),
    ).fetchone()
    if not row:
        return False
    status = row["status"] if hasattr(row, "keys") else row[1]
    if status != "failed":
        return False
    analysis_key = row["analysis_key"] if hasattr(row, "keys") else row[2]
    relational_game_id = row["relational_game_id"] if hasattr(row, "keys") else row[3]
    base_analysis_key = row["base_analysis_key"] if hasattr(row, "keys") else row[4]
    row_id = row["id"] if hasattr(row, "keys") else row[0]
    event_count = count_events_for_analysis(
        db,
        analysis_key=analysis_key,
        relational_game_id=relational_game_id,
        base_analysis_key=base_analysis_key,
    )
    if event_count <= 0:
        return False
    db.execute(
        """UPDATE analysis_runs
           SET status='completed',
               progress_pct=100,
               progress_step='Done',
               error_message=NULL,
               completed_at=COALESCE(completed_at, CURRENT_TIMESTAMP)
           WHERE id=?""",
        (row_id,),
    )
    db.commit()
    return True


def reconcile_stuck_analysis_run(db, game_id: str) -> None:
    """Mark orphaned pending/running runs failed or completed based on logs."""
    heal_failed_analysis_run_with_events(db, game_id)

    row = db.execute(
        """SELECT id, status, progress_step
           FROM analysis_runs
           WHERE analysis_key=?
           ORDER BY id DESC
           LIMIT 1""",
        (game_id,),
    ).fetchone()
    if not row:
        return

    if hasattr(row, "keys"):
        status = row["status"]
        progress_step = row["progress_step"]
        row_id = row["id"]
    else:
        row_id, status, progress_step = row[0], row[1], row[2]
    if status not in {"pending", "running"}:
        return

    log_path = ai_analysis_log_path(game_id)
    content = _read_log_tail(log_path, 8000) if os.path.exists(log_path) else ""

    if status == "running":
        if "analysis_runs updated to 'completed'" in content:
            db.execute(
                """UPDATE analysis_runs
                   SET status='completed',
                       progress_pct=100,
                       progress_step='Done',
                       completed_at=CURRENT_TIMESTAMP,
                       error_message=NULL
                   WHERE id=?""",
                (row_id,),
            )
            db.commit()
            return

        error_message = _analysis_log_error_message(content)
        if error_message:
            db.execute(
                """UPDATE analysis_runs
                   SET status='failed',
                       error_message=?,
                       progress_step='Failed',
                       completed_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (error_message, row_id),
            )
            db.commit()
            return

        if _is_sync_event_rebuild_step(progress_step):
            return

        if content and os.path.exists(log_path):
            age_seconds = time.time() - os.path.getmtime(log_path)
            if age_seconds > 1800:
                db.execute(
                    """UPDATE analysis_runs
                       SET status='failed',
                           error_message=?,
                           progress_step='Failed',
                           completed_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (
                        "Analysis run stopped responding. Check logs, install missing "
                        "packages (pip install scikit-learn), then click Rebuild again.",
                        row["id"] if hasattr(row, "keys") else row_id,
                    ),
                )
                db.commit()
        return

    if not os.path.exists(log_path):
        return

    error_message = _analysis_log_error_message(content)
    if error_message:
        db.execute(
            """UPDATE analysis_runs
               SET status='failed',
                   error_message=?,
                   progress_step='Failed',
                   completed_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (error_message, row_id),
        )
        db.commit()
        return

    age_seconds = time.time() - os.path.getmtime(log_path)
    if age_seconds > 45 and "[launcher] Started" in content:
        db.execute(
            """UPDATE analysis_runs
               SET status='failed',
                   error_message=?,
                   progress_step='Failed',
                   completed_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (
                "Analysis worker stopped before processing started. "
                "Check logs/ for details, install AI packages if needed, then click Run AI Analysis again.",
                row_id,
            ),
        )
        db.commit()


def start_analysis_subprocess(game_id, video_path):
    import sys

    log_path = ai_analysis_log_path(game_id)
    video_path = os.path.abspath(video_path)
    db_path = current_app.config["DATABASE"]
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    log_file = open(log_path, "w", encoding="utf-8")
    try:
        popen_kwargs = {
            "stdout": log_file,
            "stderr": subprocess.STDOUT,
            "cwd": os.path.dirname(os.path.abspath(__file__)),
        }
        if os.name != "nt":
            popen_kwargs["start_new_session"] = True
        elif hasattr(subprocess, "CREATE_NO_WINDOW"):
            popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        proc = subprocess.Popen(
            [sys.executable, "analysis_launcher.py", db_path, video_path, game_id],
            **popen_kwargs,
        )
        if proc is not None:
            log_file.write(f"[launcher] Started analysis_launcher.py PID={proc.pid} for {game_id}\n")
            log_file.write(f"[launcher] Python: {sys.executable}\n")
            log_file.write(f"[launcher] Log file: {log_path}\n")
            log_file.write(f"[launcher] Video: {video_path}\n")
            log_file.write(f"[launcher] Database: {db_path}\n")
            log_file.flush()

            def _watch_process() -> None:
                try:
                    code = proc.wait()
                    if code != 0:
                        tail = _read_log_tail(log_path)
                        conn = sqlite3.connect(db_path)
                        conn.execute(
                            """UPDATE analysis_runs
                               SET status='failed',
                                   error_message=?,
                                   progress_step='Failed',
                                   completed_at=CURRENT_TIMESTAMP
                               WHERE analysis_key=? AND status IN ('pending', 'running')""",
                            (f"Analysis worker exited (code {code}). {tail}"[:500], game_id),
                        )
                        conn.commit()
                        conn.close()
                finally:
                    try:
                        log_file.close()
                    except OSError:
                        pass

            threading.Thread(target=_watch_process, daemon=True, name=f"ai-watch-{game_id[:12]}").start()
        else:
            log_file.write(f"[launcher] Popen returned None for {game_id}\n")
            log_file.flush()
            log_file.close()
        return log_path
    except Exception as e:
        log_file.write(f"[launcher] Failed to start: {e}\n")
        log_file.flush()
        log_file.close()
        raise


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
    payload["display_analysis_key"] = payload.get("analysis_key") or payload.get("game_id")
    return payload

# ── Database helpers ──────────────────────────────────────

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            timeout=10,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA busy_timeout = 10000")
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


def film_page_path(stored_filename: str, game_id: str) -> str:
    """Build a Film Tool path without Flask request context (safe in background jobs)."""
    return append_query_params(
        f"/film/{quote(stored_filename, safe='')}",
        game_id=game_id,
    )


def videos_page_path() -> str:
    return "/videos"


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
    with current_app.open_resource("schema.sql", mode="r", encoding="utf-8-sig") as f:
        db.executescript(f.read())
    db.commit()
    _ensure_migration_columns(db)


def ensure_db():
    if not os.path.exists(current_app.config["DATABASE"]):
        init_db()
    else:
        db = get_db()
        _ensure_migration_columns(db)


def backfill_player_minutes(game_id=None, fps=30.0, detect_stride=1):
    """Convenience: backfill player_minutes for one or all games."""
    db = get_db()
    if game_id is not None:
        from player_minutes import backfill_player_minutes as _bf
        return _bf(db, game_id, fps, detect_stride)
    from player_minutes import backfill_all_games as _bf_all
    return _bf_all(db, fps, detect_stride)


def _migrate_analysis_runs_identity(db):
    """Split analysis_runs identity into relational game_id and text analysis_key."""
    table_exists = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='analysis_runs'"
    ).fetchone()
    if not table_exists:
        return

    columns = db.execute("PRAGMA table_info(analysis_runs)").fetchall()
    column_names = [row[1] for row in columns]
    column_types = {row[1]: (row[2] or "").upper() for row in columns}
    if column_types.get("game_id") == "INTEGER" and "analysis_key" in column_names:
        return

    def value_expr(column, fallback="NULL"):
        return column if column in column_names else fallback

    legacy_game_id_is_integer = column_types.get("game_id") == "INTEGER"
    relational_game_expr = "game_id" if legacy_game_id_is_integer else "NULL"
    legacy_key_expr = value_expr(
        "analysis_key",
        "'legacy_run_' || id" if legacy_game_id_is_integer else value_expr("game_id", "'legacy_run_' || id"),
    )
    legacy_base_expr = value_expr("base_analysis_key", value_expr("base_game_id"))

    db.execute("PRAGMA foreign_keys = OFF")
    try:
        db.execute("ALTER TABLE analysis_runs RENAME TO analysis_runs_legacy")
        db.execute(
            """CREATE TABLE analysis_runs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id      INTEGER REFERENCES games(id),
                analysis_key TEXT NOT NULL,
                video_path   TEXT NOT NULL,
                source_video_id INTEGER REFERENCES videos(id),
                base_game_id TEXT,
                base_analysis_key TEXT,
                run_label    TEXT,
                settings_json TEXT,
                run_kind     TEXT NOT NULL DEFAULT 'primary',
                status       TEXT NOT NULL DEFAULT 'pending',
                started_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT
            )"""
        )
        db.execute(
            f"""INSERT INTO analysis_runs
                   (id, game_id, analysis_key, video_path, source_video_id, base_game_id,
                    base_analysis_key, run_label, settings_json, run_kind, status,
                    started_at, completed_at, error_message)
               SELECT id,
                      {relational_game_expr},
                      COALESCE({legacy_key_expr}, 'legacy_run_' || id),
                      video_path,
                      {value_expr('source_video_id')},
                      {value_expr('base_game_id')},
                      {legacy_base_expr},
                      {value_expr('run_label')},
                      {value_expr('settings_json')},
                      COALESCE({value_expr('run_kind')}, 'primary'),
                      COALESCE(status, 'pending'),
                      started_at,
                      completed_at,
                      error_message
               FROM analysis_runs_legacy"""
        )
        db.execute("DROP TABLE analysis_runs_legacy")
        db.commit()
    finally:
        db.execute("PRAGMA foreign_keys = ON")


def _table_exists(db, table_name):
    return db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone() is not None


def _stage2_default_team_id(db):
    """Create or return the deterministic default Liberty team."""
    team = db.execute(
        """SELECT id FROM teams
           WHERE organization_name=?
             AND team_name=?
             AND program_name=?
             AND gender=?
             AND level=?
           ORDER BY id LIMIT 1""",
        (
            DEFAULT_TEAM_SEED["organization_name"],
            DEFAULT_TEAM_SEED["team_name"],
            DEFAULT_TEAM_SEED["program_name"],
            DEFAULT_TEAM_SEED["gender"],
            DEFAULT_TEAM_SEED["level"],
        ),
    ).fetchone()
    if team:
        return team["id"]

    cur = db.execute(
        """INSERT INTO teams
              (organization_name, team_name, program_name, gender, level)
           VALUES (?, ?, ?, ?, ?)""",
        (
            DEFAULT_TEAM_SEED["organization_name"],
            DEFAULT_TEAM_SEED["team_name"],
            DEFAULT_TEAM_SEED["program_name"],
            DEFAULT_TEAM_SEED["gender"],
            DEFAULT_TEAM_SEED["level"],
        ),
    )
    team_id = cur.lastrowid
    _insert_backfill_provenance(
        db,
        "team",
        team_id,
        "default_team",
        details={"seed": DEFAULT_TEAM_SEED},
    )
    return team_id


def _insert_backfill_provenance(db, entity_type, entity_id, source_id, details=None):
    if not _table_exists(db, "provenance_records") or entity_id is None:
        return
    provenance_source_id = f"platform_core_stage_2_backfill:{source_id}"
    existing = db.execute(
        """SELECT 1 FROM provenance_records
           WHERE entity_type=?
             AND entity_id=?
             AND source_type='migration'
             AND source_id=?
           LIMIT 1""",
        (entity_type, entity_id, provenance_source_id),
    ).fetchone()
    if existing:
        return
    db.execute(
        """INSERT INTO provenance_records
              (entity_type, entity_id, source_type, source_id, confidence, details_json)
           VALUES (?, ?, 'migration', ?, 1.0, ?)""",
        (
            entity_type,
            entity_id,
            provenance_source_id,
            json.dumps(details or {}, sort_keys=True),
        ),
    )


def _seed_event_types(db):
    for code, label, category, counts_for_stats, is_scoring, is_boundary in EVENT_TYPE_SEEDS:
        db.execute(
            """INSERT OR IGNORE INTO event_types
                  (code, label, category, counts_for_stats,
                   is_scoring_event, is_possession_boundary)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (code, label, category, counts_for_stats, is_scoring, is_boundary),
        )

    rows = db.execute(
        "SELECT id, code FROM event_types WHERE code IN ({})".format(
            ",".join("?" for _ in EVENT_TYPE_SEEDS)
        ),
        [seed[0] for seed in EVENT_TYPE_SEEDS],
    ).fetchall()
    for row in rows:
        _insert_backfill_provenance(
            db,
            "event_type",
            row["id"],
            f"event_type:{row['code']}",
            details={"code": row["code"]},
        )


def assign_possessions_for_game(db, game_id):
    """Idempotent possession assignment for one game.

    Reads events for the game ordered by (timestamp_ms, id), creates
    possession rows as needed, and assigns events.possession_id for each
    event.  A new possession starts on any event whose event_types row
    has is_possession_boundary = 1 — the boundary event itself belongs to
    the NEW possession.  Consecutive boundary events merge into the same
    possession.

    Safe to call multiple times: existing possession_id values on events are
    checked first; existing possessions linked to this game are reused rather
    than duplicated.  Event facts (event_type, event_type_id, player,
    shot_result, timestamp_ms, review status) are never modified.
    """
    # Collect events ordered by (timestamp_ms, id) — only those with a
    # relational_game_id matching this game.
    events = db.execute(
        """SELECT e.id, e.event_type, e.timestamp_ms, e.possession_id
             FROM events e
            WHERE e.relational_game_id = ?
            ORDER BY e.timestamp_ms ASC, e.id ASC""",
        (game_id,),
    ).fetchall()

    if not events:
        return

    # Determine which event types are possession boundaries.
    type_rows = db.execute(
        "SELECT code, is_possession_boundary FROM event_types"
    ).fetchall()
    boundary_codes = {r["code"] for r in type_rows if r["is_possession_boundary"] == 1}

    # Existing possessions for this game, linked by start_event_id so we
    # can reuse them on re-run (idempotency).
    existing = db.execute(
        """SELECT id, start_event_id FROM possessions WHERE game_id = ?""",
        (game_id,),
    ).fetchall()
    possessed_by_event = {r["start_event_id"]: r["id"] for r in existing}

    current_possession_id = None
    prev_was_boundary = False
    for ev in events:
        if ev["possession_id"] is not None:
            # Event already linked (previous run) — keep using that possession.
            current_possession_id = ev["possession_id"]
            prev_was_boundary = ev["event_type"] in boundary_codes
            continue

        is_boundary = ev["event_type"] in boundary_codes
        if is_boundary and not prev_was_boundary and current_possession_id is not None:
            # Boundary after non-boundary: end current possession. This
            # boundary event starts a new possession.
            current_possession_id = None

        if current_possession_id is None:
            # Reuse an existing possession by start_event_id if present.
            current_possession_id = possessed_by_event.get(ev["id"])

            if current_possession_id is None:
                db.execute(
                    """INSERT INTO possessions
                          (game_id, start_timestamp_ms,
                           start_event_id, source, review_status)
                       VALUES (?, ?, ?, 'manual', 'reviewed')""",
                    (game_id, ev["timestamp_ms"], ev["id"]),
                )
                current_possession_id = db.execute(
                    "SELECT last_insert_rowid()"
                ).fetchone()[0]
                possessed_by_event[ev["id"]] = current_possession_id

            db.execute(
                "UPDATE events SET possession_id = ? WHERE id = ?",
                (current_possession_id, ev["id"]),
            )
        else:
            db.execute(
                "UPDATE events SET possession_id = ? WHERE id = ?",
                (current_possession_id, ev["id"]),
            )

        prev_was_boundary = is_boundary

    from stats import score_possessions_for_game
    score_possessions_for_game(db, game_id)


def _seed_base_module_entitlement(db, team_id):
    if team_id is None:
        return
    db.execute(
        """INSERT OR IGNORE INTO module_entitlements
              (team_id, module_key, enabled, notes)
           VALUES (?, ?, 1, ?)""",
        (team_id, BASE_MODULE_ENTITLEMENT["module_key"], BASE_MODULE_ENTITLEMENT["notes"]),
    )
    row = db.execute(
        """SELECT id FROM module_entitlements
           WHERE team_id=? AND module_key=?""",
        (team_id, BASE_MODULE_ENTITLEMENT["module_key"]),
    ).fetchone()
    if row:
        _insert_backfill_provenance(
            db,
            "module_entitlement",
            row["id"],
            f"module:{BASE_MODULE_ENTITLEMENT['module_key']}",
            details={"module_key": BASE_MODULE_ENTITLEMENT["module_key"]},
        )


def _seed_demo_module_entitlements(db, team_id):
    """Seed optional demo add-on modules (stats, scouting) without schema changes."""
    if team_id is None:
        return []

    seeded_keys = []
    for entry in DEMO_MODULE_ENTITLEMENTS:
        db.execute(
            """INSERT OR IGNORE INTO module_entitlements
                  (team_id, module_key, enabled, notes)
               VALUES (?, ?, 1, ?)""",
            (team_id, entry["module_key"], entry["notes"]),
        )
        row = db.execute(
            """SELECT id FROM module_entitlements
               WHERE team_id=? AND module_key=?""",
            (team_id, entry["module_key"]),
        ).fetchone()
        if row:
            seeded_keys.append(entry["module_key"])
            _insert_backfill_provenance(
                db,
                "module_entitlement",
                row["id"],
                f"module:{entry['module_key']}",
                details={"module_key": entry["module_key"], "seed": "stage_8a_demo"},
            )
    return seeded_keys


def _backfill_roster_memberships(db, team_id):
    if team_id is None or not _table_exists(db, "players"):
        return
    db.execute(
        """INSERT INTO roster_memberships
              (player_id, team_id, season_id, jersey_number, position, grade, status)
           SELECT p.id, ?, p.season_id, p.jersey_number, p.position, p.grade, 'active'
             FROM players p
            WHERE NOT EXISTS (
                SELECT 1 FROM roster_memberships rm
                 WHERE rm.player_id = p.id
                   AND rm.team_id = ?
                   AND (
                       rm.season_id = p.season_id
                       OR (rm.season_id IS NULL AND p.season_id IS NULL)
                   )
            )""",
        (team_id, team_id),
    )
    rows = db.execute(
        """SELECT rm.id, rm.player_id
             FROM roster_memberships rm
            WHERE rm.team_id=?""",
        (team_id,),
    ).fetchall()
    for row in rows:
        _insert_backfill_provenance(
            db,
            "roster_membership",
            row["id"],
            f"player:{row['player_id']}",
            details={"player_id": row["player_id"], "team_id": team_id},
        )


def _game_id_if_relational(db, raw_game_id):
    if raw_game_id in (None, ""):
        return None
    try:
        game_id = int(raw_game_id)
    except (TypeError, ValueError):
        return None
    row = db.execute("SELECT id FROM games WHERE id=?", (game_id,)).fetchone()
    return game_id if row else None


def _backfill_video_assets_from_videos(db):
    if not _table_exists(db, "videos"):
        return
    rows = db.execute(
        """SELECT id, original_filename, stored_filename, file_path,
                  file_size_bytes, game_id, relational_game_id
             FROM videos"""
    ).fetchall()
    for row in rows:
        existing = db.execute(
            "SELECT id FROM video_assets WHERE stored_filename=? OR file_path=? LIMIT 1",
            (row["stored_filename"], row["file_path"]),
        ).fetchone()
        if existing:
            continue
        game_id = row["relational_game_id"] or _game_id_if_relational(db, row["game_id"])
        cur = db.execute(
            """INSERT INTO video_assets
                  (game_id, original_filename, stored_filename, file_path,
                   source_type, file_size_bytes, primary_asset)
               VALUES (?, ?, ?, ?, 'uploaded_video', ?, 1)""",
            (
                game_id,
                row["original_filename"],
                row["stored_filename"],
                row["file_path"],
                row["file_size_bytes"],
            ),
        )
        _insert_backfill_provenance(
            db,
            "video_asset",
            cur.lastrowid,
            f"video:{row['id']}",
            details={"video_id": row["id"], "source_table": "videos"},
        )


def _backfill_video_assets_from_sources(db):
    if not _table_exists(db, "sources"):
        return
    rows = db.execute(
        "SELECT id, game_id, source_type, source_path FROM sources"
    ).fetchall()
    for row in rows:
        existing = db.execute(
            "SELECT id FROM video_assets WHERE source_id=? OR file_path=? LIMIT 1",
            (row["id"], row["source_path"]),
        ).fetchone()
        if existing:
            continue
        filename = os.path.basename(row["source_path"] or "")
        cur = db.execute(
            """INSERT INTO video_assets
                  (game_id, source_id, original_filename, stored_filename,
                   file_path, source_type, primary_asset)
               VALUES (?, ?, ?, ?, ?, ?, 0)""",
            (
                row["game_id"],
                row["id"],
                filename or None,
                filename or None,
                row["source_path"],
                row["source_type"],
            ),
        )
        _insert_backfill_provenance(
            db,
            "video_asset",
            cur.lastrowid,
            f"source:{row['id']}",
            details={"source_id": row["id"], "source_table": "sources"},
        )


def _backfill_platform_core_stage2(db):
    """Seed deterministic platform-core data without changing route behavior."""
    required = [
        "teams",
        "roster_memberships",
        "video_assets",
        "event_types",
        "provenance_records",
        "module_entitlements",
    ]
    if not all(_table_exists(db, table) for table in required):
        return

    team_id = _stage2_default_team_id(db)
    _seed_event_types(db)
    _seed_base_module_entitlement(db, team_id)
    _backfill_roster_memberships(db, team_id)
    _backfill_video_assets_from_videos(db)
    _backfill_video_assets_from_sources(db)


def _backfill_demo_module_entitlements_stage8a(db):
    """Seed demo add-on module rows for packaging preview surfaces."""
    if not _table_exists(db, "module_entitlements"):
        return
    team_id = _stage2_default_team_id(db)
    _seed_demo_module_entitlements(db, team_id)


def _backfill_review_workflow_stage3a(db):
    """Backfill event review state and review queue rows without changing facts."""
    if not _table_exists(db, "events") or not _table_exists(db, "review_items"):
        return

    db.execute(
        """UPDATE events
              SET review_status = CASE
                    WHEN human_verified = 1 THEN 'accepted'
                    ELSE 'pending'
                  END
            WHERE review_status IS NULL OR review_status = '' OR review_status = 'pending'"""
    )
    db.execute(
        """UPDATE events
              SET source_type = CASE
                    WHEN human_verified = 1 THEN 'manual'
                    ELSE 'ai'
                  END
            WHERE source_type IS NULL OR source_type = ''"""
    )
    db.execute(
        """INSERT OR IGNORE INTO review_items
              (entity_type, entity_id, game_id, relational_game_id, review_status, priority, reason)
           SELECT 'event',
                  id,
                  game_id,
                  relational_game_id,
                  review_status,
                  'normal',
                  'Event needs coach review'
             FROM events
            WHERE review_status = 'pending'"""
    )
    db.execute(
        """UPDATE review_items
              SET review_status = (
                      SELECT e.review_status FROM events e
                       WHERE e.id = review_items.entity_id
                         AND review_items.entity_type = 'event'
                  ),
                  game_id = (
                      SELECT e.game_id FROM events e
                       WHERE e.id = review_items.entity_id
                         AND review_items.entity_type = 'event'
                  ),
                  relational_game_id = (
                      SELECT e.relational_game_id FROM events e
                       WHERE e.id = review_items.entity_id
                         AND review_items.entity_type = 'event'
                  ),
                  updated_at = CURRENT_TIMESTAMP
            WHERE entity_type = 'event'
              AND EXISTS (
                  SELECT 1 FROM events e WHERE e.id = review_items.entity_id
              )"""
    )




def _backfill_event_participants_stage4a(db):
    if not _table_exists(db, "events") or not _table_exists(db, "event_participants"):
        return
    if not _table_exists(db, "players"):
        return
    db.execute(
        """INSERT INTO event_participants
              (event_id, player_id, roster_membership_id, team_id, role,
               tracker_id, confidence, source)
           SELECT e.id,
                  p.id,
                  (SELECT rm.id FROM roster_memberships rm
                    WHERE rm.player_id = p.id
                    ORDER BY rm.id LIMIT 1),
                  COALESCE(
                      e.team_id,
                      (SELECT rm.team_id FROM roster_memberships rm
                        WHERE rm.player_id = p.id
                        ORDER BY rm.id LIMIT 1)
                  ),
                  'primary',
                  p.tracker_id,
                  e.confidence,
                  COALESCE(e.source_type, 'manual')
             FROM events e
             JOIN players p
               ON lower(trim(p.name)) = lower(trim(e.player))
            WHERE e.player IS NOT NULL
              AND trim(e.player) <> ''
              AND NOT EXISTS (
                  SELECT 1 FROM event_participants ep
                   WHERE ep.event_id = e.id
                     AND ep.role = 'primary'
                     AND ep.player_id = p.id
              )"""
    )
    db.execute(
        """UPDATE events
              SET primary_player_id = (
                      SELECT ep.player_id FROM event_participants ep
                       WHERE ep.event_id = events.id
                         AND ep.role = 'primary'
                       ORDER BY ep.id LIMIT 1
                  ),
                  primary_roster_membership_id = (
                      SELECT ep.roster_membership_id FROM event_participants ep
                       WHERE ep.event_id = events.id
                         AND ep.role = 'primary'
                       ORDER BY ep.id LIMIT 1
                  ),
                  team_id = COALESCE(team_id, (
                      SELECT ep.team_id FROM event_participants ep
                       WHERE ep.event_id = events.id
                         AND ep.role = 'primary'
                       ORDER BY ep.id LIMIT 1
                  ))
            WHERE primary_player_id IS NULL
              AND EXISTS (
                  SELECT 1 FROM event_participants ep
                   WHERE ep.event_id = events.id
                     AND ep.role = 'primary'
              )"""
    )


def _ensure_migration_columns(db):
    """Add new columns/tables to existing databases without wiping data."""
    _migrate_analysis_runs_identity(db)

    # ── New tables (idempotent) ──────────────────────────────
    db.executescript("""
        CREATE TABLE IF NOT EXISTS teams (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            organization_name TEXT,
            team_name         TEXT NOT NULL,
            program_name      TEXT,
            gender            TEXT,
            level             TEXT,
            season_default_id INTEGER REFERENCES seasons(id),
            created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS roster_memberships (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id       INTEGER NOT NULL REFERENCES players(id),
            team_id         INTEGER NOT NULL REFERENCES teams(id),
            season_id       INTEGER REFERENCES seasons(id),
            jersey_number   INTEGER,
            position        TEXT,
            grade           INTEGER,
            status          TEXT NOT NULL DEFAULT 'active',
            start_date      DATE,
            end_date        DATE,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS film_roster_players (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id       INTEGER NOT NULL REFERENCES seasons(id),
            level           TEXT NOT NULL,
            gender          TEXT NOT NULL,
            side            TEXT NOT NULL,
            player_label    TEXT NOT NULL,
            jersey_number   TEXT,
            name            TEXT,
            grade           TEXT,
            position        TEXT,
            sort_order      INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(season_id, level, gender, side, player_label)
        );
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
        CREATE TABLE IF NOT EXISTS video_assets (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id           INTEGER REFERENCES games(id),
            source_id         INTEGER REFERENCES sources(id),
            original_filename TEXT,
            stored_filename   TEXT,
            file_path         TEXT,
            source_type       TEXT,
            camera_label      TEXT,
            angle_label       TEXT,
            file_size_bytes   INTEGER,
            duration_ms       INTEGER,
            frame_rate        REAL,
            width             INTEGER,
            height            INTEGER,
            checksum          TEXT,
            transcode_status  TEXT,
            sync_group_id     TEXT,
            primary_asset     INTEGER NOT NULL DEFAULT 0,
            created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS possessions (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id            INTEGER NOT NULL REFERENCES games(id),
            team_id            INTEGER REFERENCES teams(id),
            opponent_team_id   INTEGER REFERENCES teams(id),
            period             INTEGER,
            start_timestamp_ms INTEGER NOT NULL,
            end_timestamp_ms   INTEGER,
            start_event_id     INTEGER REFERENCES events(id),
            end_event_id       INTEGER REFERENCES events(id),
            outcome            TEXT,
            points_for         INTEGER NOT NULL DEFAULT 0,
            source             TEXT NOT NULL DEFAULT 'manual',
            review_status      TEXT NOT NULL DEFAULT 'unreviewed',
            confidence         REAL,
            notes              TEXT,
            created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS track_identity_labels (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id            TEXT NOT NULL,
            relational_game_id INTEGER REFERENCES games(id),
            tracker_id         INTEGER NOT NULL,
            identity_type      TEXT NOT NULL DEFAULT 'cluster',
            jersey_number      INTEGER,
            player_name        TEXT,
            player_id          INTEGER,
            confidence         REAL,
            sample_count       INTEGER,
            source             TEXT DEFAULT 'ocr_votes',
            created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(game_id, identity_type, tracker_id)
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
        CREATE TABLE IF NOT EXISTS event_types (
            id                     INTEGER PRIMARY KEY AUTOINCREMENT,
            code                   TEXT UNIQUE NOT NULL,
            label                  TEXT NOT NULL,
            category               TEXT,
            counts_for_stats       INTEGER NOT NULL DEFAULT 1,
            is_scoring_event       INTEGER NOT NULL DEFAULT 0,
            is_possession_boundary INTEGER NOT NULL DEFAULT 0,
            created_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS event_participants (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id             INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            player_id            INTEGER REFERENCES players(id),
            roster_membership_id INTEGER REFERENCES roster_memberships(id),
            team_id              INTEGER REFERENCES teams(id),
            role                 TEXT NOT NULL,
            tracker_id           INTEGER,
            confidence           REAL,
            source               TEXT NOT NULL DEFAULT 'manual',
            created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS provenance_records (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type         TEXT NOT NULL,
            entity_id           INTEGER NOT NULL,
            source_type         TEXT NOT NULL,
            source_id           TEXT,
            source_path         TEXT,
            source_frame        INTEGER,
            source_timestamp_ms INTEGER,
            model_name          TEXT,
            model_version       TEXT,
            confidence          REAL,
            created_by_user_id  INTEGER REFERENCES users(id),
            created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            details_json        TEXT
        );
        CREATE TABLE IF NOT EXISTS review_items (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type         TEXT NOT NULL,
            entity_id           INTEGER NOT NULL,
            game_id             TEXT,
            review_status       TEXT NOT NULL DEFAULT 'pending',
            priority            TEXT NOT NULL DEFAULT 'normal',
            reason              TEXT,
            assigned_to_user_id INTEGER REFERENCES users(id),
            reviewed_by_user_id INTEGER REFERENCES users(id),
            reviewed_at         TIMESTAMP,
            notes               TEXT,
            created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(entity_type, entity_id)
        );
        CREATE TABLE IF NOT EXISTS module_entitlements (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id    INTEGER REFERENCES teams(id),
            module_key TEXT NOT NULL,
            enabled    INTEGER NOT NULL DEFAULT 1,
            starts_at  TIMESTAMP,
            ends_at    TIMESTAMP,
            notes      TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(team_id, module_key)
        );
        CREATE TABLE IF NOT EXISTS clips (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id            INTEGER REFERENCES games(id),
            video_asset_id     INTEGER REFERENCES video_assets(id),
            event_id           INTEGER REFERENCES events(id),
            possession_id      INTEGER REFERENCES possessions(id),
            clip_type          TEXT NOT NULL DEFAULT 'event',
            title              TEXT NOT NULL,
            start_timestamp_ms INTEGER NOT NULL,
            end_timestamp_ms   INTEGER NOT NULL,
            created_by_user_id INTEGER REFERENCES users(id),
            source             TEXT NOT NULL DEFAULT 'manual',
            review_status      TEXT NOT NULL DEFAULT 'reviewed',
            confidence         REAL,
            notes              TEXT,
            created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS clip_tags (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            clip_id            INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
            tag                TEXT NOT NULL,
            category           TEXT,
            created_by_user_id INTEGER REFERENCES users(id),
            created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS player_development_clips (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id       INTEGER REFERENCES players(id),
            game_id         TEXT,
            event_id        INTEGER REFERENCES events(id),
            canonical_clip_id INTEGER REFERENCES clips(id),
            relational_game_id INTEGER REFERENCES games(id),
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
        CREATE TABLE IF NOT EXISTS play_categories (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id       INTEGER REFERENCES play_categories(id) ON DELETE CASCADE,
            name            TEXT NOT NULL,
            slug            TEXT NOT NULL,
            slug_path       TEXT NOT NULL UNIQUE,
            sort_order      INTEGER NOT NULL DEFAULT 0,
            is_system       INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        CREATE TABLE IF NOT EXISTS team_photos (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            team_key        TEXT NOT NULL,
            filename        TEXT NOT NULL,
            original_name   TEXT NOT NULL,
            caption         TEXT,
            uploaded_by     INTEGER,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (uploaded_by) REFERENCES users(id)
        );
    """)
    # ── New columns on existing tables ──────────────────────
    col_migrations = [
        ("analysis_runs", "source_video_id", "ALTER TABLE analysis_runs ADD COLUMN source_video_id INTEGER REFERENCES videos(id)"),
        ("analysis_runs", "base_game_id", "ALTER TABLE analysis_runs ADD COLUMN base_game_id TEXT"),
        ("analysis_runs", "analysis_key", "ALTER TABLE analysis_runs ADD COLUMN analysis_key TEXT"),
        ("analysis_runs", "base_analysis_key", "ALTER TABLE analysis_runs ADD COLUMN base_analysis_key TEXT"),
        ("analysis_runs", "run_label", "ALTER TABLE analysis_runs ADD COLUMN run_label TEXT"),
        ("analysis_runs", "settings_json", "ALTER TABLE analysis_runs ADD COLUMN settings_json TEXT"),
        ("analysis_runs", "run_kind", "ALTER TABLE analysis_runs ADD COLUMN run_kind TEXT DEFAULT 'primary'"),
        ("analysis_runs", "progress_pct", "ALTER TABLE analysis_runs ADD COLUMN progress_pct REAL DEFAULT 0"),
        ("analysis_runs", "progress_step", "ALTER TABLE analysis_runs ADD COLUMN progress_step TEXT"),
        ("events", "source_video",   "ALTER TABLE events ADD COLUMN source_video TEXT"),
        ("events", "source_frame",   "ALTER TABLE events ADD COLUMN source_frame INTEGER"),
        ("events", "human_verified", "ALTER TABLE events ADD COLUMN human_verified INTEGER NOT NULL DEFAULT 0"),
        ("events", "confidence",     "ALTER TABLE events ADD COLUMN confidence REAL"),
        ("events", "review_status",  "ALTER TABLE events ADD COLUMN review_status TEXT NOT NULL DEFAULT 'pending'"),
        ("events", "source_type",    "ALTER TABLE events ADD COLUMN source_type TEXT DEFAULT 'ai'"),
        ("events", "possession_id",  "ALTER TABLE events ADD COLUMN possession_id INTEGER REFERENCES possessions(id)"),
        ("events", "relational_game_id", "ALTER TABLE events ADD COLUMN relational_game_id INTEGER REFERENCES games(id)"),
        ("events", "event_type_id", "ALTER TABLE events ADD COLUMN event_type_id INTEGER REFERENCES event_types(id)"),
        ("events", "team_id", "ALTER TABLE events ADD COLUMN team_id INTEGER REFERENCES teams(id)"),
        ("events", "primary_player_id", "ALTER TABLE events ADD COLUMN primary_player_id INTEGER REFERENCES players(id)"),
        ("events", "primary_roster_membership_id", "ALTER TABLE events ADD COLUMN primary_roster_membership_id INTEGER REFERENCES roster_memberships(id)"),
        ("events", "reviewed_by_user_id", "ALTER TABLE events ADD COLUMN reviewed_by_user_id INTEGER REFERENCES users(id)"),
        ("events", "reviewed_at",    "ALTER TABLE events ADD COLUMN reviewed_at TIMESTAMP"),
        ("events", "review_notes",   "ALTER TABLE events ADD COLUMN review_notes TEXT"),
        ("events", "created_by_user_id", "ALTER TABLE events ADD COLUMN created_by_user_id INTEGER REFERENCES users(id)"),
        ("events", "updated_at", "ALTER TABLE events ADD COLUMN updated_at TIMESTAMP"),
        ("stats", "relational_game_id", "ALTER TABLE stats ADD COLUMN relational_game_id INTEGER REFERENCES games(id)"),
        ("player_minutes", "relational_game_id", "ALTER TABLE player_minutes ADD COLUMN relational_game_id INTEGER REFERENCES games(id)"),
        ("shot_classifications", "relational_game_id", "ALTER TABLE shot_classifications ADD COLUMN relational_game_id INTEGER REFERENCES games(id)"),
        ("play_recognitions", "relational_game_id", "ALTER TABLE play_recognitions ADD COLUMN relational_game_id INTEGER REFERENCES games(id)"),
        ("player_effect", "relational_game_id", "ALTER TABLE player_effect ADD COLUMN relational_game_id INTEGER REFERENCES games(id)"),
        ("detections", "relational_game_id", "ALTER TABLE detections ADD COLUMN relational_game_id INTEGER REFERENCES games(id)"),
        ("videos", "relational_game_id", "ALTER TABLE videos ADD COLUMN relational_game_id INTEGER REFERENCES games(id)"),
        ("human_corrections", "relational_game_id", "ALTER TABLE human_corrections ADD COLUMN relational_game_id INTEGER REFERENCES games(id)"),
        ("review_items", "relational_game_id", "ALTER TABLE review_items ADD COLUMN relational_game_id INTEGER REFERENCES games(id)"),
        ("issue_reports", "browser_console", "ALTER TABLE issue_reports ADD COLUMN browser_console TEXT"),
        ("scheduled_games", "jv_game_time", "ALTER TABLE scheduled_games ADD COLUMN jv_game_time TIME"),
        ("scheduled_games", "frosh_game_time", "ALTER TABLE scheduled_games ADD COLUMN frosh_game_time TIME"),
        ("scheduled_games", "team", "ALTER TABLE scheduled_games ADD COLUMN team TEXT NOT NULL DEFAULT 'boys_hs'"),
        ("seasons", "season_type", "ALTER TABLE seasons ADD COLUMN season_type TEXT NOT NULL DEFAULT 'regular'"),
        ("practice_plan_items", "sort_order", "ALTER TABLE practice_plan_items ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0"),
        ("player_development_clips", "canonical_clip_id", "ALTER TABLE player_development_clips ADD COLUMN canonical_clip_id INTEGER REFERENCES clips(id)"),
        ("player_development_clips", "relational_game_id", "ALTER TABLE player_development_clips ADD COLUMN relational_game_id INTEGER REFERENCES games(id)"),
        ("users", "display_name", "ALTER TABLE users ADD COLUMN display_name TEXT"),
        ("users", "role", "ALTER TABLE users ADD COLUMN role TEXT"),
        ("users", "avatar_url", "ALTER TABLE users ADD COLUMN avatar_url TEXT"),
        ("users", "phone", "ALTER TABLE users ADD COLUMN phone TEXT"),
        ("users", "is_active", "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1"),
        ("users", "email_verified", "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0"),
        ("users", "updated_at", "ALTER TABLE users ADD COLUMN updated_at TIMESTAMP"),
        ("users", "last_login_at", "ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP"),
        ("detections", "player_cluster", "ALTER TABLE detections ADD COLUMN player_cluster INTEGER"),
        ("detections", "jersey_read", "ALTER TABLE detections ADD COLUMN jersey_read INTEGER"),
        ("detections", "jersey_confidence", "ALTER TABLE detections ADD COLUMN jersey_confidence REAL"),
        ("plays", "category_id", "ALTER TABLE plays ADD COLUMN category_id INTEGER REFERENCES play_categories(id)"),
        ("plays", "share_token", "ALTER TABLE plays ADD COLUMN share_token TEXT UNIQUE"),
        ("plays", "parent_play_id", "ALTER TABLE plays ADD COLUMN parent_play_id INTEGER REFERENCES plays(id) ON DELETE SET NULL"),
        ("plays", "progression_order", "ALTER TABLE plays ADD COLUMN progression_order INTEGER NOT NULL DEFAULT 0"),
        ("plays", "list_order", "ALTER TABLE plays ADD COLUMN list_order INTEGER"),
        ("play_steps", "source_image", "ALTER TABLE play_steps ADD COLUMN source_image TEXT"),
    ]
    existing_tables = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    for table, col, sql in col_migrations:
        if table not in existing_tables:
            continue
        try:
            cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()]
            if col not in cols:
                db.execute(sql)
        except Exception:
            pass
    _backfill_platform_core_stage2(db)
    _backfill_demo_module_entitlements_stage8a(db)
    _backfill_review_workflow_stage3a(db)
    _backfill_event_participants_stage4a(db)
    try:
        from playbook_taxonomy import ensure_playbook_taxonomy

        ensure_playbook_taxonomy(db)
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
SEASON_TYPE_OPTIONS = [
    ("regular", "Regular Season"),
    ("summer", "Summer Program"),
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


def _score_fields_from_liberty_opponent(location_type, liberty_score, opponent_score):
    liberty_score = int(liberty_score)
    opponent_score = int(opponent_score)
    if liberty_score > opponent_score:
        result = "win"
    elif liberty_score < opponent_score:
        result = "loss"
    else:
        result = "tie"

    if location_type == "away":
        home_score, away_score = opponent_score, liberty_score
    else:
        home_score, away_score = liberty_score, opponent_score
    return home_score, away_score, result


def save_scheduled_game_record(
    db,
    scheduled_game_id,
    liberty_score,
    opponent_score,
    *,
    is_conference=False,
    mark_completed=True,
):
    scheduled_game = db.execute(
        "SELECT * FROM scheduled_games WHERE id = ?",
        (scheduled_game_id,),
    ).fetchone()
    if not scheduled_game:
        return None, "Scheduled game not found."

    home_score, away_score, result = _score_fields_from_liberty_opponent(
        scheduled_game["location_type"],
        liberty_score,
        opponent_score,
    )
    source_key = f"schedule-{scheduled_game_id}"

    existing = db.execute(
        """
        SELECT id FROM games
        WHERE scheduled_game_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (scheduled_game_id,),
    ).fetchone()

    if existing:
        db.execute(
            """UPDATE games SET
               home_score = ?, away_score = ?, result = ?, is_conference = ?,
               updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (
                home_score,
                away_score,
                result,
                int(bool(is_conference)),
                existing["id"],
            ),
        )
        game_record_id = existing["id"]
    else:
        cur = db.execute(
            """INSERT INTO games
               (scheduled_game_id, source_type, source_key,
                home_score, away_score, result, is_conference)
               VALUES (?, 'manual', ?, ?, ?, ?, ?)""",
            (
                scheduled_game_id,
                source_key,
                home_score,
                away_score,
                result,
                int(bool(is_conference)),
            ),
        )
        game_record_id = cur.lastrowid

    if mark_completed:
        db.execute(
            """UPDATE scheduled_games
               SET status = 'completed', updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (scheduled_game_id,),
        )

    db.commit()
    return game_record_id, None


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
        SELECT
            sg.*,
            s.name AS season_name,
            g.id AS game_record_id,
            g.home_score,
            g.away_score,
            g.result,
            g.is_conference,
            CASE
                WHEN g.id IS NULL THEN NULL
                WHEN sg.location_type = 'away' THEN g.away_score
                ELSE g.home_score
            END AS liberty_score,
            CASE
                WHEN g.id IS NULL THEN NULL
                WHEN sg.location_type = 'away' THEN g.home_score
                ELSE g.away_score
            END AS opponent_score,
            (
                SELECT ar.analysis_key
                FROM analysis_runs ar
                WHERE ar.game_id = g.id
                ORDER BY ar.id DESC
                LIMIT 1
            ) AS analysis_key,
            (
                SELECT v.stored_filename
                FROM videos v
                WHERE v.relational_game_id = g.id
                ORDER BY v.id DESC
                LIMIT 1
            ) AS video_filename
        FROM scheduled_games sg
        JOIN seasons s ON s.id = sg.season_id
        LEFT JOIN games g ON g.id = (
            SELECT g2.id
            FROM games g2
            WHERE g2.scheduled_game_id = sg.id
            ORDER BY g2.id DESC
            LIMIT 1
        )
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
        "season_type": (edit_season["season_type"] if edit_season else "regular") or "regular",
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
        season_type_options=SEASON_TYPE_OPTIONS,
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
    """Refresh derived stats after review/auto-accept.

    Safe outside Flask app context (analysis_launcher / regenerate_events CLI):
    feature flag is resolved from Config + DB settings when current_app is absent.
    """
    from flask import has_app_context

    if has_app_context():
        enabled = feature_enabled("ENABLE_AUTO_STATS_M1")
    else:
        from config import Config

        settings = load_all_settings(
            feature_defaults=dict(Config.FEATURES),
            analysis_defaults=dict(Config.ANALYSIS_CONFIG),
            ai_defaults=AI_DEFAULTS,
            db=db,
        )
        enabled = bool(settings["features"].get("ENABLE_AUTO_STATS_M1", False))
    if not enabled:
        return
    from stats import refresh_stats

    refresh_stats(db, game_id)


# ── Page routes ───────────────────────────────────────────
