# Film Tool AI Events and Review UI

The film tool is the most UI-dense part of the project. This document summarizes the key review behaviors that matter when another engineer or AI agent is modifying the page.

## Current behaviors

### AI events panel

- The AI event list still uses an **independently scrollable panel** so coaches can browse long timelines without losing the video.
- AI-generated events render in a dedicated, scrollable side panel.
- The event list is separate from manual bookmarks so coaches can distinguish generated output from their own saved clips.
- Clicking an AI event seeks the video to the linked timestamp.

### Playback-linked highlighting

- While the video plays or seeks, the page looks for the nearest AI event to the current playback position.
- If the event is close enough, that event becomes the active row and the panel scrolls just enough to keep it visible.
- If no event is within the sync window, the active highlight clears.

### Manual bookmarks

- Manual bookmarks remain a separate, DB-backed workflow.
- They are intentionally excluded from the AI event list so the AI panel stays focused on generated output.

### Resource and debug controls

- The film tool now includes the shared runtime status strip for CPU, RAM, GPU, and live power when available.
- The **Report Bug / Idea** control opens an in-page slide-over drawer instead of navigating away.
- Report submissions capture the current page path and the browser console output automatically.

## Why this matters

- Coaches can review long event timelines without losing the video context.
- Debugging film-tool issues is easier because issue reports can now include console output from the exact page state being reported.
- Resource visibility helps when tuning analysis on CPU-only versus GPU-capable machines.

## Key files

- `templates/film_tool.html`
- `app.py`
- `docs/AI_AGENT_HANDOFF.md`
