# UI Overflow & Layout Audit

Automated visual breakage detection for the Liberty Basketball Analysis UI.

**File:** `tests/test_ui_overflow.py`

## What it does

Launches a real headless Chromium browser, navigates to each page on the running
Flask dev server, waits for JS-rendered content to settle, then runs JavaScript
in the browser to detect layout issues that indicate visual breakage.

## Issue types detected

| Type | Severity | What it means |
|------|----------|---------------|
| `TEXT_OVERFLOW_X` | HIGH | Element's text is wider than its container — text is getting cut off horizontally |
| `TEXT_OVERFLOW_Y` | MEDIUM | Element's text is taller than its container — clipped by `overflow:hidden` or `max-height` |
| `ELLIPSIS_TRUNCATED` | LOW | Element has `text-overflow:ellipsis` and content is actually being truncated |
| `TABLE_OVERFLOW` | HIGH | Table is wider than its parent container |
| `CELL_OVERFLOW` | MEDIUM | Individual table cell content is wider than the cell |
| `PAGE_OVERFLOW` | HIGH | Entire page is wider than the viewport — horizontal scrollbar will appear |
| `OVERLAPPING` | HIGH | Two or more cards/sections are overlapping each other |
| `OFF_SCREEN` | LOW | Absolutely-positioned element is placed far off-screen |
| `ZERO_SIZE_ELEMENT` | MEDIUM | Image/SVG/canvas with 0×0 dimensions — likely failed to load |

Console errors and warnings are also captured per page.

## Prerequisites

1. **Flask dev server running** on port 8081:
   ```bash
   cd /home/monk-admin/PROJECTS/liberty-basketball-analysis
   .venv/bin/python app.py
   ```

2. **Python dependencies** (already installed):
   - `playwright` — browser automation
   - System Chromium at `/snap/bin/chromium`

## Running

### Standalone (recommended)

```bash
.venv/bin/python tests/test_ui_overflow.py
```

Takes ~30 seconds for all 18 pages. Prints a summary with issue counts by
severity and type. Exits with code = number of HIGH severity issues (capped at
255), so it can be used as a CI gate.

### With pytest

```bash
.venv/bin/python -m pytest tests/test_ui_overflow.py -v
```

## Configuration

All settings are controlled via environment variables or by editing the
constants at the top of the file:

| Variable | Default | Purpose |
|----------|---------|---------|
| `LIBERTY_BASE_URL` | `http://localhost:8081` | Dev server URL |
| `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` | `/snap/bin/chromium` | Chromium binary path |
| `AUDIT_VIEWPORT_WIDTH` | `1280` | Viewport width in pixels |
| `AUDIT_VIEWPORT_HEIGHT` | `900` | Viewport height in pixels |

## Adding a new page to audit

Add a `(route, label)` tuple to the `PAGES` list:

```python
PAGES = [
    # ... existing pages ...
    ("/my-new-page", "My New Page"),
]
```

The route must be a valid GET route on the Flask app. Pages that require login
are not currently supported — the script will report them as HTTP 302 redirects.

## Adding a new issue type

Edit the `AUDIT_JS` string — this is the JavaScript that runs in the browser on
each page. It must be a self-contained arrow function that returns an array of
issue objects:

```javascript
{
  type: 'MY_NEW_TYPE',       // Unique identifier
  severity: 'HIGH',          // HIGH, MEDIUM, or LOW
  tag: el.tagName,           // HTML tag name
  class: el.className,       // CSS class (truncated to 80 chars)
  text: 'visible text',      // Text content (truncated)
  message: 'Human-readable description of the issue'
}
```

After adding a new type, update the issue types table in this doc.

## Interpreting results

### HIGH severity — fix these

These indicate visible breakage that users will notice:
- Text overflowing its container (getting cut off)
- Tables wider than their container
- Cards/sections overlapping
- Page wider than viewport (horizontal scrollbar)

### MEDIUM severity — investigate

These may be intentional or may indicate a problem:
- Vertical text truncation (could be intentional `max-height`)
- Table cell overflow
- Zero-size media elements

### LOW severity — informational

These are typically not user-visible:
- Ellipsis truncation (intentional design pattern)
- Off-screen elements (may be hidden UI like skip links)

## Known limitations

- **Login-required pages**: The script does not authenticate. Pages behind
  `@login_required` will be reported as HTTP 302. To audit these, either
  temporarily remove the decorator or add login logic to the script.
- **Dynamic content**: Pages that load data via API calls are waited for with
  a fixed 2-second delay after `networkidle`. If your page takes longer to
  render, increase `WAIT_AFTER_LOAD_MS` or add a custom wait.
- **Single viewport**: Only one viewport size is tested (1280×900 by default).
  For responsive testing, run multiple times with different
  `AUDIT_VIEWPORT_WIDTH` / `AUDIT_VIEWPORT_HEIGHT` values.
- **No baseline comparison**: This script detects absolute issues (overflow,
  overlap), not regressions from a known-good state. For regression testing,
  see the visual regression test approach (not yet implemented).

## Example output

```
================================================================================
  LIBERTY BASKETBALL — UI OVERFLOW & LAYOUT AUDIT
  Target: http://localhost:8081
  Viewport: 1280x900
================================================================================

⚠️  Dashboard / Index (/) — 2 issues (2 high, 0 med, 0 low)
   🔴 [TEXT_OVERFLOW_X] Text overflowing horizontally by 5px (130px container, 135px content)
      Class: sched-date
   🔴 [OVERLAPPING] Cards/sections overlapping by 488x48px
      Class: team-card <> team-card-top

✅ Schedule (/schedule) — No layout issues

⚠️  Games (/games) — 2 issues (2 high, 0 med, 0 low)
   🔴 [TEXT_OVERFLOW_X] Text overflowing horizontally by 150px (1060px container, 1210px content)
   🔴 [PAGE_OVERFLOW] Page content wider than viewport by 40px — horizontal scrollbar will appear

================================================================================
  AUDIT SUMMARY
================================================================================
  Pages audited:    18
  Pages OK:         13
  Pages with issues:5
  Pages failed:     0
  Total issues:     18

  By severity:
    HIGH    : 15
    MEDIUM  : 0
    LOW     : 3

  By type:
    TEXT_OVERFLOW_X          : 12
    ELLIPSIS_TRUNCATED       : 3
    OVERLAPPING              : 2
    PAGE_OVERFLOW            : 1
================================================================================
```
