# Liberty Basketball Analysis — Complete UI Frame & Tab Reference

**Generated:** 2026-05-08  
**Server:** http://localhost:8081  
**Branch:** jason-5-may-updates  

---

## How to Use This Document

Each **Tab** (nav item) is a major section. Within each tab, every **Frame** (card, panel, modal, form, table) is numbered. Use these numbers to tell me exactly what you want changed.

**Example:** *"Tab 3, Frame 2 — change the button color to red"* or *"Tab 5, Frame 4 — the table is too wide"*

---

## Global Navigation Bar (All Tabs)

The nav bar appears at the top of every page. Available tabs depend on feature flags.

| # | Nav Label | Route | Feature Flag |
|---|-----------|-------|-------------|
| N1 | Dashboard | `/` | (always) |
| N2 | Schedule | `/schedule` | ENABLE_SEASONS_SCHEDULE |
| N3 | Videos | `/videos` | ENABLE_AUTO_STATS_M1 |
| N4 | Status | `/status` | ENABLE_AUTO_STATS_M1 |
| N5 | Film Tool | `/film` | ENABLE_MANUAL_TAG_MVP |
| N6 | Games | `/games` | ENABLE_GAMES_SOURCES |
| N7 | NFHS Matches | `/nfhs-matches` | ENABLE_NFHS_MATCHING |
| N8 | Playbook | `/playbook` | ENABLE_PRACTICES |
| N9 | Practices | `/practices` | ENABLE_PRACTICES |
| N10 | Player Dev | `/player-development` | ENABLE_PLAYER_DEVELOPMENT |
| N11 | Playlists | `/practice-playlists` | ENABLE_PRACTICE_PLAYLISTS |
| N12 | Settings | `/settings` | (always) |
| N13 | Users | `/users` | (always) |
| N14 | Debug / Issues | `/debug` | (always) |

**Global Elements (appear on every page):**
- **G1** — Nav bar (logo + tabs)
- **G2** — Resource status bar (CPU, RAM, GPU pills — JS-populated)
- **G3** — Report Bug/Idea button (gradient animated, top-right)
- **G4** — Report Drawer (slide-in panel with form: type, title, details, source)

---

## Tab 1: Dashboard (`/`)

**Purpose:** Overview dashboard showing system stats, upcoming games, and recent events.

### Frame 1.1 — Stat Boxes Row
Four stat boxes loaded via JS from `/api/dashboard`:
- Seasons count
- Scheduled Games count  
- Events Tagged count
- Players count

### Frame 1.2 — Upcoming Games Table
- **Columns:** Date, Time, Opponent, Location, Status
- **Button:** "View All" → links to `/schedule`
- Loaded via JS fetch to `/api/dashboard`

### Frame 1.3 — Recent Events Table
- **Columns:** Game, Player, Event, Timestamp, Verified
- Loaded via JS fetch to `/api/dashboard`

---

## Tab 2: Schedule (`/schedule`)

**Purpose:** Manage season schedules — add/edit/delete games, import PDF schedules, export to MaxPreps CSV.

### Frame 2.1 — Page Header Buttons
- **Button:** "Clear Filters" → resets to `/schedule`
- **Button:** "+ Add Game" → scrolls to add-game form
- **Button:** "📄 Import PDF" → opens team selector modal
- **Button:** "📤 Export MaxPreps" → downloads CSV at `/schedule/export-maxpreps`

### Frame 2.2 — PDF Team Selector Modal (`pdf-team-modal`)
- **Select:** Team dropdown (Boys HS, Girls HS, Jr High Boys, Jr High Girls, etc.)
- **Button:** "Cancel" → closes modal
- **Button:** "Upload PDF" → opens file picker

### Frame 2.3 — PDF Import Preview Modal (`pdf-import-modal`)
- **Table:** Editable preview of extracted games
  - Per-row inputs: Date, JV Time, Frosh Time, Var Time, Opponent, Team, Level, Gender, Location
