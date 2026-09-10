# Branch Audit and Cleanup Plan

Date: 2026-09-09
Auditor: Claude (Opus 5), acting under `AGENT_PROTOCOL.md`
Branch this report lives on: `claude/repo-branch-audit`
Base of comparison: `origin/jason-5-may-updates` @ `05c8475`

Reporting follows the Proven / Inferred / Unknown standard.

---

## 1. Repository Truth Preflight

```
pwd                       /home/myaccount/Desktop/PROJECTS/liberty-basketball-analysis
git remote -v             origin  https://github.com/scottmcconnell1-bot/liberty-basketball-analysis.git
git branch --show-current claude/repo-branch-audit
git fetch origin          ok
git status                clean (audit branch)
git rev-parse HEAD        05c847511c158ecbb9ab14f2c461ad3cf019c602
git rev-parse origin/...  05c847511c158ecbb9ab14f2c461ad3cf019c602
```

**Proven.** Correct repository, clone current with the default branch at audit time.

---

## 2. Headline findings

1. **The newest real work is not on the default branch.** `cursor/film-tool-review-layout-ac1f`
   is **0 commits behind and 21 ahead** of `jason-5-may-updates`, with work through
   **2026-08-30** — nineteen days newer than the default branch tip. This is the
   repository's most recent push. **Proven.**
2. **A public GitHub Pages site is serving the private repository's contents**, including
   application source and a student-athlete roster. See section 6. **Proven.**
3. **73 branches, of which 59 can be deleted with high confidence** — 40 already merged,
   16 superseded by a descendant branch, 3 verified redundant. **Proven.**
4. **A whole cluster of July work never landed.** The `film-tool-reports-fix` lineage
   (Film Tool focus mode, Q1 manual-vs-AI teach, demo packaging, `film_tool_games.py`,
   `ball_possession.py`) is absent from the default branch. **Proven** that the files are
   absent; **Unknown** whether that was a deliberate abandonment or an oversight.
5. **`origin/main` shares no ancestry with the working branch** — unrelated histories.
   It is the original Apr–Jun 2026 project, frozen at `3d20bc9` (2026-06-13). **Proven.**
6. **Repository is 727 MB** because a 36.8 MB SQLite database was committed 78 times,
   alongside model weights and game video. **Proven.**

---

## 3. Branch inventory

| Category | Count | Risk to delete |
| --- | ---: | --- |
| Merged into `jason-5-may-updates` | 40 | None |
| Superseded (ancestor of another unmerged branch) | 16 | None |
| Verified redundant tips | 3 | None |
| Unmerged tips holding unique work | 11 | Requires triage |
| Special (`main`, `gh-pages`, `dataset-v2`) | 3 | Requires a decision |
| Default branch | 1 | — |
| **Total** | **73** (+`claude/repo-branch-audit` = 74) | |

---

## 4. Group A — merged, safe to delete (40)

Fully contained in `jason-5-may-updates`. Deleting these loses nothing; the commits
remain reachable from the default branch.

```
cursor/app-context-teach-fix-ac1f          cursor/playbook-taxonomy-ac1f
cursor/assisted-stat-sample-ac1f           cursor/review-in-context-ac1f
cursor/coach-ledger-ac1f                   cursor/review-workspace-mvp-ac1f
cursor/coach-portal-ac1f                   cursor/roster-dialog-fullscreen-ac1f
cursor/dashboard-blank-season-default-ac1f cursor/roster-excel-import-ac1f
cursor/fastdraw-play-match-ac1f            cursor/roster-seasons-ac1f
cursor/film-stats-nav-cleanup-ac1f         cursor/roster-upload-fix-ac1f
cursor/film-tool-settings-cleanup-ac1f     cursor/schedule-game-records-ac1f
cursor/fix-analysis-player-dropdown-ac1f   cursor/schedule-import-scores-ac1f
cursor/fix-analysis-roster-lookup-ac1f     cursor/schedule-import-verify-ac1f
cursor/fix-playbook-import-ac1f            cursor/stat-book-mvp-ac1f
cursor/fix-rebuild-events-ac1f             cursor/stat-book-upload-fix-ac1f
cursor/fix-roster-and-player-names-ac1f    cursor/sticky-choreography-ac1f
cursor/full-film-panel-ac1f                cursor/ui-spacing-fix-ac1f
cursor/highlight-clips-ac1f                cursor/video-trim-editor-ac1f
cursor/jersey-tracking-phase1-ac1f         cursor/videos-actions-ui-ac1f
cursor/maxpreps-schedule-import-ac1f       cursor/videos-archive-ac1f
cursor/no-compress-save-nfhs-ac1f          cursor/videos-fast-list-ac1f
cursor/playbook-export-share-ac1f          cursor/videos-gameid-column-ac1f
cursor/videos-roster-ui-ac1f               fix/game-id-analysis-key
```

