# Active Task

Updated: 2026-09-14  
Branch: `cursor/full-stack-bringup-ac1f`  
Base / default: `main`

## Meta

| Field | Value |
| --- | --- |
| **id** | full-stack-bringup |
| **status** | `awaiting_scott` (Tailscale login) |
| **executor** | cursor-only |

## Done (Proven)

- Stale WSL Flask on :5000 (wrong branch) stopped
- Liberty `main` serving on **http://127.0.0.1:8080** and **http://192.168.0.152:8080** (`/coach` → 200)
- Python 3.12 `.venv` with Flask + torch/ultralytics/opencv/easyocr/sklearn
- Model weights present (`models/ball_detector.pt` ~165MB, player/court models)
- Auto-accept unlocked to **0.85** (code + Settings UI); jersey OCR left enabled
- Teach loop detached **running** (pid alive)
- Tailscale **installed** but **Logged out** — Funnel URL cannot work until Scott logs in

## Scott must do once

1. Open Tailscale and log in (or visit the URL from `tailscale login`)
2. Then tell Cursor — we will run: `tailscale funnel 8080` and confirm `https://liberty-coach.tail….ts.net/coach`

## Gated still (not changed)

- `ball_confidence` remains **0.25** (production ball detector settings untouched beyond using existing `models/ball_detector.pt`)
- Event generator mode still default **expanded** (not flipped to `precision`)

## Remotes kept until site verified

`dataset-v2`, `improve/precision-and-migration`, `fix/game-id-analysis-key`, `jason-5-may-updates`, `gh-pages`
