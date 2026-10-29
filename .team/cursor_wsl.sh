#!/usr/bin/env bash
# Usage: cursor_wsl.sh <work dir (Linux path)> <prompt file (Linux path)> <out file (Linux path)>
# Runs Cursor's agent inside WSL with its Linux sandbox ALWAYS on (Scott, 2026-10-28).
# The sandbox confines Cursor to the work dir and the results folder outside the repo.
export PATH="$HOME/.local/bin:$PATH"
cd "$1" || exit 1
cursor-agent -p --sandbox enabled --trust --workspace "$1" \
  --add-dir /mnt/c/Users/scott/Documents/Liberty_Shot_Outputs \
  --output-format text "$(cat "$2")" > "$3" 2>&1
echo "[cursor_wsl] exit $? at $(date +%H:%M:%S)" >> "$3"
