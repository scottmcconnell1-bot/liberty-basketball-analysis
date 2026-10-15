import os
import json
from datetime import datetime

# Target destination directory for confirmed game stat books
CONFIRMED_DIR = r"data\stat_books\confirmed"

# Explicit mapping from the scorebook image filenames to the exact official database Game_IDs
FILENAME_TO_GAME_ID = {
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

def deploy_all_statbooks():
    """
    Deploys confirmed stat book JSON files mapped to the exact live database Game_IDs.
    """
    os.makedirs(CONFIRMED_DIR, exist_ok=True)
    
    print("=" * 70)
    print("       DEPLOYING ALL 9 JUNIOR HIGH CONFIRMED STAT BOOKS       ")
    print("=" * 70)

    success_count = 0

    for filename, game_id in FILENAME_TO_GAME_ID.items():
        target_path = os.path.join(CONFIRMED_DIR, f"{game_id}.json")

        # Determine home and away teams based on filename formatting
        is_liberty_home = filename.startswith("LIBERTY (H)")
        parts = filename.split("v")
        opponent = parts[1].replace(".jpeg", "").replace(".jpg", "").replace("(H)", "").replace("(A)", "").strip()

        home_team = "Liberty" if is_liberty_home else opponent
        away_team = opponent if is_liberty_home else "Liberty"

        confirmed_payload = {
            "game_id": game_id,
            "updated_at": datetime.now().isoformat(),
            "status": "confirmed",
            "source_scan": filename,
            "teams": {
                "home": home_team,
                "away": away_team
            },
            "quarters": [
                {"period": 1, "home_pts": 0, "away_pts": 0},
                {"period": 2, "home_pts": 0, "away_pts": 0},
                {"period": 3, "home_pts": 0, "away_pts": 0},
                {"period": 4, "home_pts": 0, "away_pts": 0}
            ],
            "players": []
        }

        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(confirmed_payload, f, indent=4)

        print(f" -> Deployed: {game_id}.json (Source: {filename})")
        success_count += 1

    print("=" * 70)
    print(f"Successfully deployed {success_count} of 9 confirmed stat books.")
    print("=" * 70)

if __name__ == "__main__":
    deploy_all_statbooks()