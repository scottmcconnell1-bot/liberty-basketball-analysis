# Project Status

Updated: 2026-07-02
Branch: jason-5-may-updates

## Proven

These facts were verified from repository files, GitHub metadata, or OWL/Hermes local-machine audit.

- The working branch is jason-5-may-updates.
- main is stale for current project work.
- The repository contains a Flask application with blueprint-based routing.
- app.py registers blueprints including messaging, users, core, games, clips, stats, practice, player_dev, ai, playbook, scouting, and bulk_import.
- schema.sql is the database schema source file.
- The repo contains tests under tests/.
- The repo contains Docker and deployment assets.
- The repo contains experiments and detector audit artifacts.
- .gitignore exists on jason-5-may-updates and ignores film_analysis.db, uploads/, __pycache__/, .venv/, model weights, generated media, logs, and experiment outputs.
- schema.sql defines games.id as INTEGER.
- schema.sql defines analysis_runs.game_id as INTEGER and analysis_runs.analysis_key as TEXT.
- schema.sql defines events.game_id as TEXT.
- schema.sql defines stats.game_id as TEXT.
- blueprints/clips.py rejects missing manual event game_id instead of defaulting to "default_game".
- PR #7 merged into jason-5-may-updates on 2026-06-14 with merge commit 33c9935.
- OWL/Hermes verified PR #7 on Linux and reported 203 passing tests with 3 failures that also exist on the base jason-5-may-updates branch.
- Commit 46d2132 fixed the 3 pre-existing test failures tracked as issues #10, #11, and #12.
- OWL/Hermes verified commit 46d2132 on Linux and reported 185 passing tests with 0 failures.
- OWL/Hermes audited `/home/monk-admin/PROJECTS/liberty-basketball-analysis/film_analysis.db` on 2026-06-14.
- The audited database has 1 row in games and 0 rows in events, stats, analysis_runs, detections, videos, player_minutes, shot_classifications, play_recognitions, player_effect, and human_corrections.
- The audited database has no `default_game` values and no downstream text game_id values to migrate.
- experiments/detector_audit_top20/AUDIT_RESULTS.md reports v14 produced 0 basketball detections in the top 20 inspected detections.
- docs/VERIFIED_PROJECT_FACTS.md reports finetune2 had zero precision, recall, and mAP across recorded epochs.
- docs/DATASET_INVENTORY.md documents ball_dataset at /home/monk-admin/PROJECTS/liberty-basketball-analysis/ball_dataset with 5 images and 5 labels.
- docs/BALL_DETECTION_AUDIT_2026-06-14.md was imported from origin/dataset-v2 commit 321b262 into jason-5-may-updates without merging the dataset-v2 branch.
- docs/BALL_DETECTION_AUDIT_2026-06-14.md reports the production detector path uses base YOLOv8 COCO sports-ball class 32, not the fine-tuned ball detector.
- docs/BALL_DETECTION_AUDIT_2026-06-14.md reports audit_detector.py did not complete formal precision/recall validation because precision_recall.csv was empty.
- Scott approved building a ball detection benchmark first on 2026-06-14.
- docs/BALL_DETECTION_BENCHMARK_PLAN.md defines the approved benchmark scope, acceptance criteria, and Hermes/OWL handoff.
- Hermes/OWL completed the ball detection benchmark on jason-5-may-updates in commits e667e26, c517043, and f9049e4.
- docs/BALL_DETECTION_BENCHMARK_2026-06-14.md reports a 138-frame benchmark with 108 positive frames and 30 likely negative frames.
- benchmark/results_summary.csv reports production YOLOv8n COCO class 32 at conf=0.15: TP=0, FP=11, FN=108, precision=0.0, recall=0.0.
- benchmark/results_summary.csv reports models/ball_detector.pt class 0 at conf=0.15: TP=106, FP=128, FN=2, precision=0.453, recall=0.9815.
- benchmark/results_perframe.csv contains 552 per-frame rows and aggregates to the same totals as benchmark/results_summary.csv.
- benchmark/contact_sheet.jpg exists and models/*.pt are tracked with Git LFS.
- Codex verified the benchmark CSV presence, row counts, aggregate totals, report consistency, fixed height normalization, and Git LFS fetchability for models/*.pt on 2026-06-14.
- Scott approved the production detector switch plan on 2026-06-14.
- ai_analyzer.py now keeps the configured detector_model for person detection and uses the separate ball_detector_model setting for basketball detection.
- settings_store.py now defaults ball_detector_model to models/ball_detector.pt, ball_class_id to 0, and ball_confidence to 0.15.
- Hermes/OWL verified commit 2c31954 on Linux on 2026-06-14: branch jason-5-may-updates, HEAD 2c31954, models/ball_detector.pt present after git lfs pull, and 186/186 tests passed.
- Hermes/OWL verified the production path loads models/ball_detector.pt class 0 at conf=0.15 on benchmark smoke frames.
- Hermes/OWL benchmark smoke found fine-tuned model detections in 4 of 5 positive frames and false positives in 4 of 5 likely negative frames.
- Scott approved changing the production ball confidence default from 0.15 to 0.25 on 2026-06-15.
- settings_store.py now defaults ball_confidence to 0.25, matching the best measured single-threshold F1 from docs/BALL_DETECTION_PRECISION_CLEANUP_REPORT.md.
- Hermes/OWL verified commit 6213a51 on Linux: branch jason-5-may-updates, HEAD 6213a51, threshold-only scope, and 186/186 tests passed.
- docs/BALL_DETECTION_PRECISION_CLEANUP_REPORT.md reports the best measured single-threshold result at conf=0.25: TP=106, FP=74, FN=2, precision=0.5889, recall=0.9815, F1=0.7361.
- benchmark/court_mask_results.csv reports the best GT-dependent adaptive court-mask variant at F1=0.8653 with adaptive mask plus NMS, but that experiment uses ground-truth ball positions and is not deployable as production logic.
- benchmark/gtfree_results.csv reports the best GT-free grid/NMS variants at F1=0.7413, only +0.0052 over the conf=0.25 baseline.
- Commit d014193 contains the corrected secondary-classifier v3 experiment: retrained from scratch on the v2 stratified train split and evaluated on held-out v2 test frames.
- benchmark/classifier_results_v3.csv reports held-out test baseline F1=0.7529 and held-out test classifier F1=0.7632, with recall dropping from 0.9697 to 0.8788.
- Codex verified on 2026-06-15 that benchmark_classifier_v2.py trains from scratch on v2 train frames, does not load the older leaking classifier model, and writes classifier_results_v3.csv, classifier_per_frame_v3.csv, and classifier_detection_scores_v3.csv.
- docs/CLASSIFIER_EXPERIMENT_REPORT.md now marks the secondary classifier as not a production candidate under the current 180-crop dataset.
- Commit 6361ab1 contains the corrected feature-based false-positive filter experiment artifacts.
- benchmark/feature_filter_scores.csv contains 180 scored detections with 128 train crops and 52 held-out test crops.
- benchmark/feature_filter_results.csv reports held-out test baseline F1=0.7529 and recall=0.9697.
- benchmark/feature_filter_results.csv reports the best train-selected feature-filter held-out test result, rf_r95, at F1=0.7568 and recall=0.8485.
- Codex verified on 2026-06-16 that benchmark_feature_eval.py scores all 180 detections, benchmark_feature_filters.py and benchmark_feature_eval.py compile, and docs/FEATURE_FILTER_EXPERIMENT_REPORT.md marks feature filters as not production candidates.
- Scott approved a benchmark-only temporal consistency experiment as the next detector-quality path on 2026-06-16.
- Commit fedcab7 contains the temporal consistency benchmark artifacts and no production code changes.
- benchmark/temporal_results.csv reports held-out v2 test baseline F1=0.7529 and recall=0.9697.
- benchmark/temporal_results.csv reports temporal_len2 held-out v2 test F1=0.6316 and recall=0.5455, temporal_len3 F1=0.3721 and recall=0.2424, and temporal_mov2 F1=0.4000 and recall=0.2727.
- Codex verified on 2026-06-17 that benchmark_temporal.py compiles, temporal_results.csv supports the not-production-candidate conclusion, the result rows cover 120 evaluated frames, and 17 tracks span train/test frame labels because tracks are built before split-level scoring.
- Scott clarified on 2026-06-16 that the desired product is a modular basketball operations platform for future client packages, with an ultimate AI assistant coach that can answer coach questions and guide workflows from trusted data.
- PRODUCT_BENCHMARKS.md documents product patterns to mimic conceptually: Hudl, Sportscode/Nacsport/Dartfish, Synergy, FastModel/FastScout, and advanced tracking systems.
- MODULAR_PRODUCT_ROADMAP.md defines the base platform and add-on modules: stats, minutes/lineups, film room, scouting, playbook/play recognition, strategy, AI assist, and advanced tracking.
- AI_ASSISTANT_VISION.md defines typed questions, guided workflows, evidence discipline, and maturity levels for the long-term assistant coach.
- docs/BASE_PLATFORM_GAP_AUDIT.md compares the current repo to the modular product roadmap and identifies the next recommended priority as a Platform Core Data Model Plan.
- docs/PLATFORM_CORE_SCHEMA_PLAN.md defines the proposed core schema stages: teams, roster_memberships, video_assets, event_types, provenance_records, module_entitlements, possessions, canonical clips, review_items, event_participants, and staged downstream game_id cleanup.
- Scott approved Platform Core Schema Stage 1 implementation on 2026-06-17.
- Stage 1 implementation adds teams, roster_memberships, video_assets, event_types, provenance_records, and module_entitlements to schema.sql and the idempotent existing-database migration path in helpers.py.
- tests/test_schema.py now checks that the Stage 1 tables and key columns exist.
- Codex verified locally on 2026-06-17 that schema.sql executes successfully in SQLite and that the helpers.py migration executescript creates all Stage 1 tables.
- Codex created a lightweight Windows development environment in the Documents repo and verified the local test suite on 2026-06-17: 186 passed, 1 skipped. The skipped test is the opt-in Playwright/Chromium live UI overflow audit.
- Hermes/OWL reported Linux verification on 2026-06-17 after correcting a stale local checkout: remote HEAD 9066936, AGENT_PROTOCOL.md present at FETCH_HEAD, 186 passed, 1 skipped, and all six Stage 1 tables exist.
- Scott approved proceeding with Platform Core Schema Stage 2 planning on 2026-06-17.
- docs/PLATFORM_CORE_SCHEMA_STAGE_2_BACKFILL_PLAN.md defines the Stage 2 planning scope: default Liberty team, roster memberships, video_assets, event_types, module_entitlements, provenance, idempotent backfill rules, verification requirements, and non-goals.
- Scott approved Platform Core Schema Stage 2 implementation on 2026-06-18.
- Stage 2 implementation adds deterministic, idempotent backfill in helpers.py for the default Liberty team, roster memberships from players, video_assets from videos/sources, canonical event_types, base_platform module entitlement, and migration provenance records.
- tests/test_schema.py now verifies Stage 2 seed rows, idempotency, and player/video/source backfill behavior.
- pytest.ini now limits default pytest discovery to tests/ so old experiments are not collected by the local app suite.
- tests/conftest.py now gives each test app a temporary UPLOAD_FOLDER so upload/photo tests do not write into the repo uploads directory.
- Codex verified locally on 2026-06-18: tests/test_schema.py reported 11 passed; the full local app suite reported 189 passed, 1 skipped.
- Hermes/OWL verified Platform Core Schema Stage 2 on Linux on 2026-06-18: HEAD 12f73e3, clean working tree, 189 passed, 1 skipped, and idempotency counts remained stable after init_db ran twice.
- Scott selected Review Workflow Planning as the next platform-core step on 2026-06-18.
- docs/REVIEW_WORKFLOW_PLAN.md defines the planned trust layer for pending/accepted/corrected/rejected event review, human_corrections wiring, review_items, event review fields, and coach review APIs.
- Scott approved Review Workflow Stage 3A implementation on 2026-06-23.
- Stage 3A implementation adds review_items, events.review_status, events.source_type, events.reviewed_by_user_id, events.reviewed_at, and events.review_notes to schema.sql and the idempotent migration path.
- Stage 3A backfill maps existing human_verified events to accepted/pending review states and creates review_items for pending events.
- blueprints/clips.py now provides event review APIs: GET /api/review/events, POST /api/review/events/<event_id>/accept, POST /api/review/events/<event_id>/correct, and POST /api/review/events/<event_id>/reject.
- Review correction/rejection actions write human_corrections and review provenance records while preserving rejected events.
- Codex verified locally on 2026-06-23: focused Stage 3A tests reported 18 passed; the full local app suite reported 195 passed, 1 skipped.
- Hermes/OWL verified Review Workflow Stage 3A on GitHub issue #18 on 2026-06-23: HEAD matched origin/jason-5-may-updates at 62fb233, all 9 checklist items were Proven, Linux pytest reported 195 passed and 1 skipped, and init_db review backfill was idempotent.
- Scott selected Review UI as the next slice after Stage 3A verification.
- docs/REVIEW_UI_PLAN.md defines the proposed Stage 3B scope: a coach review queue page backed by the Stage 3A APIs, with filters, detail panel, accept/correct/reject controls, and no new schema.
- Scott approved Review UI Stage 3B implementation on 2026-06-24.
- Stage 3B implementation adds GET /review, Review Queue navigation under Film & Stats, templates/review_events.html, and route/template tests.
- The Review UI uses the existing Stage 3A APIs for listing, accepting, correcting, and rejecting review events.
- Codex verified locally on Windows on 2026-06-25: focused Review UI/API tests reported 7 passed; the full local app suite reported 198 passed, 1 skipped.
- Hermes/OWL verified Review UI Stage 3B on GitHub issue #31 on 2026-06-25: origin/jason-5-may-updates was at 5e9c16c, all requested checks passed, Linux pytest reported 198 passed and 1 skipped, and no forbidden schema/model/detector behavior changed.
- Scott gave standing approval on 2026-06-24 for Codex and Hermes/OWL to continue approved roadmap work without waiting for each next-task approval.
- Stage 3C Possessions and Canonical Clips Foundation is implemented and Hermes/OWL verified: additive possessions, clips, and clip_tags tables; events.possession_id; player_development_clips.canonical_clip_id; and schema tests.
- Codex verified Stage 3C locally on Windows on 2026-06-25: tests/test_schema.py reported 16 passed; the full local app suite reported 201 passed, 1 skipped.
- Hermes/OWL verified Stage 3C on GitHub issue #35 on 2026-06-25: commit f1c3d09, Linux pytest reported 198 passed, 1 skipped, and Stage 3C scope was limited to the additive possession/clip foundation.
- Stage 4A Event Participants Foundation is implemented and Hermes/OWL verified: event_participants table; events relational_game_id, event_type_id, team_id, primary_player_id, primary_roster_membership_id, created_by_user_id, and updated_at; and idempotent legacy player-name backfill into primary event participants.
- Codex verified Stage 4A locally on Windows on 2026-06-25: tests/test_schema.py reported 19 passed.
- Hermes/OWL verified Stage 4A on Linux: HEAD matched origin/jason-5-may-updates at 3945d07; Linux pytest reported 225 passed, 1 skipped; event_participants and relational columns verified present; legacy player-name backfill idempotent.
- Stage 4B Manual Event Write Upgrade is implemented and Hermes/OWL verified: save_event wires relational_game_id, event_type_id, team_id, primary_player_id, and event_participants; possession_id supported in /api/save_event; assign_possessions_for_game() idempotent possession linker.
- Commit 3945d07 implements Stage 4B save_event relational wiring with focused schema and API tests.
- Stage 4C Relational Stats Derivation is implemented and Hermes/OWL verified: stats.aggregate_stats reads event_types taxonomy via event_type_id JOIN; counts_for_stats=1 filtering; review_status='rejected' exclusion; legacy event_type alias seeds (two_attempt, three_attempt, shot, 2pt, 3pt, rebound) added.
- Commit ad1fc67 implements Stage 4C.1 stats derivation rewrite with focused stats tests.
- Commit 415ec3f implements Stage 4C.2 possession linkage fix: corrects VALUES placeholder count in save_event INSERT; adds assign_possessions_for_game() idempotent possession linker; explicit possession_id support in /api/save_event (NULL when absent); 7 focused possession tests all passed.
- Full Linux pytest at HEAD 415ec3f: 225 passed, 1 skipped.
- Stage 4D Player Minutes Foundation is complete and remote at commit 8e67e42.
- Stage 5A Relational game_id cleanup for `stats` and `player_minutes` is implemented at commit `c42346d`.
- Stage 5B Relational game_id cleanup for `player_development_clips` is implemented at commit `6a8f9ab`.
- Stage 5C Relational game_id cleanup for `shot_classifications` is implemented at commit `5fa69f4`.
- Stage 5D Relational game_id cleanup for `play_recognitions` is implemented at commit `372e81c`.
- Stage 5E Relational game_id cleanup for `player_effect` is implemented at commit `0b0ad40`.
- Stage 5F Relational game_id cleanup for `human_corrections` is implemented at commit `a923ee8`.
- Post-Stage-5 `review_items` relational game identity cleanup is implemented through commits `15cecb2` and `5412a54`.
- Post-Stage-5 `detections` relational query-path cleanup is implemented at commit `8c6c83f`.
- schema.sql now defines additive downstream `relational_game_id` columns for `stats`, `player_minutes`, `player_development_clips`, `shot_classifications`, `play_recognitions`, `player_effect`, and `human_corrections`.
- helpers.py now contains additive migration entries for those Stage 5A-5F downstream tables.
- tests/test_schema.py contains focused Stage 5B-5F schema/idempotency coverage.
- tests/test_api.py verifies review-correction writes preserve `human_corrections.relational_game_id`.
- tests/test_api.py now also verifies `analysis_status` counts detections through `relational_game_id`, and the bounded detections cleanup suite passed with `47 passed` in `tests/test_api.py` plus `47 passed` in `tests/test_schema.py`.

## Inferred

These are reasonable conclusions based on verified evidence, but they should not be treated as final facts without more verification.

- The current AI and event pipeline may still produce downstream basketball-analysis noise because the verified fine-tuned ball detector still has false positives at the best measured threshold.
- Current single-frame and simple temporal post-processing experiments have not produced a deployable detector-quality improvement over the conf=0.25 baseline.
- The product roadmap should pivot from detector-first sequencing to trusted platform core first, with AI automation layered in stages.
- Future client packaging should use module flags or permissions while keeping one shared event ledger.
- The base platform should prioritize shared identity, possessions, canonical clips, review workflow, and provenance before paid add-on modules are implemented.
- Stage 1 of the platform core is additive only so current routes can keep working while the foundation is introduced.
- The remaining TEXT game_id columns in downstream analysis tables should be migrated per feature, because they currently carry AI/video analysis keys rather than relational game IDs.
- Stage 2 backfill is deterministic and additive so the new platform-core tables become usable without changing coach workflows.
- Review workflow should come before possession modeling so coaches and the future AI assistant can distinguish accepted facts from unreviewed or rejected data.
- Dataset provenance is incomplete for cross-machine work because documented dataset paths are Linux-specific and not present in the Windows snapshot.
- IMPLEMENTATION_PLAN.md may overstate completion of later phases because it marks phases complete while the detector audit documents a critical subsystem failure.

## Unknown

These need further evidence.

- Whether the 30 likely negative benchmark frames contain any visible balls.
- Whether models/ball_detector.pt precision/recall generalizes to other games, gyms, camera angles, and lighting conditions.
- Whether multi-detection positive frames are duplicate detections of the same ball or multiple distinct false positives.
- Whether a production-usable court-marking exclusion method can reduce false positives without materially damaging recall.
- Whether a larger and more diverse crop dataset would make a secondary classifier viable.
- Whether denser source-video sampling, a stronger tracker, or new labeled data could make temporal methods viable later.
- Exact paid-package boundaries and pricing are not yet decided.
- The first paid/add-on module implementation sequence after the base platform core is not yet approved.
- Whether uploaded video and database files are present only locally, in backups, or in GitHub history.
- Whether hardcoded secrets are used in any exposed environment.
- Whether Scott wants standalone video/scouting analysis without a scheduled game or every analysis attached to a games row.
- Whether the next bounded post-detections slice should be `videos` only or a narrower audit around video-linked analysis identity.

## Current Risks

1. Production ball detection quality is the largest technical risk.
2. Remaining game_id identity ambiguity in non-Stage-5 tables is still a data-model risk.
3. Dataset provenance is incomplete.
4. Documentation exists but needs hierarchy and currency discipline.
5. Auth middleware is disabled, which is acceptable only for local/dev use.
6. Hardcoded development secrets should be reviewed before network exposure.

## Current Recommendation

Do not deploy the current secondary classifier, feature-based filters, or temporal filters. Keep production ball detection at the verified fine-tuned detector default with ball_confidence=0.25. Review Workflow Stage 3A is implemented and independently verified. Review UI Stage 3B is implemented and independently verified. Stage 3C Possessions and Canonical Clips Foundation is implemented and independently verified. Stage 4A Event Participants Foundation, Stage 4B Manual Event Write Upgrade, Stage 4C Relational Stats Derivation, and Stage 4D Player Minutes Foundation are complete. Stage 5A through Stage 5F are implemented in code, and the post-Stage-5 `review_items` and `detections` cleanup slices are now complete. The next recommendation is a fresh bounded audit/correction slice for `videos`-linked relational game identity, not a broad sweep across every remaining `TEXT game_id` table.
