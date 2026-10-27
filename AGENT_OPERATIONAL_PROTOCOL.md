# OPERATIONAL PROTOCOL: Liberty Basketball Analysis
**Effective Date:** 2026-10-20 (roles updated 2026-10-26)
**Core Goal:** Reach 100% accuracy on Notus Q1 without breaking the Adrian set (0 misses called makes).

## 1. The Chain of Command (Scott, 2026-10-26)
Every agent can see the repo and the local folder. Each agent keeps to its one role:
**Scott** → **Hermes (Architect: plan)** → **Claude Code (Vetter: check the plan)** → **OpenCode/DeepSeek (Coder: write the code)** → **Claude Code (Vetter: check the code and tests)** → **Muse (check the vetter)** → commit → **Scott**

No agent checks its own work. The agents talk through files: Hermes writes `NEXT_TASK.md`, the coder reads it, and every agent reads `docs/agent_handoffs/ACTIVE.md`.

**Muse is back (2026-10-26) in a new role: it checks the vetter.** It runs free on OpenCode with `opencode/glm-5.3-flash-free`, a model family different from Hermes (Nemotron), OpenCode (DeepSeek), and Claude.

**Retired 2026-10-26:** Ollama as project manager, Gemini, and Aider as builder. `MUSE.md` and `OLLAMA.md` stay as the record of the Notus trials.
**Idle:** Cursor (Scott, 2026-10-26). Start every session from `TEAM_RECOVERY.md`.

## 2. Agent Roles & Responsibilities

### Scott (Owner)
- Scope, direction, and every gate in `AUTHORITY.md`.

### Hermes (The Architect)
- **Role:** Reads the project and breaks the goal in `ACTIVE.md` into single, small, additive tasks. Writes the plan to `NEXT_TASK.md`, including the tests to add.
- **Expectation:** Plans only; does not edit source files. Quotes test counts and scores only from commands it ran. Writes no plan when no task fits.

### OpenCode with DeepSeek (The Coder)
- **Role:** Turns a `VETTED` plan into code.
- **Expectation:** NO BLIND SAVES. Diff the change against the file on disk. Smallest change that satisfies the plan; edit only the files the plan names. Purely additive unless the plan says otherwise.
- **Rule:** No code is written until Claude Code has stamped the plan `VETTED`, and nothing is committed until Claude Code has checked the diff and the tests.

### Claude Code (The Vetter/Gatekeeper)
- **Role:** Truth verification, rule enforcement, and drift control. Took over from Muse on 2026-10-26. Does not plan, does not write project code, does not assign tasks.
- **Before code:** Vet every plan against `ACTIVE.md`, `OLLAMA.md`, and the Golden Rules. Stamp it `VETTED` or `REJECTED` with the reason.
- **After code:** Read the diff against the file on disk and run the real tests before anything is committed. Reject deleted or truncated logic, files outside the plan, and claims (test counts, scores, commits, model names) with no command behind them.
- **The Veto:** If a plan or change loosens thresholds or reruns banned trials, Claude Code MUST reject it immediately.
- **Record:** Writes verified results into `ACTIVE.md` (Proven / Inferred / Unknown).
- **Note:** `CLAUDE.md`.

### Muse (Checks the Vetter)
- **Role:** After Claude Code stamps a plan `VETTED` or code `PASS`, Muse reads the plan or diff and Claude's verdict and answers `MUSE: AGREE` or `MUSE: DISAGREE: <reason>`.
- **A DISAGREE stops the loop for Scott.** Neither Claude nor Muse overrides the other.
- **Expectation:** the Muse rules in `MUSE.md` (reject looser cutoffs and banned trials; check claims against the record). Does not plan, code, or do the first vet.

## 3. The Golden Rules (Non-Negotiable)
1. **No Loosening:** Do not move cutoffs in `ai_bridge.py` (e.g., the 170 / 80 / 8000 thresholds) to fix Notus if it risks an Adrian miss becoming a make.
2. **No Banned Trials:** The following are CLOSED (evidence in `OLLAMA.md`): Linear interpolation, ByteTrack, DeepSORT, and early windows.
3. **No Theater:** Hard-coded "results" or fake summaries are forbidden. All claims must be backed by actual track data from `gemini-upload/`.
4. **The Audit Filter:** No technical proposal is valid until Claude Code has appended a "VETTED" stamp to it. Stamps Muse wrote before 2026-10-26 still stand.
5. **Protected Files:** Do not edit `models/ball_detector.pt` directly. Do not commit credentials to the repo.

## 4. Candidate Weights Protocol
- **Creation:** Candidates may be written as separate files (e.g., `candidate_notus_net.pt`).
- **Validation:** Must be run through `validate_ball_weights.py`.
- **Success Gate:** Kept only if:
    - **Adrian:** 0 misses called makes AND $\le 12$ makes missed.
    - **Notus:** $< 7$ makes missed.

## 5. Communication Standard
- All agents must check `SESSION_STATE.md` before starting a task.
- Technical agents must explain *why* a proposal is not a banned trial.
- All responses must be direct and evidence-based.
## 6. Technical Operational Matrix (established 2026-10-25)

### 6.1 Architect
- **Primary:** Hermes (Nemotron Ultra through OpenRouter). Reads `ACTIVE.md`, `WORKLOG.md`, and the git log; writes `NEXT_TASK.md`.

### 6.2 Coder
- **Primary:** OpenCode with `deepseek-v4.1-flash-free`.
- **Strict rule:** purely additive edits. Do not refactor legacy pixel loops or tracking variables inside `run_saved_v6_rule` without a specific, isolated safety-wrapper assignment.
- **Pipeline:** `run_agent_pipeline.ps1` still calls Aider; switching it to OpenCode is an open coder task.

### 6.3 Teams Judge & Verifier (The Gatekeeper)
- **Primary:** Claude Code (vetter), running the pytest suite plus local git hooks.
- **Command:** `pytest tests/ -q`, or `.\.venv\Scripts\python.exe -m pytest tests/ -q` from the repo root. Bare `pytest` resolves to Python 3.12 (pytest 8.4.2); `python -m pytest` fails because `python` on PATH is the `hermes-agent` 3.11 venv, which has no pytest.
- **Verified baseline:** 1104 tests collected as of 2026-10-25. The previously quoted 1,095 figure has no basis in the repository (no "1095" reference exists).
- **Fail-safe:** if an edit drops the pass count below the recorded baseline, immediately run `git checkout HEAD -- <file>`.
- **Known gap:** no pre-commit hook is installed. `.git/hooks` holds only the stock `pre-push` sample plus Git-LFS `post-merge`/`post-checkout`, so this fail-safe is manual until a pre-commit gate is written.
