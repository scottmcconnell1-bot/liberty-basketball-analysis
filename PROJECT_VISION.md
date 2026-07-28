# Project Vision

Updated: 2026-06-16
Branch: jason-5-may-updates

## Purpose

Liberty Basketball Analysis is a modular basketball operations and film analysis platform for Scott McConnell's coaching workflow and future client offerings. It is intended to help review games, manage film sources, tag and analyze possessions, generate trusted player and team data, identify strategic insights, and reduce manual review effort.

This project is not a ball detector. Ball detection is one subsystem that may support basketball analysis, but the project succeeds only when it improves coaching decisions, game breakdown, player evaluation, scouting, strategy, and coach workflow.

The long-term product goal is a Liberty AI Assistant Coach layered on top of a trusted basketball operations platform. The assistant should answer coach questions, guide coaches through structured workflows, find supporting clips, produce reports, identify standout players, and recommend strategy only from evidence-backed data.

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
- The first customer is Scott's Liberty workflow, but the architecture should support modular client packages later.
- Manual-first does not mean manual forever; manual and reviewed data create the trusted foundation for future AI automation.
- AI should assist, summarize, suggest, and guide, but reviewed event data remains the source of truth.

## Current Direction

The current product direction is coach-first and modular:

- Build the trusted base platform first: teams, players, rosters, games, video assets, event ledger, clips, review/correction, and basic reports.
- Add paid or permissioned modules in stages: stats, minutes/lineups, film room, scouting, playbook/play recognition, strategy, AI assist, and advanced tracking.
- Keep all modules tied to one shared event ledger and provenance model.
- Treat ball detection and computer vision as support systems, not the product foundation.

Supporting docs:
- PRODUCT_BENCHMARKS.md
- MODULAR_PRODUCT_ROADMAP.md
- AI_ASSISTANT_VISION.md

## Success Definition

The project is successful when Scott and future clients can move from film to trusted basketball decisions faster than manual review alone, with stats, clips, lineups, scouting, strategy, and AI assistant answers all backed by reviewable evidence.
