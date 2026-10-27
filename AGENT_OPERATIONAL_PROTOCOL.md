# OPERATIONAL PROTOCOL: Liberty Basketball Analysis
**Effective Date:** 2026-10-20
**Core Goal:** Reach 100% accuracy on Notus Q1 without breaking the Adrian set (0 misses called makes).

## 1. The Chain of Command
To eliminate "AI theater" and prevent banned trials, all work must follow this flow:
**User** $\rightarrow$ **Ollama (Project Manager)** $\rightarrow$ **Technical Agent (Gemini/Hermes/Cursor)** $\rightarrow$ **Claude Code (Auditor)** $\rightarrow$ **User**

Muse was retired on 2026-10-26. Claude Code holds the Auditor role. Its note is `CLAUDE.md`.

## 2. Agent Roles & Responsibilities

### Ollama (The Project Manager & Memory)
- **Primary Point of Contact:** Translates user goals into technical tasks.
- **Synchronization:** Maintains `SESSION_STATE.md` and `OLLAMA.md`.
- **Translation:** Translates technical results back into plain English for the User.
- **Orchestration:** Delegates tasks and ensures they move through the Safety Chain.

### Gemini Coding (The Prototyper)
- **Role:** Brainstorming and drafting initial logic/scripts.
- **Expectation:** Provide mathematically distinct proposals. 
- **Rule:** MUST NOT suggest "loosening" thresholds or rerunning trials listed as "Do Not" in `OLLAMA.md`. Scripts must open real files at real paths.

### Hermes (The Architect)
- **Role:** Structural integrity and integration.
- **Expectation:** Ensure new logic fits the core pipeline without causing regressions.

### Cursor (The Developer & Reviewer)
- **Role:** Implementation and first-pass code audit.
- **Expectation:** NO BLIND SAVES. Before updating any file, Cursor must diff the proposed code against the version on disk.
- **The Auditor Role:** If any core logic or helper function is deleted or truncated in a proposal, Cursor MUST refuse to save and report the missing lines to the User.
- **Execution:** Execute the smallest change for verification.
- **Rule:** No code is to be written or run until it has passed the Claude Code audit.

### Claude Code (The Auditor/Gatekeeper)
- **Role:** Truth verification, rule enforcement, and drift control. Keeps the other agents on the current task. Took over from Muse on 2026-10-26.
- **Before code:** Vet every proposal against `OLLAMA.md`, `ACTIVE.md`, and the Golden Rules. Stamp it `VETTED` or `REJECTED` with the reason.
- **After code:** Read the diff against the file on disk and run the real tests before anything is committed. Reject deleted or truncated logic, files outside the task, and claims (test counts, scores, commits, model names) with no command behind them.
- **The Veto:** If a proposal suggests loosening thresholds or rerunning banned trials, Claude Code MUST reject it immediately.
- **Obligations:** Verify before claiming, correct errors plainly, hold guardrails unreminded, provide copyable PowerShell commands, and report honest changes.
- **Note:** `CLAUDE.md`. `MUSE.md` stays as the record of the Notus trials.

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

### 6.1 Lead Architect & Project Manager
- **Primary:** Hermes (local). Reads `WORKLOG.md` and `PROJECT_VISION.md`, maintains architectural structure, breaks macro roadmaps into single isolated tasks.
- **Alternate:** OpenAI GPT-4o / Claude 3.5 Sonnet (cloud failover), engaged when local context limits or shell-execution locks are detected.
- **Identity note:** the acting agent in this session is `deepseek-v4.1-flash-free`, not Nemotron-3-Ultra-550B. Model identity is whatever the runtime reports; do not stamp a different model name.

### 6.2 Mechanical Code Writer (The Builder)
- **Primary:** DeepSeek V4.1 (Flash Free) via Aider CLI.
- **Duty:** translate the Architect's instructions into discrete Python blocks.
- **Strict rule:** purely additive edits. Do not refactor legacy pixel loops or tracking variables inside `run_saved_v6_rule` without a specific, isolated safety-wrapper assignment.

### 6.3 Teams Judge & Verifier (The Gatekeeper)
- **Primary:** Claude Code (auditor), running the pytest suite plus local git hooks.
- **Command:** `pytest tests/ -q`, or `.\.venv\Scripts\python.exe -m pytest tests/ -q` from the repo root. Bare `pytest` resolves to Python 3.12 (pytest 8.4.2); `python -m pytest` fails because `python` on PATH is the `hermes-agent` 3.11 venv, which has no pytest.
- **Verified baseline:** 1104 tests collected as of 2026-10-25. The previously quoted 1,095 figure has no basis in the repository (no "1095" reference exists).
- **Fail-safe:** if an edit drops the pass count below the recorded baseline, immediately run `git checkout HEAD -- <file>`.
- **Known gap:** no pre-commit hook is installed. `.git/hooks` holds only the stock `pre-push` sample plus Git-LFS `post-merge`/`post-checkout`, so this fail-safe is manual until a pre-commit gate is written.
