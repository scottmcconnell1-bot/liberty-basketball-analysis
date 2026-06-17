# Roadmap

Updated: 2026-06-16
Branch: jason-5-may-updates

## Current Operating Mode

Codex is taking over as primary engineering lead. The immediate roadmap is evidence-first, but the product direction is now modular and coach-first: build a trusted basketball operations core, add modules in stages, and layer AI assistant capabilities on top of reviewed data.

Current product architecture docs:
- PRODUCT_BENCHMARKS.md
- MODULAR_PRODUCT_ROADMAP.md
- AI_ASSISTANT_VISION.md

## Near-Term Priorities

### 1. Modular Product Architecture

Status: In progress

Goals:
- Use PRODUCT_BENCHMARKS.md to mimic proven product patterns without copying proprietary work.
- Use MODULAR_PRODUCT_ROADMAP.md to define base platform and paid add-on modules.
- Use AI_ASSISTANT_VISION.md to keep the long-term AI assistant coach goal visible.
- Keep the base platform useful without advanced computer vision.
- Preserve one shared event ledger across all modules.

### 2. Source of Truth Stabilization

Status: In progress

Goals:
- Maintain PROJECT_VISION.md, ROADMAP.md, PROJECT_STATUS.md, and DECISION_LOG.md.
- Keep AUTHORITY.md and docs/CODEX_BRIEFING.md aligned with current workflow.
- Replace stale chat-history knowledge with repository documentation.

### 3. Repository Baseline Audit

Status: In progress

Goals:
- Confirm active branch and app architecture.
- Confirm entry points, blueprints, scripts, tests, deployment files, datasets, and model artifacts.
- Record all findings as Proven, Inferred, or Unknown.

### 4. Schema and Data-Model Risk Review

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

### 5. Ball Detection Audit

Status: Production switch and threshold tuning verified; post-processing experiments measured

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
- Hermes/OWL verified commit 2c31954 on Linux: 186/186 tests passed and production path loads models/ball_detector.pt class 0 at conf=0.15.
- Hermes/OWL benchmark smoke found detections in 4 of 5 positive frames and false positives in 4 of 5 likely negative frames.
- Scott approved raising the production ball confidence default to 0.25 on 2026-06-15.
- Hermes/OWL verified commit 6213a51 on Linux: threshold-only scope and 186/186 tests passed.
- docs/BALL_DETECTION_PRECISION_CLEANUP_REPORT.md reports the best measured single-threshold result at conf=0.25: TP=106, FP=74, FN=2, precision=0.5889, recall=0.9815, F1=0.7361.
- The GT-dependent adaptive court-mask benchmark improved F1, but it uses ground-truth ball positions and is not deployable as production logic.
- The GT-free grid/NMS court-marking variants did not materially improve over the conf=0.25 baseline.
- The corrected secondary-classifier v3 benchmark retrained from scratch on v2 train frames and evaluated on held-out v2 test frames.
- benchmark/classifier_results_v3.csv reports held-out test baseline F1=0.7529 and classifier F1=0.7632, while recall drops from 0.9697 to 0.8788.
- docs/CLASSIFIER_EXPERIMENT_REPORT.md marks the secondary classifier as not a production candidate with the current 180-crop dataset.
- The corrected feature-based filter experiment in commit 6361ab1 scored all 180 detections and reports held-out test baseline F1=0.7529 and rf_r95 F1=0.7568 with recall=0.8485.
- docs/FEATURE_FILTER_EXPERIMENT_REPORT.md marks feature-based filters as not production candidates.
- Scott approved a benchmark-only temporal consistency experiment on 2026-06-16.
- The temporal consistency benchmark in commit fedcab7 reports held-out v2 test temporal_len2 F1=0.6316 and recall=0.5455, worse than the baseline F1=0.7529 and recall=0.9697.
- docs/TEMPORAL_CONSISTENCY_EXPERIMENT_REPORT.md marks temporal consistency filters as not production candidates and discloses the 120 evaluated-frame count plus cross-split temporal-context caveat.

Next step:
- Do not deploy the current secondary classifier.
- Do not deploy the current feature-based filters.
- Do not deploy the current temporal consistency filters.
- Keep production ball detection at models/ball_detector.pt, class 0, conf=0.25.
- Move next to the base platform gap audit against MODULAR_PRODUCT_ROADMAP.md before adding more detector post-processing experiments.

### 6. Product Module Roadmap

Status: Direction approved, implementation not started

Base Platform:
- Teams, players, rosters, seasons, games
- Video assets
- Manual tagging
- Canonical event ledger
- Clips
- Review/correction workflow
- Basic reports

Modules:
- Stats
- Minutes and lineups
- Film room
- Scouting
- Playbook and play recognition
- Strategy
- AI assist
- Advanced tracking

Implementation rule:
- Modules may be packaged or priced separately later, but they must share one event ledger and provenance model.

### 7. Data Governance

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
