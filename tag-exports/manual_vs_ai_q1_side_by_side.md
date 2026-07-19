# Manual vs AI — Q1 Side-by-Side (Wilder)

**Verdict: Q1 TIME COVERAGE OK — compare event quality (exact / manual-only / AI-only)**

**Analysis key:** `nfhs_gam30b09cbb4f_20260706_173156_trim_20260706_180340_trim_20260706_185339_trim_20260706_191311__rerun_20260718_215754`
**Run status:** `completed` — Q1 0:00-14:31 full-source GPU

## KPIs (time ±10s + identical label)

| Metric | Value |
| --- | ---: |
| Exact matches | **37** |
| Manual-only (AI miss) | **16** |
| AI-only (false extra) | **28** |
| Manual action tags | 53 |
| AI comparable events | 65 |

## Coverage / diagnosis

GPU Q1 rerun `nfhs_gam30b09cbb4f_20260706_173156_trim_20260706_180340_trim_20260706_185339_trim_20260706_191311__rerun_20260718_215754` produced detections through 871000 ms (frames 0–21775) and comparable AI events 24180–869700 ms. Run status=completed. Timestamp span now covers ~full Q1; remaining gaps are match quality, not missing timeline.

- Covers ~full Q1: **True**
- Comparable AI event span: **24180–869700 ms** (~845.52s)
- Raw events: **376** spanning **1860–870580 ms**
- Detections: frames **0–21775** / ts **0–871000 ms** @ implied **25.0 fps** (n=164668)
- Analysis `video_path` exists: **True** (`C:\Users\scott\Documents\liberty-basketball-analysis\uploads\nfhs_gam30b09cbb4f.mp4`)
- `videos.id=8`: `C:\Users\scott\Documents\liberty-basketball-analysis\uploads\nfhs_gam30b09cbb4f.mp4` (4896559287 bytes, duration ~7290s)
- Clock offset viable: **True** — AI timestamps span Q1; constant clock-offset search is no longer blocked by a ~20s window.

## Side-by-side

