# The count gate

Three numbers on the coach's shot tags, and nothing else:

| | |
|---|---|
| **right** | the tag and the program agree on make or miss |
| **makes missed** | the tag says make, the program did not store a make |
| **misses called makes** | the tag says miss, the program stored a make |

Every tag lands in exactly one bucket, so the three always add up to the tag count. The
recorded best on the Adrian film reads **85 + 20 + 6 = 111**. Calling every shot a miss on
the same answer key reads **73 + 38 + 0** — worth remembering, because three of the six
`Scott_Hermes` rules scored at or below that 73.

A tag is predicted **make** when a stored make sits within 8 seconds of it — the teach
pass's own `MATCH_TOLERANCE_MS` — and **miss** otherwise. A tag with no stored row at all
is predicted miss, not "unknown": the make/miss contract has no third value.

## Running it

```
python scripts/shot_tag_score.py --game-id "<analysis key>" --fixture adrian_111
```

Needs `film_analysis.db` and `data/film_tags/<game id>.json`, neither of which is in git.
Run it on the home laptop, or on a clone with the Shared drive folder
**Program data from home laptop 2026-10-11** copied over it. Exit status is 1 when the
score is below the floor in `baseline.json`.

## What does not count as the program's work

`shot_tag_gate.stored_makes` ignores three kinds of row, because none of them is the
program reading the film:

- **rejected** — a human threw it out;
- **manual** — the coach's own tag, which cannot grade itself;
- **corrected** — the teach pass rewrote it from a tag inside the 8 seconds, so the answer
  came from the answer key.

`--count-taught` includes corrected rows. That answers "what does the card say now", which
is a fair question and a different one. It cannot be used to claim a gate score, and
`--update-baseline` refuses to write a floor from it.

## The floor

`baseline.json` holds one entry per answer key. **Do not lower a floor to make a change
pass.** Raise it when a change beats it, in the same pull request, and say what moved.

`adrian_111` carries 85 / 20 / 6 from `HERMES.md` and `ACTIVE.md`. That score was measured
offline on the v6 tracks, which are not in git, so **nobody has reproduced it from this
repo alone.** The first person to run the scorer on the home laptop should say in the pull
request whether the database reproduces it, and correct the number if it does not. A floor
nobody has verified is still better than a floor nobody can run, but it is not a result.

A score on a different number of tags is refused rather than compared — scoring 40 of the
111 and printing "/111" is the failure this guards against.

## Where else these numbers appear

- `scripts/accuracy_benchmark.py` reports the same three on frozen detections, in CI, on
  every pull request. Floors in `benchmarks/accuracy/baseline.json`.
- `tests/test_shot_tag_gate.py` pins the arithmetic and the match rule. Its full-111 test
  skips where the data is absent and runs for real where it is not.
- `.github/workflows/guardrails.yml` blocks a pull request that changes how a shot is read
  without pasting a score line.
