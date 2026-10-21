# Analysis of Rejected Detector Proposal (2026-10-20)

## Proposed Solution (Rejected)
A proposal suggested running `inspect_rule_logic.py` to refine the evaluation logic in `ai_bridge.py` by:
1. Implementing linear interpolation between sparse frames.
2. Expanding the column boundary check.

## Why it was Rejected (Muse Audit)
1. **Banned Trials:** Linear interpolation ("straight line between neighbors") was already trialed. Result: Adrian 98/111, Notus 0/7. Explicitly banned in `OLLAMA.md`.
2. **Forbidden Loosening:** Expanding column boundaries is a form of loosening thresholds. This risks calling misses as makes on the Adrian set, violating the "0 misses called makes" hard gate.
3. **Invalid Script:** The proposed script was "theater"—it hard-coded fake results and failed to actually analyze the code or trajectories.

## Do not open a second trace

The seven misses are already mapped in `OLLAMA.md` and `MUSE.md`. There is no `inspect_rule_logic.py` in the repo. Do not write one, and do not extract those tracks again.

## Current Status
The project is waiting for a new ball weights file to be scored by `C:\Users\scott\AppData\Local\Temp\validate_ball_weights.py`. Do not copy that file over `models/ball_detector.pt`.
