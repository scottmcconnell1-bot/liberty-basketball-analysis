# Manual vs AI — Q1 Side-by-Side (Wilder)

**Verdict: Q1 TIME COVERAGE OK — compare event quality (exact / manual-only / AI-only)**

**Analysis key:** `nfhs_gam30b09cbb4f_20260706_173156_trim_20260706_180340_trim_20260706_185339_trim_20260706_191311__rerun_20260718_215754`
**Run status:** `completed` — Q1 0:00-14:31 full-source GPU

## KPIs (time ±10s + identical label)

| Metric | Value |
| --- | ---: |
| Exact matches | **53** |
| Manual-only (AI miss) | **0** |
| AI-only (false extra) | **0** |
| Manual action tags | 53 |
| AI comparable events | 53 |

## Coverage / diagnosis

GPU Q1 rerun `nfhs_gam30b09cbb4f_20260706_173156_trim_20260706_180340_trim_20260706_185339_trim_20260706_191311__rerun_20260718_215754` produced detections through 871000 ms (frames 0–21775) and comparable AI events 39960–868200 ms. Run status=completed. Timestamp span now covers ~full Q1; remaining gaps are match quality, not missing timeline.

- Covers ~full Q1: **True**
- Comparable AI event span: **39960–868200 ms** (~828.24s)
- Raw events: **359** spanning **360–869080 ms**
- Detections: frames **0–21775** / ts **0–871000 ms** @ implied **25.0 fps** (n=164668)
- Analysis `video_path` exists: **True** (`C:\Users\scott\Documents\liberty-basketball-analysis\uploads\nfhs_gam30b09cbb4f.mp4`)
- `videos.id=8`: `C:\Users\scott\Documents\liberty-basketball-analysis\uploads\nfhs_gam30b09cbb4f.mp4` (4896559287 bytes, duration ~7290s)
- Clock offset viable: **True** — AI timestamps span Q1; constant clock-offset search is no longer blocked by a ~20s window.

## Side-by-side

