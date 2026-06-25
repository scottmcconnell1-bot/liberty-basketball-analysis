# Decision Log

Updated: 2026-06-16
Branch: jason-5-may-updates

This file records project decisions that should not live only in chat history. New entries must include the decision, rationale, decision maker, and evidence when available.

## 2026-06-14

### Decision: jason-5-may-updates is the working branch

Decision maker: Scott, confirmed through OWL/Rex coordination

Rationale:
- The main branch is stale.
- jason-5-may-updates contains the active blueprint-based Flask app, tests, Docker assets, experiments, and AI pipeline.
- Codex's Windows audit matched the jason-5-may-updates codebase.

Evidence:
- docs/CODEX_BRIEFING.md on jason-5-may-updates.
- docs/OWL_SUMMARY_FOR_CODEX.md on jason-5-may-updates.
- GitHub branch comparison reported jason-5-may-updates as the active working branch in project docs.

### Decision: Codex is primary engineering lead

Decision maker: Scott

Rationale:
- Codex has repository access and can maintain code, docs, audits, and implementation plans.
- Engineering execution inside the repository should have one owner to reduce agent drift.

Evidence:
- AUTHORITY.md.
- docs/CODEX_BRIEFING.md.

### Decision: Hermes / OWL owns infrastructure execution and independent verification

Decision maker: Scott

Rationale:
- Separates repository engineering from local machine, deployment, cron, backup, and production verification responsibilities.
- Provides independent evidence and audit capability.

Evidence:
- AUTHORITY.md.
- docs/OWL_SUMMARY_FOR_CODEX.md.

### Decision: Repository evidence outranks agent memory

Decision maker: Scott

Rationale:
- Prior confusion came from stale branch assumptions and agent memory.
- Future claims must distinguish Proven, Inferred, and Unknown.

Evidence:
- PROJECT_STATUS.md.
- docs/CODEX_BRIEFING.md.
- VISION.md principle: Evidence over assumptions.

### Decision: No schema.sql changes without Scott approval

Decision maker: Scott

Rationale:
- schema.sql is the database source of truth.
- Schema changes can affect existing data and workflows.

Evidence:
- AUTHORITY.md.
- docs/CODEX_BRIEFING.md.

### Decision: Separate relational game ID from analysis key

Decision maker: Scott

Date: 2026-06-14

Decision:
- Adopt simplified Option C from docs/GAME_ID_SCHEMA_FIX_PROPOSAL.md.
- Use analysis_runs.game_id as the optional INTEGER relation to games.id.
- Add analysis_runs.analysis_key as the TEXT identity used by AI/video analysis runs.
- Stop creating manual event rows under "default_game".
- Migrate downstream TEXT game_id usage per feature as data accumulates.

Evidence:
- OWL/Hermes Stage 1 audit found the live database had 1 games row and 0 rows in events, stats, analysis_runs, detections, videos, player_minutes, shot_classifications, play_recognitions, player_effect, and human_corrections.
- OWL/Hermes Stage 1 audit found no "default_game" values.
- Scott approved the simplified Option C direction before implementation.
- PR #7 merged into jason-5-may-updates on 2026-06-14 with merge commit 33c9935.
- OWL/Hermes verified 203 passing tests and 3 pre-existing failures that also reproduce on base.

## Pending Decisions

### Pending: downstream game_id migrations

Current evidence:
- events.game_id, detections.game_id, stats.game_id, and related analysis tables still use TEXT keys.
- The current fix intentionally keeps those downstream keys as analysis keys in this stage.

Decision needed:
- Which downstream feature should be migrated first, and whether standalone analysis runs must attach to a relational games row.

### Pending: ball detection rebuild path

Current evidence:
- v14 detector top-20 audit found 0 basketball detections.
- finetune2 recorded zero precision, recall, and mAP.

Decision needed:
- Whether to rebuild detector after the benchmark, improve data governance first, or prioritize manual/coaching workflows while detector data governance is repaired.

### Decision: Build ball detection benchmark before detector rebuild

Decision maker: Scott

Date: 2026-06-14

