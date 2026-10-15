"""Save a note for each of the 16 make/miss differences.

The list is the run of run_saved_v6_rule on the 129 tagged shots.
This script does not change ai_bridge.py and does not change that score.
A blank line stores "Pending Coach Review". It does not store a film observation.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

DISCREPANCIES = [
    {"timestamp_ms": 342800, "seek_time": "5:39.8", "tag_time": "5:42.8", "player": "Peterson", "shot": "2", "tag": "make", "rule": "miss", "reason": "ball bounces up"},
    {"timestamp_ms": 638300, "seek_time": "10:35.3", "tag_time": "10:38.3", "player": "Colman", "shot": "2", "tag": "make", "rule": "miss", "reason": "ball starts well below the rim"},
    {"timestamp_ms": 717000, "seek_time": "11:54.0", "tag_time": "11:57.0", "player": "Colman", "shot": "2", "tag": "make", "rule": "miss", "reason": "no valid crossing"},
    {"timestamp_ms": 801800, "seek_time": "13:18.8", "tag_time": "13:21.8", "player": "Dayley", "shot": "2", "tag": "make", "rule": "miss", "reason": "no valid crossing"},
    {"timestamp_ms": 1231400, "seek_time": "20:28.4", "tag_time": "20:31.4", "player": "Alvarez", "shot": "free throw", "tag": "make", "rule": "miss", "reason": "column ratio low"},
    {"timestamp_ms": 1792900, "seek_time": "29:49.9", "tag_time": "29:52.9", "player": "Dayley", "shot": "2", "tag": "make", "rule": "miss", "reason": "short net depth"},
    {"timestamp_ms": 1836700, "seek_time": "30:33.7", "tag_time": "30:36.7", "player": "Colman", "shot": "3", "tag": "make", "rule": "miss", "reason": "ball box jump"},
    {"timestamp_ms": 2479100, "seek_time": "41:16.1", "tag_time": "41:19.1", "player": "Rodus", "shot": "2", "tag": "make", "rule": "miss", "reason": "no valid crossing"},
    {"timestamp_ms": 2870400, "seek_time": "47:47.4", "tag_time": "47:50.4", "player": "Colman", "shot": "3", "tag": "make", "rule": "miss", "reason": "column ratio low"},
    {"timestamp_ms": 2962500, "seek_time": "49:19.5", "tag_time": "49:22.5", "player": "Colman", "shot": "2", "tag": "make", "rule": "miss", "reason": "sideways drift"},
    {"timestamp_ms": 3045900, "seek_time": "50:42.9", "tag_time": "50:45.9", "player": "Alvarez", "shot": "free throw", "tag": "make", "rule": "miss", "reason": "ball box jump"},
    {"timestamp_ms": 3095700, "seek_time": "51:32.7", "tag_time": "51:35.7", "player": "Mendoza", "shot": "free throw", "tag": "make", "rule": "miss", "reason": "no valid crossing"},
    {"timestamp_ms": 3393600, "seek_time": "56:30.6", "tag_time": "56:33.6", "player": "Mendoza", "shot": "2", "tag": "miss", "rule": "make", "reason": "rule called a make"},
    {"timestamp_ms": 3399400, "seek_time": "56:36.4", "tag_time": "56:39.4", "player": "Sullivan", "shot": "2", "tag": "make", "rule": "miss", "reason": "ball starts well below the rim"},
    {"timestamp_ms": 3568100, "seek_time": "59:25.1", "tag_time": "59:28.1", "player": "Peterson", "shot": "2", "tag": "make", "rule": "miss", "reason": "ball starts well below the rim"},
    {"timestamp_ms": 3673500, "seek_time": "61:10.5", "tag_time": "61:13.5", "player": "Dayley", "shot": "3", "tag": "make", "rule": "miss", "reason": "ball starts well below the rim"},
]

PENDING = "Pending Coach Review"


def load_existing_notes(output_file):
    path = Path(output_file)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_notes(notes_data, output_file):
    Path(output_file).write_text(json.dumps(notes_data, indent=2), encoding="utf-8")
    print(f"saved {len(notes_data)}  {output_file}")


def _known():
    by_ms = {}
    by_time = {}
    for item in DISCREPANCIES:
        by_ms[item["timestamp_ms"]] = item
        by_time[item["tag_time"]] = item
    return by_ms, by_time


def _clock(text):
    """5:42.8 and 05:42.8 are the same tag time."""
    parts = text.split(":")
    if len(parts) != 2:
        return text
    try:
        minutes = int(parts[0])
        seconds = float(parts[1])
    except ValueError:
        return text
    return f"{minutes}:{seconds:04.1f}"


def _lookup(raw_key, by_ms, by_time):
    text = str(raw_key).strip()
    if text in by_time:
        return by_time[text]
    clock = _clock(text)
    if clock in by_time:
        return by_time[clock]
    digits = text.replace(",", "")
    if digits.isdigit():
        return by_ms.get(int(digits))
    return None


def initialize_notes_file(output_file="coach_discrepancy_notes.json"):
    """Add any of the 16 that are missing. Leave a saved note as it is."""
    notes = load_existing_notes(output_file)
    added = 0
    for item in DISCREPANCIES:
        key = str(item["timestamp_ms"])
        current = notes.get(key, {}).get("coach_observation", "")
        if current and current != PENDING:
            continue
        if key in notes:
            continue
        notes[key] = _row(item, PENDING)
        added += 1
    save_notes(notes, output_file)
    print(f"added {added}")
    return notes


def apply_notes(supplied, output_file="coach_discrepancy_notes.json"):
    """Write notes passed in as {timestamp or tag time: observation}. Does not prompt."""
    if not Path(output_file).exists():
        initialize_notes_file(output_file)
    notes = load_existing_notes(output_file)
    by_ms, by_time = _known()
    updated = 0
    for raw_key, observation in supplied.items():
        item = _lookup(raw_key, by_ms, by_time)
        if item is None:
            print(f"not one of the 16: {raw_key}")
            continue
        text = str(observation).strip()
        if not text:
            continue
        notes[str(item["timestamp_ms"])] = _row(item, text)
        updated += 1
    save_notes(notes, output_file)
    print(f"updated {updated}")
    return notes


def _row(item, observation):
    return {
        "timestamp_ms": item["timestamp_ms"],
        "seek_time": item["seek_time"],
        "tag_time": item["tag_time"],
        "player": item["player"],
        "shot_type": item["shot"],
        "human_tag": item["tag"],
        "rule_outcome": item["rule"],
        "rule_reason": item["reason"],
        "coach_observation": observation,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def record_coach_notes(output_file="coach_discrepancy_notes.json", interactive=False):
    notes = load_existing_notes(output_file)
    print("16 differences. The rule remains 113 of 129.")
    for item in DISCREPANCIES:
        key = str(item["timestamp_ms"])
        existing = notes.get(key, {}).get("coach_observation", "")
        print(
            f"{item['tag_time']}  seek {item['seek_time']}  {item['player']} {item['shot']}  "
            f"tag {item['tag']}  rule {item['rule']}"
        )
        if existing and existing != PENDING and not interactive:
            continue
        if interactive:
            if existing:
                print(f"saved note: {existing}")
            typed = input("Note: ").strip()
            observation = typed or existing or PENDING
        else:
            observation = existing or PENDING
        if notes.get(key, {}).get("coach_observation") == observation and key in notes:
            continue
        notes[key] = _row(item, observation)
    save_notes(notes, output_file)
    return notes


if __name__ == "__main__":
    initialize_notes_file()
