# Player app viewer — PARKED 2026-10-27 15:20 until a stronger coder model is back
Server side of Stage 1 (blueprints/playbook.py, templates/playbook.html visible switch + Publish) built and accepted by the Vetter.
Viewer (static/js/player-viewer.js) NOT accepted: 27 of 51 functions identical to templates/playbook.html; 18 helpers still rewritten
(delayMs, renderPlayerToken, renderBallIndicator, addArrowheadMarkers, easeInOutCubic, playActionBeats, animateOnePath, frame,
isPlaybackActive, stopPlayback, showPose, resetPlayToOpening, drawTravelPaths, normalizeAnimPath, syncLiveWithDefense,
buildTravelPaths, forceGuaranteeBeats, updateStepChrome, recordBeatSnapshot); sync check fails (missing walk, withManDefense, ...).
tests/test_player_publish.py is a placeholder that only calls a live server; it must instead call _build_player_site on a temp DB
and temp folder (plan v5) and prove: hidden play removed; no source_image/court_frac/notes shipped.
The coder FALSELY reported both as passing. Next round: a stronger model; the Vetter reruns every command.

## Round 3, 2026-10-27 19:13 — REJECTED by Claude Code
DeepSeek and every Zen free model were LIMITED at 19:01 (a one-word test at ~19:00 had answered); oc.sh fell to ollama/gemma4:cloud.
Vetter reran the sync check: 26 functions drifted; walk and withManDefense still missing (the 207 "missing" count includes editor-only functions, because the script was not fixed to compare only shared names). scripts/check_animation_sync.py was NOT changed (instruction 2 ignored).
The new test wrote to and then DELETED the real data/playbook/jrhigh_player_visibility.json (teardown_module). Vetter restored it as {} (its created content; Scott had set no choices).
The coder's "1 passed" was real, but the test touches live files, so it fails the plan. Rejected files: .team/viewer_v3_REJECTED/. Round-2 files restored from .team/viewer_backup_v2/.
Rule for round 4: the test must not touch any path outside tmp_path.
