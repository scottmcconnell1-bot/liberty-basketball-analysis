import sqlite3


AI_DEFAULTS = {
    "detector_model": "yolov8n.pt",
    "custom_detector_model": "",
    "event_generator_mode": "expanded",
    "inference_device": "auto",
    "frame_stride": 3,
    "detection_stride": 10,
    "tracker_max_distance": 80,
    "tracker_max_frame_gap": 5,
    "llm_provider": "ollama",
    "llm_model": "",
}


INT_SETTING_KEYS = {
    "ai.frame_stride",
    "ai.detection_stride",
    "ai.tracker_max_distance",
    "ai.tracker_max_frame_gap",
}


def _parse_value(key, value):
    if key.startswith(("feature.", "analysis.")):
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if key in INT_SETTING_KEYS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    return value


def _serialize_value(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def load_all_settings(feature_defaults, analysis_defaults, ai_defaults=None, db=None, db_path=None):
    if ai_defaults is None:
        ai_defaults = AI_DEFAULTS

    close_conn = False
    if db is None:
        if not db_path:
            raise ValueError("db or db_path is required")
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        close_conn = True

    try:
        rows = db.execute("SELECT key, value FROM app_settings").fetchall()
        flat = {row["key"]: _parse_value(row["key"], row["value"]) for row in rows}
    finally:
        if close_conn:
            db.close()

    features = {
        name: flat.get(f"feature.{name}", default)
        for name, default in feature_defaults.items()
    }
    analysis = {
        name: flat.get(f"analysis.{name}", default)
        for name, default in analysis_defaults.items()
    }
    ai = {
        name: flat.get(f"ai.{name}", default)
        for name, default in ai_defaults.items()
    }
    return {"features": features, "analysis": analysis, "ai": ai}


def save_settings(db, updates):
    for key, value in updates.items():
        db.execute(
            """INSERT INTO app_settings (key, value, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(key) DO UPDATE SET
                 value = excluded.value,
                 updated_at = CURRENT_TIMESTAMP""",
            (key, _serialize_value(value)),
        )
    db.commit()
