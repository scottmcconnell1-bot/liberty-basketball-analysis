# TEAM RECOVERY — Liberty Basketball Analysis

**Last updated: 2026-10-26 21:00 MDT by Claude Code (vetter)**

> If anything breaks, start here. This file is the single source for who does what, how to open each agent, and where the work stands.
> Every agent reads it first: Hermes and OpenCode load `AGENTS.md` automatically, Claude Code loads `CLAUDE.md`, and both point here.
> It lives in git and on GitHub, so every version is saved and it survives this PC.
> If the "Last updated" time is older than the newest commit (`git log -1`), treat section 6 as stale and refresh it before working.

---

## 1. The goal (Scott, 2026-10-26)

**Now:** call every shot make or miss 100% correctly from the film, with NO manual tagging (Scott, 2026-10-26).
- Makes, team, and points come from the scoreboard: proven 43 of 43 on Adrian, final 51-26 = book (see `ACTIVE.md`).
- The video finds shot attempts (no score change = miss) and who shot.
- Next: confirm on both Notus games against their scorebooks, then Hermes structures shooter identification, then the other stats.
- Measured with `run_saved_v6_rule` in `ai_bridge.py` against Scott's tags.
- **Goal reached** = Notus A1 Q1 31 of 31 right, AND Adrian 0 misses called makes with no more makes missed than today (`AGENT_OPERATIONAL_PROTOCOL.md`: "Reach 100% accuracy on Notus Q1 without breaking the Adrian set").
- **Progress** = more shots right on either film while Adrian stays at 0 misses called makes.
- A make is `ball_through_rim` or `net_moved_after_shot`.

**Next, after make/miss:** the other stats from film (who shot, rebounds, assists, steals, turnovers, fouls), then minutes and lineups. Then the long-term product: the Liberty AI assistant coach (`PROJECT_VISION.md`).

**No deadline.** The 1 Nov 2026 date was dropped on 2026-10-26.

---

## 2. The team

| Agent | Role | Does | Does NOT |
|---|---|---|---|
| **Scott** | Owner | Decides, approves every gate in `AUTHORITY.md`, says push/merge/save | — |
| **Hermes** | Architect | Reads the project, writes ONE small task to `NEXT_TASK.md` (with its tests) | Edit source files |
| **OpenCode (DeepSeek)** | Coder | Builds a plan that Claude stamped `VETTED`, touching only the files it names | Plan, or check its own work |
| **Claude Code** | Vetter | Checks the plan before code; reads the diff and runs the real tests before commit; keeps the record honest; updates this file | Plan, write project code, assign work |
| **Cursor** | Idle | Nothing; left installed (costs nothing) | — |
| Retired 2026-10-26 | — | Muse, Ollama (project manager), Gemini, Aider. `MUSE.md` and `OLLAMA.md` are kept as the trial record. | — |

**Flow:** Scott → Hermes (plan) → Claude (vet plan) → OpenCode (code) → Claude (vet code and tests) → commit on the work branch → Scott says push/merge/save.

