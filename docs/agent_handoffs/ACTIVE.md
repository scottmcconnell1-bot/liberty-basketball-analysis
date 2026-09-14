# Active Task

Updated: 2026-09-14  
Branch: `cursor/handoff-post-e2e-ac1f` (docs only)  
Base / default: `main` (PR #143 merged)

## Meta

| Field | Value |
| --- | --- |
| **id** | post-e2e-cleanup-and-p0-pause |
| **status** | `awaiting_scott` |
| **executor** | cursor-only |

## Done (Proven)

- PR #142 merged: agent OS, Film tools, Adrian OCR, layout, person YOLO → `yolo11n.pt`
- PR #140 closed as superseded by #142
- PR #143 merged: E2E suite, seeder, notification INSERT fix, admin-reset FK order, video_trim fixes, E2E/quality docs; CI hardened for no-CV + short synthetic clips
- PR #141 closed as superseded by #143
- Feature branch `cursor/e2e-port-ac1f` deleted on merge

## Next (await Scott)

1. **Approve branch keep/delete list below** (gate: mass remote deletes)
2. Optionally close remaining open PRs that target `jason-5-may-updates` (stale / not for main)
3. Pause for Scott on **P0**: GitHub Pages exposure (`gh-pages`), auth / `/register`

## Gated

- `ball_detector.pt` / `ball_confidence`
- Feature flags False→True / teach / auto-accept
- Mass remote deletes (this inventory)
- Production flip to `precision` generator

## Branch keep / delete inventory (proposal — do not delete until Scott OK)

### Keep

| Branch | Why |
| --- | --- |
| `main` | Only integration line |
| `jason-5-may-updates` | Temporary historical pointer (policy); no new work |
| `gh-pages` | Special deploy branch — **review before any delete** (P0 exposure question) |

### Keep briefly / decide later

| Branch | Why |
| --- | --- |
| `dataset-v2` | Unclear; may hold dataset work — confirm before delete |
| `improve/precision-and-migration` | Precision path; confirm vs what landed on main |
| `fix/game-id-analysis-key` | Name suggests fix already conceptualized on main — confirm |

### Delete candidates (stale feature tips; prefer after closing related open PRs)

**Jason wipe / Claude stack (superseded ports):**

- `claude/e2e-suite` (was #141)
- `claude/local-standup` (open #139 → jason-5)
- `claude/precision-mode` (was #140 path)
- `claude/repo-branch-audit`

**Open PRs still targeting `jason-5-may-updates` (Aug 2026, not main):**  
Recommend **close without merge**, then delete head branches after Scott OK:

| PR | Head |
| --- | --- |
| #139 | `claude/local-standup` |
| #134 | `cursor/recruiting-station-ac1f` |
| #133 | `cursor/playbook-auto-digitize-ac1f` |
| #132 | `cursor/server-persist-manual-tags-ac1f` |
| #131 | `cursor/q1-manual-ai-compare-ac1f` |
| #130 | `cursor/film-tool-roster-starters-ui-ac1f` |
| #129 | `cursor/manual-tag-focus-layout-ac1f` |
| #128 | `cursor/opponent-roster-bulk-ac1f` |
| #127 | `cursor/fix-film-event-jump-ac1f` |
| #126 | `cursor/fix-scan-jerseys-json-ac1f` |
| #125 | `cursor/cv-possession-port-ac1f` |
| #124 | `cursor/fix-analysis-jersey-film-ac1f` |
| #123 | `cursor/fix-analysis-clip-ac1f` |
| #112 | `cursor/remove-preview-tab-ac1f` |
| #93 | `cursor/roster-file-type-import-ac1f` |
| #92 | `cursor/dashboard-season-selector-ac1f` |
| #91 | `cursor/maxpreps-printable-import-ac1f` |
| #90 | `cursor/fix-jrhigh-pdf-times-ac1f` |
| #67 | `cursor/setup-dev-environment-db3e` |

**Other remote `cursor/*` with no open PR to main** (~50+ tips): treat as delete candidates after a quick “anything unique vs main?” pass, or delete in one Scott-approved batch. Examples of themes already partially on main via selective ports: film-tool-*, videos-*, highlight-clips, video-trim-editor, coach-*, roster-*, schedule-*, teach-*, demo-*.

**Do not mass-delete until Scott replies with an approved list** (or “delete all candidates”).

## Report

### Proven
- `main` @ `2baec8e` includes E2E port; CI green on #143 (3.12 + 3.13)
- #141 closed superseded  

### Inferred
- Most open PRs against `jason-5-may-updates` will never land as-is; selective re-port to main is the path if anything useful remains  

### Unknown
- Whether `gh-pages` is still publishing anything sensitive
- Whether any stale `cursor/*` tip has unique value not on main  

## P0 pause (Scott decisions)

1. GitHub Pages / `gh-pages` exposure  
2. Auth model and `/register`  
