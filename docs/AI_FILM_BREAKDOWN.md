# AI Film Breakdown — Complete Specification

> Source: Scott McConnell, "AI Film Breakdown" document, May 2026
> This is the authoritative specification for what the AI film analysis system must track and how it must work.

## 1. Stats to Collect (Player + Team)

### Core Box-Score
- Points, Rebounds (offensive/defensive), Assists, Steals, Blocks, Turnovers, Fouls, Minutes

### Per-Possession Metrics
- Points per possession (PPP), offensive rating, defensive rating, turnover rate, offensive rebound rate

### Play-Type & Shot-Location Splits
- Pick-and-roll ball-handler scoring/assists, catch-and-shoot, pull-ups, post-ups
- Restricted area vs midrange vs corner 3s

### Passing & Creation
- Assist rate, secondary assists (hockey assists), assist-to-turnover, individual shot creation (ISOP)

### Defensive Impact
- Opponent FG% when guarded, contested shot rate, defensive rebound rate, steal/deflection rates, opponent PPP by action

### Lineup & Synergy
- Plus/minus by lineup, net rating by lineup, minutes together

## 2. What to Record and How to Compute It

### Points
- Count when ball legally passes through hoop
- Record source: 2-pt, 3-pt, free throw
- Total points = 2*(2PT makes) + 3*(3PT makes) + 1*(FT makes)

### Field Goals
- FG = total field goals made (2PT + 3PT)
- FGA = total field goals attempted (excludes free throws)
- FG% = FG / FGA
- Keep 2P/3P splits and 2P%/3P% separately

### Free Throws
- FT and FTA counted separately
- FT% = FT / FTA

### Rebounds
- Offensive: team/player gains possession after their team's missed shot
- Defensive: team/player gains possession after opponent's missed shot
- Count when player secures control (catch or firm tip) of live ball after missed shot or free throw

### Other Box Items
- Assists, turnovers, steals, blocks, fouls, minutes — follow standard stat definitions

## 3. Machine-Friendly Event Definitions (AI Detection Spec)

### Shot Attempt (FGA)
- **Event start**: player releases ball toward basket
- **Visual cues**: arm extension, ball leaves shooter's hand, direction toward rim
- **Contextual cues**: shooter inside court area, play clock/shot clock state
- **Label attributes**: shooter ID, timestamp, location (court coordinates), shot type (2PT/3PT/FT), frame of release

### Made Field Goal (FGM)
- Shot attempt + ball passing through hoop without whistle overturning
- **Visual/temporal rules**: detect ball entering basket plane after release; allow brief rim contact
- **Output attributes**: scorer ID, points (2 or 3), timestamp, assist ID if pass directly preceded

### Free Throw Attempt/Make
- From free-throw location, shooter stationary, no defense contesting
- Make = ball through hoop
- Tag sequence for multiple FT attempts and rebounds off missed FTs

### Rebound (General)
- After missed shot (ball contacts rim/backboard), player gains clear control of live ball
- **"Gains control"**: secure two-handed catch, one-handed firm grasp, or controlled tip
- **Time window**: first securement within 1-3 seconds after ball contacts rim/backboard
- Record: team, player, court coordinates

### Offensive vs Defensive Rebound
- If rebounder's team was the shooting team on the immediately preceding shot attempt → Offensive
- Otherwise → Defensive
- Use possession-tracking to confirm

### Assist — Machine-Spec Definition
An assist is credited to Player A if ALL of the following are true:

1. Player A makes a legal pass (ball-release frame recorded) to Player B within the same continuous possession
2. Player B receives the pass (ball control detected within reception window of 0.75s)
3. Player B makes a field goal within N seconds of Player A's pass release (default N = 2.0s, acceptable range 1.5-3.0s)
4. Player B's made shot is a direct result of the pass (no significant individual creation)

**Operational criteria for "direct result":**
- Continuous possession: no change of possession between pass and made shot
- Reception detection: Player B's first secure control within 0.75s of pass arrival
- Creation allowance: permit up to M dribbles after reception (M = 0 or 1 for stricter; default M = 1)
- Movement allowance: small footwork, gather steps, or single drive allowed; extended isolation disqualifies
- If Player B covers >2.5 meters from reception to shot AND dribble_count > 0 AND delta > 1.5s → individual creation, no assist

**Concrete detection logic:**
```
Detect pass_release_frame (tA) and pass_end_frame
Identify reception_frame (tR) where ball enters Player B control
Require: tR - tA ≤ 0.75s
Confirm: no possession change or whistle between tA and shot_made_time (tS)
Compute: delta = tS - tA; require delta ≤ 2.0s
Count: dribbles between tR and tS; require ≤ 1
Evaluate: if distance > 2.5m AND dribbles > 0 AND delta > 1.5s → no assist
If all checks pass → label assist_from = Player A, assist_type = primary
```

**Secondary assists (hockey assists):**
- Each link in chain must satisfy pass→next-made-shot ≤ 2.0s OR pass→next-pass reception ≤ 1.0s
- Practical default: secondary assist only if both intervals ≤ 1.5s and pass→final-shot ≤ 3.0s

**Edge cases:**
- Put-backs/tip-ins: treat as rebound + put-back score, not assist unless discrete pass
- Charges/offensive fouls: if called before made basket, no assist
- Shot created by shooter: if >3.0s or >2 dribbles after pass → no assist
- Deflected passes: if defender touches but offense recovers quickly within thresholds → allow assist

### Turnover
- Possession loss not resulting in made field goal
- Categorize: bad pass, travel, offensive foul, shot-clock, steal
- Visual cues: ball out-of-bounds, defender dislodging ball, foot movement without dribble, whistle