---

## 5. Group B — superseded, safe to delete (16)

Each is a strict ancestor of another unmerged branch, so its commits survive in the
descendant. These are intermediate points in stacked Cursor chains, not independent work.

| Branch | Descendant that contains it |
| --- | --- |
| `cursor/cv-possession-port-ac1f` | `cursor/fix-film-event-jump-ac1f` |
| `cursor/fix-analysis-jersey-film-ac1f` | `cursor/fix-film-event-jump-ac1f` |
| `cursor/fix-scan-jerseys-json-ac1f` | `cursor/fix-film-event-jump-ac1f` |
| `cursor/fix-jrhigh-pdf-times-ac1f` | `cursor/dashboard-season-selector-ac1f` |
| `cursor/maxpreps-printable-import-ac1f` | `cursor/dashboard-season-selector-ac1f` |
| `cursor/demo-desktop-shortcut-ac1f` | `cursor/demo-done-uninstall-ac1f` |
| `cursor/fix-demo-sfx-7z-ac1f` | `cursor/demo-done-uninstall-ac1f` |
| `cursor/fix-wilder-compare-ac1f` | `cursor/demo-done-uninstall-ac1f` |
| `cursor/film-tool-roster-starters-ui-ac1f` | `cursor/demo-done-uninstall-ac1f` |
| `cursor/manual-tag-focus-layout-ac1f` | `cursor/demo-done-uninstall-ac1f` |
| `cursor/opponent-roster-bulk-ac1f` | `cursor/demo-done-uninstall-ac1f` |
| `cursor/q1-manual-ai-compare-ac1f` | `cursor/demo-done-uninstall-ac1f` |
| `cursor/server-persist-manual-tags-ac1f` | `cursor/demo-done-uninstall-ac1f` |
| `cursor/fix-app-context-postprocess-ac1f` | `cursor/film-tool-reports-fix-ac1f` |
| `cursor/improve-ai-from-manual-q1-ac1f` | `cursor/film-tool-reports-fix-ac1f` |
| `cursor/teach-ai-manual-q1-ac1f` | `cursor/film-tool-reports-fix-ac1f` |

### Group B2 — verified redundant tips (3)

| Branch | Evidence | Verdict |
| --- | --- | --- |
| `cursor/roster-file-type-import-ac1f` | `git cherry` marks its only commit `-` (patch already in base) | Delete |
| `cursor/stage-6a-implementation-ac1f` | Base's `module_entitlements.py` / `module_keys.py` are a 191-line superset; `STAGE_INDEX.md` records Stage 6A implemented via #72 | Delete |
| `cursor/active-in-progress-devin-ac1f` | 1 commit touching only `ACTIVE.md`, 193 commits behind; that file has moved far past it | Delete |

---

## 6. Security finding — public Pages site exposing a private repository

**Proven.** GitHub Pages is enabled and public:

```
source:    branch gh-pages, path /
public:    true
status:    built
html_url:  https://scottmcconnell1-bot.github.io/liberty-basketball-analysis/
```

`gh-pages` is a single commit (`b218d07`, 2026-07-27, "Add GitHub Pages landing page")
containing **1,272 files — a full copy of the application tree**, not just a landing page.
Live HTTP checks returned **200** for:

| Path | Status |
| --- | --- |
| `/app.py` | 200 — application source |
| `/config.py` | 200 — application source |
| `/2026%20Liberty%20A%20Roster.csv` | 200 — **11 athletes, columns `POS,#,NAME,GRADE`** |
| `/AGENT_PROTOCOL.md` | 200 — internal process docs |

`models/*.pt`, `videos/Q1.mp4` and `data/videos/Q1_snippet.mp4` are also in that tree, but
they are Git LFS objects and Pages serves only the **134-byte pointer file**, not the
payload (verified: fetching `/models/ball_detector.pt` from the Pages URL returns
`version https://git-lfs.github.com/spec/v1 ...`). **Correction 2026-09-09:** an earlier
revision of this report said the weights and footage were exposed; they are not. The
source-code and roster exposure above is unchanged and remains the serious part.

