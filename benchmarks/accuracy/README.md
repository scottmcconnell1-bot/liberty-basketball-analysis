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
- **Shot tags:** right / makes missed / misses called makes, on the shot tags only, at the
  teach pass's own ±8 s. This is the count gate — see `benchmarks/shot_tags/README.md`.
  Precision and recall can hold steady while made baskets go missing; these three notice.
- **The gate:** CI fails if precision, recall or F1 drops below `baseline.json`, if `right`
  falls, or if either error count rises. A PR that improves accuracy raises the baseline in
  the same PR. A baseline with no `shots` floor is treated as incomplete, so a fixture
  cannot quietly lose the make/miss gate.

## Fixtures

| Fixture | Film | Truth | Detections |
|---|---|---|---|
| `wilder_q1/` | `videos/Q1.mp4`, Wilder varsity Q1 (906 s) | 71 coach tags, 53 of them stat events, in the 0:00–14:31 window | 226,631 from the real analyzer (yolo11n players, fine-tuned ball model, tracker on, OCR off) |

Each fixture has:

- **`truth.json`:** the coach's Film Tool tags. Player names and notes are removed;
  only type, result, time, quarter and side are kept.
- **`detections.csv.gz`:** frozen output of `ai_analyzer.run_ai_analysis` on the film.
- **`meta.json`:** video hash, analyzer commit and settings.

## Baseline (2026-10-11)

| Fixture | Precision | Recall | F1 | Matched | Shot tags: right / missed / false makes |
|---|---:|---:|---:|---:|---|
| wilder_q1 | 9.9% | 26.4% | 14.4% | — | 23 tags: 12 / 8 / 3 |

Raised from 8.8% / 24.5% / 13.0% (2026-09-30, commit 194e38b). The code had already got
better than the committed floor and nobody had raised it, so the gate was loose.

**The generator is not reproducible run to run, and it lands in one of two modes.** The
same commit on the same frozen detections gives one of these, correlated with the
possession count:

| Possession segments | Precision / recall / F1 | AI events | Shot tags: right / makes missed / misses called makes |
|---:|---|---:|---|
| 1,269 | 10.1 / 28.3 / 14.9 | 163 | 12 / 8 / 3 |
| 1,271 | 9.9 / 26.4 / 14.4 | 157 | 13 / 8 / 2 |

Observed across six runs: 1,269 on a local 3.14, on CI 3.13 twice and on CI 3.12 once;
1,271 on CI 3.13 once and on CI 3.12 once. **It is not a Python version difference and not
a local-versus-CI difference** -- both interpreters have produced both modes. Player
clustering falls out differently between runs, two segments out of 1,269 move, and
everything downstream shifts with them.

Note that the two metric families move in **opposite** directions between the modes: the
1,271 mode scores nearly two points worse on recall while scoring *better* on the shot tags
(one more right, one less false make), because it emits six fewer AI events. Reading either
family alone would tell you the run got better, or worse, when what actually happened is
that the clustering landed somewhere else.

**So every floor here is a low-water mark over observed runs, not a target.** The committed
floor passes in both modes, deliberately: `right` may not fall, the two error counts may not
rise, and the floats sit at the lower mode. A score above the floor is not an improvement,
and a fresh low is not necessarily a regression -- re-run before concluding anything, and
lower a floor only with the evidence in the pull request.

The proper fix is to seed the clustering so a fixture scores the same twice. That is a
change to the generator, so it is a Scott gate, and it is not this benchmark's job. Until
then, treat a single run as one sample.

On this answer key, calling every shot a miss would score **11 right**. The generator
scores 12. That is the honest size of the make/miss signal here, and the reason the Adrian
fixture matters more than this one.

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

**Adding a game:** done for the truth half — `adrian_q1/` now holds Scott's Adrian Jr High
Q1 tags as `truth.json` (134 tags, 44 of them shot tags), generated by
`scripts/bench/film_tags_to_truth.py` from a file that is in git. It has no
`detections.csv.gz`, so the benchmark prints `WAITING: adrian_q1` and scores nothing. The
film is not in git; build the detections on the home laptop or on a clone with the Shared
drive folder copied over it. See `adrian_q1/README.md`.

Until that lands, the make/miss gate in CI runs on Wilder — a different gym, camera and
team. Useful, and not the Adrian count.
