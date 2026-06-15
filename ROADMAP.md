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

Status: Merged

Verified issue before fix branch:
- schema.sql defines games.id as INTEGER.
- schema.sql defines events.game_id and stats.game_id as TEXT.
- blueprints/clips.py previously defaulted saved events to game_id = "default_game".

Completed:
- PR #7 merged into jason-5-may-updates at merge commit 33c9935.
- analysis_runs.game_id is now the optional INTEGER relation to games.id.
- analysis_runs.analysis_key is now the required TEXT AI/video run identity.
- Manual event saves now reject missing or unknown relational game_id.
- OWL/Hermes verified 203 passing tests and 3 pre-existing failures on Linux.
- Commit 46d2132 fixed the 3 pre-existing failures.
- OWL/Hermes reported 185 passing tests and 0 failures on Linux after commit 46d2132.

Remaining:
- Preserve downstream TEXT analysis-key columns until each feature is migrated deliberately.

### 4. Ball Detection Audit

Status: Production switch implemented; awaiting Hermes/OWL verification

Verified issue:
- experiments/detector_audit_top20/AUDIT_RESULTS.md reports v14 detector had zero basketball detections in its top 20 detections.
- docs/VERIFIED_PROJECT_FACTS.md reports finetune2 produced zero precision, recall, and mAP across recorded epochs.
- docs/BALL_DETECTION_AUDIT_2026-06-14.md reports the production path uses base YOLOv8 COCO class 32 rather than the fine-tuned ball detector.
- docs/BALL_DETECTION_AUDIT_2026-06-14.md reports no completed formal precision/recall benchmark because precision_recall.csv was empty.
- docs/BALL_DETECTION_BENCHMARK_2026-06-14.md reports production YOLOv8n COCO class 32 at conf=0.15 had TP=0, FP=11, FN=108, precision=0.0, recall=0.0.
- docs/BALL_DETECTION_BENCHMARK_2026-06-14.md reports models/ball_detector.pt class 0 at conf=0.15 had TP=106, FP=128, FN=2, precision=0.453, recall=0.9815.
- Codex verified the committed benchmark CSVs and Git LFS model fetchability on 2026-06-14.
- Scott approved docs/BALL_DETECTION_PRODUCTION_SWITCH_PLAN.md on 2026-06-14.
- Codex implemented the production switch so ball detection uses ball_detector_model/class/confidence settings separately from person detection.

Next step:
- Hermes/OWL should independently verify the implementation on Linux.
- After verification, tune ball confidence and expand verified negatives to reduce false positives.

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
