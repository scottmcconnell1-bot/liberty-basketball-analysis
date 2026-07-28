#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if command -v python3.12 >/dev/null 2>&1; then
  exec python3.12 scripts/launch_liberty.py "$@"
fi
if command -v python3 >/dev/null 2>&1; then
  exec python3 scripts/launch_liberty.py "$@"
fi

echo "Python 3.12+ is required. Install with: sudo apt install python3.12 python3.12-venv"
exit 1
