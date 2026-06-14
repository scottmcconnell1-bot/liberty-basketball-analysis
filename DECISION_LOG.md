# Decision Log

Updated: 2026-06-14
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
- Execute docs/BALL_DETECTION_BENCHMARK_PLAN.md.