- **Button:** "Cancel" → closes modal
- **Button:** "Import All Games" → POST to `/api/schedule/import-pdf/confirm`

### Frame 2.4 — Filter Bar (GET form)
- **Select:** Season (All Seasons + options)
- **Select:** Level (All Levels + Jr High, JV, Varsity)
- **Select:** Gender (All Genders + Boys, Girls)
- **Select:** Status (All Statuses + options)
- **Button:** "Apply" → submits GET filter

### Frame 2.5 — Games Table (`schedule-table`)
- **Columns:** DATE | OPPONENT (with team badge) | TIMES (JV/Frosh/Var) | Actions
- **Per-row:** "Edit" link, "Delete" button

### Frame 2.6 — Add/Edit Game Form (POST `/schedule/games/save`)
- **Hidden:** game_id, filter params
- **Select:** Season (required)
- **Text:** Program Name
- **Select:** Team
- **Select:** Level
- **Select:** Gender
- **Select:** Location Type (Home/Away)
- **Date:** Game Date (required)
- **Time:** JV Time
- **Time:** Frosh Time
- **Time:** Varsity Time (required)
- **Text:** Opponent Name (required)
- **Text:** Tournament Name
- **Select:** Status
- **Textarea:** Notes (3 rows)
- **Button:** "Reset" link
- **Button:** "Save Game"

### Frame 2.7 — Seasons Table
- **Columns:** Name | Start | End | Actions
- **Per-row:** "Edit" link, "Delete" button

### Frame 2.8 — Add/Edit Season Form (POST `/schedule/seasons/save`)
- **Hidden:** season_id
- **Text:** Name (required)
- **Date:** Start Date (required)
- **Date:** End Date (required)
- **Button:** "Add Season" / "Update Season"

---

## Tab 3: Games (`/games`)

**Purpose:** Manage game records, link video sources, track results and conference status.

### Frame 3.1 — Page Header
- **Button:** "+ Add Game" → scrolls to form

### Frame 3.2 — Games Table
- **Columns:** Game | Schedule Link | Primary Source | Result | Conference | Extra Sources | Actions
- **Per-row:** "Edit" link, "Delete" button

### Frame 3.3 — Add/Edit Game Form (POST `/games/save`)
- **Hidden:** game_id
- **Select:** Scheduled Game (Standalone scouting game + options)
- **DateTime:** Start Time
- **DateTime:** End Time
- **Select:** Source Type (required)
- **Text:** Source Key (required)
- **Text:** NFHS Game ID
- **Text:** NFHS URL
- **Number:** Home Score
- **Number:** Away Score
- **Select:** Result
- **Checkbox:** Is Conference
- **Button:** "Reset" link
- **Button:** "Save Game"

### Frame 3.4 — Link Source to Game Form (POST `/games/sources/save`)
- **Select:** Game (required)
- **Select:** Source Type (required)
- **Text:** Source Path (required)
- **Button:** "Add Source"

### Frame 3.5 — Linked Sources Table
- **Columns:** Game | Source | Actions
- **Per-row:** "Delete" button

---

## Tab 4: Videos (`/videos`)

**Purpose:** Browse uploaded videos, manage AI analysis runs, delete videos.

### Frame 4.1 — Page Header Buttons
- **Button:** "+ Upload New Video" → links to `/film`
- **Button:** "🗑 Clear All Videos" → opens clear-all modal

### Frame 4.2 — Video Table (`video-table`)
Loaded via JS from `/api/videos`.
- **Columns:** Original Filename | Opponent | Uploaded | Size | AI Status | Detections | Events | Runs | Actions
- **Per-row:** "Open in Film Tool" link, "Compare AI" link, "🗑" delete button

### Frame 4.3 — Delete Video Modal (`delete-modal`)
- **Text:** Confirmation message
- **Button:** "Cancel"
- **Button:** "Delete permanently"

### Frame 4.4 — Clear All Modal (`clear-modal`)
- **Text:** Warning message
- **Button:** "Cancel"
- **Button:** "Yes, clear everything" → POST `/api/admin/reset`

