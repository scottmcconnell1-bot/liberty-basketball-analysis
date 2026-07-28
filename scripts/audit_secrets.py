"""
CLI secrets audit for Stage 9A.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app
from helpers import ensure_db
from secrets_audit import audit_secrets, scan_repo_for_hardcoded_patterns


def main():
    with app.app_context():
        ensure_db()
        report = audit_secrets(app)
        print(f"findings={report['finding_count']} critical={report['critical']} high={report['high']} medium={report['medium']} ok={report['ok']}")
        for item in report["findings"]:
            print(f"[{item['severity']}] {item['category']}: {item['status']} — {item['message']}")
            if item.get("remediation"):
                print(f"  remediation: {item['remediation']}")

        hits = scan_repo_for_hardcoded_patterns(os.path.dirname(os.path.dirname(__file__)))
        if hits:
            print(f"repo_pattern_hits={len(hits)}")
            for hit in hits[:20]:
                print(f"  {hit['file']}:{hit['line']} ({hit['type']})")
        else:
            print("repo_pattern_hits=0")


if __name__ == "__main__":
    main()
