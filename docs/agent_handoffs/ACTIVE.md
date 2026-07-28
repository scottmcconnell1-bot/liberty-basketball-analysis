# Active Task

Updated: 2026-07-28 (Coach Portal mobile layout / readability)


Branch: `cursor/coach-portal-ac1f`


## Meta

| Field | Value |
| --- | --- |
| **id** | coach-portal-mobile-layout |
| **status** | `implemented` (ready for Scott PR when asked) |
| **assigned_to** | cursor-agent |


## Objective

Coaches open a **permanent** URL, use the **real app with real data**, stay updated — without ops surfaces, and **without permanent writes** (Option 1 read-only coach mode). Soft password gate via `LIBERTY_COACH_PASSWORD`. Scott keeps PC on. **Phone layout must be readable** (not scrunched); hamburger must open the page menu.


## Checklist

- [x] Branch `cursor/coach-portal-ac1f` off `origin/jason-5-may-updates`
- [x] `ENABLE_COACH_PORTAL` feature flag (**default True** — intentional per Scott)
- [x] `GET/POST /coach` (+ `/coach/login`) shared password; setup copy if env unset
- [x] `session["coach_portal"]`; `/coach/logout`; ops denylist `before_request` (global auth untouched)
- [x] **Read-only gate**: coach sessions allow GET/HEAD/OPTIONS; block POST/PUT/PATCH/DELETE except auth paths
- [x] Nav surgery: hide Settings/Users/Debug/NFHS/Report Bug; **Coach view · read only** badge + banner + Sign out
- [x] **Mobile nav fix**: hamburger `stopPropagation` + outside-click treats hamburger as nav chrome; skip frame-label inject on coach
- [x] **Mobile layout**: viewport ok; stack filter grids; table overflow / card layout; 16px base; 44px tap targets; coach banner wraps; practices `.table-responsive`
- [x] Docs: `docs/COACH_PORTAL.md` (read-only section), tunnel setup scripts
- [x] Tests: `tests/test_coach_portal.py` (prior slice)
- [x] Flask `app.py` restarted (teach/analysis left running); Funnel → 8080
- [ ] PR when Scott asks (not auto-opened this slice)


## Report

### Proven

- Viewport meta was already present (`width=device-width, initial-scale=1.0`); not the root cause
- Scrunch causes: multi-column **inline** filter/form grids (schedule/practices/etc.) stayed multi-col on phone; practices table lacked `.table-responsive`; dashboard `sched-row` kept a fixed date column; nav link padding under ~44px; coach badge `nowrap`
- Global fix in `templates/base.html` (+ practices wrap); desktop media queries unchanged above 768px
- Prior hamburger bug (sibling outside-click) remains fixed

### Inferred

- Scott’s “scrunched / hard to read” report is layout density after Funnel phone use, not another hamburger regression

### Unknown

- Whether Scott wants Save buttons visually disabled beyond banner/badge


## Try locally

| Step | URL / action |
| --- | --- |
| Hard refresh phone | Funnel URL → pull-to-refresh or clear cache → Dashboard / Schedule / Playbook / Practices |
| Local | http://127.0.0.1:8080/coach (narrow DevTools ≤768px) |


## Prior completed (reference)

- Coach portal read-only Option 1 + mobile hamburger fix (same branch)
- Recruiting Station MVP lived on `cursor/recruiting-station-ac1f` (PR #134) — not on this branch base; merge separately if needed
- Rebuild events / playbook export merges on `jason-5-may-updates`
