# Home laptop files over Tailscale

Updated: 2026-10-12.

Google Drive is not the handoff. The personal account filled up, and the work account cannot share the folder. The files stay on the home laptop and are served on its Tailscale address only.

## Where to copy from

While the home laptop is on and `scripts/serve_home_share.ps1` is running, the script prints the address. Ask Scott for it. It is not written in this repo. The address works only for a machine on the same Tailscale network. It is not the public coach site. The public coach site still proxies `/` to the coach app on port 8080. Do not turn Funnel on for port 8091. The script refuses to start if that port is already proxied, and it refuses to start if `.env` is in the share folder.

## What is in the folder

Clone this repo, run `git lfs pull`, then copy the served folder on top of the clone.

- `film_analysis.db` — read-only snapshot from 2026-10-11. Password hashes, phone numbers, session tokens, the NFHS login, and share tokens were removed. Do not copy this file back over the database on the home laptop.
- `uploads\nfhs_gam0a66d85e12.mp4` — the Adrian film only (video id 73).
- `data\film_tags\`, `data\hoop_tracks\`, `data\lineups\`, `data\hoopsalytics\`, `tag-exports\`.
- `offline\v6\weights\best.pt` and the three track files used for the 85 score. These are not a replacement for `models/ball_detector.pt`.

The coach portal password is not in this folder. Ask Scott for it separately.

Left on the home laptop: the other eight game films, the archive passphrase, and the NFHS login. The live model weights are in GitHub.

## Who can open it

A Tailscale invite to this network is what lets Jason or Brad reach the address. The folder is not a public link.