Decision:
- Build a labeled ball detection benchmark before retraining or replacing the detector.
- Use 30-50 representative frames with positive and negative examples.
- Evaluate current production detector behavior and existing model artifacts before considering a rebuilt detector.

Evidence:
- docs/BALL_DETECTION_AUDIT_2026-06-14.md reports the production path uses base YOLOv8 COCO sports-ball class 32 rather than the fine-tuned ball detector.
- docs/BALL_DETECTION_AUDIT_2026-06-14.md reports no completed formal precision/recall benchmark because precision_recall.csv was empty.
- Scott approved the benchmark-first path on 2026-06-14.

Follow-up:
- Completed in commits e667e26, c517043, and f9049e4.
- Codex verified committed CSVs, aggregate totals, report consistency, fixed height normalization, and Git LFS fetchability on 2026-06-14.

### Decision: Ball detection benchmark is accepted as the next production decision input

Decision maker: Codex verification, pending Scott acceptance

Date: 2026-06-14

Decision:
- Treat docs/BALL_DETECTION_BENCHMARK_2026-06-14.md and benchmark/results_summary.csv as the current benchmark evidence for detector production planning.
- Do not retrain before first correcting the production path, unless Scott decides otherwise.

Evidence:
- benchmark/results_summary.csv reports production YOLOv8n COCO class 32 at conf=0.15: TP=0, FP=11, FN=108, precision=0.0, recall=0.0.
- benchmark/results_summary.csv reports models/ball_detector.pt class 0 at conf=0.15: TP=106, FP=128, FN=2, precision=0.453, recall=0.9815.
- benchmark/results_perframe.csv contains 552 per-frame rows and aggregates to the same totals as benchmark/results_summary.csv.
- docs/BALL_DETECTION_BENCHMARK_2026-06-14.md documents the negative-frame review limitation as Unknown.

Follow-up:
- Scott approved docs/BALL_DETECTION_PRODUCTION_SWITCH_PLAN.md on 2026-06-14.
- Codex implemented the switch and requested Hermes/OWL Linux verification.

### Decision: Switch production ball detection to the fine-tuned model

Decision maker: Scott

Date: 2026-06-14

Decision:
- Keep the configured person detector model for player detection.
- Use a separate ball detector setting for basketball detection.
- Default ball detection to models/ball_detector.pt, class 0, confidence 0.15.

Evidence:
- ai_analyzer.py previously used the same YOLOv8n model for person detection and ball detection, with ball detection fixed to COCO class 32.
- benchmark/results_summary.csv reports YOLOv8n COCO class 32 at conf=0.15 had precision=0.0 and recall=0.0.
- benchmark/results_summary.csv reports models/ball_detector.pt class 0 at conf=0.15 had precision=0.453 and recall=0.9815.

Follow-up:
- Hermes/OWL verified commit 2c31954 on Linux on 2026-06-14: 186/186 tests passed, models/ball_detector.pt was present after git lfs pull, and the production path loaded models/ball_detector.pt class 0 at conf=0.15.
- Precision cleanup is now the next detector decision input.

### Decision: Raise production ball confidence default to 0.25

Decision maker: Scott

Date: 2026-06-15

Decision:
- Change the default ball detection confidence from 0.15 to 0.25.
- Do not add top-1 filtering, NMS, or a court-marking mask in this decision.

Evidence:
- docs/BALL_DETECTION_PRECISION_CLEANUP_REPORT.md reports the best measured single-threshold result at conf=0.25: TP=106, FP=74, FN=2, precision=0.5889, recall=0.9815, F1=0.7361.
- docs/BALL_DETECTION_PRECISION_CLEANUP_REPORT.md reports NMS adds only +0.005 F1 and top-1 reduces F1 to 0.5903.
- Court-marking exclusion remains unmeasured.

Follow-up:
- Hermes/OWL should verify the 0.25 default on Linux after implementation.

### Decision: Do not deploy the current secondary classifier

Decision maker: Scott approved recording the verified outcome; Codex verified repository evidence

Date: 2026-06-15

