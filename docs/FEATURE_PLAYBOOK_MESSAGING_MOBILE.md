# Feature Plan — Liberty Basketball Analysis

## 1. Playbook Feature (TheHoopsGeek-style)

### Goal
Allow coaches to create, edit, and organize basketball plays using an interactive court diagram.

### Approach
- New blueprint: `blueprints/playbook.py` with routes:
  - `/playbook` — Playbook list view (all plays, organized by category/tag)
  - `/playbook/create` — Play creator (interactive court canvas)
  - `/playbook/play/<id>` — View/play detail with animations
  - `/playbook/play/<id>/edit` — Edit existing play
- Database tables:
  - `plays` — id, name, description, category, tags, created_by, created_at, updated_at
  - `play_steps` — id, play_id, step_number, player_positions (JSON), movements (JSON), notes
  - `playbooks` — id, name, description, created_by, created_at
  - `playbook_plays` — playbook_id, play_id, order
- Frontend: HTML5 Canvas basketball court with:
  - Draggable player tokens (1-5, color-coded)
  - Movement arrows (dribble, pass, screen)
  - Step-by-step animation playback
  - Save/load plays as JSON
  - Tags/categories: Offense, Defense, Press, Out-of-Bounds, etc.

### Key UI Elements
- Court diagram (half-court SVG, 500×470 standard)
- Player dots (numbered 1-5, drag)
- Arrow tools: solid=dribble, dashed=pass, curved=screen
- Timeline: step forward/back, play animation
- Sidebar: play list, categories, search

---

## 2. Plays Import (PDF/Image + Automation)

### Goal
Import plays from PDFs, images, or other sources and convert them into playable playbook entries.

### Approach
- New routes:
  - `/playbook/import` — Upload PDF/image of a play diagram
  - `/playbook/import/parse` — OCR/vision extraction of court + players + movements
- Strategy:
  - PDF: extract embedded images using PyMuPDF, then run through detection
  - Image: accept PNG/JPG upload, analyze with OpenCV/YOLO to detect court, players, arrows
  - User reviews extracted play, corrects any mistakes, saves to playbook
  - Template matching for common play diagrams (X's and O's style)
- Automation:
  - Batch import from a folder of PDFs/images
  - Auto-tag by play name pattern matching
  - "Import from URL" — fetch play diagrams from coaching websites

### Key UI Elements
- Drag-and-drop upload zone
- Preview of extracted image
- Side-by-side: original image ↔ editable canvas
- Auto-detected player positions shown as editable dots
- "Confirm & Save" button to create play entry

---

## 3. GameChanger-Style Messaging System

### Goal
In-app messaging between coaches, assistants, and staff — like GameChanger team chat.

### Approach
- New blueprint: `blueprints/messaging.py` with routes:
  - `/messages` — Message inbox/conversation list
  - `/messages/<conversation_id>` — Individual conversation view
  - `/api/messages/send` — POST new message
  - `/api/messages/poll` — Poll for new messages (Server-Sent Events or polling)
- Database tables:
  - `conversations` — id, title, type (direct/team/announcement), created_at, updated_at
  - `conversation_members` — conversation_id, user_id, last_read_at, role
  - `messages` — id, conversation_id, sender_id, body, created_at, read_by (JSON)
  - `users` — extend with avatar_url, role (coach/assistant/player/parent)
- Features:
  - Team-wide announcement channel (all staff)
  - Direct messages between any two users
  - Push notifications (browser notifications API)
  - Message status: sent/delivered/read
  - File attachments (play images, practice plans)
  - @mentions with notification

### Key UI Elements
- Conversation list sidebar (like Slack/GameChanger)
- Message bubbles with timestamps
- Typing indicators
- Unread badge count in nav bar
- Mobile-friendly bottom nav with Messages tab

---

## 4. Mobile-Responsive / Phone Viewer Friendly

### Goal
Make the entire app work well on phones and tablets — or create a companion mobile view.

### Approach
- Add responsive meta viewport (already present in base.html)
- Add mobile-first CSS breakpoints:
  - `@media (max-width: 768px)` — phone layout
  - `@media (max-width: 1024px)` — tablet layout
- Nav changes:
  - Collapsible hamburger menu on mobile
  - Bottom tab bar for primary nav (Dashboard, Schedule, Playbook, Messages)
- Page changes:
  - Tables → card layout on mobile
  - Forms → single column
  - Film tool → touch-friendly controls
  - Play creator → touch-friendly player dragging
- PWA support:
  - Add web manifest (`/manifest.json`)
  - Add service worker for offline capability
  - Install prompt for "Add to Home Screen"
  - Touch-optimized tap targets (minimum 44×44px)

### Key UI Elements
- Bottom navigation bar (mobile): Dashboard | Schedule | Playbook | Messages
- Slide-in side menu (hamburger)
- Responsive tables → stacked cards
- Touch-friendly buttons and form fields
- Swipe gestures for play step navigation

---

# Implementation Order

## Phase A — Schedule Tab Completion (CURRENT)
1. Fix remaining test failures (level detection, vs. parsing)
2. Verify all 4 PDFs import correctly with team selector
3. Test full schedule workflow end-to-end
4. Commit and push

## Phase B — Playbook MVP
1. Database schema (plays, play_steps, playbooks, playbook_plays)
2. Basic play creator (canvas court + draggable players)
3. Save/load plays
4. Playbook list view
5. Tests

## Phase C — Plays Import
1. PDF/image upload endpoint
2. Image extraction and preview
3. Side-by-side editor
4. Batch import
5. Tests

## Phase D — Messaging System
1. Database schema (conversations, conversation_members, messages)
2. Basic send/receive API
3. Conversation list UI
4. Real-time polling
5. Notifications
6. Tests

## Phase E — Mobile Responsive
1. Audit all pages for mobile issues
2. Add responsive breakpoints
3. Bottom nav bar
4. PWA manifest + service worker
5. Touch optimization
6. Tests
