# AI Assistant Vision

Updated: 2026-06-16
Branch: jason-5-may-updates

This document defines the long-term Liberty AI assistant coach vision.

## Ultimate Goal

The ultimate goal is for AI to help Liberty coaching staff as an assistant coach.

The AI assistant should eventually:
- Answer coach questions
- Guide coaches through dropdown-driven workflows
- Pull stats from reviewed data
- Find supporting clips
- Generate scouting reports
- Identify standout players
- Identify weak points
- Suggest practice focus
- Suggest game adjustments
- Recognize plays and tendencies
- Explain what evidence supports each answer

## Interaction Modes

### Typed Questions

Examples:
- Who played the most effective minutes?
- Show me our best lineup in the second half.
- Why did we lose the rebounding battle?
- Which players struggled in transition defense?
- Show clips of every turnover against pressure.
- What should we work on in practice tomorrow?
- Who stood out besides the leading scorer?
- What sets worked best against zone?
- Build me a halftime adjustment report.

### Guided Workflows

Some coaches will prefer guided choices over typing.

Examples:
- Select game
- Select team, player, lineup, or opponent
- Select question type
- Select stats, clips, or report output
- Select confidence threshold
- Export report or playlist

The product should support both interaction styles.

## Evidence Discipline

The assistant must not invent truth.

Every answer should separate:
- Proven: supported by reviewed events, stats, clips, tests, or source files
- Inferred: a basketball conclusion based on patterns
- Unknown: not enough evidence, needs review, or missing data

When the answer uses unreviewed AI output, the assistant must say so.

## Assistant Maturity Levels

### Level 1: Data Q&A

The assistant answers from reviewed data only.

Examples:
- Player stats
- Team stats
- Minutes
- Lineups
- Clips by tag
- Basic reports

### Level 2: Workflow Assistant

The assistant helps coaches work faster.

Examples:
- Build clip playlists
- Summarize a game
- Create player reports
- Flag missing substitutions
- Flag stat anomalies
- Suggest review priorities

### Level 3: Basketball Analyst

The assistant connects stats, clips, and context.

Examples:
- Explain why a lineup worked
- Compare transition vs half-court possessions
- Identify opponent tendencies
- Identify standout players
- Suggest practice focus

### Level 4: Strategy Assistant

The assistant proposes basketball actions with evidence.

Examples:
- Suggested matchup adjustments
- Suggested lineup combinations
- Suggested defensive emphasis
- Suggested playbook actions
- Opponent scout summaries

### Level 5: Assistant Coach

The assistant becomes a high-level coaching companion.

Examples:
- Live or halftime questions
- Pre-game scout generation
- Post-game review
- Player development plans
- Play and coverage recognition
- Strategy recommendation engine

## Guardrails

AI must not become the source of truth before evidence exists.

Rules:
- Reviewed event ledger outranks AI output.
- Human corrections outrank model predictions.
- AI suggestions must carry confidence and provenance.
- High-impact recommendations must link to clips and stats.
- Coaches must be able to accept, reject, or correct AI suggestions.

## Product Principle

Manual-first does not mean manual forever.

The base platform creates trusted data. The AI assistant becomes more powerful as that data gets better.
