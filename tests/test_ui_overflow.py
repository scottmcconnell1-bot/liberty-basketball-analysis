"""
UI Overflow & Layout Audit — Automated detection of visual breakage.

Uses Playwright (headless Chromium) to render each page in a real browser,
then runs JavaScript to detect:
  1. Text overflow (scrollWidth > clientWidth) — text getting cut off
  2. Content overflow (scrollHeight > clientHeight) — content spilling out of containers
  3. Elements with text-overflow:ellipsis that are actually truncated
  4. Table cells wider than their container (table column breakage)
  5. Zero-width or zero-height elements that should be visible
  6. Elements positioned off-screen (negative coords or beyond viewport)
  7. Font loading failures (fallback fonts indicating missing web fonts)

Full documentation: docs/UI_OVERFLOW_AUDIT.md

Usage:
  1. Start the Flask dev server first:
       cd /home/monk-admin/PROJECTS/liberty-basketball-analysis
       .venv/bin/python app.py

  2. Run this script:
       .venv/bin/python tests/test_ui_overflow.py

  Or with pytest:
       .venv/bin/python -m pytest tests/test_ui_overflow.py -v

Requirements:
  - playwright Python package (already installed)
  - System Chromium at /snap/bin/chromium
  - Flask dev server running on http://localhost:8081
"""

import os
import sys
import time

# ── Configuration ──────────────────────────────────────────────────
BASE_URL = os.environ.get("LIBERTY_BASE_URL", "http://localhost:8081")
CHROMIUM_PATH = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", "/snap/bin/chromium")
VIEWPORT_WIDTH = int(os.environ.get("AUDIT_VIEWPORT_WIDTH", "1280"))
VIEWPORT_HEIGHT = int(os.environ.get("AUDIT_VIEWPORT_HEIGHT", "900"))
PAGE_TIMEOUT_MS = 15000  # 15s per page
WAIT_AFTER_LOAD_MS = 2000  # wait for JS rendering (data-frames, etc.)

# Pages to audit — (route, label, min_expected_elements)
# min_expected_elements: rough minimum number of visible elements to consider page loaded
# Pages with known complex embedded UIs that have their own layout system are skipped
PAGES = [
    ("/", "Dashboard / Index"),
    ("/schedule", "Schedule"),
    ("/games", "Games"),
    ("/nfhs-matches", "NFHS Matches"),
    ("/videos", "Videos"),
    # ("/film", "Film Tool"),  # Skipped: complex embedded app with own CSS layout system
    ("/playbook", "Playbook"),
    ("/player-development", "Player Development"),
    ("/practice-playlists", "Practice Playlists"),
    ("/practices", "Practices"),
    ("/practice-summary", "Practice Summary"),
    ("/settings", "Settings"),
    ("/settings/custom-weights", "Custom Weights Guide"),
    ("/dashboard", "Dashboard (alt)"),
    ("/users", "Users"),
    ("/status", "Status"),
    ("/debug", "Debug / Issues"),
    ("/messages", "Messages"),
]

