# OPERATIONAL PROTOCOL: Liberty Basketball Analysis
**Effective Date:** 2026-10-20
**Core Goal:** Reach 100% accuracy on Notus Q1 without breaking the Adrian set (0 misses called makes).

## 1. The Chain of Command
To eliminate "AI theater" and prevent banned trials, all work must follow this flow:
**User** $\rightarrow$ **Ollama (Project Manager)** $\rightarrow$ **Technical Agent (Gemini/Hermes/Cursor)** $\rightarrow$ **Muse (Auditor)** $\rightarrow$ **User**

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
- **Expectation:** Ensure new logic fits the core pipeline without causing regressions in other modules.

### Cursor (The Builder)
- **Role:** Implementation and refactoring.
- **Expectation:** Execute the smallest possible change for verification.
- **Rule:** No code is to be written or run until it has passed the Muse Audit.

### Muse (The Auditor/Gatekeeper)
- **Role:** Truth verification and rule enforcement.
- **Expectation:** Ruthlessly vet every proposal against `OLLAMA.md`.
- **The Veto:** If a proposal suggests loosening thresholds or rerunning banned trials, Muse MUST reject it immediately.
- **Obligations:** Verify before claiming, correct errors plainly, hold guardrails unreminded, provide copyable PowerShell commands, and report honest changes.

## 3. The Golden Rules (Non-Negotiable)
1. **No Loosening:** Do not move cutoffs in `ai_bridge.py` (e.g., the 170 / 80 / 8000 thresholds) to fix Notus if it risks an Adrian miss becoming a make.
2. **No Banned Trials:** The following are CLOSED (evidence in `OLLAMA.md`): Linear interpolation, ByteTrack, DeepSORT, and early windows.
3. **No Theater:** Hard-coded "results" or fake summaries are forbidden. All claims must be backed by actual track data from `gemini-upload/`.
4. **The Muse Filter:** No technical proposal is valid until Muse has appended a "VETTED" stamp to it.
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
