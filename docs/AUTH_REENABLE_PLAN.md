# Auth Re-enable Plan (Stage 9B prep)

Updated: 2026-07-05  
Status: **Plan only** — do not enable global auth until Scott approves production deploy.

## Current state

| Component | Behavior |
| --- | --- |
| `app.before_request` (`require_auth_for_api`) | Disabled (`pass`) — all routes open |
| `users.login_required` | Used on profile, push subscription, notifications settings |
| Session | Flask cookie signed with `SECRET_KEY` |
| Password storage | Salted SHA-256 in `users._hash_password` |

Coach surfaces (`/film`, `/review`, `/status`, `/preview`) are reachable without login today.

## Goals for re-enable

1. Protect write APIs and coach data surfaces without breaking film upload workflows.
2. Team-scoped data access (default Liberty team first).
3. Staged rollout: dev → staging → production with feature flag.

## Proposed stages

### Stage B1 — Read-only audit mode

- Add `ENABLE_AUTH_MIDDLEWARE` feature flag (default `False`).
- When `True`, `before_request` sets `g.user` from session but does not block.
- Log would-be denials for unauthenticated write routes.

### Stage B2 — API write protection

- Require session for `POST`/`PUT`/`DELETE` on `/api/*` except:
  - `/api/save_event` (manual tag MVP — may require token or coach login)
  - Health/status probes as needed
- Return `401` JSON for XHR; redirect HTML forms to `/login`.

### Stage B3 — Page protection

- Require login for `/film`, `/review`, `/scouting`, `/playbook`, `/messages`.
- Leave `/preview` and `/status` readable for demo OR protect behind coach role (Scott decision).

### Stage B4 — Team scoping

- Attach `team_id` to session user context.
- Filter games/events/clips queries by team membership.

### Stage B5 — Password hardening

- Migrate to `werkzeug.security.generate_password_hash` (pbkdf2) or argon2 on next login.
- Rotate `SECRET_KEY` with session invalidation window.

## Prerequisites (from 9A)

- [ ] Production `SECRET_KEY` set via environment
- [ ] Secrets audit clean (`python3 scripts/audit_secrets.py`)
- [ ] SMTP/VAPID configured only via env if notifications enabled

## Scott gates (explicit approval)

- Flipping `ENABLE_AUTH_MIDDLEWARE` to `True`
- Public internet exposure
- Forced login on demo `/preview` routes

## Test plan

1. `pytest tests/` with auth flag off (current baseline).
2. Auth flag on: add `tests/test_auth_middleware.py` for 401 on protected writes.
3. Manual: login → film tag → review accept → stats still trusted.

## Related

- `docs/SECRETS_AUDIT.md`
- `docs/COMPLETION_PATH.md` Stage 9B
