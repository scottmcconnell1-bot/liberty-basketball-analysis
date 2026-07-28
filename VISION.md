# Vision — Liberty Basketball Analysis

## Purpose
A basketball film and analytics system built for a real coach (Scott) to actually use in-season. Not a toy demo — a practical tool that matches how Scott coaches: schedules, games, film sources (NFHS/Pixellot/manual), stats, player development, and practice cut-ups.

## Core Principles
1. **Small, safe steps** — Every feature is built in reviewable chunks. Scott approves before moving on.
2. **Coach owns the domain** — Scott owns data model, terminology, workflow. Code serves his mental model.
3. **Feature flags everywhere** — Every major feature can be turned off without DB migrations.
4. **SQLite, schema.sql is law** — Single source of truth for the database.
5. **Don't break existing tables** — `events`, `analysis_runs`, `detections` are sacred.
6. **Limited in-season time** — Any feature must be usable in under 5 minutes on a game night.
7. **Fallback always works** — If automation fails, Scott can still watch film and take notes manually.
8. **Evidence over assumptions** — Every claim about the system must be verifiable from code, tests, or data.

## Current State (as of 2026-06-13)
- **Branch:** `jason-5-may-updates` (default branch, main source of truth)
- **Architecture:** Flask + Blueprints (11 blueprints), SQLite, vanilla HTML/JS
- **Phases P0–P2 complete:** Foundation, data model, schedule/season management
- **Phase P3 (Games & Film Sources):** Partially implemented (games blueprint exists)
- **Phase P4+ (NFHS, Stats, Practices, Player Dev):** Blueprints exist, implementation varies
- **Ball detection:** YOLO-based with heuristic assistance. Audit (v14) showed 0/20 precision. Needs rebuild.
- **Tests:** 16 test files under `tests/` covering API, schema, events, UI, playbook, messaging, tracker
- **Deployment:** Docker + docker-compose, systemd service, nginx config
- **AI analysis:** `ai_analyzer.py` runs YOLO detection, `event_generator.py` derives events, `film_analysis.py` does enhanced analysis

## What Success Looks Like
- Scott can add a season, schedule games, see them on `/schedule` — **DONE**
- Scott can create game instances, attach video sources — **PARTIALLY DONE**
- Scott can get box-score stats from tagged events with clickable video timestamps — **IN PROGRESS**
- Scott can track practices, get AI-generated practice reports — **BLUEPRINT EXISTS**
- Scott can track player development with clips tied to games/events — **BLUEPRINT EXISTS**
- Any new AI agent can read this repo and understand the project in 10 minutes

## What This Project Is NOT
- Not a heavy AI/CV project in early phases — CV comes later
- Not a SaaS or multi-user system — single coach, single machine
- Not a replacement for watching film — it augments Scott's coaching
- Not a ball detector — ball detection is one subsystem of a basketball operations platform
