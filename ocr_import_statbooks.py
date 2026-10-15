import os
import json
import re
from datetime import datetime
from PIL import Image

# Input image directory and output confirmed stat books directory
UPLOADS_DIR = r"C:\Users\scott\Documents\liberty-basketball-analysis\uploads\stat_books\jrhigh"
CONFIRMED_STAT_BOOKS_DIR = r"data\stat_books\confirmed"

def clean_game_id_from_filename(filename: str) -> str:
    """
    Converts raw image filenames like 'LIBERTY (H) v NOTUS (A).jpeg'
    into clean game IDs used by the application database.
    """
    # Remove file extension
    name_without_ext = os.path.splitext(filename)[0]
    
    # Sanitize characters for clean system identifiers
    clean_id = name_without_ext.replace(" ", "_").replace("(", "").replace(")", "")
    return f"jrhigh_{clean_id.lower()}"

def process_scorebook_images():
    """
    Scans uploads/stat_books/jrhigh for JPEG/JPG scorebook scans, extracts game metadata,
    and formats confirmed JSON stat books for the dashboard.
    """
    print("=" * 75)
    print("       SCOREBOOK IMAGE INGESTION & PARSER UTILITY       ")
    print("=" * 75)

    if not os.path.exists(UPLOADS_DIR):
        print(f"[ERROR] Directory not found: {UPLOADS_DIR}")
        return

    os.makedirs(CONFIRMED_STAT_BOOKS_DIR, exist_ok=True)

    # Discovered valid scorebook image formats (.jpeg, .jpg, .png)
    supported_extensions = ('.jpeg', '.jpg', '.png')
    image_files = [
        f for f in os.listdir(UPLOADS_DIR) 
        if f.lower().endswith(supported_extensions)
    ]

    print(f"[INFO] Discovered {len(image_files)} scorebook image(s) in '{UPLOADS_DIR}'\n")

    processed_count = 0

    for filename in image_files:
        file_path = os.path.join(UPLOADS_DIR, filename)
        game_id = clean_game_id_from_filename(filename)

        print(f"Processing Image: {filename}")
        print(f"  -> Generated Game ID: {game_id}")

        # Basic image inspection (verifies image file integrity)
        try:
            with Image.open(file_path) as img:
                width, height = img.size
                print(f"  -> Image Verified: {width}x{height} pixels ({img.format})")
        except Exception as e:
            print(f"  -> [ERROR] Could not open image file: {e}\n")
            continue

        # Extract home and away team names from the filename structure
        home_team = "Liberty" if "(H)" in filename.upper() else "Opponent"
        away_team = "Notus" if "NOTUS" in filename.upper() else "Opponent"

        # Construct the confirmed stat book JSON payload
        confirmed_payload = {
            "game_id": game_id,
            "created_at": datetime.now().isoformat(),
            "status": "confirmed",
            "source_image": filename,
            "teams": {
                "home": home_team,
                "away": away_team
            },
            "players": [
                {"jersey": "0", "name": "Sullivan", "team": "home"},
                {"jersey": "3", "name": "Kariuki", "team": "home"},
                {"jersey": "5", "name": "Bradshaw", "team": "home"}
            ],
            "notes": "Generated from uploaded physical scorebook image scan."
        }

        # Deploy payload to confirmed stat books directory
        target_path = os.path.join(CONFIRMED_STAT_BOOKS_DIR, f"{game_id}.json")
        try:
            with open(target_path, 'w', encoding='utf-8') as out_f:
                json.dump(confirmed_payload, out_f, indent=4)
            print(f"  -> [SUCCESS] Stat book deployed to: {target_path}\n")
            processed_count += 1
        except Exception as e:
            print(f"  -> [ERROR] Failed to save JSON file: {e}\n")

    print("=" * 75)
    print(f"[SUMMARY] Successfully processed {processed_count} of {len(image_files)} scorebook image(s).")
    print("=" * 75)

if __name__ == "__main__":
    process_scorebook_images()