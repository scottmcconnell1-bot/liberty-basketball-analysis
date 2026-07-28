# Modular Product Roadmap

Updated: 2026-06-16
Branch: jason-5-may-updates

This document defines Liberty as a modular basketball operations product. The architecture should support paid add-on packages over time, but all packages must share one trusted event ledger.

## Product North Star

Liberty is a coach-facing basketball operations platform with an AI assistant coach layered on top.

The platform should support:
- Full game breakdown
- Player minutes
- Team and individual stats
- Shooting stats
- Lineup stats
- Film review
- Scouting
- Play recognition
- Standout player identification
- Strategy awareness and creation
- AI-powered question answering and guided coach workflows

## Architecture Principle

Modular packaging must not create disconnected data systems.

All modules should read from and write to shared foundations:
- Teams
- Players
- Rosters
- Games
- Video assets
- Canonical event ledger
- Possessions
- Clips
- Review and correction records
- Provenance and confidence records

## Base Platform

The base platform is the operating system for every customer.

Included:
- Teams
- Seasons
- Players
- Rosters
- Games
- Video assets
- Manual tagging
- Canonical event ledger
- Clips
- Review and correction workflow
- User roles and permissions
- Basic reports
- Provenance records

Purpose:
- Make Liberty useful before advanced AI is reliable.
- Create trusted data the AI assistant can later query.
- Avoid forcing customers into all modules at once.

## Paid Add-On Modules

### Stats Module

Includes:
- Box scores
- Team stats
- Player stats
- Shooting splits
- Possession summaries
- Four Factors
- Efficiency metrics

Depends on:
- Base Platform
- Event ledger

### Minutes and Lineups Module

Includes:
- Substitutions
- Player minutes
- Plus/minus
- Lineup segments
- Lineup stats
- On/off impact

Depends on:
- Base Platform
- Event ledger
- Accurate substitution workflow

### Film Room Module

Includes:
- Searchable clips
- Playlists
- Player film pages
- Possession film
- Coach notes
- Review queues
- Sharing/export workflows

Depends on:
- Base Platform
- Video assets
- Clips

### Scouting Module

Includes:
- Opponent tendencies
- Scouting reports
- Matchup notes
- Personnel notes
- Scout packets
- Game-plan priorities

Depends on:
- Base Platform
- Film Room Module
- Stats Module

### Playbook and Play Recognition Module

Includes:
- Play calls
- Offensive sets
- Defensive coverages
- BLOB/SLOB/ATO tagging
- Pick-and-roll and action labels
- Human-reviewed play recognition

Depends on:
- Base Platform
- Film Room Module
- Possessions

### Strategy Module

Includes:
- Standout players
- Underperformers
- Strengths and weaknesses
- Practice focus suggestions
- Suggested adjustments
- Lineup impact summaries
- Playbook linkage

Depends on:
- Base Platform
- Stats Module
- Minutes and Lineups Module
- Film Room Module

### AI Assist Module

Includes:
- Natural language questions
- Guided dropdown questions
- Clip lookup
- Report generation
- Stat summaries
- Anomaly flags
- Suggested review items
- Confidence-aware answers

Depends on:
- Base Platform
- Reviewed event data
- Provenance and confidence records

### Advanced Tracking Module

Includes:
- Player tracking
- Ball tracking
- Shot quality
- Spacing
- Defender proximity
- Automated play and coverage recognition

Depends on:
- Base Platform
- Video assets
- Advanced model validation
- Strong data governance

## Phased Roadmap

### Phase 1: Platform Core

Goal:
- Build the trusted data and film foundation.

Deliver:
- Teams, players, rosters, seasons, games
- Video assets
- Manual tagging
- Event ledger
- Clips tied to events
- Review/correction workflow
- Basic reports

### Phase 2: Stats and Minutes

Goal:
- Turn reviewed events into basketball operations data.

Deliver:
- Player minutes
- Substitutions
- Box score stats
- Team stats
- Individual stats
- Shooting stats
- Plus/minus
- Lineup segments

### Phase 3: Film and Scouting

Goal:
- Make film actionable for coaches.

Deliver:
- Searchable clips
- Player film pages
- Scouting reports
- Opponent tendencies
- Coach notes
- Practice focus lists

### Phase 4: Strategy Layer

Goal:
- Turn reviewed data into coaching decisions.

Deliver:
- Standout player summaries
- Underperformer flags
- Lineup impact summaries
- Matchup analysis
- Suggested adjustments
- Playbook linkage

### Phase 5: AI Assistant

Goal:
- Let coaches ask questions and generate outputs from trusted data.

Deliver:
- Typed coach questions
- Guided dropdown questions
- Clip-backed answers
- Report generation
- Stat anomaly detection
- Suggested review tasks

### Phase 6: Advanced AI

Goal:
- Increase automation only after benchmark evidence supports it.

Deliver:
- Play recognition
- Coverage recognition
- Tracking
- Shot quality
- Recommendation engine

## Packaging Rule

Billing can be modular later, but architecture must be modular now.

Implementation implications:
- Use feature flags or module permissions.
- Keep module routes/views/services separated.
- Derive all stats from the shared event ledger.
- Avoid module-specific shadow tables that duplicate truth.
- Keep review, provenance, and confidence available across modules.
