import os
import sys
import json
from pathlib import Path

# Ensure project root is in Python's module search path
PROJECT_ROOT = Path(r"C:\Users\scott\Documents\liberty-basketball-analysis")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from stat_book.pipeline import extract_from_image, DEFAULT_TEMPLATE
except ImportError as e:
    print(f"[ERROR] Could not import 'extract_from_image': {e}")
    sys.exit(1)

# Setup paths
UPLOADS_DIR = PROJECT_ROOT / "uploads" / "stat_books" / "jrhigh"
CONFIRMED_DIR = PROJECT_ROOT / "data" / "stat_books" / "confirmed"

# Official image-to-Game_ID mapping
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

def run_extraction():
    """
    Executes extract_from_image on all remaining scorebook scans and 
    saves the confirmed box payload to data/stat_books/confirmed/.
    """
    print("=" * 75)
    print("       STAT BOOK EXTRACTION PIPELINE RUNNER       ")
    print("=" * 75)

    CONFIRMED_DIR.mkdir(parents=True, exist_ok=True)
    success_count = 0

    for image_name, game_id in IMAGE_TO_GAME_ID.items():
        # Skip Adrian since its real confirmed scorebook is already safely restored
        if "adrian" in game_id:
            print(f"\n[SKIP] Adrian game '{game_id}' is already restored.")
            continue

        image_path = UPLOADS_DIR / image_name
        target_json_path = CONFIRMED_DIR / f"{game_id}.json"

        if not image_path.exists():
            print(f"\n[WARNING] Image scan not found on disk: {image_path}")
            continue

        print(f"\nProcessing: {image_name}")
        print(f"  -> Game ID: {game_id}")

        try:
            # Run the extraction pipeline using the native template and game ID
            result = extract_from_image(
                image_path=image_path,
                template_id=DEFAULT_TEMPLATE,
                game_id=game_id
            )

            # extract_from_image returns a payload dict containing 'box' and 'meta'
            # We save the 'box' data structure as the official confirmed JSON file
            confirmed_box = result.get("box", result)

            with open(target_json_path, "w", encoding="utf-8") as f:
                json.dump(confirmed_box, f, indent=4)

            print(f"  -> [SUCCESS] Saved confirmed box score to: {target_json_path}")
            success_count += 1

        except Exception as e:
            print(f"  -> [ERROR] Extraction failed on {image_name}: {e}")

    print("\n" + "=" * 75)
    print(f"[SUMMARY] Pipeline finished successfully. Processed {success_count} game scan(s).")
    print("=" * 75)

if __name__ == "__main__":
    run_extraction()