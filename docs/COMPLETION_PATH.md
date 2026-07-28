# Liberty Completion Path

Updated: 2026-07-05
Branch: `jason-5-may-updates`
Owner: Scott McConnell
Driver: Cursor Cloud Agent (orchestrator + executor)

## North star

Scott can run Liberty as a **trusted coach operations platform**: schedule → film → tag/review → stats/minutes → scouting/playbook → decisions backed by reviewed data. AI assist layers on later; ball detection stays at verified production settings unless new labeled data appears.

## What is already done (Proven)

- Platform core Stages 1–5 + post-Stage-5 cleanup
- Review workflow (3A/3B), possessions/clips foundation (3C), event ledger upgrade (4A–4D)
- Stage 6A: module keys, read helpers, audit CLI
- Product surfaces: `/preview`, `/status`, film, review, practices, scouting, playbook
- Production ball detector: `models/ball_detector.pt`, conf=0.25
- Tests: 304+ passed on Python 3.12 (Cloud Agent)

## How work runs (no per-step Scott approval)

| Role | Responsibility |
| --- | --- |
| **Scott** | Product vision, schema approval, auth/production go-live, cancel/pivot |
| **Orchestrator** | Own this path, queue slices, review, **merge** bounded PRs |
| **Devin** | Optional executor for multi-file slices | **Retired for Liberty** — Scott uses Devin on other projects |
| **Repo** | `docs/agent_handoffs/ACTIVE.md` = current task; this file = full path |

### Orchestrator may do without asking Scott

- Implement bounded slices in this document
- Merge PRs after tests pass and scope matches ACTIVE.md
- Update `PROJECT_STATUS.md`, `STAGE_INDEX.md`, `ACTIVE.md`, `QUEUE.md`
- Queue slices in ACTIVE.md / QUEUE.md
- Fix tests, docs, dev-env gaps that block the path

### Orchestrator must pause for Scott

- Any `schema.sql` structure change
- Feature flag `False` → `True` for coach-visible behavior
- Re-enabling auth middleware or exposing to public internet
- Production detector / model changes
- Paid billing / multi-tenant packaging
- Large UX redesigns

Standing approval recorded: Scott 2026-07-05 — follow this completion path autonomously within the gates above.

---

## Phase 1 — Platform core finish (current)

| Stage | Work | Status |
| --- | --- | --- |
| 6A | Module keys + read helpers + audit CLI | **Done** (#72) |
| 6C | Entitlements section on `/status` | **Next** |
| 6B | Soft module gating: `feature_enabled AND is_module_entitled` on add-on routes (scouting, playbook, player_dev) | Queued |
| 6D | Auth + team-scoped checks | **Deferred** — Scott gate |

## Phase 2 — Coach-trust product proof

| Stage | Work |
| --- | --- |
| 7A | Fix dev onboarding: `requirements.txt` → point at `requirements-dev.txt` or add shim |
| 7B | Wire possession counts into film/stats views (read-only, idempotent linker already exists) |
| 7C | Player minutes visible on stats/game surfaces |
| 7D | Review queue: surface unreviewed vs accepted counts on `/status` and `/preview` |
| 7E | Canonical clips: link player_dev clips to canonical_clip_id in UI |

## Phase 3 — Module packaging (soft)

| Stage | Work |
| --- | --- |
| 8A | Seed optional module_entitlements rows for demo modules (stats, scouting) — **additive SQL in helpers migration only if Scott approves schema**; prefer INSERT via backfill helper without schema change |
| 8B | `/preview` shows module enabled/disabled per team |
| 8C | Stats module: box score reads only accepted review_status events |

## Phase 4 — Deploy-ready Liberty (Scott gate)

| Stage | Work |
| --- | --- |
| 9A | Secrets audit: VAPID, SMTP, hardcoded keys |
| 9B | Auth middleware plan + staged re-enable |
| 9C | Docker production smoke on clean VM |
| 9D | Transfer bundle + Hermes/Linux parity doc |

## Phase 5 — AI assist MVP (after trusted data exists)

| Stage | Work |
| --- | --- |
| 10A | Read-only assistant API: answer from reviewed events + stats + clips citations |
| 10B | Guided workflow: game → player → clip list |
| 10C | Do **not** expand ball detector until new labeled benchmark |

---

## Explicit deferrals

- Secondary classifier, temporal filters, feature filters (not production candidates)
- New detector training without new labeled data
- Stripe/billing
- Multi-customer hosting

## Success definition

Scott opens `/preview` and `/status`, uploads film, tags events, reviews queue, sees stats/minutes and module state — all on one SQLite ledger without manual agent relay. Tests green on Python 3.12.

## Related

- `docs/agent_handoffs/QUEUE.md` — ordered upcoming slices
- `docs/ORCHESTRATION.md` — agent roles and billing
- `MODULAR_PRODUCT_ROADMAP.md` — product modules
- `docs/STAGE_INDEX.md` — stage numbering
