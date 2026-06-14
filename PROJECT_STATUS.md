# Project Status

Updated: 2026-06-14
Branch: jason-5-may-updates

## Proven

These facts were verified from repository files or GitHub metadata.

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
- schema.sql defines events.game_id as TEXT.
- schema.sql defines stats.game_id as TEXT.
- blueprints/clips.py defaults missing event game_id to the string "default_game".
- experiments/detector_audit_top20/AUDIT_RESULTS.md reports v14 produced 0 basketball detections in the top 20 inspected detections.
- docs/VERIFIED_PROJECT_FACTS.md reports finetune2 had zero precision, recall, and mAP across recorded epochs.
- docs/DATASET_INVENTORY.md documents ball_dataset at /home/monk-admin/PROJECTS/liberty-basketball-analysis/ball_dataset with 5 images and 5 labels.

## Inferred

These are reasonable conclusions based on verified evidence, but they should not be treated as final facts without more verification.

- The current AI and event pipeline may produce downstream basketball-analysis outputs from weak or unreliable ball-detection inputs.
- The game_id type mismatch is likely to create integrity and join problems as game-linked event/stat workflows mature.
- Dataset provenance is incomplete for cross-machine work because documented dataset paths are Linux-specific and not present in the Windows snapshot.
- IMPLEMENTATION_PLAN.md may overstate completion of later phases because it marks phases complete while the detector audit documents a critical subsystem failure.

## Unknown

These need further evidence.

- Current test pass/fail status on the Linux machine.
- Current test pass/fail status on the Windows snapshot.
- Actual current precision and recall of the active detector.
- Which detector model is currently active in production-like runs.
- Whether all model artifacts referenced in docs exist on the active machine.
- Whether uploaded video and database files are present only locally, in backups, or in GitHub history.
- Whether hardcoded secrets are used in any exposed environment.

## Current Risks

1. Ball detection quality is the largest technical risk.
2. game_id type consistency is a data-model risk.
3. Dataset provenance is incomplete.
4. Documentation exists but needs hierarchy and currency discipline.
5. Auth middleware is disabled, which is acceptable only for local/dev use.
6. Hardcoded development secrets should be reviewed before network exposure.

## Current Recommendation

Do not start new feature work yet. First complete baseline verification, document the schema fix proposal for Scott approval, and begin a formal ball detection audit.