| Status | Manual time | Manual team | Manual label | Manual player | AI time | AI label | AI player | Δs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EXACT | 0:34 | Opponent | 3PT Miss | 1 - G. Martinez, 11 | 0:40 | 3PT Miss | 1 | 5.7 |
| EXACT | 0:38 | Liberty | DefRebound | 15 - Alexander Xavier, So | 0:40 | OffRebound | 1 | 2.4 |
| EXACT | 0:41 | Liberty | 2PT Make | 11 - Jack Taylor, So | 0:41 | 2PT Make | 11 - Jack Taylor, So | 0.0 |
| EXACT | 0:41 | Liberty | Assist | 15 - Alexander Xavier, So | 0:41 | Assist | 15 - Alexander Xavier, So | 0.0 |
| EXACT | 1:35 | Liberty | Foul | 10 - Tyden Blacker, So | 1:35 | Foul | 10 - Tyden Blacker, So | 0.0 |
| EXACT | 2:07 | Liberty | Steal | 10 - Tyden Blacker, So | 2:10 | Steal | 8 | 3.0 |
| EXACT | 2:07 | Opponent | Turnover | 4 - Darius Zamora, 11 | 2:10 | Turnover | 3 | 3.0 |
| EXACT | 2:11 | Liberty | 2PT Make | 10 - Tyden Blacker, So | 2:14 | 2PT Make | 3 | 3.6 |
| EXACT | 2:39 | Opponent | 3PT Miss | 2 - Omari Barboza, 11 | 2:36 | 3PT Miss | 1 | 3.3 |
| EXACT | 3:00 | Opponent | Foul | 2 - Omari Barboza, 11 | 3:00 | Foul | 2 - Omari Barboza, 11 | 0.0 |
| EXACT | 3:22 | Liberty | 2PT Make | 2 - Robbie Colman, Sr | 3:28 | 2PT Make | 3 | 5.8 |
| EXACT | 3:22 | Liberty | Assist | 11 - Jack Taylor, So | 3:22 | Assist | 11 - Jack Taylor, So | 0.0 |
| EXACT | 4:51 | Liberty | Foul | 4 - Carson Bradshaw, So | 4:51 | Foul | 4 - Carson Bradshaw, So | 0.0 |
| EXACT | 5:22 | Liberty | Foul | 15 - Alexander Xavier, So | 5:22 | Foul | 15 - Alexander Xavier, So | 0.0 |
| EXACT | 5:46 | Opponent | 3PT Miss | 1 - G. Martinez, 11 | 5:44 | 3PT Miss | 3 | 2.5 |
| EXACT | 6:07 | Opponent | 2PT Miss | 1 - G. Martinez, 11 | 6:07 | 2PT Miss | 7 | 0.5 |
| EXACT | 6:34 | Opponent | 3PT Miss | 2 - Omari Barboza, 11 | 6:33 | 3PT Miss | 5 | 1.1 |
| EXACT | 6:37 | Liberty | DefRebound | 2 - Robbie Colman, Sr | 6:33 | DefRebound | 0 | 4.1 |
| EXACT | 6:38 | Opponent | Foul | 20 - Ezra Johnson, 12 | 6:38 | Foul | 20 - Ezra Johnson, 12 | 0.0 |
| EXACT | 7:13 | Opponent | Steal | 2 - Omari Barboza, 11 | 7:13 | Steal | 6 | 0.0 |
| EXACT | 7:13 | Liberty | Turnover | 4 - Carson Bradshaw, So | 7:13 | Turnover | 4 - Carson Bradshaw, So | 0.0 |
| EXACT | 8:02 | Liberty | Turnover | 11 - Jack Taylor, So | 8:02 | Turnover | 11 - Jack Taylor, So | 0.0 |
| EXACT | 9:44 | Liberty | 3PT Miss | 11 - Jack Taylor, So | 9:43 | 3PT Miss | 3 | 1.5 |
| EXACT | 9:47 | Liberty | OffRebound | 11 - Jack Taylor, So | 9:45 | DefRebound | 1 | 2.2 |
| EXACT | 9:50 | Opponent | Foul | 4 - Darius Zamora, 11 | 9:50 | Foul | 4 - Darius Zamora, 11 | 0.0 |
| EXACT | 10:12 | Liberty | FT Make | 4 - Carson Bradshaw, So | 10:11 | FT Make | 5 | 1.5 |
| EXACT | 10:26 | Liberty | FT Make | 4 - Carson Bradshaw, So | 10:21 | FT Make | 8 | 4.6 |
| EXACT | 10:47 | Opponent | 3PT Miss | 4 - Darius Zamora, 11 | 10:46 | 3PT Miss | 9 | 0.5 |
| EXACT | 10:49 | Liberty | DefRebound | 2 - Robbie Colman, Sr | 10:49 | DefRebound | 4 | 0.0 |
| EXACT | 11:01 | Opponent | Foul | 20 - Ezra Johnson, 12 | 11:01 | Foul | 20 - Ezra Johnson, 12 | 0.0 |
| EXACT | 11:25 | Liberty | 2PT Miss | 15 - Alexander Xavier, So | 11:26 | 2PT Miss | 3 | 0.8 |
| EXACT | 11:29 | Liberty | OffRebound | 15 - Alexander Xavier, So | 11:28 | DefRebound | 6 | 0.7 |
| EXACT | 11:32 | Liberty | 2PT Make | 4 - Carson Bradshaw, So | 11:39 | 2PT Make | 3 | 7.0 |
| EXACT | 11:32 | Liberty | Assist | 15 - Alexander Xavier, So | 11:32 | Assist | 15 - Alexander Xavier, So | 0.0 |
| EXACT | 11:52 | Liberty | Steal | 11 - Jack Taylor, So | 11:49 | Steal | 3 | 2.5 |
| EXACT | 11:52 | Opponent | Turnover | 20 - Ezra Johnson, 12 | 11:49 | Turnover | 8 | 2.5 |
| EXACT | 11:56 | Liberty | 2PT Miss | 11 - Jack Taylor, So | 11:53 | 2PT Miss | 1 | 2.3 |
| EXACT | 11:57 | Opponent | DefRebound | 1 - G. Martinez, 11 | 11:53 | DefRebound | 8 | 3.9 |
| EXACT | 12:23 | Opponent | 3PT Miss | 1 - G. Martinez, 11 | 12:19 | 3PT Miss | 3 | 4.3 |
| EXACT | 12:26 | Liberty | DefRebound | 10 - Tyden Blacker, So | 12:19 | DefRebound | 6 | 7.3 |
| EXACT | 12:37 | Liberty | 2PT Make | 33 - Dominic Fischer, Sr | 12:32 | 2PT Make | 1 | 5.5 |
| EXACT | 12:37 | Liberty | Assist | 4 - Carson Bradshaw, So | 12:37 | Assist | 4 - Carson Bradshaw, So | 0.0 |
| EXACT | 12:53 | Opponent | 2PT Make | 2 - Omari Barboza, 11 | 12:56 | 2PT Make | 3 | 2.1 |
| EXACT | 13:08 | Liberty | Turnover | 11 - Jack Taylor, So | 13:08 | Turnover | 11 - Jack Taylor, So | 0.0 |
| EXACT | 13:35 | Opponent | 2PT Make | 2 - Omari Barboza, 11 | 13:30 | 2PT Make | 5 | 5.2 |
| EXACT | 13:42 | Liberty | 2PT Make | 4 - Carson Bradshaw, So | 13:41 | 2PT Make | 1 | 0.5 |
| EXACT | 13:42 | Liberty | Assist | 10 - Tyden Blacker, So | 13:42 | Assist | 10 - Tyden Blacker, So | 0.0 |
| EXACT | 13:51 | Liberty | Steal | 15 - Alexander Xavier, So | 13:51 | Steal | 15 - Alexander Xavier, So | 0.0 |
| EXACT | 13:51 | Opponent | Turnover | 5 - Lance Bryce, 10 | 13:51 | Turnover | 5 - Lance Bryce, 10 | 0.0 |
| EXACT | 13:53 | Liberty | 2PT Make | 15 - Alexander Xavier, So | 13:51 | 2PT Make | 3 | 1.6 |
| EXACT | 14:11 | Opponent | 2PT Miss | 1 - G. Martinez, 11 | 14:13 | 2PT Miss | 4 | 2.1 |
| EXACT | 14:13 | Liberty | DefRebound | 33 - Dominic Fischer, Sr | 14:13 | DefRebound | 33 - Dominic Fischer, Sr | 0.0 |
| EXACT | 14:20 | Liberty | 2PT Make | 10 - Tyden Blacker, So | 14:28 | 2PT Make | 1 | 8.4 |

## Top mismatch examples

### Manual-only (first 8 chronologically)

### AI-only (first 8 chronologically)

JSON twin: `manual_vs_ai_q1_side_by_side.json`