#!/usr/bin/env bash
# Run the test suite inside Docker instead of a local venv.
#
#   bash scripts/docker_test.sh            # full CV image (OpenCV + YOLO), like the home PC
#   bash scripts/docker_test.sh --ci       # python:3.12-slim + requirements.txt, like CI
#   bash scripts/docker_test.sh -- -k speed   # extra pytest args after --
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE=full
if [[ "${1:-}" == "--ci" ]]; then MODE=ci; shift; fi
if [[ "${1:-}" == "--" ]]; then shift; fi

if [[ "$MODE" == "ci" ]]; then
  exec docker run --rm -v "$ROOT":/src:ro python:3.12-slim bash -c '
    apt-get update -qq >/dev/null && apt-get install -y -qq --no-install-recommends ffmpeg >/dev/null
    cp -r /src /app && cd /app && pip install -q -r requirements.txt >/dev/null
    python -m pytest -p no:cacheprovider -q tests/ "$@"' _ "$@"
fi

docker image inspect liberty-analysis:cpu >/dev/null 2>&1 || docker build -t liberty-analysis:cpu "$ROOT"
exec docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e YOLO_CONFIG_DIR=/tmp/yolo \
  -v "$ROOT":/app -w /app liberty-analysis:cpu python -m pytest -p no:cacheprovider -q tests/ "$@"
