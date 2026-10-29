#!/usr/bin/env bash
# Usage: run_hermes.sh <prompt file (Linux path)>
export PATH="$HOME/.local/bin:$PATH"
cd "${2:-/mnt/c/Users/scott/Documents/liberty-basketball-analysis}" || exit 1
hermes chat -q "$(cat "$1")"
