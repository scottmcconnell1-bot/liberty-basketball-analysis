"""Tests for Stage 9A secrets audit."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from secrets_audit import (
    KNOWN_DEV_SECRET,
    audit_secrets,
    scan_repo_for_hardcoded_patterns,
)


def test_audit_secrets_reports_dev_secret_fallback(app):
    with app.app_context():
        app.config["SECRET_KEY"] = KNOWN_DEV_SECRET
        app.config["VAPID_PRIVATE_KEY"] = ""
        app.config["VAPID_PUBLIC_KEY"] = ""
        report = audit_secrets(app)
    categories = {f["category"] for f in report["findings"]}
    assert "flask_secret_key" in categories
    assert "vapid" in categories
    assert "nfhs_credentials" in categories
    assert report["high"] >= 1


def test_audit_secrets_ok_when_custom_secret(app):
    with app.app_context():
        app.config["SECRET_KEY"] = "custom-production-secret-value"
        app.config["VAPID_PRIVATE_KEY"] = "private-key-material"
        app.config["VAPID_PUBLIC_KEY"] = "public-key-material"
        app.config["SMTP_SERVER"] = "smtp.example.com"
        app.config["SMTP_USERNAME"] = "user"
        app.config["SMTP_PASSWORD"] = "pass"
        app.config["SMTP_FROM"] = "liberty@example.com"
        report = audit_secrets(app)
    secret_finding = next(f for f in report["findings"] if f["category"] == "flask_secret_key")
    assert secret_finding["status"] == "configured"
    smtp_finding = next(f for f in report["findings"] if f["category"] == "smtp")
    assert smtp_finding["status"] == "configured"


def test_config_does_not_ship_vapid_private_key():
    from config import Config

    assert "BEGIN PRIVATE KEY" not in Config.VAPID_PRIVATE_KEY
    assert "BEGIN PUBLIC KEY" not in Config.VAPID_PUBLIC_KEY


def test_audit_secrets_cli_runs():
    import subprocess

    result = subprocess.run(
        [sys.executable, "scripts/audit_secrets.py"],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "findings=" in result.stdout


def test_repo_scan_skips_clean_config():
    root = os.path.dirname(os.path.dirname(__file__))
    hits = [
        h for h in scan_repo_for_hardcoded_patterns(root)
        if h["file"] == "config.py" and h["type"] == "private_key_block"
    ]
    assert hits == []
