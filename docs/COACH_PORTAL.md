# Coach Portal (Approach A)

Permanent link for coaches to open the **live Liberty app with real data**, without ops surfaces (Settings, Users, Debug, Status, NFHS matching, admin wipe, analysis start).

Scott keeps the PC on and the Flask app listening. Coaches use a shared password at `/coach`.

## Quick start (Scott)

1. Keep Liberty running on all interfaces, port **8080**:
   - `Start Liberty.bat`, or
   - `py -3.12 app.py` with `PORT=8080` (default in `app.py`)
2. Set a shared password (env only — no DB / `schema.sql`):

```bat
set LIBERTY_COACH_PASSWORD=choose-a-strong-shared-password
```

Or add that line near the top of a local launcher wrapper before starting the app.

3. Share with coaches: `https://liberty-coach.tail368a37.ts.net/coach`
4. After login, coaches land on **`/coach/progress`** — live HUDL queue %, active analysis, and fixed-panel gates (plus the nightly `LEARNING_STATUS.md` text).
5. Feature flag `ENABLE_COACH_PORTAL` defaults **True** (intentional). Uncheck in Settings if you need to disable the routes.

Keep Liberty + Funnel on port **8080** via `py -3.12 scripts/start_hoops_teach_detached.py` so coaches always hit the same app that is learning.

If `LIBERTY_COACH_PASSWORD` is empty, `/coach` shows setup instructions instead of a login form.

## Soft gate behavior

| Action | Result |
| --- | --- |
| `GET/POST /coach` or `/coach/login` | Password gate → `session["coach_portal"] = True` |
| `GET /coach/logout` | Clears coach portal session |
| Coach session + ops path | Redirect to `/` (HTML) or `403` (API) |
| Global API auth | **Unchanged** — `require_auth_for_api` still a no-op |

Denied while `coach_portal` is set (non-exhaustive): `/settings`, `/users`, `/debug`, `/status`, `/preview`, `/nfhs-matches`, `/api/admin/*`, `/api/nfhs_matches*`, upload/analyze/regenerate endpoints.

Allowed: Dashboard, schedule, practices, playbook, messages, film/videos **read** paths, static, share URLs, login.

### Read-only coach mode

When `session["coach_portal"]` is True, coaches can **browse** the real app and data but **cannot make permanent changes**:

| Request | Result |
| --- | --- |
| `GET` / `HEAD` / `OPTIONS` | Allowed (except ops denylist above) |
| `POST` to `/coach`, `/coach/login`, `/coach/logout`, `/login`, `/logout` | Allowed (auth flow only) |
| Other `POST` / `PUT` / `PATCH` / `DELETE` | Blocked — JSON APIs return `{"error": "Coach view is read-only"}` with **403**; HTML forms flash and redirect back |

Examples blocked: schedule save/delete, playbook create/save/delete, recruiting edits, practices save, uploads, analyze, message send, clip tags.

Templates get `coach_portal` and `coach_readonly` (same flag). Nav shows **Coach view · read only** plus a page banner.

Nav in Coach view: hides More → Settings / Users / Debug / NFHS Matches and Report Bug; shows a **Coach view · read only** badge + Sign out.

## Permanent URL options (do not use free quick tunnels)

Free `cloudflared tunnel --url http://127.0.0.1:8080` (and similar) creates a **temporary** hostname that changes — **do not use those for coaches**.

### Option 1 — Cloudflare named tunnel (stable hostname)

Needs a domain on Cloudflare (or a subdomain you control there).

1. Install [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/) for Windows.
2. `cloudflared tunnel login` (once, in a browser).
3. `cloudflared tunnel create liberty-coach`
4. Config (example `%USERPROFILE%\.cloudflared\config.yml`):

```yaml
tunnel: <TUNNEL_UUID>
credentials-file: C:\Users\<you>\.cloudflared\<TUNNEL_UUID>.json

ingress:
  - hostname: liberty-coach.yourdomain.com
    service: http://127.0.0.1:8080
  - service: http_status:404
```

5. Add a Cloudflare DNS CNAME for `liberty-coach` → `<TUNNEL_UUID>.cfargotunnel.com` (cloudflared can do this with `tunnel route dns`).
6. Run: `cloudflared tunnel run liberty-coach`
7. Share: `https://liberty-coach.yourdomain.com/coach`

### Option 2 — Tailscale Funnel (no Cloudflare domain)

Permanent-ish HTTPS on `https://<machine>.<tailnet>.ts.net` without coaches installing Tailscale when **Funnel** is enabled.

1. Install [Tailscale](https://tailscale.com/download) on Scott’s PC; sign in.
2. Enable HTTPS / Funnel for the machine (Tailscale admin console + CLI as documented for your plan).
3. Point Funnel at local port 8080, e.g.:

```bat
tailscale funnel 8080
```

4. Share: `https://<machine>.<tailnet>.ts.net/coach`

Alternative: **MagicDNS** if coaches join the same tailnet (they install Tailscale) — then `http://<machine>:8080/coach` or MagicDNS hostname works on the private network without Funnel.

## Password reminder snippet

```bat
REM Optional: set before Start Liberty.bat / app.py
if not defined LIBERTY_COACH_PASSWORD set LIBERTY_COACH_PASSWORD=change-me
```

See also `scripts/setup_coach_tunnel.md` for a short checklist (no credentialed installs required from the agent).

## Out of scope (deferred)

- Global auth middleware / `AUTH_REENABLE`
- Per-coach user accounts required for portal entry
- Storing coach password hash in SQLite (`schema.sql` gate)
