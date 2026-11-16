"""D2 train job runner (spec .team/specs/23_d2_train_job_spec.md v2, sections 3-5).

Run with the GPU Python (Python312, torch cu128). Order, each step stops for Scott on failure:
  0. D1 test path proof: repo venv, --step arc-rule-report on D1's own candidates.json -> must be 29 / 0.
  1. v6 val metrics on the D2 val split (before training).
  2. Train from v6 with the fixed section 3 numbers -> runs/d2v1/weights/best.pt (outside the repo).
  3. d2v1 val metrics on the same split.
  4. D1 test with only the weights changed: repo venv, --step extract, then --step arc-rule-report.
     Step extract may exit on the 0.90 mapping gate (agreement with v6 points); per spec section 4
     that alone is not a stop when candidates.json was written. Any other error stops.
  5. Report: d2_train/d2_report.md. Pass = makes_right > 29 AND misses_called_makes == 0. One try.
Nothing in models/ is read or written; ball_confidence stays 0.28 (inside keep_ball_detections.py).
"""
import json
import os
import subprocess
import sys
import time

REPO = "C:/Users/scott/Documents/liberty-basketball-analysis"
VENV = REPO + "/.venv/Scripts/python.exe"
D1_SCRIPT = REPO + "/.team/shot_detectors/keep_ball_detections.py"
V6 = "C:/Users/scott/AppData/Local/Temp/ball_net_runs/v6/weights/best.pt"
TRACKS = "C:/Users/scott/AppData/Local/Temp"
D1_CANDIDATES = "C:/Users/scott/Documents/Liberty_Shot_Outputs/ball_arc/candidates.json"
OUT = "C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_train"
DATA = OUT + "/ds/data.yaml"
RUNS = OUT + "/runs"
NAME = "d2v1"
NEW = RUNS + "/" + NAME + "/weights/best.pt"
TEST = OUT + "/test"
D1_MAKES_RIGHT = 29
TRAIN_ARGS = dict(imgsz=640, batch=16, freeze=10, single_cls=True, device=0, seed=42, deterministic=True,
                  epochs=30, patience=10, workers=2, project=RUNS, name=NAME, exist_ok=False)
VAL_ARGS = dict(split="val", imgsz=640, batch=16, device=0)
GATE_TEXT = "MAPPING CHECK GATE FAILED"


def stop(msg):
    print("STOP for Scott: " + msg)
    raise SystemExit(msg)


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def venv(*args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    p = subprocess.run([VENV, D1_SCRIPT, *args], cwd=REPO, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    with open(TEST + "/venv_log.txt", "a", encoding="utf-8") as f:
        f.write("$ %s\n%s\n%s\nexit %d\n\n" % (" ".join(args), p.stdout, p.stderr, p.returncode))
    return p


def summary(results_json):
    s = json.load(open(results_json, encoding="utf-8"))["summary"]
    return s["makes_right"], s["misses_called_makes"]


def arc_report(candidates, tag):
    p = venv("--step", "arc-rule-report", "--candidates-json", candidates, "--tracks-dir", TRACKS,
             "--out-json", "%s/%s_results.json" % (TEST, tag), "--out-md", "%s/%s_report.md" % (TEST, tag))
    if p.returncode != 0:
        stop("arc-rule-report (%s) failed, exit %d; see %s/venv_log.txt" % (tag, p.returncode, TEST))
    return summary("%s/%s_results.json" % (TEST, tag))


def extract_ok(returncode, stdout, candidates_path):
    """Spec 23 section 4: the 0.90 mapping gate alone is not a stop if candidates.json was written."""
    if returncode == 0:
        return True
    return GATE_TEXT in stdout and os.path.exists(candidates_path)


def val(model_path):
    from ultralytics import YOLO
    m = YOLO(model_path).val(data=DATA, project=OUT + "/val", name=os.path.basename(os.path.dirname(os.path.dirname(model_path))) or "m", **VAL_ARGS)
    return {"precision": float(m.box.mp), "recall": float(m.box.mr), "mAP50": float(m.box.map50)}


def main():
    t0 = time.time()
    for p in (V6, DATA, D1_CANDIDATES, VENV):
        if not os.path.exists(p):
            stop("missing " + p)
    if os.path.exists(TEST) or os.path.exists(RUNS):
        stop("test or runs folder already exists; not overwriting")
    os.makedirs(TEST)

    log("step 0: D1 test path proof")
    s0 = arc_report(D1_CANDIDATES, "d1_repeat")
    if s0 != (D1_MAKES_RIGHT, 0):
        stop("step 0 gave %r, not (29, 0)" % (s0,))

    log("step 1: v6 val")
    v6_val = val(V6)
    log("v6 val %r" % v6_val)

    log("step 2: train")
    from ultralytics import YOLO
    t_train = time.time()
    YOLO(V6).train(data=DATA, **TRAIN_ARGS)
    t_train = time.time() - t_train
    if not os.path.exists(NEW):
        stop("training wrote no " + NEW)

    log("step 3: d2v1 val")
    new_val = val(NEW)
    log("d2v1 val %r" % new_val)

    log("step 4: D1 test, extract with d2v1 (CPU, repo venv)")
    cand = TEST + "/candidates.json"
    p = venv("--step", "extract", "--v6-weights", NEW, "--tracks-dir", TRACKS, "--out-json", cand)
    if not extract_ok(p.returncode, p.stdout, cand):
        stop("extract failed, exit %d; see %s/venv_log.txt" % (p.returncode, TEST))
    agree = json.load(open(cand, encoding="utf-8"))["mapping_check"]
    makes_right, misses_called = arc_report(cand, "d2")
    passed = makes_right > D1_MAKES_RIGHT and misses_called == 0

    rows = "\n".join("| %s | %.4f | %.4f |" % (k, v6_val[k], new_val[k]) for k in ("precision", "recall", "mAP50"))
    report = f"""# D2 train job report (spec 23 v2)

Result: **{"PASS" if passed else "FAIL"}** (pass = makes_right > 29 AND misses_called_makes == 0). One try; gate 3 is Scott's.

## Val split (same split, both models)

| Metric | v6 | d2v1 |
|---|---|---|
{rows}

## D1 test (only the weights changed)

| | D1 (v6) | D2 (d2v1) |
|---|---|---|
| makes_right | 29 | {makes_right} |
| misses_called_makes | 0 | {misses_called} |

- Step 0 (D1 candidates rerun on the repo venv): makes_right {s0[0]}, misses_called_makes {s0[1]}.
- Agreement with v6 ball points: {agree["hits"]}/{agree["total"]} = {agree["rate"]:.4f} (v6 itself: 3798/3800 = 0.9995).
- Extract exit code: {p.returncode}{" (mapping gate only, allowed by spec 23 section 4)" if p.returncode else ""}.

New weights: `{NEW}` (outside the repo; models/ unchanged; ball_confidence 0.28).
Wall time: training {t_train:.0f} s, total {time.time() - t0:.0f} s.
"""
    with open(OUT + "/d2_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    log(report)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