## 4. Features and Labels for Training

### Core Labels Per Frame/Segment
- Player bounding boxes with consistent IDs
- Ball bounding box
- Ball state: in-hand, in-flight, on-rim, in-hoop, loose
- Court homography coordinates (x, y)
- Timestamp, current possession team

### Event-Level Annotations
- shot_release_frame, shot_result (make/miss)
- rebound_frame, rebound_player_id, rebound_type (off/def)
- assist_from_id, turnover_type

### Derived Features for Models
- Shot distance from rim, shooter angle
- Defender proximity at release (meters)
- Shot contest indicator (binary/score)
- Ball flight vector, time-to-rim
- Nearest defender IDs and distances
- Number of players in paint, rebounding box occupancy

### Temporal Windows
- Annotate short windows (±1-3s) around key events for context (who boxed out, who contested, trajectory)

## 5. Practical AI Detection Pipeline

1. **Preprocess**: Run person and ball detectors (YOLO/Detectron/Faster-RCNN), track players (ReID + Kalman filter), compute court homography
2. **Low-level event detectors**: Classify ball state transitions (release → flight → rim → rebound/score) using object detector + temporal classifier (temporal CNN / LSTM)
3. **Rule-based post-processing**: Convert low-level detections to box-score events using deterministic rules
4. **Human-in-the-loop validation**: Sample clipped events, compare to human labels, correct model biases, use active learning

## 6. What to Look for in Film (Player Development Focus)

### Decision Patterns
- Choices in pick-and-roll, late-clock actions, pass vs shoot decisions
- Link decision frequency to turnover and assist rates

### Shot Selection Context
- Contested vs uncontested, pull-ups vs catch-and-shoot, rushed vs balanced possessions

### Off-Ball Movement & Spacing
- Cutting, screens, relocating to open spots
- Poor movement explains low assist rate and stagnant offense

### Defensive Fundamentals and Effort
- On-ball defense angles, help rotation timing, closeouts, transition pursuit, boxing out
- Match observations to defensive rating and opponent PPP

### Rebounding & Finishing at Rim
- Technique, boxing out, weak-side help
- Combine with offensive/defensive rebound rates

### Habitual Errors vs Strengths
- Isolate repeated breakdowns (late closeouts, over-helping)
- Isolate repeat high-value plays (post-entry vision, drive-and-kick)

### Body Language and Mental Factors
- Effort on 50/50 plays, reaction after mistakes, bench energy

## 7. Scouting — What to Extract

### Primary Personnel & Roles
- Ball-handler, go-to scorer, primary rim protector, best rebounder, most dangerous spot-up shooter
- Note usage and how often plays run for them

### Offensive Triggers & Sets
- Actions that start offense (sideline out, horns, early PnR)
- What they run under pressure (iso, spread PnR, post touches)
- Tag possessions that produce their best PPP

### Defensive Scheme and Tendencies
- Man, drop, switch, 2-3 zone, trap frequency
- How they defend PnR (show/drop/ice/switch frequency)
- Relate to opponent PPP against them

### Late-Clock and Situational Play
- Go-to plays in late shot-clock, end-of-quarter, out-of-bounds, foul-game situations
- Practice defending those scenarios

### Mismatches and Personnel Vulnerabilities
- Who struggles switching to smaller/faster or bigger/stronger opponents
- Which bench players change spacing or rebounding

### Pace, Turnover Tendencies, and Rebounding Profile
- Fast and gamble for steals vs slow and methodical
- Crash for offensive boards vs leave transition exposed

### Scouting Report Format
- Scouting video clips
- 10-15 bullet tactical summary
- 3 practice points to exploit opponent weaknesses

## 8. Film Tagging Schema (What to Store Per Clip)

### Clip Metadata
- game_time, quarter, score, offensive_team, defensive_team, lineup on court

### Action Metadata
- action_type (PnR, isolation, post entry, transition)
- trigger_frame, initiator_id, primary_targets (IDs)
- result (score/miss/turnover), PPP for that action

### Tactical Notes
- Defender coverage on action (drop/switch/hedge)
- Ball side help, timeout/sub call, substitution change

### Prioritization
- Use frequency × negative outcome OR frequency × PPP allowed to pick 2 practice focuses

### Drill Mapping
- Map each teach_point to a single drill and measurable target
- Example: "reduce open corner 3s allowed off PnR by 50%" → closeout footwork + drop/sprint recovery drill

## 9. Micro Sessions (Practice Integration)

1. Show 3 clips: bad example, correct pro example, corrected teammate
2. Run 6-8 reps of the drill at game speed
3. Reinforce with immediate film feedback

## 10. Scouting Report Deliverables

### Executive Summary (Top 6 Items)
- Offensive identity, defensive identity, 3 primary weapons, 2 quick exploitable weaknesses, tempo

### Playbook Digest
- Five most used offensive sets and how they react to pressure

### Situational Cheat Sheets
- Late shot clock plays, inbound plays, press breaker, substitution windows to attack
- Give players 3-sentence answers for each situation

### Tape Package
- 6-10 clips (high impact possessions) with timestamps and coach cue lines to show players pre-game

## 11. Coaching Application Example

**Stat trigger**: Team turnover rate up 6% last game, assist rate down.
**Film find**: Point guard forcing pull-up 3s off penetration 9 times, leading to contested shots or turnovers.
**Action**: Show clips, run decision-making PnR drills, reduce mental clutter by limiting teaching points to "attack baseline or kick," measure turnover rate next 3 games.