---

## Tab 5: Film Tool (`/film`)

**Purpose:** Tag basketball events on video, manage games, generate reports. This is the most complex page with sub-tabs.

### Frame 5.1 — Top Bar Sub-Tabs
- **Button:** "Tagger" → shows Frame 5.2–5.7
- **Button:** "Games" → shows Frame 5.8
- **Button:** "Reports" → shows Frame 5.9

### Frame 5.2 — Top Bar Action Buttons (all views)
- **Button:** "Resume Last Game" → loads last tagged game
- **Button:** "Save Game" → saves current game data
- **Button:** "Manage Terms" → opens term dialog (Frame 5.10)
- **Button:** "Manage Rosters" → opens roster dialog (Frame 5.11)
- **Button:** "◐" → theme toggle (dark/light)
- **Button:** "Export Game Data" → exports current game as JSON

### Frame 5.3 — AI Analysis Upload Form (`aiUploadForm`) — Tagger View
- **File Input:** Video file (required)
- **Text Input:** Opponent name
- **Button:** "Upload and Analyze"
- **Progress Bar:** Upload progress (hidden by default)

### Frame 5.4 — Game Info Panel — Tagger View
- **Button:** "Hide game info" toggle
- **Button:** "Start New Game"
- **Score Cards:** "Our Team" / "Opponent" with running score
- **Select:** Game Type (My Game, Scout Game)
- **Select:** Competition Type (Non-Conference, Conference, Tournament)
- **Text:** Game Date
- **Text:** Our Team Name (default: "Liberty")
- **Text:** Opponent
- **Select:** Game Result (Not set, Win, Loss)
- **Text:** Home Team Name
- **Text:** Away Team Name
- **Text:** Output Directory + "Select" folder picker button

### Frame 5.5 — Video Player — Tagger View
- **File Input:** Local video file picker
- **Video Element:** Native HTML5 video with controls
- **Playback Controls:** `|<` , -30s, -10s, -3s, 0.5x, 0.25x, Play/Pause, 1x, 2.5x, 5x, +3s, +10s, +30s, `>|`
- **Time Display:** Current time / duration
- **Last Tagged Time Display**

### Frame 5.6 — Tagging Panel — Tagger View
**Possession/Flow Events:** BLOB, End QTR, Jump Ball, OB, SLOB, Start QTR, Time Out, Tip  
**Scoring/Offense Events:** And-1, Assist, FT Make, FT Miss, Off Reb, 2PT Make, 2PT Miss, 3PT Make, 3PT Miss, Turnover  
**Defense/Misc Events:** Block, Def Reb, Foul, Steal, Violation  
- **Button:** "Undo" — undo last tag
- **Button:** "Clear All" — clear all tags
- **Button:** "SUB" — substitution
- **Button:** "Starters" — opens starters dialog (Frame 5.14)
- **Event Count Display**

### Frame 5.7 — Bookmarks Panel — Tagger View
- **Text:** Game ID
- **Text:** Label
- **Text:** Note
- **Button:** "Save Current Time" — bookmark current video time
- **Button:** "Refresh" — reload bookmarks
- **Bookmarks List**

### Frame 5.8 — Games View
- **My Games Grid** — grid of saved games
- **Scout Games Grid** — grid of scout games

### Frame 5.9 — Reports View
- **Select:** Report Scope (Selected Game, My Games Season to Date, Scout Games Season to Date, All Saved Games)
- **Select:** Report Type (Team Totals, Individual Totals, Opponent Totals, Team Record, Box Score, Raw Data)
- **Button:** "Generate Report"
- **Report Title** display
- **Report Summary** textarea (readonly)
- **Report Table** (dynamic columns)
- **Quick Stats KPI Grid**
- **Button:** "Save Report"
- **Button:** "Print"

### Frame 5.10 — Current Tagged Events Table
- **Columns:** # | Label | Player | Quarter | Team | Side | Category | Event Type | Result | Start | Duration | Notes | Row
- **Per-row:** Clone button, Delete button

