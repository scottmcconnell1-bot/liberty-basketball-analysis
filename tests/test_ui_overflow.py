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
  7. Overlapping card/section elements
  8. Page wider than viewport (horizontal scrollbar)

Routes are auto-discovered from the Flask URL map at runtime. Pages that
require authentication or database state are automatically skipped.

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
import subprocess

# ── Configuration ──────────────────────────────────────────────────
BASE_URL = os.environ.get("LIBERTY_BASE_URL", "http://localhost:8081")
CHROMIUM_PATH = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", "/snap/bin/chromium")
VIEWPORT_WIDTH = int(os.environ.get("AUDIT_VIEWPORT_WIDTH", "1280"))
VIEWPORT_HEIGHT = int(os.environ.get("AUDIT_VIEWPORT_HEIGHT", "900"))
PAGE_TIMEOUT_MS = 15000  # 15s per page
WAIT_AFTER_LOAD_MS = 2000  # wait for JS rendering (data-frames, etc.)

# CSS selectors that are allowed to overflow (intentional horizontal scroll).
# Add new selectors here as the app grows — no need to touch the JS.
ALLOWED_OVERFLOW_SELECTORS = [".table-responsive"]

# Routes matching any of these prefixes are always skipped.
SKIP_PREFIXES = ("/api/", "/uploads/", "/sw.js")

# Routes matching any of these substrings are skipped (downloads, exports).
SKIP_SUBSTRINGS = ("/export/", "/download/")

# Routes with these suffixes are skipped (static assets, service workers).
SKIP_SUFFIXES = (".js", ".css", ".ico", ".png", ".jpg", ".svg", ".woff", ".woff2", ".ttf")


def discover_pages():
    """Auto-discover page routes from the Flask URL map.

    Returns a list of (route, label) tuples for GET-accessible pages
    that don't require URL parameters (no <int:...> or <path:...>).

    Skips:
    - API routes (everything under /api/)
    - POST-only routes
    - Routes with dynamic URL parameters (need DB state)
    - Routes that redirect to login (detected at runtime)
    - Static asset routes
    """
    # Import the Flask app directly — works because this script runs
    # from the project directory where app.py lives.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import app

    pages = []
    seen = set()

    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        route = rule.rule

        # Skip static files
        if rule.endpoint == "static":
            continue

        # Skip by prefix
        if any(route.startswith(p) for p in SKIP_PREFIXES):
            continue

        # Skip by substring (downloads, exports)
        if any(sub in route for sub in SKIP_SUBSTRINGS):
            continue

        # Skip by suffix (static assets)
        if any(route.endswith(s) for s in SKIP_SUFFIXES):
            continue

        # Skip non-GET routes
        methods = rule.methods - {"HEAD", "OPTIONS"}
        if "GET" not in methods:
            continue

        # Skip routes with URL parameters (need real DB IDs)
        if "<" in route and ">" in route:
            continue

        # Skip duplicates (some routes have multiple methods registered)
        if route in seen:
            continue
        seen.add(route)

        # Build a human-readable label from the route
        label = route.strip("/").replace("/", " > ").replace("-", " ").title()
        if not label:
            label = "Dashboard"

        pages.append((route, label))

    return pages


# ── JavaScript audit code run in the browser ──────────────────────
# This is injected into each page to detect layout issues.
# ALLOWED_OVERFLOW_SELECTORS is interpolated in from Python config.
ALLOWED_OVERFLOW_JS = ", ".join(f'"{s}"' for s in ALLOWED_OVERFLOW_SELECTORS)

