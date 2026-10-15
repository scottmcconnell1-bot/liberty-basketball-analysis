import os
import json
from datetime import datetime

# Define target paths
UPLOADS_DIR = r"C:\Users\scott\Documents\liberty-basketball-analysis\uploads\stat_books\jrhigh"
CONFIRMED_STAT_BOOKS_DIR = r"data\stat_books\confirmed"

def batch_import_books():
    """
    Recursively scans the jrhigh stat_books directory, extracts game metadata,
    and deploys confirmed stat books to data/stat_books/confirmed/.
    """
    print("=" * 75)
    print("       STAT BOOK RECURSIVE INGESTION & DEPLOYMENT UTILITY       ")
    print("=" * 75)

    # Step 1: Validate input directory
    if not os.path.exists(UPLOADS_DIR):
        print(f"[ERROR] Uploads directory not found at: {UPLOADS_DIR}")
        return

    # Ensure output directory exists
    os.makedirs(CONFIRMED_STAT_BOOKS_DIR, exist_ok=True)

    # Step 2: Collect all JSON files in UPLOADS_DIR and subfolders
    discovered_files = []
    for root, _, files in os.walk(UPLOADS_DIR):
        for file in files:
            if file.lower().endswith(".json"):
                discovered_files.append(os.path.join(root, file))

    print(f"[INFO] Discovered {len(discovered_files)} JSON file(s) in '{UPLOADS_DIR}'\n")

    if not discovered_files:
        print("[WARNING] No .json files found. Checking directory contents:")
        try:
            items = os.listdir(UPLOADS_DIR)
            print(f"  Contents of '{UPLOADS_DIR}': {items}")
        except Exception as e:
            print(f"  Unable to list contents: {e}")
        return

    # Step 3: Process each discovered file
    processed_count = 0

    for file_path in discovered_files:
        filename = os.path.basename(file_path)
        print(f"Processing: {filename}")
        print(f"  Full Path: {file_path}")

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                book_data = json.load(f)
        except Exception as e:
            print(f"  [ERROR] Failed to parse JSON payload: {e}\n")
            continue

        # Determine Game ID (from payload or fallback to file name)
        game_id = book_data.get("game_id")
        if not game_id:
            game_id = os.path.splitext(filename)[0]

        teams = book_data.get("teams", {})
        home_team = teams.get("home", "Liberty")
        away_team = teams.get("away", "Opponent")

        print(f"  -> Game ID Resolved: {game_id}")
        print(f"  -> Teams: Home={home_team} | Away={away_team}")

        # Build confirmed stat book payload
        confirmed_payload = {
            "game_id": game_id,
            "updated_at": datetime.now().isoformat(),
            "status": "confirmed",
            "teams": teams,
            "source_file": filename,
            "players": book_data.get("players", []),
            "data": book_data
        }

        # Step 4: Save to confirmed stat books directory
        target_path = os.path.join(CONFIRMED_STAT_BOOKS_DIR, f"{game_id}.json")
        try:
            with open(target_path, 'w', encoding='utf-8') as out_f:
                json.dump(confirmed_payload, out_f, indent=4)
            print(f"  -> [SUCCESS] Deployed to: {target_path}\n")
            processed_count += 1
        except Exception as e:
            print(f"  -> [ERROR] Failed to write confirmed stat book: {e}\n")

    print("=" * 75)
    print(f"[SUMMARY] Successfully deployed {processed_count} of {len(discovered_files)} stat book(s).")
    print("=" * 75)

if __name__ == "__main__":
    batch_import_books()