| Status | Manual time | Manual team | Manual label | Manual player | AI time | AI label | AI player | Δs |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EXACT | 0:34 | Opponent | 3PT Miss | 1 - G. Martinez, 11 | 0:41 | 3PT Miss | 1 | 7.2 |
| EXACT | 0:38 | Liberty | DefRebound | 15 - Alexander Xavier, So | 0:42 | OffRebound | 1 | 3.9 |
| MANUAL_ONLY | 0:41 | Liberty | 2PT Make | 11 - Jack Taylor, So | — | — | — | — |
| MANUAL_ONLY | 0:41 | Liberty | Assist | 15 - Alexander Xavier, So | — | — | — | — |
| MANUAL_ONLY | 1:35 | Liberty | Foul | 10 - Tyden Blacker, So | — | — | — | — |
| EXACT | 2:07 | Liberty | Steal | 10 - Tyden Blacker, So | 2:11 | Steal | 8 | 4.5 |
| EXACT | 2:07 | Opponent | Turnover | 4 - Darius Zamora, 11 | 2:11 | Turnover | 3 | 4.5 |
| EXACT | 2:11 | Liberty | 2PT Make | 10 - Tyden Blacker, So | 2:05 | 2PT Make | 8 | 5.5 |
| EXACT | 2:39 | Opponent | 3PT Miss | 2 - Omari Barboza, 11 | 2:37 | 3PT Miss | 1 | 1.8 |
| MANUAL_ONLY | 3:00 | Opponent | Foul | 2 - Omari Barboza, 11 | — | — | — | — |
| EXACT | 3:22 | Liberty | 2PT Make | 2 - Robbie Colman, Sr | 3:29 | 2PT Make | 3 | 7.3 |
| MANUAL_ONLY | 3:22 | Liberty | Assist | 11 - Jack Taylor, So | — | — | — | — |
| MANUAL_ONLY | 4:51 | Liberty | Foul | 4 - Carson Bradshaw, So | — | — | — | — |
| MANUAL_ONLY | 5:22 | Liberty | Foul | 15 - Alexander Xavier, So | — | — | — | — |
| EXACT | 5:46 | Opponent | 3PT Miss | 1 - G. Martinez, 11 | 5:45 | 3PT Miss | 3 | 1.0 |
| EXACT | 6:07 | Opponent | 2PT Miss | 1 - G. Martinez, 11 | 6:08 | 2PT Miss | 7 | 1.0 |
| EXACT | 6:34 | Opponent | 3PT Miss | 2 - Omari Barboza, 11 | 6:34 | 3PT Miss | 5 | 0.4 |
| EXACT | 6:37 | Liberty | DefRebound | 2 - Robbie Colman, Sr | 6:34 | DefRebound | 0 | 2.6 |
| MANUAL_ONLY | 6:38 | Opponent | Foul | 20 - Ezra Johnson, 12 | — | — | — | — |
| EXACT | 7:13 | Liberty | Turnover | 4 - Carson Bradshaw, So | 7:14 | Turnover | 4 | 1.5 |
| MANUAL_ONLY | 7:13 | Opponent | Steal | 2 - Omari Barboza, 11 | — | — | — | — |
| MANUAL_ONLY | 8:02 | Liberty | Turnover | 11 - Jack Taylor, So | — | — | — | — |
| EXACT | 9:44 | Liberty | 3PT Miss | 11 - Jack Taylor, So | 9:44 | 3PT Miss | 3 | 0.0 |
| EXACT | 9:47 | Liberty | OffRebound | 11 - Jack Taylor, So | 9:46 | DefRebound | 1 | 0.7 |
| MANUAL_ONLY | 9:50 | Opponent | Foul | 4 - Darius Zamora, 11 | — | — | — | — |
| EXACT | 10:12 | Liberty | FT Make | 4 - Carson Bradshaw, So | 10:12 | FT Make | 5 | 0.0 |
| EXACT | 10:26 | Liberty | FT Make | 4 - Carson Bradshaw, So | 10:23 | FT Make | 8 | 3.1 |
| EXACT | 10:47 | Opponent | 3PT Miss | 4 - Darius Zamora, 11 | 10:48 | 3PT Miss | 9 | 1.0 |
| EXACT | 10:49 | Liberty | DefRebound | 2 - Robbie Colman, Sr | 10:51 | DefRebound | 4 | 1.5 |
| MANUAL_ONLY | 11:01 | Opponent | Foul | 20 - Ezra Johnson, 12 | — | — | — | — |
| EXACT | 11:25 | Liberty | 2PT Miss | 15 - Alexander Xavier, So | 11:28 | 2PT Miss | 3 | 2.3 |
| EXACT | 11:29 | Liberty | OffRebound | 15 - Alexander Xavier, So | 11:29 | DefRebound | 6 | 0.8 |
| EXACT | 11:32 | Liberty | 2PT Make | 4 - Carson Bradshaw, So | 11:40 | 2PT Make | 3 | 8.5 |
| MANUAL_ONLY | 11:32 | Liberty | Assist | 15 - Alexander Xavier, So | — | — | — | — |
| EXACT | 11:52 | Liberty | Steal | 11 - Jack Taylor, So | 11:51 | Steal | 3 | 1.0 |
| EXACT | 11:52 | Opponent | Turnover | 20 - Ezra Johnson, 12 | 11:51 | Turnover | 8 | 1.0 |
| EXACT | 11:56 | Liberty | 2PT Miss | 11 - Jack Taylor, So | 11:55 | 2PT Miss | 1 | 0.8 |
| EXACT | 11:57 | Opponent | DefRebound | 1 - G. Martinez, 11 | 11:55 | DefRebound | 8 | 2.4 |
| EXACT | 12:23 | Opponent | 3PT Miss | 1 - G. Martinez, 11 | 12:20 | 3PT Miss | 3 | 2.8 |
| EXACT | 12:26 | Liberty | DefRebound | 10 - Tyden Blacker, So | 12:20 | DefRebound | 6 | 5.8 |
| EXACT | 12:37 | Liberty | 2PT Make | 33 - Dominic Fischer, Sr | 12:33 | 2PT Make | 1 | 4.0 |
| MANUAL_ONLY | 12:37 | Liberty | Assist | 4 - Carson Bradshaw, So | — | — | — | — |
| EXACT | 12:53 | Opponent | 2PT Make | 2 - Omari Barboza, 11 | 12:57 | 2PT Make | 3 | 3.6 |
| EXACT | 13:08 | Liberty | Turnover | 11 - Jack Taylor, So | 13:05 | Turnover | 2 | 3.2 |
| EXACT | 13:35 | Opponent | 2PT Make | 2 - Omari Barboza, 11 | 13:32 | 2PT Make | 5 | 3.7 |
| EXACT | 13:42 | Liberty | 2PT Make | 4 - Carson Bradshaw, So | 13:43 | 2PT Make | 1 | 1.0 |
| MANUAL_ONLY | 13:42 | Liberty | Assist | 10 - Tyden Blacker, So | — | — | — | — |
| EXACT | 13:51 | Liberty | Steal | 15 - Alexander Xavier, So | 13:41 | Steal | 3 | 9.6 |
| EXACT | 13:51 | Opponent | Turnover | 5 - Lance Bryce, 10 | 13:41 | Turnover | 9 | 9.6 |
| EXACT | 13:53 | Liberty | 2PT Make | 15 - Alexander Xavier, So | 13:53 | 2PT Make | 3 | 0.1 |
| EXACT | 14:11 | Opponent | 2PT Miss | 1 - G. Martinez, 11 | 14:15 | 2PT Miss | 4 | 3.6 |
| MANUAL_ONLY | 14:13 | Liberty | DefRebound | 33 - Dominic Fischer, Sr | — | — | — | — |
| EXACT | 14:20 | Liberty | 2PT Make | 10 - Tyden Blacker, So | 14:30 | 2PT Make | 1 | 9.9 |
| AI_ONLY | — | — | — | — | 0:24 | 2PT Miss | 7 | — |
| AI_ONLY | — | — | — | — | 0:28 | DefRebound | 8 | — |
| AI_ONLY | — | — | — | — | 1:34 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 2:16 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 2:50 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 3:04 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 3:16 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 4:43 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 4:55 | 2PT Miss | 4 | — |
| AI_ONLY | — | — | — | — | 5:12 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 5:22 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 5:34 | 2PT Miss | 4 | — |
| AI_ONLY | — | — | — | — | 5:57 | 2PT Miss | 4 | — |
| AI_ONLY | — | — | — | — | 6:46 | 2PT Miss | 6 | — |
| AI_ONLY | — | — | — | — | 7:11 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 7:23 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 7:57 | 2PT Miss | 8 | — |
| AI_ONLY | — | — | — | — | 8:11 | 2PT Miss | 7 | — |
| AI_ONLY | — | — | — | — | 9:32 | 2PT Miss | 2 | — |
| AI_ONLY | — | — | — | — | 10:01 | 2PT Miss | 0 | — |
| AI_ONLY | — | — | — | — | 10:35 | 2PT Miss | 9 | — |
| AI_ONLY | — | — | — | — | 10:59 | 2PT Miss | 4 | — |
| AI_ONLY | — | — | — | — | 11:14 | 2PT Miss | 1 | — |
| AI_ONLY | — | — | — | — | 12:07 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 12:07 | DefRebound | 0 | — |
| AI_ONLY | — | — | — | — | 12:46 | 2PT Miss | 3 | — |
| AI_ONLY | — | — | — | — | 13:08 | 2PT Miss | 0 | — |
| AI_ONLY | — | — | — | — | 14:04 | 2PT Miss | 9 | — |

