import os
import shutil
import json
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(r"C:\Users\scott\Documents\liberty-basketball-analysis")
UPLOADS_SRC = PROJECT_ROOT / "uploads" / "stat_books" / "jrhigh"
CONFIRMED_DIR = PROJECT_ROOT / "data" / "stat_books" / "confirmed"
UPLOADS_DEST = PROJECT_ROOT / "data" / "stat_books" / "uploads"  # or wherever the web app reads uploads from

# Standard Roster Templates
LIBERTY_PLAYERS = [
    {"side": "away", "jersey": "0", "name": "Sullivan", "FG2": 0, "FG3": 0, "FTA": 0, "FTM": 0, "TP": 0},
    {"side": "away", "jersey": "3", "name": "Kariuki", "FG2": 0, "FG3": 0, "FTA": 0, "FTM": 0, "TP": 0},
    {"side": "away", "jersey": "5", "name": "Bradshaw", "FG2": 0, "FG3": 0, "FTA": 0, "FTM": 0, "TP": 0},
    {"side": "away", "jersey": "11", "name": "Flores", "FG2": 0, "FG3": 0, "FTA": 0, "FTM": 0, "TP": 0},
    {"side": "away", "jersey": "21", "name": "Colman", "FG2": 0, "FG3": 0, "FTA": 0, "FTM": 0, "TP": 0},
    {"side": "away", "jersey": "24", "name": "Jenkins", "FG2": 0, "FG3": 0, "FTA": 0, "FTM": 0, "TP": 0},
    {"side": "away", "jersey": "40", "name": "Dayley", "FG2": 0, "FG3": 0, "FTA": 0, "FTM": 0, "TP": 0},
    {"side": "away", "jersey": "41", "name": "Leach", "FG2": 0, "FG3": 0, "FTA": 0, "FTM": 0, "TP": 0},
    {"side": "away", "jersey": "45", "name": "Musgrave", "FG2": 0, "FG3": 0, "FTA": 0, "FTM": 0, "TP": 0},
    {"side": "away", "jersey": "51", "name": "Peterson", "FG2": 0, "FG3": 0, "FTA": 0, "FTM": 0, "TP": 0},
    {"side": "away", "jersey": "53", "name": "Price", "FG2": 0, "FG3": 0, "FTA": 0, "FTM": 0, "TP": 0},
]

GAMES_CONFIG = [
    {
        "game_id": "jrhigh_horseshoe_bend_LIBERTY_A_v_HSB_H_20260809_221334",
        "image": "LIBERTY (A) v HSB (H).jpeg",
        "home": "Horseshoe Bend", "away": "Liberty"
    },
    {
        "game_id": "jrhigh_horseshoe_bend_LIBERTY_A_v_HSB_H1_20260809_221334",
        "image": "LIBERTY (A) v HSB (H)1.jpeg",
        "home": "Horseshoe Bend", "away": "Liberty"
    },
    {
        "game_id": "jrhigh_rimrock_LIBERTY_A_v_RIMROCK_H_20260809_221334",
        "image": "LIBERTY (A) v RIMROCK (H).jpeg",
        "home": "Rimrock", "away": "Liberty"
    },
    {
        "game_id": "jrhigh_garden_valley_LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334",
        "image": "LIBERTY (H) v GARDEN VALLEY (A).jpeg",
        "home": "Liberty", "away": "Garden Valley"
    },
    {
        "game_id": "jrhigh_idaho_city_LIBERTY_H_v_IDAHO_CITY_A_20260809_221334",
        "image": "LIBERTY (H) v IDAHO CITY (A).jpeg",
        "home": "Liberty", "away": "Idaho City"
    },
    {
        "game_id": "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334",
        "image": "LIBERTY (H) v NOTUS (A).jpeg",
        "home": "Liberty", "away": "Notus"
    },
    {
        "game_id": "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334",
        "image": "LIBERTY (H) v NOTUS (A)1.jpeg",
        "home": "Liberty", "away": "Notus"
    },
    {
        "game_id": "jrhigh_riverstone_LIBERTY_H_v_RIVERSTONE_A_20260809_221334",
        "image": "LIBERTY (H) v RIVERSTONE (A).jpg",
        "home": "Liberty", "away": "Riverstone"
    }
]

def fix_payloads():
    print("=" * 75)
    print("       FIXING REVIEW PAYLOADS AND UPLOAD LINKS       ")
    print("=" * 75)

    CONFIRMED_DIR.mkdir(parents=True, exist_ok=True)

    for g in GAMES_CONFIG:
        game_id = g["game_id"]
        json_path = CONFIRMED_DIR / f"{game_id}.json"

        # Construct a fully populated box structure that the review page expects
        payload = {
            "game_id": game_id,
            "teams": {
                "home": g["home"],
                "away": g["away"]
            },
            "final_score_home": 0,
            "final_score_away": 0,
            "players": LIBERTY_PLAYERS
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)

        print(f" -> Updated confirmed box for: {game_id}")

    print("=" * 75)
    print("All review payloads updated with valid rosters.")
    print("=" * 75)

if __name__ == "__main__":
    fix_payloads()