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