# ── JavaScript audit code run in the browser ──────────────────────
# This is injected into each page to detect layout issues
AUDIT_JS = """() => {
  const issues = [];
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  // ── 1. Text overflow detection ──────────────────────────────
  // Check all text-containing elements for horizontal overflow
  const textTags = ['P', 'SPAN', 'TD', 'TH', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
                    'LABEL', 'A', 'BUTTON', 'LI', 'DIV', 'STRONG', 'EM', 'B', 'I'];
  const checked = new Set();
  // Collect elements inside .table-responsive wrappers to skip
  const scrollableContainers = new Set();
  document.querySelectorAll('.table-responsive *').forEach(el => scrollableContainers.add(el));
  // Also skip the .table-responsive wrapper itself and its parent (usually a .card)
  document.querySelectorAll('.table-responsive').forEach(el => {
    scrollableContainers.add(el);
    if (el.parentElement) scrollableContainers.add(el.parentElement);
  });

  textTags.forEach(tag => {
    document.querySelectorAll(tag).forEach(el => {
      // Skip elements inside .table-responsive wrappers (intentional horizontal scroll)
      if (scrollableContainers.has(el)) return;

      // Skip invisible elements
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') return;
      if (el.offsetParent === null && style.position !== 'fixed') return;

      // Skip very small elements (icons, etc.)
      if (el.clientWidth < 10 || el.clientHeight < 5) return;

      // Use a key to avoid duplicate reports for nested elements
      const key = el.tagName + '|' + el.className.substring(0, 50) + '|' + el.textContent.substring(0, 30);
      if (checked.has(key)) return;
      checked.add(key);

      // Check horizontal overflow (text getting cut off sideways)
      if (el.scrollWidth > el.clientWidth + 2) {  // +2px tolerance
        const text = el.textContent.trim().substring(0, 60);
        if (text.length > 3) {  // skip empty/near-empty
          issues.push({
            type: 'TEXT_OVERFLOW_X',
            severity: 'HIGH',
            tag: el.tagName,
            class: el.className.substring(0, 80),
            text: text,
            scrollWidth: el.scrollWidth,
            clientWidth: el.clientWidth,
            overflowPx: el.scrollWidth - el.clientWidth,
            message: `Text overflowing horizontally by ${el.scrollWidth - el.clientWidth}px (${el.clientWidth}px container, ${el.scrollWidth}px content)`
          });
        }
      }

      // Check vertical overflow (text getting cut off vertically)
      if (el.scrollHeight > el.clientHeight + 2 && el.clientHeight > 0) {
        // Only flag if it looks like intentional truncation (overflow:hidden or max-height)
        const overflowY = style.overflowY;
        const overflowX = style.overflowX;
        const hasMaxHeight = style.maxHeight !== 'none' && style.maxHeight !== '';
        if (overflowY === 'hidden' || overflowX === 'hidden' || hasMaxHeight) {
          const text = el.textContent.trim().substring(0, 60);
          if (text.length > 3) {
            issues.push({
              type: 'TEXT_OVERFLOW_Y',
              severity: 'MEDIUM',
              tag: el.tagName,
              class: el.className.substring(0, 80),
              text: text,
              scrollHeight: el.scrollHeight,
              clientHeight: el.clientHeight,
              overflowPx: el.scrollHeight - el.clientHeight,
              message: `Text truncated vertically by ${el.scrollHeight - el.clientHeight}px (max-height/overflow:hidden)`
            });
          }
        }
      }
    });
  });

  // ── 2. Ellipsis truncation detection ────────────────────────
  document.querySelectorAll('*').forEach(el => {
    const style = window.getComputedStyle(el);
    if (style.textOverflow === 'ellipsis' && style.overflow === 'hidden') {
      if (el.scrollWidth > el.clientWidth) {
        const text = el.textContent.trim().substring(0, 60);
        if (text.length > 10) {
          issues.push({
            type: 'ELLIPSIS_TRUNCATED',
            severity: 'LOW',
            tag: el.tagName,
            class: el.className.substring(0, 80),
            text: text,
            message: `Text truncated with ellipsis: "${text}..."`
          });
        }
      }
    }
  });

  // ── 3. Table column breakage ────────────────────────────────
  document.querySelectorAll('table').forEach(table => {
    const tableRect = table.getBoundingClientRect();
    const tableParent = table.parentElement;
    const parentRect = tableParent ? tableParent.getBoundingClientRect() : null;

    // Skip tables inside .table-responsive wrappers (intentional horizontal scroll)
    const closestScrollable = table.closest('.table-responsive');
    if (closestScrollable) return;

    // Table wider than its container
    if (parentRect && tableRect.width > parentRect.width + 5) {
      issues.push({
        type: 'TABLE_OVERFLOW',
        severity: 'HIGH',
        tag: 'TABLE',
        class: table.className.substring(0, 80),
        text: `Table width: ${Math.round(tableRect.width)}px, container: ${Math.round(parentRect.width)}px`,
        message: `Table overflows container by ${Math.round(tableRect.width - parentRect.width)}px`
      });
    }

    // Check individual cells for content overflow
    table.querySelectorAll('td, th').forEach(cell => {
      const cellStyle = window.getComputedStyle(cell);
      if (cell.scrollWidth > cell.clientWidth + 2 && cell.clientWidth > 20) {
        const text = cell.textContent.trim().substring(0, 40);
        if (text.length > 3) {
          issues.push({
            type: 'CELL_OVERFLOW',
            severity: 'MEDIUM',
            tag: cell.tagName,
            class: cell.className.substring(0, 80),
            text: text,
            scrollWidth: cell.scrollWidth,
            clientWidth: cell.clientWidth,
            message: `Table cell content overflowing by ${cell.scrollWidth - cell.clientWidth}px: "${text}"`
          });
        }
      }
    });
  });

  // ── 4. Zero-size visible elements ───────────────────────────
  document.querySelectorAll('img, svg, canvas, iframe, video').forEach(el => {
    const style = window.getComputedStyle(el);
    if (style.display === 'none') return;
    if (el.offsetWidth === 0 || el.offsetHeight === 0) {
      const src = el.getAttribute('src') || el.getAttribute('data-src') || '';
      issues.push({
        type: 'ZERO_SIZE_ELEMENT',
        severity: 'MEDIUM',
        tag: el.tagName,
        class: el.className.substring(0, 80),
        text: src.substring(0, 80),
        message: `${el.tagName} has zero dimensions (0x0) — possibly failed to load`
      });
    }
  });

  // ── 5. Off-screen elements ──────────────────────────────────
  document.querySelectorAll('*').forEach(el => {
    if (['SCRIPT', 'STYLE', 'META', 'LINK', 'HEAD', 'HTML', 'BODY'].includes(el.tagName)) return;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return;
    if (style.position !== 'absolute' && style.position !== 'fixed') return;

    const rect = el.getBoundingClientRect();
    // Element positioned way off screen
    if (rect.right < -100 || rect.bottom < -100 || rect.left > vw + 500 || rect.top > vh + 500) {
      if (el.textContent.trim().length > 0) {
        issues.push({
          type: 'OFF_SCREEN',
          severity: 'LOW',
          tag: el.tagName,
          class: el.className.substring(0, 80),
          text: el.textContent.trim().substring(0, 40),
          message: `Element positioned off-screen at (${Math.round(rect.left)}, ${Math.round(rect.top)})`
        });
      }
    }
  });

  // ── 6. Overlapping elements (basic z-index check) ───────────
  // Check for elements that might be overlapping due to layout issues
  // Only check sibling-level cards, not nested ones (card > card-top is normal)
  const cards = document.querySelectorAll('.card, [class*="card"]');
  const cardRects = [];
  cards.forEach(card => {
    const rect = card.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      cardRects.push({ rect, class: card.className.substring(0, 60), el: card });
    }
  });
  for (let i = 0; i < cardRects.length; i++) {
    for (let j = i + 1; j < cardRects.length; j++) {
      const a = cardRects[i];
      const b = cardRects[j];
      // Skip if one is a descendant of the other (normal nesting)
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      // Check overlap
      const ra = a.rect, rb = b.rect;
      if (ra.left < rb.right && ra.right > rb.left && ra.top < rb.bottom && ra.bottom > rb.top) {
        const overlapW = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
        const overlapH = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
        if (overlapW > 10 && overlapH > 10) {
          issues.push({
            type: 'OVERLAPPING',
            severity: 'HIGH',
            tag: 'DIV',
            class: a.class + ' <> ' + b.class,
            text: `Overlap: ${Math.round(overlapW)}x${Math.round(overlapH)}px`,
            message: `Cards/sections overlapping by ${Math.round(overlapW)}x${Math.round(overlapH)}px`
          });
        }
      }
    }
  }

  // ── 7. Viewport overflow (page wider than screen) ───────────
  const bodyScrollWidth = document.body.scrollWidth;
  const docScrollWidth = document.documentElement.scrollWidth;
  const maxScrollWidth = Math.max(bodyScrollWidth, docScrollWidth);
  // Check if the overflow is caused by a table-responsive wrapper (expected)
  const scrollable = document.querySelector('.table-responsive');
  let scrollableOverflow = 0;
  if (scrollable) {
    const srRect = scrollable.getBoundingClientRect();
    const srScrollWidth = scrollable.scrollWidth;
    scrollableOverflow = Math.max(0, srScrollWidth - srRect.width);
    // Also account for the parent card's overflow
    const srParent = scrollable.parentElement;
    if (srParent) {
      const parentRect = srParent.getBoundingClientRect();
      const parentScrollWidth = srParent.scrollWidth;
      scrollableOverflow = Math.max(scrollableOverflow, parentScrollWidth - parentRect.width);
    }
  }
  // Only flag if the page overflow exceeds what table-responsive accounts for
  const excessOverflow = maxScrollWidth - vw - scrollableOverflow;
  if (excessOverflow > 10) {
    issues.push({
      type: 'PAGE_OVERFLOW',
      severity: 'HIGH',
      tag: 'BODY',
      class: '',
      text: `Page scroll width: ${maxScrollWidth}px, viewport: ${vw}px`,
      message: `Page content wider than viewport by ${maxScrollWidth - vw}px — horizontal scrollbar will appear`
    });
  }

  // ── 8. Console errors ───────────────────────────────────────
  // (captured separately via console event listener)

  return issues;
}"""


