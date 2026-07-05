"""
Stage 9A secrets audit helpers.

Read-only checks for VAPID, SMTP, Flask secret key, and NFHS credential storage.
Does not print secret values.
"""

import os
import re

KNOWN_DEV_SECRET = "liberty-basketball-dev-secret-key-2026"
KNOWN_NFHS_XOR_KEY = "liberty_basketball_nfhs_2026"

# Historical committed VAPID material fingerprint (config.py pre-9A). Empty after remediation.
LEGACY_VAPID_PUBLIC_FINGERPRINT = "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE1HfK"


def _is_set(value):
    return bool(value and str(value).strip())


def _mask_fingerprint(value, length=12):
    if not value:
        return ""
    text = str(value).strip().replace("\n", "")
    return text[:length] + "…" if len(text) > length else text


def audit_secrets(app):
    """Return structured findings for operator review."""
    findings = []

    secret_key = app.config.get("SECRET_KEY") or os.environ.get("SECRET_KEY", "")
    if secret_key == KNOWN_DEV_SECRET:
        findings.append(
            {
                "severity": "high",
                "category": "flask_secret_key",
                "status": "dev_fallback",
                "message": "Flask SECRET_KEY uses the committed development fallback.",
                "remediation": "Set SECRET_KEY env var before production deploy.",
            }
        )
    elif not _is_set(secret_key):
        findings.append(
            {
                "severity": "critical",
                "category": "flask_secret_key",
                "status": "missing",
                "message": "Flask SECRET_KEY is not configured.",
                "remediation": "Set SECRET_KEY to a long random value.",
            }
        )
    else:
        findings.append(
            {
                "severity": "ok",
                "category": "flask_secret_key",
                "status": "configured",
                "message": "Flask SECRET_KEY is set (custom value).",
                "remediation": "Rotate periodically; keep out of git.",
            }
        )

    vapid_private = app.config.get("VAPID_PRIVATE_KEY", "")
    vapid_public = app.config.get("VAPID_PUBLIC_KEY", "")
    if not _is_set(vapid_private) or not _is_set(vapid_public):
        findings.append(
            {
                "severity": "medium",
                "category": "vapid",
                "status": "missing",
                "message": "VAPID keys are not configured; push notifications are disabled.",
                "remediation": "Set VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY via environment.",
            }
        )
    elif LEGACY_VAPID_PUBLIC_FINGERPRINT in str(vapid_public):
        findings.append(
            {
                "severity": "critical",
                "category": "vapid",
                "status": "committed_default",
                "message": "VAPID public key matches legacy committed default in config.py.",
                "remediation": "Generate new VAPID keys; store only in environment/secret manager.",
            }
        )
    else:
        findings.append(
            {
                "severity": "ok",
                "category": "vapid",
                "status": "configured",
                "message": f"VAPID keys configured (public fp: {_mask_fingerprint(vapid_public)}).",
                "remediation": "Never commit private key; rotate if previously exposed in git.",
            }
        )

    smtp_fields = {
        "SMTP_SERVER": app.config.get("SMTP_SERVER", ""),
        "SMTP_USERNAME": app.config.get("SMTP_USERNAME", ""),
        "SMTP_PASSWORD": app.config.get("SMTP_PASSWORD", ""),
        "SMTP_FROM": app.config.get("SMTP_FROM", ""),
    }
    if all(_is_set(smtp_fields[k]) for k in ("SMTP_SERVER", "SMTP_USERNAME", "SMTP_PASSWORD")):
        findings.append(
            {
                "severity": "ok",
                "category": "smtp",
                "status": "configured",
                "message": f"SMTP configured for server {_mask_fingerprint(smtp_fields['SMTP_SERVER'], 24)}.",
                "remediation": "Use app-specific SMTP password; restrict via env only.",
            }
        )
    else:
        missing = [k for k, v in smtp_fields.items() if not _is_set(v) and k != "SMTP_FROM"]
        findings.append(
            {
                "severity": "medium",
                "category": "smtp",
                "status": "missing",
                "message": "SMTP is not fully configured; email notifications are disabled.",
                "remediation": "Set SMTP_SERVER, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM in environment.",
                "details": {"missing": missing},
            }
        )

    findings.append(
        {
            "severity": "high",
            "category": "nfhs_credentials",
            "status": "weak_obfuscation",
            "message": "NFHS passwords use XOR obfuscation with a hardcoded key in nfhs.py.",
            "remediation": "Migrate to Fernet/env-derived key (Scott gate); treat DB nfhs_credentials as sensitive.",
            "details": {"xor_key_fingerprint": _mask_fingerprint(KNOWN_NFHS_XOR_KEY)},
        }
    )

    findings.append(
        {
            "severity": "medium",
            "category": "auth_middleware",
            "status": "disabled",
            "message": "Global API auth middleware in app.py is intentionally disabled (pass).",
            "remediation": "Follow docs/AUTH_REENABLE_PLAN.md before public production.",
        }
    )

    password_hash_note = (
        "User passwords use salted SHA-256 in users.py; prefer bcrypt/argon2 before production auth."
    )
    findings.append(
        {
            "severity": "medium",
            "category": "user_passwords",
            "status": "sha256",
            "message": password_hash_note,
            "remediation": "Upgrade hash on login rehash path when auth is re-enabled.",
        }
    )

    return {
        "finding_count": len(findings),
        "critical": sum(1 for f in findings if f["severity"] == "critical"),
        "high": sum(1 for f in findings if f["severity"] == "high"),
        "medium": sum(1 for f in findings if f["severity"] == "medium"),
        "ok": sum(1 for f in findings if f["severity"] == "ok"),
        "findings": findings,
    }


def scan_repo_for_hardcoded_patterns(root):
    """Lightweight grep for obvious secret patterns in tracked source files."""
    patterns = [
        (re.compile(r"BEGIN PRIVATE KEY"), "private_key_block"),
        (re.compile(r"password\s*=\s*['\"][^'\"]{8,}['\"]"), "hardcoded_password_literal"),
        (re.compile(r"api[_-]?key\s*=\s*['\"][^'\"]+['\"]", re.I), "hardcoded_api_key"),
    ]
    hits = []
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "uploads"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for filename in filenames:
            if not filename.endswith((".py", ".js", ".html", ".env", ".yml", ".yaml", ".json")):
                continue
            path = os.path.join(dirpath, filename)
            try:
                with open(path, encoding="utf-8", errors="ignore") as handle:
                    for lineno, line in enumerate(handle, start=1):
                        for pattern, label in patterns:
                            if pattern.search(line) and "secrets_audit" not in path:
                                hits.append(
                                    {
                                        "file": os.path.relpath(path, root),
                                        "line": lineno,
                                        "type": label,
                                    }
                                )
            except OSError:
                continue
    return hits