Decision:
- Do not deploy the MobileNetV2 secondary classifier from the current 180-crop benchmark dataset.
- Treat the earlier classifier results in commits 47656e1 and 991611a as superseded because they were contaminated by training/evaluation leakage.
- Treat commit d014193 and benchmark/classifier_results_v3.csv as the current classifier decision evidence.

Rationale:
- The corrected v3 experiment retrained from scratch on the v2 stratified train split and evaluated on held-out v2 test frames.
- The classifier provides only a negligible held-out F1 improvement and reduces recall below the project threshold.
- Ball detection recall remains important for downstream basketball analysis, possession review, and coach workflow; a post-processing filter that drops too many true balls should not be promoted to production.

Evidence:
- benchmark_classifier_v2.py trains a new model from v2 train frames and saves models/court_fp_classifier_v2.pt.
- benchmark/classifier_results_v3.csv reports held-out test baseline: TP=32, FP=20, FN=1, precision=0.6154, recall=0.9697, F1=0.7529.
- benchmark/classifier_results_v3.csv reports held-out test classifier: TP=29, FP=14, FN=4, precision=0.6744, recall=0.8788, F1=0.7632.
- benchmark/classifier_results_v3.csv reports held-out test classifier_nms matches classifier at F1=0.7632.
- Codex verified on 2026-06-15 that the v2 train/test split has 82 train frames, 37 test frames, and 0 overlap, and that classifier_detection_scores_v3.csv contains 128 train crops and 52 test crops.

Follow-up:
- Keep production at the fine-tuned ball detector with ball_confidence=0.25.
- Revisit secondary classification only with substantially more labeled hard-negative and hard-positive crop data or a simpler feature-based approach that can be validated on held-out frames.

### Decision: Do not deploy current feature-based false-positive filters

Decision maker: Scott approved recording the verified outcome; Codex verified repository evidence

Date: 2026-06-16

Decision:
- Do not deploy the current Logistic Regression or Random Forest feature-based false-positive filters.
- Treat commit 6361ab1 and benchmark/feature_filter_results.csv as the current feature-filter decision evidence.
- Keep any further detector post-processing work benchmark-only until held-out evidence supports production use.

Rationale:
- The corrected feature-filter evaluation scores all 180 detections and reports train/test/all metrics from real model outputs.
- The best train-selected feature filter provides only negligible held-out F1 improvement and reduces recall below the project threshold.
- Single-frame geometry, location, color, shape, texture, and detector-confidence features do not separate balls from court-marking false positives well enough in the current benchmark.

Evidence:
- benchmark/feature_filter_scores.csv contains 180 scored detections: 128 train crops and 52 held-out test crops.
- benchmark/feature_filter_results.csv reports held-out test baseline: TP=32, FP=20, FN=1, precision=0.6154, recall=0.9697, F1=0.7529.
- benchmark/feature_filter_results.csv reports held-out test rf_r95: TP=28, FP=13, FN=5, precision=0.6829, recall=0.8485, F1=0.7568.
- Codex verified on 2026-06-16 that benchmark_feature_eval.py scores all detections, benchmark_feature_filters.py and benchmark_feature_eval.py compile, and docs/FEATURE_FILTER_EXPERIMENT_REPORT.md marks feature filters as not production candidates.

Follow-up:
- Run a benchmark-only temporal consistency experiment next.
- Do not change production detector behavior without a separate Scott approval after benchmark evidence is reviewed.

### Decision: Run benchmark-only temporal consistency experiment

Decision maker: Scott

Date: 2026-06-16

Decision:
- Use temporal consistency as the next detector-quality experiment.
- Keep the experiment benchmark-only with no production code changes.
- Evaluate whether frame-to-frame motion can reject static court-marking false positives while preserving ball recall.

Rationale:
- Previous single-frame post-processing attempts failed to meet the project recall/F1 bar.
- Static court markings should behave differently from a basketball across nearby frames.
- Temporal filtering may use information that single-frame crop classifiers and feature filters cannot see.

