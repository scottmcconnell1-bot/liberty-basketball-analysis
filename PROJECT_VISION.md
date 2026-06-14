# Project Vision

Updated: 2026-06-14
Branch: jason-5-may-updates

## Purpose

Liberty Basketball Analysis is a basketball operations and film analysis platform for Scott McConnell's coaching workflow. It is intended to help review games, manage schedules and film sources, tag and analyze possessions, generate useful basketball information, and reduce manual review effort.

This project is not a ball detector. Ball detection is one subsystem that may support basketball analysis, but the project succeeds only when it improves coaching decisions and game-night workflow.

## Core Questions

Every feature should be evaluated against these questions:

1. Does this improve basketball analysis?
2. Does this improve coach workflow?
3. Does this improve data quality?
4. Does this reduce manual review effort?
5. Does this support future basketball operations features?

## Product Principles

- Scott owns the basketball vision and final decisions.
- Repository files are the source of truth, not chat history or agent memory.
- Work must be small, reviewable, verified, and documented.
- Automation must have a manual fallback.
- Evidence must be separated into Proven, Inferred, and Unknown.
- SQLite remains the persistence layer unless Scott approves otherwise.
- Vanilla HTML/JS remains the frontend approach unless Scott approves otherwise.
- The system is for a single coach and team workflow, not a SaaS product.

## Current Direction

The current priority is not new feature expansion. The project first needs a verified baseline:

- Confirm source-of-truth documentation.
- Verify schema and data-model risks.
- Audit the ball detection subsystem from evidence.
- Document dataset provenance and label quality.
- Stabilize workflow between Codex, OWL/Hermes, and Scott.

## Success Definition

The project is successful when Scott can use it during the season to move from film to actionable basketball decisions faster and with better evidence than manual review alone.