# Accuracy benchmark

The benchmark scores the **event generator** against the coach's own tags on real film,
on every PR (issue #153). It needs no GPU, OpenCV/YOLO or LFS, so it runs in CI.

```
python scripts/accuracy_benchmark.py                  # print metrics; exit 1 on a regression
python scripts/accuracy_benchmark.py --update-baseline # accept new numbers (commit baseline.json)
```

- **Matching:** AI events are matched to tags by type (and make/miss for shots) within
  ±10 s, using the same matcher as `tag-exports/manual_vs_ai_q1_compare.py`.
- **Metrics:** precision = matched / AI events; recall = matched / tagged events.
- **The gate:** CI fails if precision, recall or F1 drops below `baseline.json`. A PR
  that improves accuracy raises the baseline in the same PR.

## Fixtures

| Fixture | Film | Truth | Detections |
|---|---|---|---|
| `wilder_q1/` | `videos/Q1.mp4`, Wilder varsity Q1 (906 s) | 71 coach tags, 53 of them stat events, in the 0:00–14:31 window | 226,631 from the real analyzer (yolo11n players, fine-tuned ball model, tracker on, OCR off) |

Each fixture has:

- **`truth.json`:** the coach's Film Tool tags. Player names and notes are removed;
  only type, result, time, quarter and side are kept.
- **`detections.csv.gz`:** frozen output of `ai_analyzer.run_ai_analysis` on the film.
- **`meta.json`:** video hash, analyzer commit and settings.

## Baseline (2026-09-30, commit 194e38b)

| Fixture | Precision | Recall | F1 | Matched |
|---|---:|---:|---:|---:|
| wilder_q1 | 8.8% | 24.5% | 13.0% | 13 / 53 |

The per-type table printed by the script shows where the errors are:

- **Free throws:** 23 missed FTs that did not happen (the largest false alarm).
- **Turnovers:** 50 AI turnovers against 6 real.
- **Fouls:** none detected.
- **3PT:** 0 of 7 threes matched.
- **Rebounds:** 6 of 8 found, the best category.

## When to rebuild detections

The frozen detections test the **event logic**: `event_generator`, `stat_rules`,
`court_memory` and so on. Changes to the **detector** need new detections:
YOLO models, `ball_confidence`, the tracker, or `ai_analyzer` itself. Rebuild them in
Docker, from real footage:

```
docker run --rm -v $PWD:/app -w /app -v <lfs dir>:/lfs:ro -v <out>:/out \
  -v <lfs dir>/ball_detector.pt:/app/models/ball_detector.pt:ro liberty-analysis:cpu \
  python scripts/bench/build_accuracy_fixture.py --video /lfs/Q1.mp4 --out /out --commit $(git rev-parse --short HEAD)
```

This takes about 50 minutes on CPU. Then copy `detections.csv.gz` and `meta.json` into the
fixture folder and re-run `--update-baseline` in the same PR, stating why the numbers moved.

**Adding a game:** Scott's Adrian Jr High Q1 tags (`tag-exports/jrhigh_adrian_q1_manual_tags.json`)
could be a second fixture. The film is on the home PC, so build it there.
