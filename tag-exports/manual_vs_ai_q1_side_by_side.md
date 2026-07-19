# Manual vs AI — Q1 Side-by-Side (Wilder)

**Verdict: Q1 TIME COVERAGE OK — compare event quality (exact / manual-only / AI-only)**

**Analysis key:** `nfhs_gam30b09cbb4f_20260706_173156_trim_20260706_180340_trim_20260706_185339_trim_20260706_191311__rerun_20260718_215754`
**Run status:** `completed` — Q1 0:00-14:31 full-source GPU

## KPIs (time ±8s + identical label)

| Metric | Value |
| --- | ---: |
| Exact matches | **20** |
| Manual-only (AI miss) | **33** |
| AI-only (false extra) | **225** |
| Manual action tags | 53 |
| AI comparable events | 245 |

## Coverage / diagnosis

GPU Q1 rerun `nfhs_gam30b09cbb4f_20260706_173156_trim_20260706_180340_trim_20260706_185339_trim_20260706_191311__rerun_20260718_215754` produced detections through 871000 ms (frames 0–21775) and comparable AI events 320–868320 ms. Run status=completed. Timestamp span now covers ~full Q1; remaining gaps are match quality, not missing timeline.

- Covers ~full Q1: **True**
- Comparable AI event span: **320–868320 ms** (~868.0s)
- Raw events: **599** spanning **320–869080 ms**
- Detections: frames **0–21775** / ts **0–871000 ms** @ implied **25.0 fps** (n=164668)
- Analysis `video_path` exists: **True** (`C:\Users\scott\Documents\liberty-basketball-analysis\uploads\nfhs_gam30b09cbb4f.mp4`)
- `videos.id=8`: `C:\Users\scott\Documents\liberty-basketball-analysis\uploads\nfhs_gam30b09cbb4f.mp4` (4896559287 bytes, duration ~7290s)
- Clock offset viable: **True** — AI timestamps span Q1; constant clock-offset search is no longer blocked by a ~20s window.

## Side-by-side

