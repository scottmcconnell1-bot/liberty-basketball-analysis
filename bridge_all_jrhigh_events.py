import sqlite3
import json
import os

# Database Path
DB_PATH = "film_analysis.db"

# List of all 9 official Junior High Game IDs from the live database
JR_HIGH_GAME_IDS = [
    "jrhigh_horseshoe_bend_LIBERTY_A_v_HSB_H_20260809_221334",
    "jrhigh_horseshoe_bend_LIBERTY_A_v_HSB_H1_20260809_221334",
    "jrhigh_rimrock_LIBERTY_A_v_RIMROCK_H_20260809_221334",
    "jrhigh_garden_valley_LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334",
    "jrhigh_idaho_city_LIBERTY_H_v_IDAHO_CITY_A_20260809_221334",
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A_20260809_221334",
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334",
    "jrhigh_riverstone_LIBERTY_H_v_RIVERSTONE_A_20260809_221334",
    "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
]

# Track-to-Jersey Mapping Rules
# Maps raw detector camera tracks to jersey numbers and team designations.
TRACK_MAPPING = {
    "0": {"jersey": "0", "team": "home"},
    "1": {"jersey": "0", "team": "home"},
    "2": {"jersey": "2", "team": "home"},
    "3": {"jersey": "3", "team": "home"},
    "4": {"jersey": "4", "team": "away"},
    "5": {"jersey": "5", "team": "away"},
    "6": {"jersey": "6", "team": "away"},
    "7": {"jersey": "7", "team": "away"},
    "8": {"jersey": "5", "team": "home"},
    "9": {"jersey": "9", "team": "away"}
}

def bridge_all_games():
    """
    Scans film_analysis.db for all 9 junior high games and updates event details_json payloads 
    to assign jersey numbers and team sides for all camera tracks.
    """
    print("=" * 75)
    print("       BATCH EVENT BRIDGING UTILITY (ALL 9 JUNIOR HIGH GAMES)       ")
    print("=" * 75)

    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database file '{DB_PATH}' not found in project root.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    total_updated_events = 0

    for game_id in JR_HIGH_GAME_IDS:
        print(f"\nProcessing Game ID: {game_id}")

        cursor.execute("SELECT id, player, details_json FROM events WHERE game_id = ?", (game_id,))
        rows = cursor.fetchall()

        if not rows:
            print("  -> [INFO] No event rows found in database for this game ID.")
            continue

        game_updated_count = 0

        for row_id, player_cell, details_raw in rows:
            player_str = str(player_cell).strip() if player_cell is not None else ""

            # Check if player cell corresponds to a known track ID or numeric string
            if player_str in TRACK_MAPPING:
                mapping = TRACK_MAPPING[player_str]

                try:
                    details = json.loads(details_raw) if details_raw else {}
                except json.JSONDecodeError:
                    details = {}

                # Inject jersey_number and team metadata if missing
                details["jersey_number"] = mapping["jersey"]
                details["team"] = mapping["team"]

                updated_json_str = json.dumps(details)
                cursor.execute(
                    "UPDATE events SET details_json = ? WHERE id = ?",
                    (updated_json_str, row_id)
                )
                game_updated_count += 1

        total_updated_events += game_updated_count
        print(f"  -> [SUCCESS] Updated {game_updated_count} event rows out of {len(rows)} total rows.")

    conn.commit()
    conn.close()

    print("\n" + "=" * 75)
    print(f"[SUMMARY] Batch bridging complete! Total event rows updated: {total_updated_events}")
    print("=" * 75)

if __name__ == "__main__":
    bridge_all_games()