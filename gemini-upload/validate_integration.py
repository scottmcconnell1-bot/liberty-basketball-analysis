"""Score the Adrian tracks with and without an identity homography."""
import json
from pathlib import Path

import numpy as np

from ai_bridge import run_saved_v6_rule

tracks_path = Path(__file__).resolve().parent / "v6_tracks.json"
rows = json.loads(tracks_path.read_text(encoding="utf-8"))
tag_timestamps = [row["t"] for row in rows if row.get("hoop") and len(row["hoop"]) == 4]

baseline = run_saved_v6_rule(tag_timestamps, str(tracks_path), homography_matrix=None)
assert baseline["total_tags"] == 111
assert baseline["right"] == 99
assert baseline["makes_missed"] == 12
assert baseline["misses_called_makes"] == 0
assert baseline["applied_to_core"] is False

identity = run_saved_v6_rule(
    tag_timestamps,
    str(tracks_path),
    homography_matrix=np.eye(3, dtype=np.float64),
)
assert baseline == identity
