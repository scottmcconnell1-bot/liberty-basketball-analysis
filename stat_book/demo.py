"""Seed demo / sample drafts for pipeline practice."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .checksum import apply_validation
from .paths import ROOT, ensure_dirs, template_dir, upload_dir
from .schema import build_confirmed_box


# Liberty side from HSB District Finals sample (manual ground truth for validation)
LIBERTY_HSB_PLAYERS = [
    {"jersey": "11", "name": "E. Flores", "team": "home", "extras": {"fg2": 1, "fg3": 0}, "fta": 0, "ftm": 0, "pts": 2},
    {"jersey": "21", "name": "H. Coleman", "team": "home", "extras": {"fg2": 3, "fg3": 3}, "fta": 4, "ftm": 2, "pts": 17},
    {"jersey": "40", "name": "L. Dayley", "team": "home", "extras": {"fg2": 5, "fg3": 4}, "fta": 2, "ftm": 1, "pts": 23},
    {"jersey": "51", "name": "C. Peterson", "team": "home", "extras": {"fg2": 3, "fg3": 0}, "fta": 0, "ftm": 0, "pts": 6},
]

HSB_PLAYERS = [
    {"jersey": "1", "name": None, "team": "away", "extras": {"fg2": 3, "fg3": 6}, "fta": 2, "ftm": 1, "pts": 25},
    {"jersey": "4", "name": None, "team": "away", "extras": {"fg2": 5, "fg3": 0}, "fta": 1, "ftm": 1, "pts": 11},
    {"jersey": "5", "name": None, "team": "away", "extras": {"fg2": 1, "fg3": 0}, "fta": 2, "ftm": 1, "pts": 3},
    {"jersey": "12", "name": None, "team": "away", "extras": {"fg2": 1, "fg3": 0}, "fta": 2, "ftm": 1, "pts": 3},
    {"jersey": "21", "name": None, "team": "away", "extras": {"fg2": 4, "fg3": 0}, "fta": 4, "ftm": 2, "pts": 10},
]


def ensure_spiral_template() -> Path:
    ensure_dirs()
    tdir = template_dir("liberty_spiral_scorebook")
    tdir.mkdir(parents=True, exist_ok=True)
    if not (tdir / "blank.png").is_file():
        raise FileNotFoundError("Missing blank.png — copy Scott's blank spiral template first")
    if not (tdir / "layout.json").is_file():
        raise FileNotFoundError("Missing layout.json for liberty_spiral_scorebook")
    return tdir


def create_sample_draft(
    game_id: str = "sample-hsb-liberty",
    upload_folder: str | Path | None = None,
) -> dict:
    """Copy HSB/Liberty filled sample into uploads and seed a validated draft box."""
    ensure_spiral_template()
    sample = template_dir("liberty_spiral_scorebook") / "sample_hsb_liberty.png"
    if not sample.is_file():
        sample = ROOT / "uploads" / "stat_books" / "samples" / "hsb_liberty_district_finals.png"
    work = upload_dir(game_id, upload_folder)
    original = work / "original.png"
    if sample.is_file():
        shutil.copy2(sample, original)

    players = LIBERTY_HSB_PLAYERS + HSB_PLAYERS
    home_pts = sum(p["pts"] for p in LIBERTY_HSB_PLAYERS)
    away_pts = sum(p["pts"] for p in HSB_PLAYERS)
    box = build_confirmed_box(
        game_id=game_id,
        template_id="liberty_spiral_scorebook",
        players=players,
        home_team="Liberty",
        away_team="HSB",
        final_score_home=48,
        final_score_away=49,
        quarters=[
            {"period": 1, "home_pts": 15, "away_pts": 7},
            {"period": "1H", "home_pts": 23, "away_pts": 22},
            {"period": 3, "home_pts": 36, "away_pts": 32},
            {"period": "F", "home_pts": 48, "away_pts": 49},
        ],
        checksums={},
    )
    box = apply_validation(box)
    # Note: partial roster — final_score_sum may flag until remaining players entered
    payload = {
        "box": box,
        "meta": {
            "align_mode": "sample_seed",
            "ocr": {"backend": "manual_seed", "easyocr": False, "tesseract": False},
            "aligned_image": str(original) if original.is_file() else None,
            "notes": "Seeded from Scott HSB/Liberty sample partial roster for review UI.",
            "home_pts_partial": home_pts,
            "away_pts_partial": away_pts,
        },
    }
    with (work / "draft.json").open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    return payload
