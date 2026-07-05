"""
CLI audit for Stage 6A module entitlements.
"""

from app import app
from helpers import ensure_db, get_db
from module_entitlements import audit_team_entitlements


def main():
    with app.app_context():
        ensure_db()
        db = get_db()
        report = audit_team_entitlements(db)
        print(f"team_count={report['team_count']}")
        for team in report["teams"]:
            enabled = ", ".join(team["enabled_module_keys"]) or "(none)"
            disabled = ", ".join(team["disabled_module_keys"]) or "(none)"
            missing = ", ".join(team["missing_module_keys"]) or "(none)"
            print(f"team_id={team['team_id']}")
            print(f"  enabled={enabled}")
            print(f"  disabled={disabled}")
            print(f"  missing={missing}")


if __name__ == "__main__":
    main()
