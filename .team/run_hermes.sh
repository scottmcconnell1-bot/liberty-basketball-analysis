#!/usr/bin/env bash
# Usage: run_hermes.sh <prompt file (Linux path)>
cd /mnt/c/Users/scott/Documents/liberty-basketball-analysis || exit 1
hermes chat -q "$(cat "$1")"
