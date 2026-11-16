#!/usr/bin/env bash
# Usage: cursor_ask.sh <prompt file (Linux path)> <out file (Linux path)> - read-only question to Cursor (sandbox on)
export PATH="$HOME/.local/bin:$PATH"
cd /mnt/c/Users/scott/Documents/liberty-basketball-analysis || exit 1
cursor-agent -p --sandbox enabled --trust --output-format text "$(cat "$1")" > "$2" 2>&1
echo "[cursor_ask] exit $? at $(date +%H:%M:%S)" >> "$2"
