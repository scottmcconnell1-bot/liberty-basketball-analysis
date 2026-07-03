# Agent Protocol

Updated: 2026-07-02
Branch: jason-5-may-updates

This file is the repository-level protocol for ALPHA, OWL, and any other project agent. It exists so operating rules live in the repository instead of private agent memory.

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


## Stage Numbering

Agents must read `docs/STAGE_INDEX.md` before naming, renaming, verifying, or reporting platform stages.

Do not reuse stage numbers. In particular:

- Stage 3B means Review UI.
- Stage 3C means Possessions and Canonical Clips Foundation.

If a new slice is needed between existing stages, add a lettered stage instead of rewriting history.
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

## Agent Naming

Use these names consistently in issues, comments, and handoffs:

- `ALPHA` = navigator, reviewer, scope controller
- `OWL` = executor, verifier, poller-driven worker

Do not require older names such as Codex, Hermes, OWL/Hermes, or Rex for normal coordination.

If older names appear in historical docs or issue text, interpret them as legacy aliases only:

- `Codex` => `ALPHA`
- `Hermes`, `OWL/Hermes`, `Rex` => `OWL`

## GitHub Handoff Fallback

ALPHA may create GitHub issues titled `[OWL ACTION]` to request OWL verification, audit work, or bounded implementation work.

Preferred return path:

1. OWL reads the issue.
2. Runs Repository Truth Preflight.
3. Verifies the issue checklist.
4. Posts a Proven / Inferred / Unknown report as a comment on the same issue.
5. Adds the `OWL DONE` label only after successful completion.

Communication rule:

- A label alone is never a complete handoff.
- Every meaningful state change between ALPHA and OWL must include a human-readable GitHub comment on the same issue.
- If a comment is missing, the label state is non-authoritative and must be treated as suspect until clarified.

## ALPHA Continuation Contract

ALPHA must use this section as the operational contract after OWL posts issue results.

Trigger:

- Any open `[OWL ACTION]` issue that now has an OWL comment with a final Proven / Inferred / Unknown report and the `OWL DONE` label

Required ALPHA action on the next cycle:

1. Read the issue body, OWL's latest report, and any linked repository evidence.
2. Decide the next program move without waiting for Scott to relay that OWL is done.
3. Perform exactly one of these actions:
   - create the next `[OWL ACTION]` issue
   - comment on the same issue with `[OWL FOLLOWUP]` and a narrower correction
   - record ALPHA's approval/review decision if the issue was a review gate
   - state a real blocker that requires Scott
4. Leave repository evidence of the decision in GitHub, not only chat.

Rules that prevent ALPHA idle drift:

- ALPHA must not wait for Scott to copy an `OWL DONE` report that already exists on GitHub.
- `OWL DONE` is a continuation trigger for ALPHA, not a resting state.
- If the newest open `[OWL ACTION]` issue is `OWL DONE`, ALPHA must either advance the queue or explain the blocker the same cycle.
- If ALPHA needs more OWL work, ALPHA must open the next bounded issue immediately instead of assuming OWL will infer the next slice.
- If no blocker exists, ALPHA owns momentum.

## OWL Poller Contract

OWL's poller must use this section as the operational contract.

Watch target:

- Repository: `scottmcconnell1-bot/liberty-basketball-analysis`
- Branch: `origin/jason-5-may-updates`
- Primary work queue: open GitHub issues labeled `OWL ACTION`

Poll order on every cycle:

1. Run Repository Truth Preflight locally.
2. Fetch the current open GitHub issues labeled `OWL ACTION`.
3. Sort those issues by issue number descending unless ALPHA explicitly pins a different issue in a newer `[OWL FOLLOWUP]` comment.
4. For each candidate issue, read:
   - the issue body
   - the latest comments
   - the latest `[OWL FOLLOWUP]` comment from ALPHA, if present
5. Choose work using this priority:
   - first: newest open `OWL ACTION` issue without `OWL DONE`
   - second: any open `OWL ACTION` issue with `OWL NEEDS` that now has a newer `[OWL FOLLOWUP]` from ALPHA
   - third: any still-open `OWL ACTION` issue not yet completed
6. If no open `OWL ACTION` issues exist, remain idle but continue polling. Do not assume the program is finished.

Rules that prevent idle drift:

