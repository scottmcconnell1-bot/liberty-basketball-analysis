import sqlite3
import json
import os

DB_PATH = "film_analysis.db"
GAME_ID = "jrhigh_notus_LIBERTY_H_v_NOTUS_A1_20260809_221334"

def inspect_scoring_schema():
    """
    Connects to film_analysis.db, retrieves column metadata and sample event rows,
    and displays the exact JSON structure for scoring records.
    """
    print("=" * 75)
    print("       SCORING EVENT SCHEMA INSPECTION UTILITY       ")
    print("=" * 75)

    if not os.path.exists(DB_PATH):
        print(f"[ERROR] Database file '{DB_PATH}' not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Step 1: Inspect table column names
    cursor.execute("PRAGMA table_info(events);")
    columns = cursor.fetchall()
    column_names = [col[1] for col in columns]
    print(f"[INFO] Table 'events' Columns: {column_names}\n")

    # Step 2: Fetch sample rows to inspect details_json contents
    cursor.execute("SELECT * FROM events WHERE game_id = ? LIMIT 10", (GAME_ID,))
    rows = cursor.fetchall()

    print(f"--- Sample Event Records for Game: {GAME_ID} ---")
    for idx, row in enumerate(rows, start=1):
        # Map row tuple to column dictionary
        row_dict = dict(zip(column_names, row))
        player_cell = row_dict.get("player")
        details_raw = row_dict.get("details_json")

        print(f"\nRecord #{idx}:")
        print(f"  -> Player Cell: {player_cell}")
        
        # Display other non-JSON columns if present
        for col in column_names:
            if col not in ("id", "game_id", "details_json", "player"):
                print(f"  -> Column [{col}]: {row_dict[col]}")

        # Parse and display details_json structure
        if details_raw:
            try:
                details_parsed = json.loads(details_raw)
                print(f"  -> Parsed details_json Keys: {list(details_parsed.keys())}")
                print(f"  -> Full JSON Contents: {json.dumps(details_parsed)}")
            except json.JSONDecodeError:
                print(f"  -> Raw details_json String: {details_raw}")

    conn.close()
    print("\n" + "=" * 75)

if __name__ == "__main__":
    inspect_scoring_schema()