# Roadmap

Updated: 2026-06-14
Branch: jason-5-may-updates

## Current Operating Mode

Codex is taking over as primary engineering lead. The immediate roadmap is evidence-first: verify the current system, document known risks, and avoid new feature work until the baseline is clear.

## Near-Term Priorities

### 1. Source of Truth Stabilization

Status: In progress

Goals:
- Maintain PROJECT_VISION.md, ROADMAP.md, PROJECT_STATUS.md, and DECISION_LOG.md.
- Keep AUTHORITY.md and docs/CODEX_BRIEFING.md aligned with current workflow.
- Replace stale chat-history knowledge with repository documentation.

### 2. Repository Baseline Audit

Status: In progress

Goals:
- Confirm active branch and app architecture.
- Confirm entry points, blueprints, scripts, tests, deployment files, datasets, and model artifacts.
- Record all findings as Proven, Inferred, or Unknown.

### 3. Schema and Data-Model Risk Review

Status: Needs Scott approval before schema changes

Verified issue:
- schema.sql defines games.id as INTEGER.
- schema.sql defines events.game_id and stats.game_id as TEXT.
- blueprints/clips.py defaults saved events to game_id = "default_game".

Next step:
- Propose a narrow schema/app fix with migration considerations and tests.
- Do not change schema.sql until Scott approves.

### 4. Ball Detection Audit

Status: Required before detector rebuild

Verified issue:
- experiments/detector_audit_top20/AUDIT_RESULTS.md reports v14 detector had zero basketball detections in its top 20 detections.
- docs/VERIFIED_PROJECT_FACTS.md reports finetune2 produced zero precision, recall, and mAP across recorded epochs.

Next step:
- Inventory active detector architecture, datasets, labels, validation method, and model artifacts.
- Establish a benchmark before rebuilding.

### 5. Data Governance

Status: Needs improvement

Goals:
- Document every dataset and model artifact.
- Record label source, review status, confidence, contamination risk, and platform-specific paths.
- Make dataset provenance usable across both Linux and Windows environments.

## Deferred Work

Do not start new feature expansion until the baseline is documented and major risks are triaged.

Deferred examples:
- New AI event features.
- New ball detection training runs.
- UI expansion beyond verified bug fixes.
- Production exposure changes before auth/secrets review.

## Approval Gates

Scott approval is required for:
- schema.sql changes
- feature scope changes
- new tables or columns
- feature flag changes
- API design changes
- UI/UX flow changes
- production/deployment direction changes
- merging work into jason-5-may-updates