Evidence:
- docs/CLASSIFIER_EXPERIMENT_REPORT.md rejects the MobileNet secondary classifier under current evidence.
- docs/FEATURE_FILTER_EXPERIMENT_REPORT.md rejects the current feature-based filters under current evidence.
- Scott selected temporal consistency after feature-filter verification.

Follow-up:
- Hermes/OWL should implement and run the benchmark-only temporal consistency experiment and provide committed artifacts for Codex verification.

### Decision: Do not deploy current temporal consistency filters

Decision maker: Scott

Date: 2026-06-16

Decision:
- Do not deploy the current temporal consistency filters.
- Treat commit fedcab7 and benchmark/temporal_results.csv as benchmark-only evidence.
- Keep production ball detection at models/ball_detector.pt, class 0, conf=0.25 until stronger evidence supports another change.

Rationale:
- benchmark/temporal_results.csv reports held-out v2 test baseline F1=0.7529 and recall=0.9697.
- The best temporal test recall is 0.5455 for temporal_len2, far below the project recall threshold of 0.95.
- Temporal len2 improves precision from 0.6154 to 0.7500, but reduces F1 from 0.7529 to 0.6316.
- Temporal len3 and temporal_mov2 reduce recall even further.

Evidence:
- benchmark/temporal_detection_scores.csv contains 180 detections from models/ball_detector.pt at conf=0.25.
- benchmark/temporal_tracks.csv contains 133 tracks.
- benchmark/temporal_results.csv reports temporal_len2 test: TP=18, FP=6, FN=15, precision=0.7500, recall=0.5455, F1=0.6316.
- Codex verified on 2026-06-17 that benchmark_temporal.py compiles, the commit is benchmark-only, no production code changed, and docs/TEMPORAL_CONSISTENCY_EXPERIMENT_REPORT.md now discloses the 120 evaluated-frame count and cross-split temporal-context caveat.

Follow-up:
- Stop pursuing single-frame or simple temporal post-processing as the primary near-term path unless new labeled evidence changes the detector-quality picture.
- Move the next planning step to the base platform gap audit against MODULAR_PRODUCT_ROADMAP.md.

### Decision: Implement Platform Core Schema Stage 1

Decision maker: Scott

Date: 2026-06-17

Decision:
- Implement Stage 1 from docs/PLATFORM_CORE_SCHEMA_PLAN.md.
- Keep the change additive only.
- Do not implement possessions, canonical clips, review queues, event ledger rewrites, or downstream TEXT game_id cleanup in this stage.

Scope:
- Add teams.
- Add roster_memberships.
- Add video_assets.
- Add event_types.
- Add provenance_records.
- Add module_entitlements.
- Add schema tests for the new tables.

Rationale:
- The base platform needs shared identity, media, taxonomy, provenance, and module entitlement foundations before paid packages or AI assistant behavior are built.
- Additive tables reduce risk and preserve current routes while establishing the next data model layer.

Verification required:
- Codex local SQLite verification for fresh schema and idempotent migration SQL.
- Hermes/OWL Linux verification with the full pytest suite before treating the implementation as fully verified.

### Decision: Adopt modular basketball operations platform direction

Decision maker: Scott

Date: 2026-06-16

Decision:
- Define Liberty as a modular basketball operations platform, not a detector-first project.
- Support a base platform plus add-on modules that can become paid packages for clients.
- Keep all modules tied to one shared event ledger, review workflow, and provenance model.
- Treat the long-term AI goal as an assistant coach layered on top of trusted data.

Rationale:
- Perplexity research identified the full product requirements: game breakdown, player minutes, team and player stats, lineups, clips, scouting, play recognition, standout players, strategy notes, and reports.
- Gemini's critique supported a manual-first, AI-assisted build sequence to avoid depending on imperfect computer vision for early product value.
- Scott confirmed the desired client package model and ultimate AI assistant coach goal.

Evidence:
- PRODUCT_BENCHMARKS.md records external product patterns to mimic conceptually.
- MODULAR_PRODUCT_ROADMAP.md defines the base platform and add-on modules.
- AI_ASSISTANT_VISION.md defines the long-term assistant coach interaction model.