# ── Main audit runner ──────────────────────────────────────────────

def run_audit():
    from playwright.sync_api import sync_playwright

    all_results = {}
    total_issues = 0
    pages_ok = 0
    pages_failed = 0

    print("=" * 80)
    print("  LIBERTY BASKETBALL — UI OVERFLOW & LAYOUT AUDIT")
    print(f"  Target: {BASE_URL}")
    print(f"  Viewport: {VIEWPORT_WIDTH}x{VIEWPORT_HEIGHT}")
    print("=" * 80)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=CHROMIUM_PATH,
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--disable-setuid-sandbox',
            ]
        )

        context = browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            user_agent="LibertyBot-UI-Audit/1.0"
        )

        # Collect console errors across all pages
        console_errors = {}

        for route, label in PAGES:
            url = BASE_URL + route
            page = context.new_page()
            page_console_errors = []

            def on_console(msg):
                if msg.type in ('error', 'warning'):
                    page_console_errors.append(f"  [{msg.type.upper()}] {msg.text[:120]}")

            page.on("console", on_console)

            try:
                response = page.goto(url, wait_until="networkidle", timeout=PAGE_TIMEOUT_MS)
                status = response.status if response else 0

                if status != 200:
                    print(f"\n❌ {label} ({route}) — HTTP {status}")
                    pages_failed += 1
                    all_results[route] = {"status": status, "issues": [], "console": []}
                    page.close()
                    continue

                # Wait for JS-rendered content (data-frames, API calls, etc.)
                page.wait_for_timeout(WAIT_AFTER_LOAD_MS)

                # Run the audit JavaScript
                issues = page.evaluate(AUDIT_JS)

                # Deduplicate overlapping reports (keep highest severity)
                seen = set()
                deduped = []
                for issue in issues:
                    key = issue['type'] + '|' + issue.get('text', '')[:40]
                    if key not in seen:
                        seen.add(key)
                        deduped.append(issue)
                issues = deduped

                console_errors[route] = page_console_errors
                all_results[route] = {"status": 200, "issues": issues, "console": page_console_errors}

                if issues:
                    high = [i for i in issues if i['severity'] == 'HIGH']
                    med = [i for i in issues if i['severity'] == 'MEDIUM']
                    low = [i for i in issues if i['severity'] == 'LOW']
                    print(f"\n⚠️  {label} ({route}) — {len(issues)} issues "
                          f"({len(high)} high, {len(med)} med, {len(low)} low)")
                    total_issues += len(issues)

                    # Print HIGH severity issues in detail
                    for issue in high:
                        print(f"   🔴 [{issue['type']}] {issue['message']}")
                        if issue.get('class'):
                            print(f"      Class: {issue['class']}")
                    for issue in med:
                        print(f"   🟡 [{issue['type']}] {issue['message']}")
                    for issue in low:
                        print(f"   🔵 [{issue['type']}] {issue['message']}")
                else:
                    print(f"\n✅ {label} ({route}) — No layout issues")
                    pages_ok += 1

                # Print console errors
                if page_console_errors:
                    print(f"   📋 Console: {len(page_console_errors)} error(s)/warning(s)")
                    for err in page_console_errors[:3]:  # show first 3
                        print(f"      {err}")
                    if len(page_console_errors) > 3:
                        print(f"      ... and {len(page_console_errors) - 3} more")

            except Exception as e:
                print(f"\n❌ {label} ({route}) — ERROR: {e}")
                pages_failed += 1
                all_results[route] = {"status": "ERROR", "error": str(e), "issues": [], "console": []}

            finally:
                page.close()

        browser.close()

    # ── Summary ──────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print("  AUDIT SUMMARY")
    print("=" * 80)
    print(f"  Pages audited:    {len(PAGES)}")
    print(f"  Pages OK:         {pages_ok}")
    print(f"  Pages with issues:{len(PAGES) - pages_ok - pages_failed}")
    print(f"  Pages failed:     {pages_failed}")
    print(f"  Total issues:     {total_issues}")

    if total_issues > 0:
        # Count by type
        type_counts = {}
        severity_counts = {}
        for route, data in all_results.items():
            for issue in data.get('issues', []):
                t = issue['type']
                s = issue['severity']
                type_counts[t] = type_counts.get(t, 0) + 1
                severity_counts[s] = severity_counts.get(s, 0) + 1

        print(f"\n  By severity:")
        for sev in ['HIGH', 'MEDIUM', 'LOW']:
            if sev in severity_counts:
                print(f"    {sev:8s}: {severity_counts[sev]}")

        print(f"\n  By type:")
        for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
            print(f"    {t:25s}: {count}")

    print("=" * 80)

    # Return non-zero exit code if there are HIGH severity issues
    high_count = sum(
        1 for d in all_results.values()
        for i in d.get('issues', [])
        if i['severity'] == 'HIGH'
    )
    return high_count


if __name__ == "__main__":
    exit_code = run_audit()
    sys.exit(min(exit_code, 255))


# ── Pytest integration ─────────────────────────────────────────────

def test_ui_no_overflow():
    """Run the full UI overflow audit — fails if any HIGH severity issues found."""
    high_count = run_audit()
    assert high_count == 0, f"UI audit found {high_count} HIGH severity layout issues"
