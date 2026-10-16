import sqlite3
from pathlib import Path

# Set paths
PROJECT_ROOT = Path(r"C:\Users\scott\Documents\liberty-basketball-analysis")
DB_PATH = PROJECT_ROOT / "film_analysis.db"
ADRIAN_GAME_ID = "jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334"

def inspect_disagreements():
    """
    Inspects the events table schema dynamically and queries the Adrian game 
    records to locate disputed make/miss events and review statuses.
    """
    print("=" * 80)
    print("       ADRIAN GAME TELEMETRY & SCHEMA INSPECTOR       ")
    print("=" * 80)

    if not DB_PATH.exists():
        print(f"[ERROR] Database file not found at: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Discover actual column names in the events table
    cursor.execute("PRAGMA table_info(events);")
    columns_info = cursor.fetchall()
    
    if not columns_info:
        print("[ERROR] The 'events' table was not found or has no columns.")
        conn.close()
        return

    existing_columns = [col[1] for col in columns_info]
    print(f"\n[INFO] Detected 'events' columns ({len(existing_columns)} total):")
    print(f"  -> {', '.join(existing_columns)}\n")

    # 2. Build a flexible query based on available columns
    select_cols = []
    possible_cols = [
        "id", "game_id", "frame", "frame_idx", "time_sec", "timestamp_ms",
        "jersey", "jersey_number", "player_name", "event_type", 
        "review_status", "human_verified", "confidence", "make_miss"
    ]

    for col in possible_cols:
        if col in existing_columns:
            select_cols.append(col)

    # Fallback to SELECT * if custom column list is too narrow
    if not select_cols:
        query = f"SELECT * FROM events WHERE game_id = ? LIMIT 20;"
    else:
        cols_str = ", ".join(select_cols)
        query = f"SELECT {cols_str} FROM events WHERE game_id = ? LIMIT 20;"

    print(f"[INFO] Executing query across available columns for game: {ADRIAN_GAME_ID}")
    cursor.execute(query, (ADRIAN_GAME_ID,))
    rows = cursor.fetchall()

    if not rows:
        print(f"\n[INFO] No event rows found matching game_id = '{ADRIAN_GAME_ID}'.")
    else:
        print(f"\n[SUCCESS] Retrieved {len(rows)} event row(s) for inspection:\n")
        display_cols = select_cols if select_cols else existing_columns
        for idx, row in enumerate(rows, 1):
            print(f"--- Event #{idx} ---")
            for col_name, val in zip(display_cols, row):
                print(f"  {col_name:<20}: {val}")
            print()

    conn.close()
    print("=" * 80)

if __name__ == "__main__":
    inspect_disagreements()