### Frame 5.11 — Manage Terms Dialog (`termDialog`)
- **Select:** Term field
- **Text:** New term input
- **Button:** "Add Term"
- **Terms List** with delete buttons
- **Button:** "Close"

### Frame 5.12 — Manage Rosters Dialog (`rosterDialog`)
- **Radio:** Level (Jr High, JV, Varsity)
- **Radio:** Gender (Boys, Girls, Coed)
- **Toggle:** Side (Our, Opp, Home, Away)
- **File Input:** CSV roster import
- **Player List**
- **Button:** "Add player"
- **Button:** "Close"

### Frame 5.13 — Add Player Dialog (`playerDialog`)
- **Text:** Position
- **Number:** Number
- **Text:** Name
- **Text:** Grade
- **Button:** "Cancel"
- **Button:** "Save"

### Frame 5.14 — Starters Dialog (`startersDialog`)
- **Liberty Starters** list (checkboxes, max 5)
- **Opponent Starters** list (checkboxes, max 5)
- **Button:** "Cancel"
- **Button:** "Save starters"

### Frame 5.15 — Quick Tag Dialog (`quickTagDialog`)
- **Dynamic team/player selection buttons**
- **Button:** "Cancel"

---

## Tab 6: Playbook (`/playbook`)

**Purpose:** Create and manage basketball plays with an interactive SVG court canvas. Draw player movements, passes, screens, and build step-by-step play animations.

### Frame 6.1 — Page Header
- **Button:** "+ New Play" → opens canvas editor
- **Select:** Category filter (All Categories, Offense, Defense, Press, Transition, Out of Bounds, Special)
- **Text Input:** Search plays (filters table)

### Frame 6.2 — Plays List Table
- **Columns:** Name | Category | Playbook | Steps | Updated | Actions
- **Per-row:** "View" link, "Edit" link, "Export" link, "Delete" button

### Frame 6.3 — Court Canvas & Editor Controls (Editor/View mode)
- **Button:** "+ Add Step" — add a new step to the play
- **Button:** "Duplicate" — duplicate current step
- **Button:** "Remove Step" — delete current step
- **Select:** Tool (Select/Move, Dribble Arrow, Pass Arrow, Screen Arrow)
- **Button:** "◀ Prev" — go to previous step
- **Step Label Display** (e.g., "Step 2 of 5")
- **Button:** "Next ▶" — go to next step
- **Button:** "▶ Play All" — animate all steps (view mode only)
- **SVG Court Canvas** — half-court with draggable player tokens (5 colors)
- **Textarea:** Step notes

### Frame 6.4 — Save Play Form (POST `/playbook/save`)
- **Hidden:** play_id, diagram_json, steps_json
- **Text:** Play Name (required)
- **Select:** Category
- **Textarea:** Description (2 rows)
- **Text:** Tags
- **Select:** Playbook
- **Button:** "💾 Save Play"

### Frame 6.5 — Step List
- Clickable step items (populated by JS)

---

## Tab 7: Player Development (`/player-development`)

**Purpose:** Tag and organize video clips of player actions for development review. Create clips from game footage categorized by skill type.

### Frame 7.1 — Page Header
- **Link:** "Clear Filters" → resets filters
- **Button:** "+ Add Clip" → scrolls to clip form

### Frame 7.2 — Filter Bar (GET form)
- **Select:** Player (All Players + options)
- **Select:** Season (All Seasons + options)
- **Select:** Category (All Categories, Turnover, Missed Boxout, Good Action, Defense, Offense, General)
- **Text:** Game ID
- **Button:** "Apply"

### Frame 7.3 — Clips Table
- **Columns:** Player | Label | Category | Start | End | Game | Season | Notes | Actions
- **Per-row:** "Delete" button

