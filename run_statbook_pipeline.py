import os
import sys
import json
from pathlib import Path

# Ensure the project root directory is in Python's module search path
PROJECT_ROOT = Path(r"C:\Users\scott\Documents\liberty-basketball-analysis")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import your repository's native stat_book modules safely
try:
    from stat_book.pipeline import process_scorebook_image
except ImportError as e:
    print(f"[ERROR] Could not import 'stat_book.pipeline': {e}")
    sys.exit(1)

# Setup paths
UPLOADS_DIR = PROJECT_ROOT / "uploads" / "stat_books" / "jrhigh"
CONFIRMED_DIR = PROJECT_ROOT / "data" / "stat_books" / "confirmed"

# Map image filenames directly to official live Game_IDs
IMAGE_TO_GAME_ID = {
    "LIBERTY (A) v HSB (H).jpeg": "jrhigh_horseshoe_bend_LIBERTY_A_v_HSB_H_20260809_221334",
    "LIBERTY (A) v HSB (H)1.jpeg": "jrhigh_horseshoe_bend_LIBERTY_A_v_HSB_H1_20260809_221334",
    "LIBERTY (A) v RIMROCK (H).jpeg": "jrhigh_rimrock_LIBERTY_A_v_RIMROCK_H_20260809_221334",
    "LIBERTY (H) v GARDEN VALLEY (A).jpeg": "jrhigh_garden_valley_LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334",
    "LIBERTY (H) v IDAHO CITY (A).jpeg": "jrhigh_idaho_city_LIBERTY_H_v_IDAHO_CITY_A_20260809_221334",
    "LIBERTY (H) v NOTUS (A).jpeg": "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334",
    "LIBERTY (H) v NOTUS (A)1.jpeg": "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334",
    "LIBERTY (H) v RIVERSTONE (A).jpg": "jrhigh_riverstone_LIBERTY_H_v_RIVERSTONE_A_20260809_221334",
    "LIBERTY (A) v ADRIAN (H).jpeg": "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
}

def run_pipeline():
    """
    Passes scorebook scans through stat_book.pipeline to extract handwritten totals
    and deploys confirmed JSON files using official Game_IDs.
    """
    print("=" * 75)
    print("       STAT_BOOK NATIVE OCR PIPELINE EXECUTOR       ")
    print("=" * 75)

    CONFIRMED_DIR.mkdir(parents=True, exist_ok=True)
    processed_count = 0

    for image_name, game_id in IMAGE_TO_GAME_ID.items():
        # Skip Adrian since its real confirmed scorebook is already restored
        if "adrian" in game_id:
            print(f"\n[SKIP] Adrian game '{game_id}' is already restored with real totals.")
            continue

        image_path = UPLOADS_DIR / image_name
        target_json_path = CONFIRMED_DIR / f"{game_id}.json"

        if not image_path.exists():
            print(f"\n[WARNING] Image scan not found: {image_path}")
            continue

        print(f"\nProcessing Image: {image_name}")
        print(f"  -> Target Game ID: {game_id}")

        try:
            # Execute the stat_book module pipeline extraction logic
            result = process_scorebook_image(str(image_path), game_id=game_id)
            
            with open(target_json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=4)

            print(f"  -> [SUCCESS] Saved extracted stat book to: {target_json_path}")
            processed_count += 1

        except Exception as e:
            print(f"  -> [ERROR] Pipeline failed on {image_name}: {e}")

    print("\n" + "=" * 75)
    print(f"[SUMMARY] Pipeline execution complete! Processed {processed_count} scorebook scan(s).")
    print("=" * 75)

if __name__ == "__main__":
    run_pipeline()