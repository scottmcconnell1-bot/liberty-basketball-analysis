#!/usr/bin/env python3
"""
MaxPreps Ranking Scraper — Uses Playwright for isolated browser scraping.

Replaces the agent-browser subprocess approach in blueprints/core.py
which conflicts with the browser tool's shared agent-browser session.

Usage:
  .venv/bin/python scripts/scrape_maxpreps_rankings.py [--state Idaho]

Returns JSON to stdout:
  {"varsity_boys": {"ranking": 17, "url": "..."}, "varsity_girls": {"ranking": null, "url": "..."}}
"""

import argparse
import json
import re
import sys
import time

CHROMIUM_PATH = "/snap/bin/chromium"

STATE_SLUG_OVERRIDES = {
    "idaho": "id",
}

DIVISION_IDS = {
    ("id", "boys"): "b006084a-35a3-4277-b62e-8782f19ac85a",
    ("id", "girls"): "17ff4bb2-1a40-4f38-a3e1-637f78af15f2",
}


def get_ranking(state: str, gender: str) -> tuple:
    """Scrape MaxPreps for the Liberty team ranking. Returns (ranking_int_or_None, url)."""
    from playwright.sync_api import sync_playwright

    state_slug = state.lower().replace(" ", "-")
    state_slug = STATE_SLUG_OVERRIDES.get(state_slug, state_slug)
    gender_slug = "boys" if gender == "boys" else "girls"

    div_id = DIVISION_IDS.get((state_slug, gender_slug))
    if div_id:
        if gender_slug == "girls":
            url = f"https://www.maxpreps.com/{state_slug}/basketball/girls/25-26/class/class-2a/rankings/1/?statedivisionid={div_id}"
        else:
            url = f"https://www.maxpreps.com/{state_slug}/basketball/25-26/class/class-2a/rankings/1/?statedivisionid={div_id}"
    else:
        url = f"https://www.maxpreps.com/{state_slug}/basketball/25-26/class/class-2a/rankings/1/"

    ranking = None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=CHROMIUM_PATH,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        try:
            page.goto(url, wait_until="domcontentloaded")
            time.sleep(5)
            # Wait for rankings content to render
            page.wait_for_selector("table", timeout=15000)
        except Exception as e:
            print(f"[scrape] Warning: {e}", file=sys.stderr)

        # Use JS evaluation to find Liberty's ranking in the table
        try:
            result = page.evaluate("""() => {
                // Find all table rows
                const rows = document.querySelectorAll('tr');
                for (const row of rows) {
                    const rowText = row.textContent || '';
                    if (rowText.toLowerCase().includes('liberty')) {
                        // Get all cells in this row
                        const cells = row.querySelectorAll('td, th');
                        for (const cell of cells) {
                            const text = cell.textContent.trim();
                            // Rank is a small integer (1-50)
                            const num = parseInt(text, 10);
                            if (!isNaN(num) && num >= 1 && num <= 50 && text === String(num)) {
                                return num;
                            }
                        }
                    }
                }
                // Fallback: try divs/spans with rank-like content
                const allCells = document.querySelectorAll('td, th, [class*="cell"], [class*="rank"]');
                for (let i = 0; i < allCells.length; i++) {
                    const text = allCells[i].textContent.trim();
                    if (text.toLowerCase().includes('liberty')) {
                        // Look at previous siblings for a rank number
                        for (let j = Math.max(0, i - 5); j < i; j++) {
                            const prevText = allCells[j].textContent.trim();
                            const num = parseInt(prevText, 10);
                            if (!isNaN(num) && num >= 1 && num <= 50 && prevText === String(num)) {
                                return num;
                            }
                        }
                    }
                }
                return null;
            }""")
            if result:
                ranking = result
        except Exception as e:
            print(f"[scrape] JS eval failed: {e}", file=sys.stderr)

        browser.close()

    return ranking, url


def main():
    parser = argparse.ArgumentParser(description="Scrape MaxPreps rankings for Liberty teams")
    parser.add_argument("--state", default="Idaho", help="State name (default: Idaho)")
    args = parser.parse_args()

    results = {}
    for team_key, gender in [("varsity_boys", "boys"), ("varsity_girls", "girls")]:
        print(f"[scrape] Scraping {team_key} ({gender})...", file=sys.stderr)
        ranking, url = get_ranking(args.state, gender)
        results[team_key] = {"ranking": ranking, "url": url}
        print(f"[scrape] {team_key}: ranking={ranking}", file=sys.stderr)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
