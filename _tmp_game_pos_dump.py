"""Dump OCR/seeded positions for 1-Game sheets."""
from pathlib import Path
from playbook_sheet_align import (
    analyze_sheet_image,
    seed_game_sheet_positions,
    apply_game_sequence_routes,
    _GAME_SHEET_START,
)

base = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f")
for page in ["0032", "0033", "0034", "0035", "0036"]:
    path = base / f"page_{page}.png"
    if not path.is_file():
        print(page, "MISSING")
        continue
    raw = analyze_sheet_image(path)["positions"]
    print(f"\n=== {page} OCR ===")
    for k in sorted(raw):
        if k.startswith("o"):
            print(f"  {k}: {raw[k]}")
    seeded = {k: dict(v) for k, v in raw.items()}
    seed_game_sheet_positions(seeded, image_path=path)
    print("  seeded gaps:", {k: seeded[k] for k in seeded if k not in raw or raw.get(k) != seeded.get(k)})
