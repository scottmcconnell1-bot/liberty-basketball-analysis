"""
CLI helper to seed demo module entitlements (stats, scouting) for packaging preview.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app
from helpers import ensure_db, get_db
from module_entitlements import audit_team_entitlements, seed_demo_module_entitlements


def main():
    with app.app_context():
        ensure_db()
        db = get_db()
        seeded = seed_demo_module_entitlements(db)
        print(f"seeded={','.join(seeded) or '(none)'}")
        report = audit_team_entitlements(db)
        for team in report["teams"]:
            enabled = ", ".join(team["enabled_module_keys"]) or "(none)"
            missing = ", ".join(team["missing_module_keys"]) or "(none)"
            print(f"team_id={team['team_id']} enabled={enabled} missing={missing}")


if __name__ == "__main__":
    main()
