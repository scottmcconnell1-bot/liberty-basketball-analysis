# Active Task — HANDOFF FOR NEW CHAT

Updated: 2026-08-11 (archive prior conversation; continue here)

**Paste this whole file into a new Cursor agent chat, then archive the old thread.**

---

## Repo / branch / site

| Item | Value |
| --- | --- |
| Repo | `C:\Users\scott\Documents\liberty-basketball-analysis` |
| Branch | `jason-5-may-updates` (`git pull` first) |
| Site | `https://liberty-coach.tail368a37.ts.net` -> local `:8080` |
| Flask Python | `C:\Users\scott\AppData\Local\Programs\Python\Python312\python.exe` |
| Login | Staff **email** (not username) + usual password |

## Product definition of done

A game is **done** when:

1. Scorebook photo -> `/stat-books` -> confirm -> `data/stat_books/confirmed/<game_id>.json`
2. Film events -> **Review** Accept/Correct/Reject -> official ledger (`events` with accepted/corrected)

GPU/CV finishing alone is **not** done. **Auto-accept is locked off** (no confidence thresholds).

## Ops (important)

- Teach loop **PAUSED**: `data/hoopsalytics/TEACH_LOOP_PAUSED` present; watchdog disabled earlier. **Do not** resume full HUDL backlog.
- Videos: **Active -> 9 JrHigh**, **Archive -> 54** older games.
- Scorebook images staged: `uploads/stat_books/jrhigh/`
- Prefer **one game at a time** for AI (not batch teach).

## Shipped (already on tip)

- Videos light list (no N+ detection COUNT)
- Active / Archive tabs + bulk archive
- Actions UI: Film Tool / Review / Archive / More (2x2)
- **GameID** column (match scorebooks)
- `/stat-books` MVP; upload fix for commas in game_id (e.g. `jrhigh_adrian,_or_...`)
- Review workspace Accept / Correct / Reject
- Sticky playbook + FastDraw vector extract
- **Highlights** from reviewed ledger (`/highlights`, jersey/event filters, generate clips / clip list)
- **FastDraw play/set match** (rank-only MVP; Film Tool panel + `/api/film/<game_id>/play-matches`; see `docs/PLAYBOOK_PLAY_MATCH.md`)

## Immediate open bug (Scott screenshot 2026-08-11)

**Film Tool AI failed on JrHigh Adrian:**

- File: `LIBERTY_A_v_ADRIAN_H_20260809_221334.mp4`
- game_id: `jrhigh_adrian,_or_LIBERTY_A_v_ADRIAN_H_20260809_221334`
- Error UI: *Analysis run stopped responding. Check logs, install missing packages (**pip install scikit-learn**), then click Rebuild again.*
- Button: **Retry AI Analysis**

**Next agent should:**

1. `pip install scikit-learn` into **Python 3.12** (same interpreter as Flask)
2. Clear hung `analysis_runs` for this game if needed
3. Restart Flask with Python312 on :8080
4. Retry AI on **this game only**; confirm progress past sklearn error
5. Then E2E: `/stat-books` confirm for same GameID -> Review ledger -> optional `/highlights`

## Suggested first message for new agent

> Read `docs/agent_handoffs/ACTIVE.md`. Fix Adrian JrHigh AI analysis (missing scikit-learn / hung run). Use Python312. Do not unpause teach backlog. After Retry works, walk one E2E: scorebook confirm + Review.

## Proven / Inferred / Unknown

- **Proven:** DoD shift; teach paused; JrHigh active list; scorebook comma fix; Adrian error text names sklearn; highlight-clips + fastdraw-play-match merged onto jason
- **Inferred:** Flask must use Python312 (system), not a bare `python` without deps
- **Unknown:** Whether sklearn already installed after partial fix attempt


---

## Linux standup note (2026-09-09) — separate machine, separate branch

A second environment now exists: a Linux workstation on branch `claude/local-standup`
(not pushed). Everything above still describes Scott's Windows box. For the Linux box read
`docs/agent_handoffs/LOCAL_STANDUP_2026-09-09.md`. Two items from this file are affected:

- **Unknown → Proven (on Linux):** `scikit-learn` is in `requirements-dev.txt` and installed
  there; the Adrian "install scikit-learn" error does not reproduce on that machine.
- The `/play/share/<token>` route 500'd on every token (`sqlite3.Row.get`) — fixed on that
  branch; Scott's box still has the bug until merged.