| Status | Manual time | Manual team | Manual label | Manual player | AI time | AI label | AI player | Δs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MANUAL_ONLY | 0:34 | Opponent | 3PT Miss | 1 - G. Martinez, 11 | — | — | — | — |
| EXACT | 0:38 | Liberty | DefRebound | 15 - Alexander Xavier, So | 0:40 | DefRebound | 1 | 2.4 |
| MANUAL_ONLY | 0:41 | Liberty | 2PT Make | 11 - Jack Taylor, So | — | — | — | — |
| MANUAL_ONLY | 0:41 | Liberty | Assist | 15 - Alexander Xavier, So | — | — | — | — |
| MANUAL_ONLY | 1:35 | Liberty | Foul | 10 - Tyden Blacker, So | — | — | — | — |
| EXACT | 2:07 | Liberty | Steal | 10 - Tyden Blacker, So | 2:10 | Steal | 8 | 3.0 |
| EXACT | 2:07 | Opponent | Turnover | 4 - Darius Zamora, 11 | 2:10 | Turnover | 3 | 3.0 |
| EXACT | 2:11 | Liberty | 2PT Make | 10 - Tyden Blacker, So | 2:04 | 2PT Make | 8 | 7.0 |
| MANUAL_ONLY | 2:39 | Opponent | 3PT Miss | 2 - Omari Barboza, 11 | — | — | — | — |
| MANUAL_ONLY | 3:00 | Opponent | Foul | 2 - Omari Barboza, 11 | — | — | — | — |
| MANUAL_ONLY | 3:22 | Liberty | 2PT Make | 2 - Robbie Colman, Sr | — | — | — | — |
| MANUAL_ONLY | 3:22 | Liberty | Assist | 11 - Jack Taylor, So | — | — | — | — |
| MANUAL_ONLY | 4:51 | Liberty | Foul | 4 - Carson Bradshaw, So | — | — | — | — |
| MANUAL_ONLY | 5:22 | Liberty | Foul | 15 - Alexander Xavier, So | — | — | — | — |
| MANUAL_ONLY | 5:46 | Opponent | 3PT Miss | 1 - G. Martinez, 11 | — | — | — | — |
| EXACT | 6:07 | Opponent | 2PT Miss | 1 - G. Martinez, 11 | 6:07 | 2PT Miss | 7 | 0.5 |
| MANUAL_ONLY | 6:34 | Opponent | 3PT Miss | 2 - Omari Barboza, 11 | — | — | — | — |
| EXACT | 6:37 | Liberty | DefRebound | 2 - Robbie Colman, Sr | 6:33 | DefRebound | 0 | 4.1 |
| MANUAL_ONLY | 6:38 | Opponent | Foul | 20 - Ezra Johnson, 12 | — | — | — | — |
| EXACT | 7:13 | Opponent | Steal | 2 - Omari Barboza, 11 | 7:13 | Steal | 6 | 0.0 |
| EXACT | 7:13 | Liberty | Turnover | 4 - Carson Bradshaw, So | 7:13 | Turnover | 4 | 0.0 |
| MANUAL_ONLY | 8:02 | Liberty | Turnover | 11 - Jack Taylor, So | — | — | — | — |
| MANUAL_ONLY | 9:44 | Liberty | 3PT Miss | 11 - Jack Taylor, So | — | — | — | — |
| MANUAL_ONLY | 9:47 | Liberty | OffRebound | 11 - Jack Taylor, So | — | — | — | — |
| MANUAL_ONLY | 9:50 | Opponent | Foul | 4 - Darius Zamora, 11 | — | — | — | — |
| MANUAL_ONLY | 10:12 | Liberty | FT Make | 4 - Carson Bradshaw, So | — | — | — | — |
| MANUAL_ONLY | 10:26 | Liberty | FT Make | 4 - Carson Bradshaw, So | — | — | — | — |
| MANUAL_ONLY | 10:47 | Opponent | 3PT Miss | 4 - Darius Zamora, 11 | — | — | — | — |
| EXACT | 10:49 | Liberty | DefRebound | 2 - Robbie Colman, Sr | 10:49 | DefRebound | 4 | 0.0 |
| MANUAL_ONLY | 11:01 | Opponent | Foul | 20 - Ezra Johnson, 12 | — | — | — | — |
| EXACT | 11:25 | Liberty | 2PT Miss | 15 - Alexander Xavier, So | 11:26 | 2PT Miss | 3 | 0.8 |
| MANUAL_ONLY | 11:29 | Liberty | OffRebound | 15 - Alexander Xavier, So | — | — | — | — |
| EXACT | 11:32 | Liberty | 2PT Make | 4 - Carson Bradshaw, So | 11:39 | 2PT Make | 3 | 7.0 |
| MANUAL_ONLY | 11:32 | Liberty | Assist | 15 - Alexander Xavier, So | — | — | — | — |
| EXACT | 11:52 | Liberty | Steal | 11 - Jack Taylor, So | 11:49 | Steal | 3 | 2.5 |
| EXACT | 11:52 | Opponent | Turnover | 20 - Ezra Johnson, 12 | 11:49 | Turnover | 8 | 2.5 |
| EXACT | 11:56 | Liberty | 2PT Miss | 11 - Jack Taylor, So | 11:53 | 2PT Miss | 1 | 2.3 |
| EXACT | 11:57 | Opponent | DefRebound | 1 - G. Martinez, 11 | 11:53 | DefRebound | 8 | 3.9 |
| MANUAL_ONLY | 12:23 | Opponent | 3PT Miss | 1 - G. Martinez, 11 | — | — | — | — |
| EXACT | 12:26 | Liberty | DefRebound | 10 - Tyden Blacker, So | 12:33 | DefRebound | 3 | 7.3 |
| MANUAL_ONLY | 12:37 | Liberty | 2PT Make | 33 - Dominic Fischer, Sr | — | — | — | — |
| MANUAL_ONLY | 12:37 | Liberty | Assist | 4 - Carson Bradshaw, So | — | — | — | — |
| MANUAL_ONLY | 12:53 | Opponent | 2PT Make | 2 - Omari Barboza, 11 | — | — | — | — |
| EXACT | 13:08 | Liberty | Turnover | 11 - Jack Taylor, So | 13:04 | Turnover | 2 | 4.7 |
| EXACT | 13:35 | Opponent | 2PT Make | 2 - Omari Barboza, 11 | 13:30 | 2PT Make | 5 | 5.2 |
| MANUAL_ONLY | 13:42 | Liberty | 2PT Make | 4 - Carson Bradshaw, So | — | — | — | — |
| MANUAL_ONLY | 13:42 | Liberty | Assist | 10 - Tyden Blacker, So | — | — | — | — |
| MANUAL_ONLY | 13:51 | Liberty | Steal | 15 - Alexander Xavier, So | — | — | — | — |
| MANUAL_ONLY | 13:51 | Opponent | Turnover | 5 - Lance Bryce, 10 | — | — | — | — |
| MANUAL_ONLY | 13:53 | Liberty | 2PT Make | 15 - Alexander Xavier, So | — | — | — | — |
| EXACT | 14:11 | Opponent | 2PT Miss | 1 - G. Martinez, 11 | 14:13 | 2PT Miss | 4 | 2.1 |
| EXACT | 14:13 | Liberty | DefRebound | 33 - Dominic Fischer, Sr | 14:15 | DefRebound | 8 | 1.3 |
| MANUAL_ONLY | 14:20 | Liberty | 2PT Make | 10 - Tyden Blacker, So | — | — | — | — |
| AI_ONLY | — | — | — | — | 0:00 | 2PT Miss | 7 | — |
| AI_ONLY | — | — | — | — | 0:00 | DefRebound | 8 | — |
| AI_ONLY | — | — | — | — | 0:01 | Steal | 7 | — |
| AI_ONLY | — | — | — | — | 0:01 | Turnover | 8 | — |
| AI_ONLY | — | — | — | — | 0:13 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 0:15 | DefRebound | 2 | — |
| AI_ONLY | — | — | — | — | 0:16 | Steal | 8 | — |
| AI_ONLY | — | — | — | — | 0:16 | Turnover | 2 | — |
| AI_ONLY | — | — | — | — | 0:23 | 2PT Miss | 7 | — |
| AI_ONLY | — | — | — | — | 0:26 | DefRebound | 8 | — |
| AI_ONLY | — | — | — | — | 0:35 | Steal | 3 | — |
| AI_ONLY | — | — | — | — | 0:35 | Turnover | 8 | — |
| AI_ONLY | — | — | — | — | 0:40 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 0:57 | 2PT Make | 3 | — |
| AI_ONLY | — | — | — | — | 0:57 | Assist | 8 | — |
| AI_ONLY | — | — | — | — | 1:00 | Steal | 3 | — |
| AI_ONLY | — | — | — | — | 1:00 | Turnover | 7 | — |
| AI_ONLY | — | — | — | — | 1:09 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 1:10 | DefRebound | 3 | — |
| AI_ONLY | — | — | — | — | 1:19 | Steal | 8 | — |
| AI_ONLY | — | — | — | — | 1:19 | Turnover | 9 | — |
| AI_ONLY | — | — | — | — | 1:20 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 1:20 | DefRebound | 9 | — |
| AI_ONLY | — | — | — | — | 1:23 | DefRebound | 9 | — |
| AI_ONLY | — | — | — | — | 1:32 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 1:33 | DefRebound | 3 | — |
| AI_ONLY | — | — | — | — | 1:33 | Steal | 1 | — |
| AI_ONLY | — | — | — | — | 1:33 | Turnover | 3 | — |
| AI_ONLY | — | — | — | — | 1:50 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 1:50 | DefRebound | 5 | — |
| AI_ONLY | — | — | — | — | 1:53 | Steal | 9 | — |
| AI_ONLY | — | — | — | — | 1:53 | Turnover | 8 | — |
| AI_ONLY | — | — | — | — | 1:54 | DefRebound | 3 | — |
| AI_ONLY | — | — | — | — | 2:14 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 2:16 | DefRebound | 6 | — |
| AI_ONLY | — | — | — | — | 2:24 | Steal | 8 | — |
| AI_ONLY | — | — | — | — | 2:24 | Turnover | 4 | — |
| AI_ONLY | — | — | — | — | 2:25 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 2:27 | DefRebound | 4 | — |
| AI_ONLY | — | — | — | — | 2:34 | Steal | 1 | — |
| AI_ONLY | — | — | — | — | 2:34 | Turnover | 8 | — |
| AI_ONLY | — | — | — | — | 2:36 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 2:42 | Steal | 3 | — |
| AI_ONLY | — | — | — | — | 2:42 | Turnover | 1 | — |
| AI_ONLY | — | — | — | — | 2:49 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 2:52 | DefRebound | 8 | — |
| AI_ONLY | — | — | — | — | 2:54 | Steal | 8 | — |
| AI_ONLY | — | — | — | — | 2:54 | Turnover | 3 | — |
| AI_ONLY | — | — | — | — | 3:02 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 3:05 | DefRebound | 8 | — |
| AI_ONLY | — | — | — | — | 3:09 | Steal | 4 | — |
| AI_ONLY | — | — | — | — | 3:09 | Turnover | 8 | — |
| AI_ONLY | — | — | — | — | 3:14 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 3:18 | DefRebound | 3 | — |
| AI_ONLY | — | — | — | — | 3:20 | Steal | 8 | — |
| AI_ONLY | — | — | — | — | 3:20 | Turnover | 3 | — |
| AI_ONLY | — | — | — | — | 3:28 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 3:28 | DefRebound | 8 | — |
| AI_ONLY | — | — | — | — | 3:32 | Steal | 8 | — |
| AI_ONLY | — | — | — | — | 3:32 | Turnover | 9 | — |
| AI_ONLY | — | — | — | — | 3:40 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 3:43 | DefRebound | 8 | — |
| AI_ONLY | — | — | — | — | 3:45 | Steal | 8 | — |
| AI_ONLY | — | — | — | — | 3:45 | Turnover | 3 | — |
| AI_ONLY | — | — | — | — | 3:56 | 2PT Miss | 7 | — |
| AI_ONLY | — | — | — | — | 3:56 | DefRebound | 8 | — |
| AI_ONLY | — | — | — | — | 4:06 | Steal | 8 | — |
| AI_ONLY | — | — | — | — | 4:06 | Turnover | 3 | — |
| AI_ONLY | — | — | — | — | 4:08 | 2PT Miss | 0 | — |
| AI_ONLY | — | — | — | — | 4:09 | DefRebound | 1 | — |
| AI_ONLY | — | — | — | — | 4:18 | 2PT Miss | 4 | — |
| AI_ONLY | — | — | — | — | 4:19 | DefRebound | 4 | — |
| AI_ONLY | — | — | — | — | 4:22 | DefRebound | 4 | — |
| AI_ONLY | — | — | — | — | 4:26 | Steal | 3 | — |
| AI_ONLY | — | — | — | — | 4:26 | Turnover | 8 | — |
| AI_ONLY | — | — | — | — | 4:29 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 4:34 | DefRebound | 4 | — |
| AI_ONLY | — | — | — | — | 4:36 | Steal | 8 | — |
| AI_ONLY | — | — | — | — | 4:36 | Turnover | 1 | — |
| AI_ONLY | — | — | — | — | 4:41 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 4:41 | DefRebound | 3 | — |
| AI_ONLY | — | — | — | — | 4:45 | DefRebound | 1 | — |
| AI_ONLY | — | — | — | — | 4:53 | 2PT Make | 4 | — |
| AI_ONLY | — | — | — | — | 5:10 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 5:10 | DefRebound | 0 | — |
| AI_ONLY | — | — | — | — | 5:11 | Steal | 9 | — |
| AI_ONLY | — | — | — | — | 5:11 | Turnover | 0 | — |
| AI_ONLY | — | — | — | — | 5:21 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 5:23 | DefRebound | 6 | — |
| AI_ONLY | — | — | — | — | 5:29 | Steal | 5 | — |
| AI_ONLY | — | — | — | — | 5:29 | Turnover | 2 | — |
| AI_ONLY | — | — | — | — | 5:33 | 2PT Miss | 4 | — |
| AI_ONLY | — | — | — | — | 5:33 | DefRebound | 9 | — |
| AI_ONLY | — | — | — | — | 5:37 | DefRebound | 0 | — |
| AI_ONLY | — | — | — | — | 5:44 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 5:44 | Steal | 3 | — |
| AI_ONLY | — | — | — | — | 5:44 | Turnover | 8 | — |
| AI_ONLY | — | — | — | — | 5:45 | DefRebound | 8 | — |
| AI_ONLY | — | — | — | — | 5:56 | 2PT Miss | 4 | — |
| AI_ONLY | — | — | — | — | 5:57 | DefRebound | 9 | — |
| AI_ONLY | — | — | — | — | 6:05 | Steal | 7 | — |
| AI_ONLY | — | — | — | — | 6:05 | Turnover | 6 | — |
| AI_ONLY | — | — | — | — | 6:07 | DefRebound | 0 | — |
| AI_ONLY | — | — | — | — | 6:11 | DefRebound | 6 | — |
| AI_ONLY | — | — | — | — | 6:20 | 2PT Miss | 5 | — |
| AI_ONLY | — | — | — | — | 6:33 | 2PT Miss | 5 | — |
| AI_ONLY | — | — | — | — | 6:40 | Steal | 7 | — |
| AI_ONLY | — | — | — | — | 6:40 | Turnover | 2 | — |
| AI_ONLY | — | — | — | — | 6:44 | 2PT Make | 6 | — |
| AI_ONLY | — | — | — | — | 6:44 | Assist | 5 | — |
| AI_ONLY | — | — | — | — | 6:49 | Steal | 6 | — |
| AI_ONLY | — | — | — | — | 6:49 | Turnover | 9 | — |
| AI_ONLY | — | — | — | — | 6:57 | 2PT Miss | 0 | — |
| AI_ONLY | — | — | — | — | 7:00 | DefRebound | 7 | — |
| AI_ONLY | — | — | — | — | 7:00 | Steal | 3 | — |
| AI_ONLY | — | — | — | — | 7:00 | Turnover | 7 | — |
| AI_ONLY | — | — | — | — | 7:09 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 7:11 | DefRebound | 2 | — |
| AI_ONLY | — | — | — | — | 7:22 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 7:24 | DefRebound | 8 | — |
| AI_ONLY | — | — | — | — | 7:30 | Steal | 6 | — |
| AI_ONLY | — | — | — | — | 7:30 | Turnover | 9 | — |
| AI_ONLY | — | — | — | — | 7:33 | 2PT Miss | 9 | — |
| AI_ONLY | — | — | — | — | 7:37 | DefRebound | 7 | — |
| AI_ONLY | — | — | — | — | 7:44 | 2PT Miss | 6 | — |
| AI_ONLY | — | — | — | — | 7:44 | DefRebound | 5 | — |
| AI_ONLY | — | — | — | — | 7:48 | DefRebound | 0 | — |
| AI_ONLY | — | — | — | — | 7:53 | Steal | 2 | — |
| AI_ONLY | — | — | — | — | 7:53 | Turnover | 5 | — |
| AI_ONLY | — | — | — | — | 7:56 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 8:10 | 2PT Miss | 7 | — |
| AI_ONLY | — | — | — | — | 8:10 | DefRebound | 0 | — |
| AI_ONLY | — | — | — | — | 8:14 | DefRebound | 0 | — |
| AI_ONLY | — | — | — | — | 8:20 | 2PT Miss | 0 | — |
| AI_ONLY | — | — | — | — | 8:20 | Steal | 0 | — |
| AI_ONLY | — | — | — | — | 8:20 | Turnover | 4 | — |
| AI_ONLY | — | — | — | — | 8:22 | DefRebound | 8 | — |
| AI_ONLY | — | — | — | — | 8:33 | 2PT Miss | 2 | — |
| AI_ONLY | — | — | — | — | 8:33 | DefRebound | 7 | — |
| AI_ONLY | — | — | — | — | 8:35 | Steal | 6 | — |
| AI_ONLY | — | — | — | — | 8:35 | Turnover | 9 | — |
| AI_ONLY | — | — | — | — | 8:46 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 8:46 | DefRebound | 0 | — |
| AI_ONLY | — | — | — | — | 8:50 | DefRebound | 0 | — |
| AI_ONLY | — | — | — | — | 8:58 | 2PT Miss | 5 | — |
| AI_ONLY | — | — | — | — | 8:58 | DefRebound | 0 | — |
| AI_ONLY | — | — | — | — | 9:02 | DefRebound | 3 | — |
| AI_ONLY | — | — | — | — | 9:03 | Steal | 3 | — |
| AI_ONLY | — | — | — | — | 9:03 | Turnover | 0 | — |
| AI_ONLY | — | — | — | — | 9:09 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 9:09 | DefRebound | 3 | — |
| AI_ONLY | — | — | — | — | 9:13 | DefRebound | 4 | — |
| AI_ONLY | — | — | — | — | 9:21 | 2PT Miss | 4 | — |
| AI_ONLY | — | — | — | — | 9:24 | DefRebound | 3 | — |
| AI_ONLY | — | — | — | — | 9:31 | 2PT Miss | 2 | — |
| AI_ONLY | — | — | — | — | 9:31 | DefRebound | 6 | — |
| AI_ONLY | — | — | — | — | 9:35 | DefRebound | 9 | — |
| AI_ONLY | — | — | — | — | 9:36 | Steal | 2 | — |
| AI_ONLY | — | — | — | — | 9:36 | Turnover | 7 | — |
| AI_ONLY | — | — | — | — | 9:43 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 9:45 | DefRebound | 1 | — |
| AI_ONLY | — | — | — | — | 9:48 | Steal | 8 | — |
| AI_ONLY | — | — | — | — | 9:48 | Turnover | 3 | — |
| AI_ONLY | — | — | — | — | 10:00 | 2PT Miss | 0 | — |
| AI_ONLY | — | — | — | — | 10:00 | DefRebound | 0 | — |
| AI_ONLY | — | — | — | — | 10:02 | Steal | 6 | — |
| AI_ONLY | — | — | — | — | 10:02 | Turnover | 2 | — |
| AI_ONLY | — | — | — | — | 10:03 | DefRebound | 4 | — |
| AI_ONLY | — | — | — | — | 10:11 | 2PT Make | 5 | — |
| AI_ONLY | — | — | — | — | 10:13 | Steal | 3 | — |
| AI_ONLY | — | — | — | — | 10:13 | Turnover | 8 | — |
| AI_ONLY | — | — | — | — | 10:21 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 10:22 | DefRebound | 8 | — |
| AI_ONLY | — | — | — | — | 10:22 | Steal | 3 | — |
| AI_ONLY | — | — | — | — | 10:22 | Turnover | 8 | — |
| AI_ONLY | — | — | — | — | 10:33 | 2PT Miss | 9 | — |
| AI_ONLY | — | — | — | — | 10:34 | DefRebound | 0 | — |
| AI_ONLY | — | — | — | — | 10:35 | Steal | 8 | — |
| AI_ONLY | — | — | — | — | 10:35 | Turnover | 3 | — |
| AI_ONLY | — | — | — | — | 10:46 | 2PT Miss | 9 | — |
| AI_ONLY | — | — | — | — | 10:50 | Steal | 2 | — |
| AI_ONLY | — | — | — | — | 10:50 | Turnover | 6 | — |
| AI_ONLY | — | — | — | — | 10:58 | 2PT Miss | 4 | — |
| AI_ONLY | — | — | — | — | 10:58 | DefRebound | 6 | — |
| AI_ONLY | — | — | — | — | 11:02 | DefRebound | 4 | — |
| AI_ONLY | — | — | — | — | 11:02 | Steal | 0 | — |
| AI_ONLY | — | — | — | — | 11:02 | Turnover | 4 | — |
| AI_ONLY | — | — | — | — | 11:13 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 11:13 | DefRebound | 2 | — |
| AI_ONLY | — | — | — | — | 11:24 | Steal | 3 | — |
| AI_ONLY | — | — | — | — | 11:24 | Turnover | 4 | — |
| AI_ONLY | — | — | — | — | 11:27 | DefRebound | 3 | — |
| AI_ONLY | — | — | — | — | 12:01 | Steal | 8 | — |
| AI_ONLY | — | — | — | — | 12:01 | Turnover | 3 | — |
| AI_ONLY | — | — | — | — | 12:05 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 12:08 | DefRebound | 4 | — |
| AI_ONLY | — | — | — | — | 12:19 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 12:19 | DefRebound | 6 | — |
| AI_ONLY | — | — | — | — | 12:23 | Steal | 0 | — |
| AI_ONLY | — | — | — | — | 12:23 | Turnover | 6 | — |
| AI_ONLY | — | — | — | — | 12:32 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 12:44 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 12:48 | DefRebound | 6 | — |
| AI_ONLY | — | — | — | — | 12:55 | Steal | 8 | — |
| AI_ONLY | — | — | — | — | 12:55 | Turnover | 0 | — |
| AI_ONLY | — | — | — | — | 12:56 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 12:56 | DefRebound | 8 | — |
| AI_ONLY | — | — | — | — | 13:00 | DefRebound | 3 | — |
| AI_ONLY | — | — | — | — | 13:04 | Steal | 7 | — |
| AI_ONLY | — | — | — | — | 13:06 | 2PT Miss | 0 | — |
| AI_ONLY | — | — | — | — | 13:10 | DefRebound | 3 | — |
| AI_ONLY | — | — | — | — | 13:20 | 2PT Miss | 4 | — |
| AI_ONLY | — | — | — | — | 13:21 | DefRebound | 4 | — |
| AI_ONLY | — | — | — | — | 13:40 | Steal | 3 | — |
| AI_ONLY | — | — | — | — | 13:40 | Turnover | 9 | — |
| AI_ONLY | — | — | — | — | 13:41 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 13:41 | DefRebound | 8 | — |
| AI_ONLY | — | — | — | — | 13:51 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 13:55 | DefRebound | 1 | — |
| AI_ONLY | — | — | — | — | 14:03 | 2PT Miss | 9 | — |
| AI_ONLY | — | — | — | — | 14:06 | DefRebound | 0 | — |
| AI_ONLY | — | — | — | — | 14:25 | Steal | 8 | — |
| AI_ONLY | — | — | — | — | 14:25 | Turnover | 2 | — |
| AI_ONLY | — | — | — | — | 14:28 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 14:28 | DefRebound | 4 | — |