The roster is the sharpest issue: named minors with grade levels, published on an
indexable domain. `.env.example` returned 404, and no credential files were found in the
tree — **Proven** for the paths checked; **Unknown** whether anything sensitive sits at a
path not yet enumerated.

**This is the one item I would not defer.** Recommended sequence, all requiring your
approval since each is outward-facing:

1. Disable Pages, or repoint it at a branch containing *only* the landing page.
2. Delete the `gh-pages` branch as it currently stands.
3. If a public landing page is wanted, rebuild it as an orphan branch holding one
   `index.html` and nothing else.
4. Assume anything served has been fetched and cached; treat the roster as disclosed.

---

## 7. Group C — unmerged tips holding unique work (11)

Ordered by my read of value. Nothing here is deleted without your call.

### C1. `cursor/film-tool-review-layout-ac1f` — **promote, do not delete**
2026-08-30 · 21 ahead / **0 behind** · 41 files · +13,264 lines

Strictly ahead of the default branch — the repo's newest state. Real commits:

- `27b99a5` Relax early-game Adrian jersey lookaround for sparse OCR
- `599ce50` Spread Adrian ledger events across game time and add film sync (`film_sync.py`)
- `19fcd25` / `3755bfd` Liberty server watchdog scheduling
- 17 × `chore: daily learning status` — automated, but they carry real changes to
  `adrian_identity.py`, `adrian_quality.py`, `static/js/film-tool.js`

New modules absent from the default branch: `adrian_identity.py`, `adrian_quality.py`,
`film_sync.py`, `scripts/watchdog_liberty_server.ps1`.

**Inferred:** this is the live line of work and the default branch is the stale one.
**Caveat:** the chore commits also committed `data/flask_8080_restart.err.log` (884 lines)
— strip logs before merging.

### C2. `cursor/film-tool-reports-fix-ac1f` — triage, highest-value orphan
2026-07-20 · 42 commits · 56 files · +14,762 lines

Tip of the July chain. Absent from the default branch: `film_tool_games.py`, Film Tool
Focus mode, Q1 manual-vs-AI comparison and supervised teach templates, Windows repair
scripts, `tests/test_film_tool_games.py`, `test_film_tool_open_bootstrap.py`,
`test_film_tool_report_team_normalize.py`.

**Unknown:** whether this was abandoned deliberately. Given `ACTIVE.md` still describes
manual Q1 tagging as central, I would not delete it before you rule on it.

### C3. `cursor/demo-done-uninstall-ac1f` — triage
2026-07-19 · 8 commits unique vs C2 · LibertyDemo one-click coach demo packaging
(SFX installer, web DONE/uninstall button, port 8090+ handling).

Only meaningful if coach demo distribution is still a goal.

### C4. `cursor/fix-film-event-jump-ac1f` — triage
2026-07-13 · 26 commits · 40 files · +4,103 lines. Carries `ball_possession.py`
(CV possession port) — absent from the default branch, and adjacent to Stage 3C
possessions work.

### C5. `cursor/recruiting-station-ac1f` — triage (feature scope = Scott gate)
2026-07-23 · 3 commits · +1,389 lines · `blueprints/recruiting.py`, `recruiting.py`,
`templates/recruiting.html`, `config.py` flag. Entirely absent from the default branch.

### C6. `cursor/playbook-auto-digitize-ac1f` — triage
2026-07-23 · 1 commit · +1,217 lines · `playbook_digitize.py`,
`scripts/digitize_playbook_plays.py`, `tests/test_playbook_digitize.py`. Complements the
already-merged FastDraw play-match work.

### C7. `cursor/dashboard-season-selector-ac1f` — **blocked, schema change**
2026-07-06 · 9 commits · +1,080 lines. Adds `season_type TEXT NOT NULL DEFAULT 'regular'`
to `seasons` in `schema.sql`.

`AUTHORITY.md`: *"If schema.sql needs to change → STOP. Get Scott's approval first."*
Blocked pending your decision.

### C8. `cursor/remove-preview-tab-ac1f` — small, likely still wanted
2026-07-07 · 1 commit · **−520 lines**. Removes the product-preview tab.
`templates/product_preview.html` is still present in the default branch, so this was never
applied. Deleting code is a Scott gate.

### C9. `cursor/fix-analysis-clip-ac1f` — small fix
2026-07-07 · 1 commit · 3 files · +53 lines, incl. `tests/test_analysis_helpers.py`.
Cheap to rebase and verify.

