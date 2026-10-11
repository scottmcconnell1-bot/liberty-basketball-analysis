# Home laptop files over Tailscale

Updated: 2026-10-11.

Google Drive is not the handoff. The personal account filled up, and the work account cannot share the folder. The files stay on the home laptop and are served on its Tailscale address only.

## Where to copy from

On the tailnet, the home machine is `liberty-coach` at `100.107.224.49`. While that laptop is on and `scripts/serve_home_share.ps1` is running:

`http://100.107.224.49:8091/`

That address works only for a machine on the same Tailscale network. It is not the public coach site. The public site, `https://liberty-coach.tail368a37.ts.net`, still proxies `/` to the coach app on port 8080. Do not turn Funnel on for port 8091.

## What is in the folder

Clone this repo, run `git lfs pull`, then copy the served folder on top of the clone.

- `film_analysis.db` — read-only snapshot from 2026-10-11. Password hashes, phone numbers, session tokens, the NFHS login, and share tokens were removed. Do not copy this file back over the database on the home laptop.
- `uploads\nfhs_gam0a66d85e12.mp4` — the Adrian film only (video id 73).
- `data\film_tags\`, `data\hoop_tracks\`, `data\lineups\`, `data\hoopsalytics\`, `tag-exports\`.
- `.env` — the coach portal password only.
- `offline\v6\weights\best.pt` and the three track files used for the 85 score. These are not a replacement for `models/ball_detector.pt`.

Left on the home laptop: the other eight game films, the archive passphrase, and the NFHS login. The live model weights are in GitHub.

## Who can open it

A Tailscale invite to this network is what lets Jason or Brad reach the address. The folder is not a public link.
