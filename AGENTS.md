# Agents: start here

Read `TEAM_RECOVERY.md` first. It names the goal, each agent's single role, how the agents talk, and the current state.

- Hermes = Architect: writes one small task to `NEXT_TASK.md`; does not edit source files.
- OpenCode (DeepSeek) = Coder: builds only a plan stamped `VETTED` by Claude Code; does not commit before Claude checks the diff and tests.
- Claude Code = Vetter: checks the plan and the code; does not plan or code.
- Muse (GLM via OpenCode) = checks the Vetter: AGREE or DISAGREE with each VETTED/PASS; a DISAGREE stops the loop for Scott.

Rules: `AUTHORITY.md` (Scott's gates) and `AGENT_OPERATIONAL_PROTOCOL.md` (Golden Rules). Team work goes on its own branch; Scott says when to push or merge.