Follow-up:
- Audit the current repo schema/routes against the modular product roadmap.
- Decide the first implementation module after documentation: base platform core, stats/minutes, film room, or another Scott-approved package.

### Decision: Plan Platform Core Schema Stage 2 Backfill

Decision maker: Scott

Date: 2026-06-17

Decision:
- Proceed with Platform Core Schema Stage 2 planning after Stage 1 schema foundations were implemented and locally verified.
- Keep Stage 2 planning focused on deterministic, additive backfill only.
- Do not implement Stage 2 code until Scott reviews and approves the plan.

Scope:
- Default Liberty team seed/backfill.
- Roster memberships from existing player rows.
- Video asset records from existing verifiable video or analysis inputs.
- Canonical event type seed rows.
- Initial module entitlement seed rows.
- Provenance records for deterministic migration/backfill actions where useful.

Non-scope:
- Possession modeling.
- Canonical clip generation.
- Review queue implementation.
- Event ledger rewrite.
- Paid-package enforcement.
- Ball detection or AI event-generation behavior changes.

Rationale:
- Stage 1 created the platform-core tables, but empty tables do not yet support coach workflows or future modules.
- Stage 2 should make the foundation usable without changing current product behavior.
- Deterministic backfill reduces manual setup while avoiding unsupported basketball facts.

Evidence:
- docs/PLATFORM_CORE_SCHEMA_PLAN.md defines the staged platform-core approach.
- Hermes/OWL reported on 2026-06-17 that Stage 2 backfill does not exist in committed repo state and that Stage 1 tables exist after schema initialization.
- docs/PLATFORM_CORE_SCHEMA_STAGE_2_BACKFILL_PLAN.md records the proposed Stage 2 scope, non-goals, verification requirements, and risks.

Follow-up:
- Scott reviews the Stage 2 backfill plan.
- If approved, Codex implements idempotent backfill helpers and focused tests.
- Hermes/OWL verifies the implementation on Linux before it is treated as complete.

### Decision: Tighten Agent Protocol for Project Isolation and Verification Safety

Decision maker: Scott

Date: 2026-06-18

Decision:
- Update AGENT_PROTOCOL.md with explicit no cross-project contamination rules.
- Update AGENT_PROTOCOL.md with explicit no stash, reset, clean, or destructive checkout rules during verification unless Scott approves the specific action.

Rationale:
- Hermes/OWL included unrelated trader_bot/Alpaca information in Liberty project context.
- Hermes/OWL also used force reset during verification after local checkout conflicts.
- Liberty project truth must come from the Liberty repository and verified evidence, not private memory or unrelated project state.

Evidence:
- Scott approved the protocol update on 2026-06-18.
- AGENT_PROTOCOL.md now requires agents to verify the Liberty repository path and remote before reporting.
- AGENT_PROTOCOL.md now instructs agents to report local-change blockers as Unknown and ask for approval before using stash, reset, clean, or destructive checkout.

Follow-up:
- Hermes/OWL should read AGENT_PROTOCOL.md before the next verification task.
- If local changes block verification, Hermes/OWL should use a clean clone/worktree only after Scott approves the approach.

### Decision: Implement Platform Core Schema Stage 2 Backfill

Decision maker: Scott

Date: 2026-06-18

Decision:
- Implement Stage 2 from docs/PLATFORM_CORE_SCHEMA_STAGE_2_BACKFILL_PLAN.md.
- Keep the implementation additive, deterministic, and idempotent.
- Do not add possession modeling, review queues, paid-package enforcement, event ledger rewrites, or ball detection behavior changes in this stage.

Scope implemented:
- Default Liberty team seed/backfill.
- Roster memberships from existing players.
- Video asset records from existing videos and game sources.
- Canonical event type seed rows.
- Base platform module entitlement.
- Migration provenance records for deterministic backfill actions.
- Focused tests for seed rows, idempotency, and player/video/source backfill.

Rationale:
- Stage 1 created platform-core tables, but the empty tables needed deterministic seed/backfill data before later modules can depend on them.
- Backfill is limited to verifiable repository/database facts and avoids unsupported basketball inferences.

