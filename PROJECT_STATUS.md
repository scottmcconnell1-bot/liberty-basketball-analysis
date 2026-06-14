# Project Status

Updated: 2026-06-14
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

## Inferred

These are reasonable conclusions based on verified evidence, but they should not be treated as final facts without more verification.

- The current AI and event pipeline may produce downstream basketball-analysis outputs from weak or unreliable ball-detection inputs.
- The next detector step should likely be a labeled benchmark before retraining, because formal precision/recall validation is not complete.
- The remaining TEXT game_id columns in downstream analysis tables should be migrated per feature, because they currently carry AI/video analysis keys rather than relational game IDs.
- Dataset provenance is incomplete for cross-machine work because documented dataset paths are Linux-specific and not present in the Windows snapshot.
- IMPLEMENTATION_PLAN.md may overstate completion of later phases because it marks phases complete while the detector audit documents a critical subsystem failure.

## Unknown

These need further evidence.

- Current test pass/fail status on the Windows snapshot.
- Actual current precision and recall of the active detector.
- Which detector model is currently active in production-like runs.
- Whether all model artifacts referenced in docs exist on the active machine.
- Whether uploaded video and database files are present only locally, in backups, or in GitHub history.
- Whether hardcoded secrets are used in any exposed environment.
- Whether Scott wants standalone video/scouting analysis without a scheduled game or every analysis attached to a games row.

## Current Risks

1. Ball detection quality is the largest technical risk.
2. Remaining game_id identity ambiguity in downstream tables is a data-model risk.
3. Dataset provenance is incomplete.
4. Documentation exists but needs hierarchy and currency discipline.
5. Auth middleware is disabled, which is acceptable only for local/dev use.
6. Hardcoded development secrets should be reviewed before network exposure.

## Current Recommendation

Do not start new feature work yet. Review docs/BALL_DETECTION_AUDIT_2026-06-14.md, then decide whether to build the detector benchmark first, rebuild the detector, or shift near-term effort toward manual coach film workflows.
