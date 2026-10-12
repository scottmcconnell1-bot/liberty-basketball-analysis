# adrian_q1 — waiting on frozen detections

`truth.json` is here: 134 of the coach's Q1 tags, **44 of them shot tags** (15 makes,
29 misses), window 961 s, which is the `lastTaggedTime` of 16:00.7 in the export. It was
built from a file that is in git, so it needs no laptop:

```
python scripts/bench/film_tags_to_truth.py \
    tag-exports/jrhigh_adrian_q1_manual_tags.json \
    --out benchmarks/accuracy/adrian_q1/truth.json \
    --film "uploads/nfhs_gam0a66d85e12.mp4 (Adrian Jr High vs Liberty A, video 73), Q1"
```

`detections.csv.gz` is **not** here, so the benchmark prints `WAITING: adrian_q1` and
scores nothing. The film is not in git. Build the detections where the film is — the home
laptop, or a clone with the Shared drive folder copied over it — exactly as
`benchmarks/accuracy/README.md` describes for `wilder_q1`:

```
docker run --rm -v $PWD:/app -w /app -v <lfs dir>:/lfs:ro -v <out>:/out \
  -v <lfs dir>/ball_detector.pt:/app/models/ball_detector.pt:ro liberty-analysis:cpu \
  python scripts/bench/build_accuracy_fixture.py \
      --video uploads/nfhs_gam0a66d85e12.mp4 --out /out --commit $(git rev-parse --short HEAD)
```

Then copy `detections.csv.gz` and `meta.json` into this folder, run
`python scripts/accuracy_benchmark.py --update-baseline`, and say in the pull request what
the first numbers were. Do not hand-write a baseline.

## Why this fixture is the one that matters

`wilder_q1` is a different gym, a different camera and a different team. The count that is
actually being argued about is the Adrian film, and every number in
`docs/agent_handoffs/plans/` comes from a database nobody can open in CI. Once this fixture
has detections, the make/miss gate runs against the Adrian film on every pull request, and
a change that quietly loses a made basket stops being something you have to take on trust.

Q1 only. The 111-tag answer key covers the whole film and stays a home-machine job —
`scripts/shot_tag_score.py`, floor in `benchmarks/shot_tags/baseline.json`.
