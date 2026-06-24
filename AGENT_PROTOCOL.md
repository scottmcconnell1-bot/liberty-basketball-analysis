# Agent Protocol

Updated: 2026-06-24
Branch: jason-5-may-updates

This file is the repository-level protocol for Codex, Hermes/OWL/Rex, and any other project agent. It exists so operating rules live in the repository instead of private agent memory.

## Authority Order

When sources disagree, use this order:

1. Scott's current decision or instruction
2. Repository files on the active branch
3. Git history and remote branch state
4. Test results and runtime logs
5. Source-of-truth docs
6. Agent analysis
7. Agent memory

Agent memory is advisory only. It is never project truth.

## Project Isolation

Liberty basketball work must stay isolated from all unrelated projects.

Agents must not include information, logs, memory, reports, account data, operational status, or recommendations from unrelated projects in Liberty project responses. This includes, but is not limited to, trader_bot, Alpaca, market positions, trading reports, or any non-Liberty repository.

Before reporting, agents must verify the current working directory and remote URL point to the Liberty basketball repository:

```bash
pwd
git remote -v
```

If the current repository is not Liberty basketball, stop and report:

`Unknown; wrong repository context.`

Do not continue Liberty verification from another project directory.

## Repository Truth Preflight

Before making any claim about commits, branches, files, docs, tests, or repository state, run and report:

```bash
pwd
git remote -v
git branch --show-current
git fetch origin jason-5-may-updates
git status --short --branch
git rev-parse HEAD
git rev-parse origin/jason-5-may-updates
```

If local `HEAD` differs from `origin/jason-5-may-updates`, run:

```bash
git pull --ff-only origin jason-5-may-updates
```

Only after this preflight may an agent say a commit exists, does not exist, a file changed, a doc is current, or the local clone is clean.

## Verification Safety

Verification must not destroy, hide, or rewrite local work.

Agents must not run these commands during verification unless Scott explicitly approves the specific action:

- `git reset --hard`
- `git checkout -- <path>`
- `git clean`
- `git stash`
- `git stash pop`
- forced branch checkout that overwrites local changes

If local changes block verification, report:

`Unknown; local changes block verification. Approval needed to use a clean clone, worktree, stash, reset, or other cleanup.`

Preferred alternatives:

1. Use a clean clone.
2. Use a separate worktree.
3. Verify the remote tree directly with non-destructive Git commands.
4. Ask Scott before changing local state.

## No Repo Claims Without Fetch/Compare

Agents must not treat a local clone as current until after fetching and comparing `HEAD` to `origin/jason-5-may-updates`.

Required language:

- If preflight has not run: `Not verified yet.`
- If local `HEAD` differs from origin: `Local clone is stale.`
- If remote fetch fails: `Unknown; remote fetch failed.`

Do not say `fabricated`, `false`, `not real`, or `does not exist` about repository state until after preflight checks the remote branch.

## Memory Rules

Do not edit, consolidate, delete, rewrite, or add private memory entries during project work unless Scott explicitly says: `update memory`.

Private agent memory must not delay verification or execution. If memory conflicts with repository evidence, repository evidence wins.

Agents should read this file instead of saving these rules into private memory.

## No Duplicate Commits Before Preflight

Before creating corrective commits, agents must:

1. Run Repository Truth Preflight.
2. Confirm the relevant commit or file state is absent from `origin/jason-5-may-updates`.
3. Confirm the work is not already present under a different commit.
4. Report the evidence.

If the local clone was stale, pull and re-check before proposing or creating a duplicate commit.

## GitHub Handoff Fallback

Codex may create GitHub issues titled `[OWL ACTION]` to request Hermes/OWL/Rex verification.

Preferred return path:

1. Hermes/OWL/Rex reads the issue.
2. Runs Repository Truth Preflight.
3. Verifies the issue checklist.
4. Posts a Proven / Inferred / Unknown report as a comment on the same issue.
5. Adds the `OWL DONE` label only after successful completion.

## GitHub Handoff State Labels

GitHub labels are the machine-readable coordination state between Codex and Hermes/OWL/Rex.

- `OWL ACTION`: Hermes/OWL/Rex has work to perform or verify.
- `OWL DONE`: Hermes/OWL/Rex completed the task successfully; Codex may review the evidence and continue.
- `OWL NEEDS`: Hermes/OWL/Rex is blocked and needs Codex input before it can continue.

Hermes/OWL/Rex must not use `OWL DONE` for partial work, failed verification, timeouts, unclear instructions, missing permissions, or missing runtime configuration.

When Hermes/OWL/Rex needs Codex input:

1. Comment on the issue with a short Proven / Inferred / Unknown report.
2. Ask the specific question or state the exact blocker.
3. Add label `OWL NEEDS`.
4. Do not add `OWL DONE`.

When Codex responds to `OWL NEEDS`:

1. Comment on the same issue with `[OWL FOLLOWUP]`.
2. Include `Required next action for Hermes/OWL:` followed by the specific next step.
3. Keep the response small enough for the poller to process without timing out.

When Hermes/OWL/Rex successfully resolves the blocker:

1. Comment with the final Proven / Inferred / Unknown report.
2. Remove `OWL NEEDS` if present.
3. Add `OWL DONE`.

For large tasks that time out, do not keep retrying the same oversized issue body. Split the work into smaller `[OWL ACTION]` issues or ask Codex for a smaller follow-up using `OWL NEEDS`.

If Hermes/OWL/Rex does not have GitHub issue-comment permission, do not fight the token or repeatedly retry failed comment commands.

Use the repository fallback instead:

1. Create `docs/agent_handoffs/` if it does not exist.
2. Write the verification report to `docs/agent_handoffs/ISSUE_<number>_<short_task>.md`.
3. Commit and push that report to `jason-5-may-updates`.
4. Report only the commit hash and report path in chat.

This keeps Scott from being the messenger while preserving repository evidence.

## Reporting Standard

Reports must separate:

- Proven: directly verified from repository files, Git history, tests, logs, or runtime behavior.
- Inferred: reasonable conclusions based on evidence.
- Unknown: information not yet verified.

Do not present inferred information as proven fact.

## Production Safety

Benchmark experiments and documentation updates must not change production behavior unless Scott explicitly approves the production change.

For detector work, production remains:

- `models/ball_detector.pt`
- class `0`
- `ball_confidence=0.25`

until a later Scott-approved production change is recorded in the source-of-truth docs.
