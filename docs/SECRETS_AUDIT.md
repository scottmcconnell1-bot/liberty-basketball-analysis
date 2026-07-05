# Secrets Audit (Stage 9A)

Updated: 2026-07-05  
Branch: `jason-5-may-updates`  
Status: **Audit complete** — remediation items below require Scott approval before production.

## Scope

Inventory of secret-bearing configuration for Liberty Basketball Analysis:

- Flask `SECRET_KEY`
- VAPID browser push keys
- SMTP email credentials
- NFHS Network stored credentials
- User password hashing
- Auth middleware state

## Operator CLI

```bash
python3 scripts/audit_secrets.py
```

Programmatic report: `secrets_audit.audit_secrets(app)`.

Environment template: `.env.example` (copy locally; never commit `.env`).

## Findings summary

| Category | Severity | Status | Notes |
| --- | --- | --- | --- |
| Flask `SECRET_KEY` | High | Dev fallback active | `app.py` uses `liberty-basketball-dev-secret-key-2026` when env unset |
| VAPID keys | Medium | Env-only (post-9A) | Committed defaults removed from `config.py`; set `VAPID_*` env vars to enable push |
| SMTP | Medium | Optional / env | Empty by default; notifications skip email when unset |
| NFHS `password_enc` | High | Weak obfuscation | XOR with hardcoded key `liberty_basketball_nfhs_2026` in `nfhs.py` |
| NFHS OAuth tokens | Medium | Temp files | Cached under system temp (`nfhs_token_*.json`) |
| Auth middleware | Medium | Disabled | `app.before_request` is `pass` — see `docs/AUTH_REENABLE_PLAN.md` |
| User passwords | Medium | SHA-256 + salt | Not bcrypt/argon2; upgrade before public auth |

## Required before production

1. Set `SECRET_KEY` to a long random value (32+ bytes).
2. Generate fresh VAPID key pair; store only in environment/secret manager.
3. Configure SMTP via environment if email notifications are enabled.
4. Replace NFHS XOR obfuscation with Fernet or secret-manager-backed encryption (Scott gate).
5. Re-enable auth per `docs/AUTH_REENABLE_PLAN.md` (Scott gate).

## Files reviewed

| File | Secret surface |
| --- | --- |
| `config.py` | VAPID, SMTP env reads |
| `app.py` | `SECRET_KEY` fallback |
| `services/notifications.py` | VAPID + SMTP consumers |
| `nfhs.py` | XOR key, token cache paths |
| `blueprints/scouting.py` | NFHS credential persistence |
| `blueprints/users.py` | Password hash, VAPID public endpoint |

## Related

- `docs/AUTH_REENABLE_PLAN.md` — Stage 9B staged auth plan
- `docs/COMPLETION_PATH.md` — Phase 4 deploy gates
