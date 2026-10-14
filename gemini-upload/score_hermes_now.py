"""Score run_saved_v6_rule in the ai_bridge.py next to this file."""
import json
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
sys.path.insert(0, str(here))
import ai_bridge

tracks_path = here / "v6_tracks.json"
tracks = json.loads(tracks_path.read_text(encoding="utf-8"))
times = [row["t"] for row in tracks if row.get("hoop")]
out = ai_bridge.run_saved_v6_rule(times, str(tracks_path))
print("applied_to_core", out["applied_to_core"])
print("right", out["right"], "makes_missed", out["makes_missed"], "misses_called_makes", out["misses_called_makes"])
print("--- true makes called misses ---")
for row in out["results"]:
    if row["true"] and not row["pred"]:
        details = row["details"]
        print(row["tag_ts"], details.get("reason") or details.get("veto_reason"))