AUDIT_JS = f"""() => {{
  const issues = [];
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const allowedOverflowSelectors = [{ALLOWED_OVERFLOW_JS}];

  // Build a set of elements inside allowed-overflow containers
  const scrollableContainers = new Set();
  allowedOverflowSelectors.forEach(sel => {{
    document.querySelectorAll(sel).forEach(el => {{
      scrollableContainers.add(el);
      if (el.parentElement) scrollableContainers.add(el.parentElement);
      el.querySelectorAll('*').forEach(child => scrollableContainers.add(child));
    }});
  }});

  // ── 1. Text overflow detection ──────────────────────────────
  const textTags = ['P', 'SPAN', 'TD', 'TH', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
                    'LABEL', 'A', 'BUTTON', 'LI', 'DIV', 'STRONG', 'EM', 'B', 'I'];
  const checked = new Set();

  textTags.forEach(tag => {{
    document.querySelectorAll(tag).forEach(el => {{
      if (scrollableContainers.has(el)) return;

      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') return;
      if (el.offsetParent === null && style.position !== 'fixed') return;
      if (el.clientWidth < 10 || el.clientHeight < 5) return;

      const key = el.tagName + '|' + el.className.substring(0, 50) + '|' + el.textContent.substring(0, 30);
      if (checked.has(key)) return;
      checked.add(key);

      if (el.scrollWidth > el.clientWidth + 2) {{
        const text = el.textContent.trim().substring(0, 60);
        if (text.length > 3) {{
          issues.push({{
            type: 'TEXT_OVERFLOW_X',
            severity: 'HIGH',
            tag: el.tagName,
            class: el.className.substring(0, 80),
            text: text,
            scrollWidth: el.scrollWidth,
            clientWidth: el.clientWidth,
            overflowPx: el.scrollWidth - el.clientWidth,
            message: `Text overflowing horizontally by ${{el.scrollWidth - el.clientWidth}}px (${{el.clientWidth}}px container, ${{el.scrollWidth}}px content)`
          }});
        }}
      }}

      if (el.scrollHeight > el.clientHeight + 2 && el.clientHeight > 0) {{
        const overflowY = style.overflowY;
        const overflowX = style.overflowX;
        const hasMaxHeight = style.maxHeight !== 'none' && style.maxHeight !== '';
        if (overflowY === 'hidden' || overflowX === 'hidden' || hasMaxHeight) {{
          const text = el.textContent.trim().substring(0, 60);
          if (text.length > 3) {{
            issues.push({{
              type: 'TEXT_OVERFLOW_Y',
              severity: 'MEDIUM',
              tag: el.tagName,
              class: el.className.substring(0, 80),
              text: text,
              scrollHeight: el.scrollHeight,
              clientHeight: el.clientHeight,
              overflowPx: el.scrollHeight - el.clientHeight,
              message: `Text truncated vertically by ${{el.scrollHeight - el.clientHeight}}px (max-height/overflow:hidden)`
            }});
          }}
        }}
      }}
    }});
  }});

  // ── 2. Ellipsis truncation detection ────────────────────────
  document.querySelectorAll('*').forEach(el => {{
    const style = window.getComputedStyle(el);
    if (style.textOverflow === 'ellipsis' && style.overflow === 'hidden') {{
      if (el.scrollWidth > el.clientWidth) {{
        const text = el.textContent.trim().substring(0, 60);
        if (text.length > 10) {{
          issues.push({{
            type: 'ELLIPSIS_TRUNCATED',
            severity: 'LOW',
            tag: el.tagName,
            class: el.className.substring(0, 80),
            text: text,
            message: `Text truncated with ellipsis: "${{text}}..."`
          }});
        }}
      }}
    }}
  }});

  // ── 3. Table column breakage ────────────────────────────────
  document.querySelectorAll('table').forEach(table => {{
    const tableRect = table.getBoundingClientRect();
    const tableParent = table.parentElement;
    const parentRect = tableParent ? tableParent.getBoundingClientRect() : null;

    const closestScrollable = table.closest(allowedOverflowSelectors.join(','));
    if (closestScrollable) return;

    if (parentRect && tableRect.width > parentRect.width + 5) {{
      issues.push({{
        type: 'TABLE_OVERFLOW',
        severity: 'HIGH',
        tag: 'TABLE',
        class: table.className.substring(0, 80),
        text: `Table width: ${{Math.round(tableRect.width)}}px, container: ${{Math.round(parentRect.width)}}px`,
        message: `Table overflows container by ${{Math.round(tableRect.width - parentRect.width)}}px`
      }});
    }}

    table.querySelectorAll('td, th').forEach(cell => {{
      if (cell.scrollWidth > cell.clientWidth + 2 && cell.clientWidth > 20) {{
        const text = cell.textContent.trim().substring(0, 40);
        if (text.length > 3) {{
          issues.push({{
            type: 'CELL_OVERFLOW',
            severity: 'MEDIUM',
            tag: cell.tagName,
            class: cell.className.substring(0, 80),
            text: text,
            scrollWidth: cell.scrollWidth,
            clientWidth: cell.clientWidth,
            message: `Table cell content overflowing by ${{cell.scrollWidth - cell.clientWidth}}px: "${{text}}"`
          }});
        }}
      }}
    }});
  }});

  // ── 4. Zero-size visible elements ───────────────────────────
  document.querySelectorAll('img, svg, canvas, iframe, video').forEach(el => {{
    const style = window.getComputedStyle(el);
    if (style.display === 'none') return;
    if (el.offsetWidth === 0 || el.offsetHeight === 0) {{
      const src = el.getAttribute('src') || el.getAttribute('data-src') || '';
      issues.push({{
        type: 'ZERO_SIZE_ELEMENT',
        severity: 'MEDIUM',
        tag: el.tagName,
        class: el.className.substring(0, 80),
        text: src.substring(0, 80),
        message: `${{el.tagName}} has zero dimensions (0x0) — possibly failed to load`
      }});
    }}
  }});

  // ── 5. Off-screen elements ──────────────────────────────────
  document.querySelectorAll('*').forEach(el => {{
    if (['SCRIPT', 'STYLE', 'META', 'LINK', 'HEAD', 'HTML', 'BODY'].includes(el.tagName)) return;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return;
    if (style.position !== 'absolute' && style.position !== 'fixed') return;

    const rect = el.getBoundingClientRect();
    if (rect.right < -100 || rect.bottom < -100 || rect.left > vw + 500 || rect.top > vh + 500) {{
      if (el.textContent.trim().length > 0) {{
        issues.push({{
          type: 'OFF_SCREEN',
          severity: 'LOW',
          tag: el.tagName,
          class: el.className.substring(0, 80),
          text: el.textContent.trim().substring(0, 40),
          message: `Element positioned off-screen at (${{Math.round(rect.left)}}, ${{Math.round(rect.top)}})`
        }});
      }}
    }}
  }});

  // ── 6. Overlapping elements ─────────────────────────────────
  const cards = document.querySelectorAll('.card, [class*="card"]');
  const cardRects = [];
  cards.forEach(card => {{
    const rect = card.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {{
      cardRects.push({{ rect, class: card.className.substring(0, 60), el: card }});
    }}
  }});
  for (let i = 0; i < cardRects.length; i++) {{
    for (let j = i + 1; j < cardRects.length; j++) {{
      const a = cardRects[i];
      const b = cardRects[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const ra = a.rect, rb = b.rect;
      if (ra.left < rb.right && ra.right > rb.left && ra.top < rb.bottom && ra.bottom > rb.top) {{
        const overlapW = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left);
        const overlapH = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
        if (overlapW > 10 && overlapH > 10) {{
          issues.push({{
            type: 'OVERLAPPING',
            severity: 'HIGH',
            tag: 'DIV',
            class: a.class + ' <> ' + b.class,
            text: `Overlap: ${{Math.round(overlapW)}}x${{Math.round(overlapH)}}px`,
            message: `Cards/sections overlapping by ${{Math.round(overlapW)}}x${{Math.round(overlapH)}}px`
          }});
        }}
      }}
    }}
  }}

  // ── 7. Viewport overflow (page wider than screen) ───────────
  const bodyScrollWidth = document.body.scrollWidth;
  const docScrollWidth = document.documentElement.scrollWidth;
  const maxScrollWidth = Math.max(bodyScrollWidth, docScrollWidth);

  let scrollableOverflow = 0;
  allowedOverflowSelectors.forEach(sel => {{
    const el = document.querySelector(sel);
    if (el) {{
      const srRect = el.getBoundingClientRect();
      scrollableOverflow = Math.max(scrollableOverflow, el.scrollWidth - srRect.width);
      if (el.parentElement) {{
        const parentRect = el.parentElement.getBoundingClientRect();
        scrollableOverflow = Math.max(scrollableOverflow, el.parentElement.scrollWidth - parentRect.width);
      }}
    }}
  }});

  const excessOverflow = maxScrollWidth - vw - scrollableOverflow;
  if (excessOverflow > 10) {{
    issues.push({{
      type: 'PAGE_OVERFLOW',
      severity: 'HIGH',
      tag: 'BODY',
      class: '',
      text: `Page scroll width: ${{maxScrollWidth}}px, viewport: ${{vw}}px`,
      message: `Page content wider than viewport by ${{maxScrollWidth - vw}}px — horizontal scrollbar will appear`
    }});
  }}

  return issues;
}}"""


