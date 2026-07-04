# Roadmap

Updated: 2026-07-02
Branch: jason-5-may-updates

## Current Operating Mode

Codex is taking over as primary engineering lead. The immediate roadmap is evidence-first, but the product direction is now modular and coach-first: build a trusted basketball operations core, add modules in stages, and layer AI assistant capabilities on top of reviewed data.

Current product architecture docs:
- docs/STAGE_INDEX.md locks stage numbering and must be checked before naming new platform-core stages.
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

Status: Direction approved; base platform Stage 1, Stage 2, Stage 3A, Stage 3B, Stage 3C, Stage 4A, Stage 4B, Stage 4C, and Stage 4D verified

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

Current audit:
- docs/BASE_PLATFORM_GAP_AUDIT.md verifies that many product surfaces already exist, but the platform core is still partial.
- Missing or partial foundations include first-class teams, roster memberships, possessions, canonical clips, complete review/correction workflow, module entitlements, and remaining relational game_id cleanup.

Current implementation:
- Scott approved Stage 1 on 2026-06-17.
- Stage 1 adds teams, roster_memberships, video_assets, event_types, provenance_records, and module_entitlements as additive schema foundations.
- Hermes/OWL reported Linux verification for Stage 1 on 2026-06-17: remote HEAD 9066936, 186 passed, 1 skipped, and all six Stage 1 tables exist.
- Scott approved proceeding with Stage 2 planning on 2026-06-17.
- docs/PLATFORM_CORE_SCHEMA_STAGE_2_BACKFILL_PLAN.md defines the proposed deterministic backfill for default Liberty team, roster memberships, video_assets, event_types, module_entitlements, and provenance records.
- Scott approved Stage 2 implementation on 2026-06-18.
- Stage 2 adds idempotent helpers.py backfill logic and tests/test_schema.py coverage for deterministic seeds, repeated initialization, and player/video/source backfill.
- Codex local Windows verification reported 189 passed, 1 skipped on 2026-06-18.
- Hermes/OWL Linux verification reported 189 passed, 1 skipped and stable idempotency counts after init_db ran twice on 2026-06-18.
- Scott selected Review Workflow Planning as the next platform-core step on 2026-06-18.
- docs/REVIEW_WORKFLOW_PLAN.md defines Stage 3A: review_items, event review state, human_corrections wiring, review APIs, and accepted/corrected/rejected event states.
- Scott approved Stage 3A implementation on 2026-06-23.
- Stage 3A adds review_items, event review state columns, review-state backfill, event review APIs, human_corrections wiring, and focused tests.
- Codex local Windows verification reported 195 passed, 1 skipped on 2026-06-23.
- Hermes/OWL Linux verification on GitHub issue #18 reported all 9 Stage 3A checks Proven, Linux pytest at 195 passed and 1 skipped, and idempotent review backfill.
- Possessions, canonical clips, event ledger rewrites, and downstream TEXT game_id cleanup remain deferred to later approved stages.
- Scott selected Review UI as the next slice after Stage 3A verification.
- docs/REVIEW_UI_PLAN.md defines the proposed Stage 3B coach review queue page.
- Scott approved Stage 3B implementation on 2026-06-24.
- Stage 3B adds a feature-gated Review Queue page, navigation, filters, event detail editing, and accept/correct/reject controls backed by the Stage 3A APIs.
- Codex local Windows verification reported 198 passed, 1 skipped on 2026-06-25.
- Hermes/OWL Linux verification on GitHub issue #31 reported all requested Stage 3B checks passed, Linux pytest at 198 passed and 1 skipped, and no forbidden behavior changes.
- Scott gave standing approval on 2026-06-24 for Codex and Hermes/OWL to continue approved roadmap work without waiting for each next-task approval.
- Stage 3C Possessions and Canonical Clips Foundation is implemented and Hermes/OWL verified.
- Stage 3C adds additive possessions, clips, and clip_tags schema plus event/clip link columns, without possession inference, clipping automation, UI changes, detector work, or paid-package enforcement.
- Codex local Windows verification reported 201 passed, 1 skipped on 2026-06-25.
- Hermes/OWL Linux verification on issue #35 confirmed commit f1c3d09 with 198 passed, 1 skipped.
- Stage 4A Event Participants Foundation is implemented and Hermes/OWL verified.
- Stage 4A adds event_participants and event relational identity/player/team link columns without changing event-generation behavior, stats derivation, UI, detector settings, or paid-package enforcement.
- Hermes/OWL Linux verification for Stage 4A: HEAD matched origin at 3945d07, 225 passed, 1 skipped, event_participants and relational columns verified present, and legacy player-name backfill idempotent.
- Stage 4B Manual Event Write Upgrade is implemented and Hermes/OWL verified.
- Stage 4B wires save_event to relational_game_id, event_type_id, team_id, primary_player_id, event_participants, and possession_id; adds assign_possessions_for_game() idempotent possession linker.
- Commit 3945d07 implements Stage 4B save_event relational wiring.
- Stage 4C Relational Stats Derivation is implemented and Hermes/OWL verified.
- Stage 4C.1 (commit ad1fc67): stats.aggregate_stats reads event_types taxonomy via event_type_id JOIN; counts_for_stats=1 filtering; review_status='rejected' exclusion; legacy event_type alias seeds (two_attempt, three_attempt, shot, 2pt, 3pt, rebound) added.
- Stage 4C.2 (commit 415ec3f): corrects VALUES placeholder count in save_event INSERT; adds assign_possessions_for_game() idempotent possession linker; explicit possession_id support in /api/save_event (NULL when absent); 7 focused possession tests all passed.
- Full Linux pytest at HEAD 415ec3f: 225 passed, 1 skipped.
- Stage 4D Player Minutes Foundation is complete and remote at commit 8e67e42.
- Stage 5A Relational game_id cleanup for `stats` and `player_minutes` is implemented at `c42346d`.
- Stage 5B Relational game_id cleanup for `player_development_clips` is implemented at `6a8f9ab`.
- Stage 5C Relational game_id cleanup for `shot_classifications` is implemented at `5fa69f4`.
- Stage 5D Relational game_id cleanup for `play_recognitions` is implemented at `372e81c`.
- Stage 5E Relational game_id cleanup for `player_effect` is implemented at `0b0ad40`.
- Stage 5F Relational game_id cleanup for `human_corrections` is implemented at `a923ee8`.
- The repo now carries additive downstream `relational_game_id` support across the Stage 5A-5F analysis/review outputs while preserving legacy TEXT `game_id` behavior.
- Post-Stage-5 event read-path relational alignment is implemented at `d1a1b2c`.

Next step:
- Keep documentation and handoff artifacts synchronized with the actual bounded slices already implemented on `jason-5-may-updates`.
- Target the next bounded identity seam at event lifecycle cleanup: legacy generated-event delete/replace paths in `event_generator.py` and `blueprints/ai.py` still key by TEXT analysis key and should be aligned to canonical relational game identity with legacy fallback.

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