Evidence:
- helpers.py contains the Stage 2 backfill helpers and calls them from _ensure_migration_columns after Stage 1 tables exist.
- tests/test_schema.py verifies Stage 2 seeds, idempotency, roster membership backfill, and video asset backfill.
- Codex local verification on 2026-06-18: tests/test_schema.py reported 11 passed.
- Codex local verification on 2026-06-18: full local app suite reported 189 passed, 1 skipped.

Follow-up:
- Hermes/OWL should verify the Stage 2 implementation on Linux after running AGENT_PROTOCOL.md preflight.
- Scott should choose whether Stage 3 is review workflow planning or possession/canonical clip modeling after Linux verification.

### Decision: Plan Review Workflow Before Possession Modeling

Decision maker: Scott

Date: 2026-06-18

Decision:
- Make Review Workflow Planning the next platform-core step after Stage 2 verification.
- Plan the review workflow before possession modeling or canonical clip implementation.
- Keep this step planning-only until Scott approves implementation.

Rationale:
- Coaches need a trusted way to accept, correct, reject, and annotate data before later modules depend on it.
- The future AI assistant should answer from reviewed facts and clearly separate accepted, inferred, and unknown information.
- Possessions, play recognition, stats, scouting, and strategy reports will be more reliable if built on a reviewed event layer.

Evidence:
- schema.sql already contains events.human_verified, events.confidence, human_corrections, player_development_clips, and provenance_records.
- blueprints/clips.py already exposes event create/list/update/delete APIs.
- player_development.py already exposes clip CRUD helpers for player development clips.
- No review_items table or unified review queue exists yet.
- docs/REVIEW_WORKFLOW_PLAN.md records the proposed Stage 3A review workflow.

Follow-up:
- Scott reviews docs/REVIEW_WORKFLOW_PLAN.md.
- If approved, Codex implements Stage 3A as additive review workflow schema/API work with focused tests.
- Hermes/OWL verifies the implementation on Linux before Stage 3A is treated as complete.

### Decision: Implement Review Workflow Stage 3A

Decision maker: Scott

Date: 2026-06-23

Decision:
- Implement Stage 3A from docs/REVIEW_WORKFLOW_PLAN.md.
- Keep the implementation additive and API/test focused.
- Do not implement possession modeling, canonical clips, paid-package enforcement, review UI, model training, or ball detection changes in this stage.

Scope implemented:
- review_items table.
- events review state fields: review_status, source_type, reviewed_by_user_id, reviewed_at, and review_notes.
- Idempotent backfill from human_verified to accepted/pending review states.
- Review queue rows for pending events.
- Event review APIs for listing, accepting, correcting, and rejecting events.
- human_corrections records for correction and rejection actions.
- provenance_records rows for review actions.
- Tests for schema, idempotent backfill, and review API behavior.

Rationale:
- Coaches need a trust layer before possessions, strategy, scouting, and AI assistant answers depend on event data.
- Review states let the project distinguish proven coach-reviewed facts from pending AI/manual/inferred data.

Evidence:
- Codex local verification on 2026-06-23: focused Stage 3A tests reported 18 passed.
- Codex local verification on 2026-06-23: full local app suite reported 195 passed, 1 skipped.
- Hermes/OWL Linux verification on GitHub issue #18 reported all 9 Stage 3A checks Proven, Linux pytest at 195 passed and 1 skipped, and idempotent review backfill.

Follow-up:
- Scott should choose whether the next slice is review UI, possession modeling, or canonical clips.

### Decision: Plan Review UI as Stage 3B

Decision maker: Scott

Date: 2026-06-23

Decision:
- Make Review UI the next platform-core slice after verified Review Workflow Stage 3A.
- Plan Stage 3B before implementation.
- Keep Stage 3B focused on a coach-facing review queue page backed by existing Stage 3A APIs.

Rationale:
- Stage 3A created review status, review_items, human_corrections wiring, provenance, and review APIs.
- Coaches need a usable page to turn pending events into accepted/corrected/rejected data before possessions, canonical clips, stats trust, and AI assistant answers rely on those events.
- A lightweight page can improve workflow without changing schema or detector behavior.

