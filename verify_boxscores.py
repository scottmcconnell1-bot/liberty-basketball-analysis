import sqlite3
import json
import os

DB_PATH = "film_analysis.db"
TARGET_GAMES = [
    "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334",
    "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"
]

def verify_game_boxscores():
    """
    Reads details_json from events in film_analysis.db for updated games
    and computes points attributed to Home vs. Away teams.
    """
    print("=" * 75)
    print("       BOX SCORE VERIFICATION & AGGREGATION UTILITY       ")
    print("=" * 75)

    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database '{DB_PATH}' not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for game_id in TARGET_GAMES:
        print(f"\n--- Checking Game: {game_id} ---")
        cursor.execute("SELECT player, details_json FROM events WHERE game_id = ?", (game_id,))
        rows = cursor.fetchall()

        home_points = 0
        away_points = 0
        unmatched_points = 0

        for player_cell, details_raw in rows:
            if not details_raw:
                continue

            try:
                details = json.loads(details_raw)
            except json.JSONDecodeError:
                continue

            # Identify scoring event type
            event_type = str(details.get("eventtype", "")).lower()
            
            # Point valuation logic
            pts = 0
            if "three" in event_type:
                pts = 3
            elif "free throw" in event_type or "ft" in event_type:
                pts = 1
            elif "made" in event_type or "two" in event_type or "shot" in event_type:
                pts = 2

            if pts > 0:
                jersey = details.get("jersey_number")
                team = details.get("team")

                if jersey is not None and team is not None:
                    if team == "home":
                        home_points += pts
                    elif team == "away":
                        away_points += pts
                else:
                    unmatched_points += pts

        print(f"  -> Home Team Points: {home_points}")
        print(f"  -> Away Team Points: {away_points}")
        print(f"  -> Unmatched Points: {unmatched_points}")

    conn.close()
    print("\n" + "=" * 75)

if __name__ == "__main__":
    verify_game_boxscores()