## Top mismatch examples

### Manual-only (first 8 chronologically)
- `0:41` Liberty **2PT Make** — 11 - Jack Taylor, So
- `0:41` Liberty **Assist** — 15 - Alexander Xavier, So
- `1:35` Liberty **Foul** — 10 - Tyden Blacker, So
- `3:00` Opponent **Foul** — 2 - Omari Barboza, 11
- `3:22` Liberty **Assist** — 11 - Jack Taylor, So
- `4:51` Liberty **Foul** — 4 - Carson Bradshaw, So
- `5:22` Liberty **Foul** — 15 - Alexander Xavier, So
- `6:38` Opponent **Foul** — 20 - Ezra Johnson, 12

### AI-only (first 8 chronologically)
- `0:24` **2PT Miss** — 7 (event `72528`)
- `0:28` **DefRebound** — 8 (event `72530`)
- `1:34` **2PT Miss** — 8 (event `72553`)
- `2:16` **2PT Miss** — 3 (event `72572`)
- `2:50` **2PT Miss** — 1 (event `72587`)
- `3:04` **2PT Miss** — 8 (event `72592`)
- `3:16` **2PT Miss** — 8 (event `72598`)
- `4:43` **2PT Miss** — 1 (event `72631`)

JSON twin: `manual_vs_ai_q1_side_by_side.json`