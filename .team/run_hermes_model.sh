#!/usr/bin/env bash
# Usage: run_hermes_model.sh <model> <prompt file (Linux path)> <out file (Linux path)>
# Same as run_hermes.sh but with an explicit OpenRouter model (default model returned empty replies 2026-11-11).
export PATH="$HOME/.local/bin:$PATH"
cd /mnt/c/Users/scott/Documents/liberty-basketball-analysis || exit 1
hermes chat -m "$1" --provider openrouter -q "$(cat "$2")" > "$3" 2>&1
echo "[hermes] exit $? at $(date +%H:%M:%S)" >> "$3"