**Rules every agent follows:** `AUTHORITY.md` (Scott's gates) and `AGENT_OPERATIONAL_PROTOCOL.md` (Golden Rules: no looser cutoffs, no banned trials, no hard-coded results, `applied_to_core` stays false). No agent checks its own work.

---

## 3. How the agents talk

They talk through files in the repo, never through chat memory.

| File | Who writes | Who reads |
|---|---|---|
| `TEAM_RECOVERY.md` (this file) | Claude, at the end of every session and every loop round | Everyone, first |
| `docs/agent_handoffs/ACTIVE.md` | Claude (verified results, Proven / Inferred / Unknown) | Everyone |
| `NEXT_TASK.md` | Hermes | Claude, then OpenCode |
| `docs/agent_handoffs/TEAM_LOG.md` (when the team loop is built) | Every agent: what it did, found, needs, and brainstorm ideas | Everyone |
| git commits | OpenCode (after Claude passes them) | Everyone |

**Branches:** team work goes on its own branch, never straight to `main`. Scott reviews it and says push/merge/save.

**Team loop (being built, 2026-10-26):** a script that runs Hermes → Claude → OpenCode → Claude in rounds. Agents brainstorm together when stuck. It stops on goal reached, a Scott gate, no progress, an agent down, or a round cap, and then writes a recap. Design: `C:\Users\scott\Documents\Team_Loop_Design_2026-10-26.md`. Until it exists, run the agents by hand (section 4). Do not use `run_agent_pipeline.ps1`; it still calls the retired Aider.

---

## 4. How to open each agent

The repo is at `C:\Users\scott\Documents\liberty-basketball-analysis` (in Ubuntu: `/mnt/c/Users/scott/Documents/liberty-basketball-analysis`).

**Claude Code (vetter):** Start → Windows PowerShell →
```powershell
cd C:\Users\scott\Documents\liberty-basketball-analysis
claude
```

**Hermes (architect):** Start → Ubuntu →
```bash
cd /mnt/c/Users/scott/Documents/liberty-basketball-analysis
hermes
```
One-shot, no chat window: `hermes chat -q "your prompt"`. Hermes uses Nemotron Ultra through OpenRouter (set in `~/.hermes/config.yaml`; the key is NOT in the repo).

**OpenCode (coder):** Start → Windows PowerShell →
```powershell
cd C:\Users\scott\Documents\liberty-basketball-analysis
opencode
```
Pick the model `deepseek-v4.1-flash-free`. One-shot: `opencode run -m opencode/deepseek-v4.1-flash-free "your prompt"`.

**Cursor:** idle. Do not start it for this project.

---

## 5. Startup prompts (copy and paste)

**Hermes:**
> Work in /mnt/c/Users/scott/Documents/liberty-basketball-analysis. Read TEAM_RECOVERY.md first, then AUTHORITY.md, AGENT_OPERATIONAL_PROTOCOL.md, docs/agent_handoffs/ACTIVE.md, docs/agent_handoffs/HERMES.md, and the git log. You are the Architect. Choose the single smallest additive task that moves the goal in TEAM_RECOVERY.md section 1 forward, obeys the Golden Rules, and crosses no Scott gate. Write it, with the exact files to change and the tests to add, to NEXT_TASK.md. Quote numbers only from commands you ran. If no task fits, do not write NEXT_TASK.md; say why. Do not edit source files.

**Claude Code:**
> Read TEAM_RECOVERY.md and CLAUDE.md. You are the Vetter. Check that section 6 is current against git and ACTIVE.md. If NEXT_TASK.md exists, vet it and stamp it VETTED or REJECTED with the reason. If there are uncommitted code changes, read the diff and run the tests. Report Proven / Inferred / Unknown. Save long reports to a file in C:\Users\scott\Documents and open it in Notepad.

**OpenCode:**
> Read TEAM_RECOVERY.md and AGENTS.md. You are the Coder. Build NEXT_TASK.md only if it carries a VETTED stamp from Claude Code. Change only the files it names, purely additive, and add the tests it lists. Run the tests with .\.venv\Scripts\python.exe -m pytest <the test files> -q. Do not commit; Claude vets first. Report exactly what you changed.

---

## 6. Current state (update every session)

- **Branch:** `main` = GitHub `main`. Last commit: see `git log -1`.
- **Make/miss (Proven, 2026-10-26):** Adrian Q1–Q3 99 of 111, 12 makes missed, 0 misses called makes (whole film 113 of 129). Notus A1 Q1 24 of 31, 7 makes missed, 0 misses called makes.
- **Candidate ball-weights files:** both failed the gate (Oct 20 and Oct 25). Details in `ACTIVE.md`.
- **Court:** Liberty is 92 ft (half court 40.75 ft from the hoop). The NFHS camera pans, so one four-point calibration fits one camera view only.
- **Tests:** 1115 collected. Failures that existed before 2026-10-26 (transfer-bundle tar on Windows, Ollama-pull, panel write, calendar day) are unchanged.
- **In progress (branch `team/auto`, not pushed):**
  - The team loop `team_loop.ps1` is built and vetted (`6843dec`).
  - OpenCode is building the make/miss review page.
  - Next: the free gate script, the cheaper Claude model, and free-model fallbacks.
- **Team status:** `.team/STATUS.md` (desktop shortcut "TEAM STATUS - Liberty").
- **Jason and Brad:** updated with `docs/agent_handoffs/UPDATE_2026-10-26.md`; their branches are even with `main`.
- **Open for Scott:** none blocking.

---

## 7. Catastrophic recovery (PC lost, or nothing starts)

1. **Get the code:** `git clone https://github.com/scottmcconnell1-bot/liberty-basketball-analysis.git` then `git lfs pull`.
2. **Python:** create `.venv` with Python 3.12 and run `.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt`. Check with `.\.venv\Scripts\python.exe -m pytest tests/test_ai_bridge.py -q`.
3. **Hermes (Ubuntu/WSL):** `sudo apt install -y clang cmake`, then `hermes pm repair`, `hermes update`, `hermes pm doctor`. The OpenRouter key must be re-entered in Hermes (it is not in git).
4. **OpenCode:** `npm install -g opencode-ai`, then pick `deepseek-v4.1-flash-free`.
5. **Claude Code:** install, run `claude` in the repo; it loads `CLAUDE.md` and this file.
6. **Files that are NOT in GitHub (restore by hand):**
   - Offline backup: `C:\Users\scott\Documents\liberty_offline_backup\` (checksums in `MANIFEST.sha256`):
     - `temp_scoring\`: the BODD YOLOv8 hoop model, `v6_tracks.json` (Adrian tracks behind 99/111), `v6_tracks_notus_q1.json`, `validate_ball_weights.py`, `collect_notus_q1_bodd.py`, `ball_net_runs\`, the Oct 20 validation results. Copy these back to `C:\Users\scott\AppData\Local\Temp\`; the scripts expect them there.
     - `film_tags\`: Scott's shot tags. Copy back to `data\film_tags\`.
   - `film_analysis.db` (about 570 MB, gitignored). See `docs/BACKUP_AND_ARCHIVE.md` and `Backup Liberty Database.bat`.
   - That backup folder is on this PC only. Copy it to a USB drive or cloud folder for real protection.
7. **Then:** open each agent (section 4), paste its prompt (section 5), and continue from section 6.

---

## 8. Update log

- 2026-10-26 21:00 MDT — Claude Code: scoreboard-only makes proven on Adrian (43/43, 51-26); goal is now no manual tagging.

- 2026-10-26 20:40 MDT — Claude Code: team loop vetted on `team/auto`; Jason and Brad update written; their branches fast-forwarded.

- 2026-10-26 20:05 MDT — Claude Code: file created. Roster (Hermes/OpenCode/Claude), goal (make/miss first), how to open and recover, offline backup of Temp scoring files and film tags.