# ── Main audit runner ──────────────────────────────────────────────

def run_audit():
    from playwright.sync_api import sync_playwright

    # Discover pages at runtime — no hardcoded list
    pages = discover_pages()

    all_results = {}
    total_issues = 0
    pages_ok = 0
    pages_failed = 0
    pages_skipped = 0

    print("=" * 80)
    print("  LIBERTY BASKETBALL — UI OVERFLOW & LAYOUT AUDIT")
    print(f"  Target: {BASE_URL}")
    print(f"  Viewport: {VIEWPORT_WIDTH}x{VIEWPORT_HEIGHT}")
    print(f"  Pages discovered: {len(pages)}")
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

        for route, label in pages:
            url = BASE_URL + route
            page = context.new_page()
            page_console_errors = []

            def on_console(msg):
                if msg.type in ('error', 'warning'):
                    page_console_errors.append(f"  [{msg.type.upper()}] {msg.text[:120]}")

            page.on("console", on_console)

            try:
                # Use domcontentloaded instead of networkidle because the app has
                # background polling (setInterval) that prevents networkidle from firing.
                response = page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                status = response.status if response else 0

                # Auto-detect auth redirects (302 → login page)
                if status == 302:
                    print(f"⏭️  {label} ({route}) — Skipped (redirect, auth required)")
                    pages_skipped += 1
                    all_results[route] = {"status": 302, "issues": [], "console": [], "skipped": True}
                    page.close()
                    continue

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

                # Deduplicate overlapping reports
                seen = set()
                deduped = []
                for issue in issues:
                    key = issue['type'] + '|' + issue.get('text', '')[:40]
                    if key not in seen:
                        seen.add(key)
                        deduped.append(issue)
                issues = deduped

                all_results[route] = {"status": 200, "issues": issues, "console": page_console_errors}

                if issues:
                    high = [i for i in issues if i['severity'] == 'HIGH']
                    med = [i for i in issues if i['severity'] == 'MEDIUM']
                    low = [i for i in issues if i['severity'] == 'LOW']
                    print(f"\n⚠️  {label} ({route}) — {len(issues)} issues "
                          f"({len(high)} high, {len(med)} med, {len(low)} low)")
                    total_issues += len(issues)

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

                if page_console_errors:
                    print(f"   📋 Console: {len(page_console_errors)} error(s)/warning(s)")
                    for err in page_console_errors[:3]:
                        print(f"      {err}")
                    if len(page_console_errors) > 3:
                        print(f"      ... and {len(page_console_errors) - 3} more")

            except Exception as e:
                error_str = str(e)
                # Download endpoints trigger a browser download which Playwright treats as an error
                if "Download is starting" in error_str:
                    print(f"⏭️  {label} ({route}) — Skipped (download endpoint)")
                    pages_skipped += 1
                    all_results[route] = {"status": "DOWNLOAD", "issues": [], "console": [], "skipped": True}
                else:
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
    print(f"  Pages discovered:  {len(pages)}")
    print(f"  Pages audited:     {len(pages) - pages_skipped}")
    print(f"  Pages skipped:     {pages_skipped} (auth/redirect)")
    print(f"  Pages OK:          {pages_ok}")
    print(f"  Pages with issues: {len(pages) - pages_ok - pages_failed - pages_skipped}")
    print(f"  Pages failed:      {pages_failed}")
    print(f"  Total issues:      {total_issues}")

    if total_issues > 0:
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
    """Run the full UI overflow audit — fails if any HIGH severity issues found.

    Requires:
    - Flask dev server running on http://localhost:8081
    - Playwright + Chromium installed

    Run with:
        .venv/bin/python -m pytest tests/test_ui_overflow.py -v
    """
    high_count = run_audit()
    assert high_count == 0, f"{high_count} HIGH severity layout issue(s) found"
