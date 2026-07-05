# Agent Handoffs

This folder is the fallback return channel for ALPHA/OWL handoffs when GitHub issue comments are unavailable.

Preferred workflow:

1. ALPHA creates or updates a GitHub issue titled `[OWL ACTION]`.
2. OWL reads the issue body plus the latest `[OWL FOLLOWUP]` comment from ALPHA, if any.
3. OWL verifies the checklist and posts a report as an issue comment.

Fallback workflow:

1. OWL writes the report here.
2. File name format: `ISSUE_<number>_<short_task>.md`.
3. Report format: Proven / Inferred / Unknown.
4. Commit and push the report to `jason-5-may-updates`.
5. Report only the commit hash and report path in chat.

This folder prevents Scott from having to copy/paste full verification reports between agents.

Current top-level GitHub sync note:

- `ALPHA_GITHUB_SYNC_2026-07-05.md` is the latest branch-wide handoff snapshot for new agents with no chat context.

Poller reminder:

- OWL's primary queue is always the newest open GitHub issue labeled `OWL ACTION`.
- If an issue has `OWL NEEDS`, OWL must keep polling that same issue for a newer `[OWL FOLLOWUP]` from ALPHA.
- OWL must not go idle while an open actionable `OWL ACTION` issue exists.