Evidence:
- GitHub issue #18 records Hermes/OWL Linux verification of Stage 3A: all 9 checks Proven and pytest at 195 passed, 1 skipped.
- docs/REVIEW_UI_PLAN.md records the proposed Stage 3B scope and non-goals.

Follow-up:
- Scott reviews docs/REVIEW_UI_PLAN.md.
- If approved, Codex implements Stage 3B with route/template/static tests and then requests Hermes/OWL verification.

### Decision: Implement Review UI Stage 3B

Decision maker: Scott

Date: 2026-06-24

Decision:
- Implement Stage 3B from docs/REVIEW_UI_PLAN.md.
- Keep the implementation UI/API-client focused.
- Do not add schema changes, possession modeling, canonical clips, paid-package enforcement, model training, or ball detection changes in this stage.

Scope implemented:
- GET /review route gated by ENABLE_MANUAL_TAG_MVP.
- Review Queue navigation under Film & Stats.
- templates/review_events.html coach review queue page.
- Filters for review status, game_id, event_type, source_type, player, and confidence range.
- Event detail panel with editable correction fields.
- Accept, correct, and reject actions backed by the existing Stage 3A review APIs.
- Route/template tests for Review UI rendering, navigation visibility, and feature gating.

Rationale:
- Stage 3A created the review data model and APIs, but coaches need a usable page to convert pending event data into accepted, corrected, or rejected facts.
- The future AI assistant, possessions, stats, scouting, and strategy modules should depend on reviewed data rather than raw pending detections.

Evidence:
- Codex local Windows verification on 2026-06-25: focused Review UI/API tests reported 7 passed.
- Codex local Windows verification on 2026-06-25: full local app suite reported 198 passed, 1 skipped.

Follow-up:
- Hermes/OWL verified Stage 3B on Linux through GitHub issue #31: 198 passed, 1 skipped, with no forbidden behavior changes.

### Decision: Implement Possessions and Canonical Clips Foundation Stage 3C

Decision maker: Scott

Date: 2026-06-25

Decision:
- Continue the approved platform-core roadmap without waiting for another next-task approval.
- Implement Stage 3C as an additive possession and canonical clip foundation.
- Do not implement possession inference, automatic clipping, UI changes, paid-package enforcement, model training, or ball detection changes in this stage.

Scope implemented locally:
- possessions table.
- clips table.
- clip_tags table.
- events.possession_id optional link column.
- player_development_clips.canonical_clip_id optional link column.
- Schema tests for table existence, link columns, idempotency, and manual event-possession-clip linkage.

Rationale:
- Possessions and canonical clips are required before reliable stats, scouting, strategy, film-room reuse, and AI assistant citations can share the same reviewed basketball units.
- The first slice should create the foundation without changing current event workflows.

Evidence:
- Codex local Windows verification on 2026-06-25: tests/test_schema.py reported 16 passed; the full local app suite reported 201 passed, 1 skipped.

Follow-up:
- Run full local app suite.
- Push Stage 3C after local verification.
- Request Hermes/OWL Linux verification through GitHub.

### Decision: Lock Stage Numbering

Decision maker: Codex under Scott standing approval

Date: 2026-06-25

Decision:
- Create docs/STAGE_INDEX.md as the source of truth for platform stage numbering.
- Preserve completed stage names instead of rewriting history.
- Lock Stage 3B as Review UI and Stage 3C as Possessions and Canonical Clips Foundation.

Rationale:
- Stage 3B was used for Review UI after Stage 3A, while the older platform plan also referenced possessions/clips as Stage 3B.
- Renaming completed work would confuse GitHub issues, commits, and Hermes/OWL verification reports.
- A locked index prevents future agents from reusing or renumbering stages.

Evidence:
- GitHub issue #31 verified Stage 3B Review UI.
- Commit f1c3d09 implements Stage 3C Possessions and Canonical Clips Foundation.

Follow-up:
- Hermes/OWL should verify Stage 3C through issue #35.
- Future reports should reference docs/STAGE_INDEX.md before naming stages.