## Top mismatch examples

### Manual-only (first 8 chronologically)
- `0:34` Opponent **3PT Miss** — 1 - G. Martinez, 11
- `0:41` Liberty **2PT Make** — 11 - Jack Taylor, So
- `0:41` Liberty **Assist** — 15 - Alexander Xavier, So
- `1:35` Liberty **Foul** — 10 - Tyden Blacker, So
- `2:39` Opponent **3PT Miss** — 2 - Omari Barboza, 11
- `3:00` Opponent **Foul** — 2 - Omari Barboza, 11
- `3:22` Liberty **2PT Make** — 2 - Robbie Colman, Sr
- `3:22` Liberty **Assist** — 11 - Jack Taylor, So

### AI-only (first 8 chronologically)
- `0:00` **2PT Miss** — 7 (event `71923`)
- `0:00` **DefRebound** — 8 (event `71925`)
- `0:01` **Steal** — 7 (event `71926`)
- `0:01` **Turnover** — 8 (event `71927`)
- `0:13` **2PT Miss** — 8 (event `71931`)
- `0:15` **DefRebound** — 2 (event `71933`)
- `0:16` **Steal** — 8 (event `71934`)
- `0:16` **Turnover** — 2 (event `71935`)

JSON twin: `manual_vs_ai_q1_side_by_side.json`