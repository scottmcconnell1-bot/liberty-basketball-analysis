# Product Benchmarks

Updated: 2026-06-16
Branch: jason-5-may-updates

This document records the external product patterns Liberty should study, mimic conceptually, and improve. It does not authorize copying proprietary code, design, data, branding, or private workflows.

## Strategic Conclusion

Liberty should be built as a modular basketball operations platform, not as a detector-first project.

The product pattern to mimic is:

```text
Trusted video and event workflow -> reviewed stats and clips -> scouting and strategy -> AI assistant coach
```

The product pattern to avoid is:

```text
Raw computer vision -> unreviewed stats -> coach-facing truth
```

## Benchmark Products

### Hudl

Primary pattern:
- Team video library
- Clip sharing
- Player and coach review
- Simple workflow for teams, athletes, and staff

What Liberty should borrow:
- Video-first organization
- Easy clip access
- Player/team review workflow
- Shareable film outputs

What Liberty should improve:
- More transparent event provenance
- More coach-customized strategy notes
- Stronger modular packaging around stats, scouting, and AI assistance

### Hudl Sportscode / Nacsport / Dartfish

Primary pattern:
- Fast manual tagging
- Live or postgame coding
- Custom buttons/categories
- Timeline review
- Clip generation from tagged events

What Liberty should borrow:
- Manual-first tagging speed
- Keyboard-driven and button-driven event capture
- Coach-defined tag categories
- Event timeline tied directly to video clips

What Liberty should improve:
- Basketball-specific event ledger and stat generation
- Built-in player minutes, lineups, and possessions
- AI assistant layered over reviewed data

### Synergy Sports

Primary pattern:
- Basketball-specific possession, event, play type, and player tendency database
- Stats linked to clips
- Scouting and player development workflows

What Liberty should borrow:
- Possession-based organization
- Event taxonomy for basketball
- Play type and tendency reporting
- Clip-backed scouting evidence

What Liberty should improve:
- Team-specific language and playbook customization
- Transparent Proven / Inferred / Unknown reporting
- Modular packaging for different customer levels

### FastModel / FastDraw / FastScout

Primary pattern:
- Playbook
- Scouting report creation
- Game-plan and strategy workflow

What Liberty should borrow:
- Play and action vocabulary
- Scouting packet structure
- Practice focus and game-plan linkage
- Strategy notes connected to film

What Liberty should improve:
- Connect playbook concepts to reviewed game events and clips
- Let the AI assistant answer questions from the team's own event ledger

### Second Spectrum / SportVU / ShotTracker-Type Systems

Primary pattern:
- Advanced player and ball tracking
- Spacing, shot quality, player location, and movement analytics

What Liberty should borrow later:
- Tracking data model concepts
- Spatial tracking table design
- Shot quality and spacing vocabulary

What Liberty should not copy into the MVP:
- Assumption of reliable full-court automated tracking
- High-end play recognition before trusted event and lineup foundations exist

## Liberty Product Position

Liberty should be designed as:

```text
Sportscode-style tagging
+ Synergy-lite basketball event database
+ FastScout-style strategy reporting
+ AI assistant coach
```

## MVP Implications

The MVP should be useful without computer vision.

Required MVP foundations:
- Teams, players, rosters, seasons, and games
- Video assets and clip management
- Canonical event ledger
- Manual tagging workflow
- Possessions
- Substitutions and player minutes
- Team and player stats
- Review and correction workflow
- Basic reports

AI should assist the workflow, not define truth, until automation proves it can meet coach-grade reliability.

## Sources Used During Product Review

- Hudl: https://www.hudl.com
- Hudl Sportscode: https://www.hudl.com/products/sportscode
- Synergy Sports support and product context: https://support.synergysports.com
- FastModel Sports: https://fastmodelsports.com
- Nacsport: https://www.nacsport.com
- Dartfish: https://www.dartfish.com
- NBA Stats glossary: https://www.nba.com/stats/help/glossary
- FIBA Statisticians Manual: https://assets.fiba.basketball
