#!/usr/bin/env bash
# Stage 9C — Docker production smoke on a clean Linux host with Docker installed.
# Builds the CPU image, starts compose, runs HTTP smoke tests, optional secrets audit.
#
# Usage:
#   bash scripts/docker_production_smoke.sh
#   KEEP_RUNNING=1 bash scripts/docker_production_smoke.sh
#   COMPOSE_FILE=docker-compose.yml PORT=8080 bash scripts/docker_production_smoke.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
PORT="${PORT:-8080}"
BASE_URL="http://127.0.0.1:${PORT}"
KEEP_RUNNING="${KEEP_RUNNING:-0}"
WAIT_SECONDS="${WAIT_SECONDS:-90}"

log() { echo "[docker-smoke] $*"; }
fail() { echo "[docker-smoke] ERROR: $*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || fail "docker is not installed"
docker compose version >/dev/null 2>&1 || fail "docker compose plugin is not available"
command -v curl >/dev/null 2>&1 || fail "curl is required"

cd "${ROOT_DIR}"

log "Building image (compose file: ${COMPOSE_FILE})"
docker compose -f "${COMPOSE_FILE}" build

log "Starting container"
docker compose -f "${COMPOSE_FILE}" up -d

cleanup() {
  if [[ "${KEEP_RUNNING}" == "1" ]]; then
    log "KEEP_RUNNING=1 — leaving container up at ${BASE_URL}"
    return
  fi
  log "Stopping container"
  docker compose -f "${COMPOSE_FILE}" down
}
trap cleanup EXIT

log "Waiting up to ${WAIT_SECONDS}s for ${BASE_URL}/status"
deadline=$((SECONDS + WAIT_SECONDS))
until curl -sf "${BASE_URL}/status" >/dev/null 2>&1; do
  if (( SECONDS >= deadline )); then
    docker compose -f "${COMPOSE_FILE}" logs --tail=80 web || true
    fail "app did not become ready within ${WAIT_SECONDS}s"
  fi
  sleep 2
done
log "App responded on /status"

log "Running HTTP smoke tests"
bash "${ROOT_DIR}/scripts/smoke_test.sh" "${BASE_URL}" standalone

if docker compose -f "${COMPOSE_FILE}" exec -T web python scripts/audit_secrets.py >/dev/null 2>&1; then
  log "Secrets audit (in container)"
  docker compose -f "${COMPOSE_FILE}" exec -T web python scripts/audit_secrets.py
else
  log "Skipping in-container secrets audit (script unavailable in image)"
fi

log "Docker production smoke passed"