### C10. `cursor/setup-dev-environment-db3e` — low value, stale
2026-07-05 · 1 commit · `AGENTS.md` only (absent from the default branch). Its content is
**factually wrong today** — it claims `requirements.txt` and `requirements.docker.txt` do
not exist; both do. Salvage the Cursor Cloud notes into `CLAUDE.md`, then delete.

### C11. `dataset-v2` — archive, do not merge
2026-06-14 · 10 commits · 3,103 files. Ball-detection dataset v2 plus the audit concluding
the v14 detector was non-functional (0/20). Historical evidence, not code to merge.
**Recommend:** tag as `archive/dataset-v2`, then delete the branch.

---

## 8. Group D — `origin/main`

**Proven:** `main` and `jason-5-may-updates` have **no merge base** — unrelated histories.
`main` is the original project (2026-04-27 → 2026-06-13, 27 files, last commit `3d20bc9`
"Add comprehensive Codex briefing document" by Rex). GitHub's default branch is correctly
set to `jason-5-may-updates`.

A branch named `main` that is neither default nor ancestral is a trap for any new
contributor or agent. **Recommend:** tag `archive/main-original-history` at `3d20bc9`,
then delete the branch. Nothing is lost — a tag pins the history permanently.

---

## 9. Cleanup plan

Every phase is reversible except where noted. No deletions have been performed.

### Phase 0 — Pages exposure (urgent, needs your approval)
Disable or repoint GitHub Pages; drop the current `gh-pages` tree. Section 6.

### Phase 1 — Delete the 40 merged branches (zero risk)
Safety tag first, then delete. Recoverable from the tag either way.

### Phase 2 — Delete the 16 superseded + 3 redundant branches (zero risk)
Commits survive in their descendants or the default branch.

### Phase 3 — Preserve history as tags, then delete the branch
`archive/main-original-history` → `main`; `archive/dataset-v2` → `dataset-v2`.

### Phase 4 — Decide the branch model
Recommendation: **fast-forward `jason-5-may-updates` to
`cursor/film-tool-review-layout-ac1f`** (0 behind, so it is a clean fast-forward), after
stripping the committed log file. This makes the default branch the newest state again.
Merging to `jason-5-may-updates` is a Scott gate.

### Phase 5 — Triage the orphaned July work
One bounded `[OWL ACTION]`-style pass per branch, newest first: C2 → C4 → C6 → C3.
For each: rebase onto the current tip, run the suite, keep or drop on evidence.

### Phase 6 — Repository hygiene (separate effort)
727 MB, dominated by history, not the working tree:

| Blob | Size |
| --- | --- |
| `yolov8m.pt` | 49.7 MB |
| `uploads/Q1-2min-Copy_-_Copy_20260505_020628.mp4` | 42.1 MB |
| `yolo11m.pt` | 38.8 MB |
| `film_analysis.db` | 36.8 MB × **78 commits** |

`film_analysis.db` is now gitignored and untracked — good. The `models/*.pt` files are
gitignored but **still tracked**, so the ignore rule does nothing for them. 792 `.log`
objects exist across history. Shrinking this requires history rewriting
(`git filter-repo`), which breaks every existing clone — a deliberate, scheduled decision,
not part of branch cleanup.

**End state: 73 branches → 14**, plus archive tags.

---

## 10. What needs Scott's decision

1. **Pages exposure** — disable, repoint, or accept. (Section 6)
2. **Fast-forward the default branch** to `cursor/film-tool-review-layout-ac1f`.
3. **Authorize Phase 1–3 deletions** (59 branches, all recoverable via tags).
4. **`season_type` schema change** — C7 stays blocked until you rule.
5. **Recruiting station** — is it still in scope? (C5)
6. **Remove the preview tab** — deleting a feature is your call. (C8)
7. **July cluster** — abandoned on purpose, or dropped by accident? (C2/C3/C4)
8. **History rewrite** for repo size — yes, no, or later.

---

## 11. Verification notes

- Ancestry via `git merge-base --is-ancestor` across all 32 unmerged branches (pairwise).
- Patch equivalence via `git cherry` (detects squash/cherry-pick landings).
- Feature presence via `git cat-file -e <base>:<path>`.
- Pages exposure via the GitHub API plus live `curl` status checks.
- **Unknown:** the test suite was **not** run. This machine has Python 3.14.7; the project
  targets 3.12/3.13 and no virtualenv exists. The recorded baseline (360 passed, 1 skipped)
  is quoted from `docs/STAGE_INDEX.md`, not reproduced.
