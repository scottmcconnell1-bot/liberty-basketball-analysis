"""Candidate shot moments for the clip model = union of the old finder's moments and trigger2 (camera-pan
safe) moments on the same base run, merged when closer than MERGE_MS (old finder's moment wins the tie).

Usage: python candidates.py <out.json> <fps> <old moments.json>[,<old2>...] <frames.json>[,<frames2>...]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trigger2  # noqa: E402

MERGE_MS = 1000
R_TRIG = 1.5


def main():
    out, fps = sys.argv[1], float(sys.argv[2])
    old = []
    for p in sys.argv[3].split(","):
        old += [dict(m, src="finder") for m in json.load(open(p))["moments"]]
    new = []
    for p in sys.argv[4].split(","):
        new += [dict(m, src="trigger2") for m in trigger2.build(p, fps, R_TRIG)]
    allm = sorted(old + new, key=lambda m: (m["t_ms"], 0 if m["src"] == "finder" else 1))
    keep = []
    for m in allm:
        if keep and m["t_ms"] - keep[-1]["t_ms"] <= MERGE_MS:
            if keep[-1]["src"] != "finder" and m["src"] == "finder":
                keep[-1] = m
            continue
        keep.append(m)
    json.dump({"fps": fps, "moments": keep}, open(out, "w"))
    print(f"old {len(old)} + trigger2 {len(new)} -> {len(keep)} candidates -> {out}")


if __name__ == "__main__":
    main()
