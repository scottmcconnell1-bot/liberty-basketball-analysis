# Setup checklist — Coach portal permanent tunnel

Printable steps for Scott. Does **not** install cloudflared/Tailscale for you (those need your login).

## Before the tunnel

1. Liberty app listening: `http://127.0.0.1:8080` (and `0.0.0.0:8080`).
2. Set password:

```bat
set LIBERTY_COACH_PASSWORD=your-shared-password
```

3. Confirm locally: open `http://127.0.0.1:8080/coach`, enter password, confirm Dashboard loads and Settings is hidden.

## Pick one permanent option

### A) Cloudflare named tunnel

- Domain on Cloudflare required.
- Install cloudflared → login → create named tunnel → ingress to `http://127.0.0.1:8080`.
- Share `https://<hostname>/coach`.
- Do **not** use `cloudflared tunnel --url` (temporary).

### B) Tailscale Funnel

- Install Tailscale on this PC → enable Funnel → `tailscale funnel 8080`.
- Share `https://<machine>.<tailnet>.ts.net/coach`.
- Or have coaches join the tailnet (MagicDNS) if you prefer private-only access.

## Keep alive

- PC awake / not sleeping hard.
- Flask + tunnel process running (Startup folder or Task Scheduler optional later).

Full write-up: `docs/COACH_PORTAL.md`.
