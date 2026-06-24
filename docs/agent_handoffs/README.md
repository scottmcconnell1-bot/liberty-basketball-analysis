# Agent Handoffs

This folder is the fallback return channel for Codex/Hermes/OWL/Rex handoffs when GitHub issue comments are unavailable.

Preferred workflow:

1. Codex creates a GitHub issue titled `[OWL ACTION]`.
2. Hermes/OWL/Rex verifies the checklist and posts a report as an issue comment.

Fallback workflow:

1. Hermes/OWL/Rex writes the report here.
2. File name format: `ISSUE_<number>_<short_task>.md`.
3. Report format: Proven / Inferred / Unknown.
4. Commit and push the report to `jason-5-may-updates`.
5. Report only the commit hash and report path in chat.

This folder prevents Scott from having to copy/paste full verification reports between agents.