### Frame 7.4 — Add Clip Form (POST `/api/clips`)
- **Select:** Player
- **Select:** Season
- **Text:** Game ID
- **Text:** Clip Label (required)
- **Number:** Clip Start (ms) (required)
- **Number:** Clip End (ms) (required)
- **Select:** Category (General, Turnover, Missed Boxout, Good Action, Defense, Offense)
- **Textarea:** Notes (2 rows)
- **Button:** "Save Clip"

---

## Tab 8: Practice Playlists (`/practice-playlists`)

**Purpose:** Organize player development clips into ordered playlists for practice sessions.

### Frame 8.1 — Page Header
- **Link:** "Clear Filters"
- **Button:** "+ New Playlist" → scrolls to form

### Frame 8.2 — Filter Bar (GET form)
- **Select:** Season
- **Select:** Level
- **Select:** Status (Draft, Active, Archived)
- **Button:** "Apply"

### Frame 8.3 — Playlists Table
- **Columns:** Name | Season | Level | Status | Updated | Actions
- **Per-row:** "View" link, "Delete" button

### Frame 8.4 — Playlist Detail (when viewing a playlist)
- **Clips Table:** # | Player | Label | Category | Start | End | Remove
- **Add Clip Form:**
  - **Number:** Clip ID
  - **Button:** "Add Clip"

### Frame 8.5 — Create Playlist Form (POST `/api/playlists`)
- **Text:** Name (required)
- **Select:** Season
- **Select:** Level
- **Select:** Status (Draft, Active, Archived)
- **Button:** "Create Playlist"

---

## Tab 9: Practices (`/practices`)

**Purpose:** Schedule and manage practice sessions. Write practice plans, generate AI notes, track coach notes.

### Frame 9.1 — Page Header
- **Link:** "Range Summary" → `/practice-summary`
- **Button:** "+ Add Practice" → scrolls to form

### Frame 9.2 — Filter Bar (GET form)
- **Select:** Season
- **Select:** Level
- **Select:** Status
- **Button:** "Apply"

### Frame 9.3 — Practices Table
- **Columns:** Date | Season | Level | Status | Plan Source | Notes | Actions
- **Per-row:** "Edit" link, "Report" link, "Generate Notes" button, "Delete" button

### Frame 9.4 — Add/Edit Practice Form (POST `/practices/save`)
- **Hidden:** practice_id, filter params
- **Select:** Season (required)
- **Select:** Level
- **Date:** Practice Date (required)
- **Select:** Status
- **Select:** Plan Source
- **Textarea:** Plan Text (4 rows)
- **Textarea:** Coach Notes (4 rows)
- **Button:** "Reset" link
- **Button:** "Save Practice"

---

## Tab 10: Practice Summary (`/practice-summary`)

**Purpose:** View aggregated practice data across date ranges and filters.

### Frame 10.1 — Page Header
- **Link:** "Back to Practices" → `/practices`

### Frame 10.2 — Filter/Generate Form (GET)
- **Select:** Season
- **Select:** Level
- **Select:** Status
- **Date:** Start Date
- **Date:** End Date
- **Button:** "Generate"

### Frame 10.3 — Range Summary
- Pre-formatted summary text (AI-generated overview of practices in range)

### Frame 10.4 — Practices Table
- **Columns:** Date | Season | Status | Summary

---

## Tab 11: Practice Report (`/practices/<id>/report`)

**Purpose:** View detailed report for a single practice — plan, coach notes, AI notes, combined summary.

### Frame 11.1 — Page Header
- **Link:** "Back to Practices" → `/practices`
- **Button:** "Refresh AI Notes" → POST to regenerate AI notes

### Frame 11.2 — View Options Form (GET)
- **Checkbox:** Show Plan
- **Checkbox:** Show Coach Notes
- **Checkbox:** Show AI Notes
- **Checkbox:** Show Combined Summary
- **Button:** "Update View"

### Frame 11.3 — Practice Plan Section
- Pre-formatted practice plan text

### Frame 11.4 — Coach Notes Section
- Pre-formatted coach notes text

### Frame 11.5 — AI Notes Section
- Pre-formatted AI-generated notes

