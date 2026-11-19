"""Q4 blind score: same matching as rim_first_measure.build_report, Q4 tags only.

rim_first_measure drops Q4 by design (Q4 never read during design), so the
blind check keeps only Q4 tags and reuses its build_report with the filter
bypassed by passing tags whose quarter is relabelled. Nothing else changes.
"""
import json
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\scott\Documents\liberty-basketball-analysis")
sys.path.insert(0, str(ROOT / ".team" / "shot_detectors"))
sys.path.insert(0, str(ROOT))

from collect_flight_tracks import load_shot_tags  # noqa: E402
from rim_first_measure import MATCH_WINDOW_MS, build_report, render_summary  # noqa: E402

tags = load_shot_tags(ROOT / "data/film_tags/jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334.json")
q4 = [dict(t, quarter="Q4_blind") for t in tags if t.get("quarter") == "Q4"]
moments = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["moments"]
out = Path(sys.argv[2])
if out.exists():
    raise SystemExit(f"refuse: {out} exists")
report = build_report(moments, q4, MATCH_WINDOW_MS)
out.mkdir(parents=True)
(out / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
(out / "summary.md").write_text(render_summary(report), encoding="utf-8")
print("q4 tags", len(q4), "moments", len(moments))
print(render_summary(report))