- OWL must not wait for chat if an open `OWL ACTION` issue already defines the next step.
- OWL must not stop polling after posting `OWL NEEDS`.
- After posting `OWL NEEDS`, OWL must keep polling the same issue and newer `OWL ACTION` issues for `[OWL FOLLOWUP]` from ALPHA.
- If multiple open `OWL ACTION` issues exist, OWL must prefer the newest issue unless ALPHA explicitly says otherwise in issue comments.
- OWL must not infer the next task from stale historical issues when a newer open `OWL ACTION` issue exists.
- OWL must not treat stale labels, contradictory labels, or unlabeled issue history as sufficient instruction when the issue comments tell a different story.

Single source of truth for an OWL task:

1. Scott's newest direct instruction
2. The current open GitHub issue body
3. The newest `[OWL FOLLOWUP]` comment from ALPHA on that same issue
4. This `AGENT_PROTOCOL.md`
5. Repository code/docs on `origin/jason-5-may-updates`

If sources conflict, use the highest item in that list and report the conflict explicitly.

## GitHub Handoff State Labels

GitHub labels are the machine-readable coordination state between ALPHA and OWL.

- `OWL ACTION`: OWL has work to perform or verify.
- `OWL DONE`: OWL completed the task successfully; ALPHA may review the evidence and continue.
- `OWL NEEDS`: OWL is blocked and needs ALPHA input before it can continue.

OWL must not use `OWL DONE` for partial work, failed verification, timeouts, unclear instructions, missing permissions, or missing runtime configuration.

## Actionable Comment Standard

The comment body, not the label by itself, is the authoritative communication artifact.

An actionable OWL comment must be one of these:

1. Progress update:
   - States what bounded work was done
   - States what remains
   - Does not claim completion
2. Blocker report:
   - Uses Proven / Inferred / Unknown
   - States the exact blocker
   - States the exact next action needed from ALPHA
3. Completion report:
   - Uses Proven / Inferred / Unknown
   - Lists the files changed
   - Lists the exact tests run and their result
   - States whether the work is pushed to `origin/jason-5-may-updates`
   - If pushed, includes the commit hash
   - If not pushed, explicitly says `Not pushed yet`

Non-actionable noise does not count as progress or completion. Examples:

- repeated API failure spam
- a label change without a matching comment
- a chat message that is not mirrored in GitHub
- `done`, `working`, or `ready` with no evidence
- local-only claims that are not yet reflected in the repo or issue comment

ALPHA must not treat an issue as complete unless a completion report exists.

OWL must not treat local unpushed work as complete program state.

If OWL has completed code locally but has not pushed or cannot comment, OWL must say so explicitly and use the repository fallback or `OWL NEEDS`.

## Invalid Label States

These combinations are invalid and must be corrected:

- open issue with both `OWL DONE` and `OWL NEEDS`
- `OWL DONE` with no visible completion comment
- `OWL NEEDS` with no visible blocker comment
- closed issue with `OWL NEEDS` still present

When ALPHA or OWL sees an invalid label state, they must:

1. trust the latest actionable comment over the label
2. correct the label state if they have permission
3. report the mismatch explicitly if they cannot correct it

When OWL needs ALPHA input:

1. Comment on the issue with a short Proven / Inferred / Unknown report.
2. Ask the specific question or state the exact blocker.
3. Add label `OWL NEEDS`.
4. Do not add `OWL DONE`.

When ALPHA responds to `OWL NEEDS`:

1. Comment on the same issue with `[OWL FOLLOWUP]`.
2. Include `Required next action for OWL:` followed by the specific next step.
3. Keep the response small enough for the poller to process without timing out.

When OWL successfully resolves the blocker:

1. Comment with the final Proven / Inferred / Unknown report.
2. Remove `OWL NEEDS` if present.
3. Add `OWL DONE`.

When OWL posts `OWL DONE`, ALPHA must treat that issue as actionable on the next poll/review cycle and continue without requiring a Scott relay.

When OWL completes implementation work:

1. Push first if push is part of the approved workflow for that issue.
2. Then post the completion report with commit hash and tests.
3. Then add `OWL DONE`.

If push did not happen yet, OWL must not imply that the repository already contains the result.

For large tasks that time out, do not keep retrying the same oversized issue body. Split the work into smaller `[OWL ACTION]` issues or ask ALPHA for a smaller follow-up using `OWL NEEDS`.

If OWL does not have GitHub issue-comment permission, do not fight the token or repeatedly retry failed comment commands.

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
