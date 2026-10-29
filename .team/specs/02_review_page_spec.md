VETTED by Claude Code, 2026-10-26: Scott asked for a page to verify every make/miss call with a clip. Coder: OpenCode. Branch: team/auto. Data checked: run_saved_v6_rule returns results rows with 'tag_ts' (video ms), 'true', 'pred'; Notus tracks have 31 rows (t 55400..883400 ms).

# Task: make/miss review page

## Files
- `scripts/build_review_page.py` (new)
- `tests/test_build_review_page.py` (new)

Do not edit any other file. Do not change ai_bridge.py or any cutoff.

## What it builds
`C:\Users\scott\Documents\Liberty_Review\make_miss_review.html`: one self-contained HTML file (inline CSS and JS, no internet needed). Create the folder if missing. Print the output path. Optional flag `--open` opens it in the default browser.

Data, for each film:
- Notus A1 Q1: tracks `gemini-upload/notus_q1_v6_tracks.json`, video `uploads/LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4`.
- Adrian Q1–Q3: tracks `%TEMP%\v6_tracks.json`, falling back to `C:\Users\scott\Documents\liberty_offline_backup\temp_scoring\v6_tracks.json` (same lookup as scripts/team_score.py; import it from there rather than copying it). Video `uploads/nfhs_gam0a66d85e12.mp4`.
- Times: `times = [r["t"] for r in rows if r.get("hoop") and len(r["hoop"]) == 4]`, then `run_saved_v6_rule(times, path)` with stdout suppressed. Use `results` rows: `tag_ts` (video milliseconds), `pred` (AI make true/false), `true` (Scott's tag make true/false).

## Page
- Header: title "Make/Miss Review", build time, the score per film (right of total, makes missed, misses called makes), and git short hash plus branch.
- One row per shot, ordered by film then time:
  - film, a row id `<film>-<tag_ts>`, and the video time as m:ss.s.
  - the AI call as a big MAKE (green) or MISS (red) label.
  - `<video controls preload="none" src="file:///C:/Users/scott/Documents/liberty-basketball-analysis/uploads/<file>#t=<start>,<end>">` with start = max(0, tag_ts/1000 - 3) and end = tag_ts/1000 + 6, both in seconds with one decimal. Add a "Replay clip" button that seeks back to start and plays.
  - buttons "Correct" and "Incorrect", and a one-line note box.
  - Scott's original tag (MAKE/MISS), hidden until a page-level "Show my tags" checkbox is ticked.
- Filters at the top: All, Not reviewed, Marked incorrect, AI disagrees with my tag.
- Running count: reviewed X of N, correct, incorrect.
- Marks and notes save to localStorage on every change (key includes the build's git hash so a new build starts fresh; keep earlier builds' marks under their own keys).
- "Save my review" button downloads `make_miss_review_<yyyyMMdd_HHmm>.json`: `{"built": ..., "git": ..., "rows": [{"id", "film", "tag_ts", "ai_call", "scott_tag", "mark": "correct"|"incorrect"|null, "note"}]}`.
- Readable at laptop and phone width, with large tap targets.

## Tests (tests/test_build_review_page.py)
- Build the page for the Notus film only (expose a function that takes a list of films and an output path; write to tmp_path).
- Assert 31 shot rows; that each video src ends with a `#t=start,end` fragment where end - start == 9.0 (or less when start was clamped to 0); and that the AI MAKE count equals the number of `pred` true rows.
- Skip any Adrian part if its tracks are missing.

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_build_review_page.py tests/test_team_score.py -q`, then `.\.venv\Scripts\python.exe scripts/build_review_page.py` and report the path and the row counts. Do not commit; Claude vets first.
