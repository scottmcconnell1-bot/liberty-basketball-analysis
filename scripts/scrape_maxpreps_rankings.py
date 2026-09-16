#!/usr/bin/env python3
"""Scrape MaxPreps rankings for Liberty teams over HTTP (Windows-safe)."""

import argparse
import json
import sys

from maxpreps_web import scrape_ranking


def main():
    parser = argparse.ArgumentParser(description="Scrape MaxPreps rankings for Liberty teams")
    parser.add_argument("--state", default="Idaho", help="State name (default: Idaho)")
    args = parser.parse_args()

    results = {}
    for team_key, gender in [("varsity_boys", "boys"), ("varsity_girls", "girls")]:
        print(f"[scrape] Scraping {team_key} ({gender})...", file=sys.stderr)
        result = scrape_ranking(args.state, gender)
        results[team_key] = {"ranking": result["ranking"], "url": result["url"], "error": result.get("error")}
        print(f"[scrape] {team_key}: ranking={result['ranking']} error={result.get('error')}", file=sys.stderr)

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