### Frame 11.6 — Combined Summary Section
- Pre-formatted combined summary

---

## Tab 12: Settings (`/settings`)

**Purpose:** Configure application settings — feature flags, AI model settings, vision runtime, local LLM models.

### Frame 12.1 — Settings Sub-Tabs
- **Button:** "Settings" → `/settings` (this page)
- **Button:** "Custom Weights Guide" → `/settings/custom-weights`

### Frame 12.2 — Hardware Info (read-only)
- GPU name
- GPU Memory
- Packages (OpenCV/Ultralytics/Torch)
- Local LLMs

### Frame 12.3 — Feature Flags Form (POST `/settings`)
- **Checkboxes:** Feature flags (ENABLE_AUTO_STATS_M1, ENABLE_EXTENDED_EVENTS_M2, ENABLE_GAMES_SOURCES, ENABLE_MANUAL_TAG_MVP, ENABLE_NFHS_MATCHING, ENABLE_PLAYER_DEVELOPMENT, ENABLE_PRACTICES, ENABLE_PRACTICE_PLAYLISTS, ENABLE_SEASONS_SCHEDULE, ENABLE_SEASON_REVIEW, ENABLE_WEEKLY_PACKET)
- **Checkboxes:** Analysis behavior flags (USE_DRIBBLE_EVENTS, USE_DRIBBLE_HEURISTICS)

### Frame 12.4 — Vision Runtime Settings
- **Select:** AI Detector Model (with recommended marker)
- **Text:** Custom Detector Model (shown when "custom" selected)
- **Select:** AI Inference Device
- **Select:** AI Event Generator Mode
- **Select:** AI Frame Stride
- **Number:** AI Tracker Max Distance
- **Number:** AI Tracker Max Frame Gap

### Frame 12.5 — Local AI Models
- **Select:** LLM Provider
- **Select:** LLM Model

### Frame 12.6 — Save Button
- **Button:** "Save Settings"

### Frame 12.7 — Recommended Ollama Models
- Per model: label, value, fit description
- **Badge:** "Installed" or **Button:** "Pull Model"

### Frame 12.8 — Pull Custom Model
- **Text:** Model name
- **Button:** "Pull Model"

---

## Tab 13: Custom Weights Guide (`/settings/custom-weights`)

**Purpose:** Documentation page explaining how to train custom YOLO weights for basketball detection.

### Frame 13.1 — Settings Sub-Tabs
- **Button:** "Settings" → `/settings`
- **Button:** "Custom Weights Guide" → this page

### Frame 13.2 — Content Cards (read-only)
- Informational cards with training instructions
- Example training command
- Dataset structure example
- dataset.yaml example

---

## Tab 14: Users (`/users`)

**Purpose:** View and manage application users.

### Frame 14.1 — Users Table
Loaded via JS from `/api/users`.
- **Columns:** Username | Email | Role | Created | Actions
- **Per non-admin row:** "Delete" button (with confirm dialog)

---

## Tab 15: Status (`/status`)

**Purpose:** Monitor live analysis runs and detection/event counts. Auto-refreshes every 5 seconds.

### Frame 15.1 — Analysis Runs Table
- **Columns:** # | Game ID | Video | Status | Started | Completed

### Frame 15.2 — Detections & Events Table
- **Columns:** Game ID | Detections | Events Tagged

---

## Tab 16: NFHS Matches (`/nfhs-matches`)

**Purpose:** Link scheduled games to NFHS (National Federation of State High School Associations) game records for video matching.

### Frame 16.1 — Add NFHS Candidate Form (POST `/nfhs-matches/add`)
- **Select:** Scheduled Game (required)
- **Text:** NFHS Game ID (required)
- **Text:** NFHS URL (required)
- **Number:** Confidence (0-1, step 0.01)
- **Button:** "Add Candidate"

### Frame 16.2 — Matches Table
- **Columns:** Scheduled Game | NFHS | Status | Confidence | Actions
- **Per-row:** "Confirm" button (if not confirmed), "Reject" button (if not rejected)

