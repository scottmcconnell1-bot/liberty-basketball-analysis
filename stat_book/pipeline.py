"""Load layout, extract cells, produce draft confirmed-box JSON."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .align import crop_norm_cell, load_image_bgr, save_image_bgr, warp_to_template
from .checksum import apply_validation
from .ocr import describe_ocr_status, read_digit_cell
from .paths import blank_path, layout_path, sanitize_game_id, sanitize_template_id, upload_dir
from .schema import build_confirmed_box, normalize_player

DEFAULT_TEMPLATE = "liberty_spiral_scorebook"


def load_layout(template_id: str) -> dict:
    path = layout_path(template_id)
    if not path.is_file():
        raise FileNotFoundError(f"Missing layout.json for {template_id}")
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("layout.json must be an object")
    data.setdefault("template_id", template_id)
    return data


def save_layout(template_id: str, layout: dict) -> Path:
    tid = sanitize_template_id(template_id)
    path = layout_path(tid)
    path.parent.mkdir(parents=True, exist_ok=True)
    layout = dict(layout)
    layout["template_id"] = tid
    with path.open("w", encoding="utf-8") as fh:
        json.dump(layout, fh, indent=2)
        fh.write("\n")
    return path


def _sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _ensure_player(bucket: dict[tuple[str, int], dict], team: str, index: int) -> dict:
    key = (team, index)
    if key not in bucket:
        bucket[key] = {"jersey": None, "name": None, "team": team, "extras": {}}
    return bucket[key]


def extract_from_image(
    image_path: str | Path,
    template_id: str,
    game_id: str,
    corners: list[list[float]] | None = None,
    upload_folder: str | Path | None = None,
) -> dict[str, Any]:
    tid = sanitize_template_id(template_id)
    gid = sanitize_game_id(game_id)
    layout = load_layout(tid)
    page = layout.get("page_size") or {"width": 1024, "height": 1024}
    out_w = int(page.get("width") or 1024)
    out_h = int(page.get("height") or 1024)

    image = load_image_bgr(image_path)
    align_mode = "identity"
    working = image
    if image is not None and corners and len(corners) == 4:
        warped = warp_to_template(image, corners, out_w, out_h)
        if warped is not None:
            working = warped
            align_mode = "homography"

    work_dir = upload_dir(gid, upload_folder)
    aligned_path = work_dir / "aligned.png"
    if working is not None:
        save_image_bgr(aligned_path, working)

    players_map: dict[tuple[str, int], dict] = {}
    cell_reads: list[dict] = []
    final_scores: dict[str, int | None] = {"home": None, "away": None}
    team_names: dict[str, str | None] = {"home": None, "away": None}
    ocr_info = describe_ocr_status()

    for cell in layout.get("cells") or []:
        field = cell.get("field")
        team = cell.get("team") or "home"
        idx = int(cell.get("player_index", 0)) if "player_index" in cell else None
        crop = None
        if working is not None and all(k in cell for k in ("x0", "y0", "x1", "y1")):
            crop = crop_norm_cell(
                working,
                float(cell["x0"]),
                float(cell["y0"]),
                float(cell["x1"]),
                float(cell["y1"]),
                pad=0.002,
            )

        value = None
        conf = 0.0
        engine = "none"
        if field == "name":
            # Skip text OCR in v1 — coach fills on review
            pass
        elif field == "team_name":
            pass
        else:
            value, conf, engine = read_digit_cell(crop) if crop is not None else (None, 0.0, "none")

        if field == "final_score" and team in final_scores and value is not None:
            final_scores[team] = value
        elif field in ("fg2", "fg3", "fta", "ftm", "pts", "jersey") and idx is not None:
            player = _ensure_player(players_map, team, idx)
            if field == "jersey":
                player["jersey"] = None if value is None else str(value)
            elif field == "pts":
                player["pts"] = value
            elif field == "fta":
                player["fta"] = value
            elif field == "ftm":
                player["ftm"] = value
            elif field in ("fg2", "fg3"):
                player.setdefault("extras", {})[field] = value

        cell_reads.append(
            {
                "key": cell.get("key"),
                "field": field,
                "team": team,
                "player_index": idx,
                "value": value,
                "confidence": round(float(conf), 3),
                "engine": engine,
            }
        )

    players = [normalize_player(players_map[k]) for k in sorted(players_map.keys(), key=lambda t: (t[0], t[1]))]
    # Drop fully empty rows to keep review usable
    players = [
        p
        for p in players
        if p.get("jersey") is not None
        or p.get("pts") is not None
        or (p.get("extras") or {}).get("fg2") is not None
        or (p.get("extras") or {}).get("fg3") is not None
    ]

    box = build_confirmed_box(
        game_id=gid,
        template_id=tid,
        players=players,
        home_team=team_names.get("home") or "Liberty",
        away_team=team_names.get("away"),
        final_score_home=final_scores.get("home"),
        final_score_away=final_scores.get("away"),
        checksums={
            k: v
            for k, v in {
                "upload_sha256": _sha256_file(Path(image_path)),
                "template_layout_sha256": _sha256_file(layout_path(tid)),
                "blank_sheet_sha256": _sha256_file(blank_path(tid)),
            }.items()
            if v
        },
    )
    box = apply_validation(box)

    payload = {
        "box": box,
        "meta": {
            "align_mode": align_mode,
            "ocr": ocr_info,
            "aligned_image": str(aligned_path) if aligned_path.is_file() else None,
            "cell_reads": cell_reads,
        },
    }
    draft_path = work_dir / "draft.json"
    with draft_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    return payload


def load_draft(game_id: str, upload_folder: str | Path | None = None) -> dict | None:
    path = upload_dir(game_id, upload_folder) / "draft.json"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def save_draft(game_id: str, payload: dict, upload_folder: str | Path | None = None) -> Path:
    path = upload_dir(game_id, upload_folder) / "draft.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    return path