---

## Tab 17: Debug / Issues (`/debug`)

**Purpose:** View and manage bug reports, feature requests, and AI failure logs.

### Frame 17.1 — Report Section
- **Button:** "Open Report Form" → opens base template report drawer

### Frame 17.2 — Filter Form (GET)
- **Select:** Entry Type (All, Bug, Issue, Recommendation, Note)
- **Select:** Entry Status (All, Open, Completed)
- **Text:** Search query
- **Button:** "Filter"

### Frame 17.3 — Saved Reports Table
- **Columns:** ID | Type | Title | Source | Status | Created | Action
- **Per-row:** Browser console expand (details/summary), "Mark Completed" button

### Frame 17.4 — Recent AI Failures Table
- **Columns:** Run | Game ID | Error | Started | Completed

### Frame 17.5 — Application Logs
- **Text:** Log filter query
- **Button:** "Filter Logs"
- **Log Display** (monospace, max-height 420px)

---

## Tab 18: Analysis Compare (`/videos/<id>/compare`)

**Purpose:** Compare different AI analysis runs on the same video.

### Frame 18.1 — Page Header
- **Link:** "Back to Videos" → `/videos`
- **Link:** "Open Primary Run" → `/film/<filename>`

### Frame 18.2 — Rerun Form (POST `/ai/rerun/<vid_id>`)
- **Text:** Run Label
- **Read-only:** Current settings display
- **Button:** "Rerun AI with Current Settings"

### Frame 18.3 — Analysis Runs Table
- **Columns:** Run | Status | Detector | Generator | Device | LLM | Detections | Events | Created | Actions
- **Per-row:** "Open in Film Tool" link

---

## Quick Reference — All Modals/Dialogs

| # | Name | Triggered By | Tab |
|---|------|-------------|-----|
| M1 | Report Drawer | "Report Bug/Idea" button (global) | All |
| M2 | PDF Team Selector | "📄 Import PDF" button | Schedule |
| M3 | PDF Import Preview | After PDF upload | Schedule |
| M4 | Delete Video | "🗑" button on video row | Videos |
| M5 | Clear All Videos | "🗑 Clear All Videos" button | Videos |
| M6 | Manage Terms | "Manage Terms" button | Film Tool |
| M7 | Manage Rosters | "Manage Rosters" button | Film Tool |
| M8 | Add Player | "Add player" button in roster dialog | Film Tool |
| M9 | Quick Tag | Context-dependent | Film Tool |
| M10 | Starters | "Starters" button | Film Tool |

---

## Quick Reference — All API Endpoints

| Endpoint | Method | Returns | Used By |
|----------|--------|---------|---------|
| `/api/dashboard` | GET | Dashboard stats JSON | Dashboard |
| `/api/videos` | GET | Videos list JSON | Videos page |
| `/api/users` | GET | Users list JSON | Users page |
| `/api/users/<id>` | DELETE | Status JSON | Users page |
| `/api/seasons` | GET | Seasons list JSON | Various |
| `/api/playlists` | GET/POST | Playlists JSON | Playlists page |
| `/api/clips` | GET/POST | Clips JSON | Player Dev page |
| `/api/nfhs_matches` | GET/POST | NFHS matches JSON | NFHS page |
| `/api/schedule/import-pdf` | POST | Parsed games JSON | Schedule page |
| `/api/schedule/import-pdf/confirm` | POST | Import result | Schedule page |
| `/api/resource-status` | GET | CPU/RAM/GPU JSON | Base template |
| `/api/admin/reset` | POST | Reset status | Videos page |
| `/api/playbook/play/<id>` | GET | Play JSON | Playbook editor |
| `/api/save_event` | POST | Event save result | Film Tool |
| `/api/analysis_status/<id>` | GET | Analysis status | Film Tool |
| `/api/stats/<id>` | GET | Game stats | Film Tool |
| `/api/upload_video` | POST | Upload result | Film Tool |
