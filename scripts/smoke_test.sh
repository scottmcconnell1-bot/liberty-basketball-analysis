#!/bin/bash
# smoke_test.sh — Deployment smoke tests for Liberty Basketball Analysis
# Tests both standalone and container deployment paths
# Usage: bash smoke_test.sh [standalone|container|all]

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PASS=0
FAIL=0

pass() { echo -e "${GREEN}[PASS]${NC} $1"; PASS=$((PASS + 1)); }
fail() { echo -e "${RED}[FAIL]${NC} $1"; FAIL=$((FAIL + 1)); }
skip() { echo -e "${YELLOW}[SKIP]${NC} $1"; }

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BASE_URL="${1:-http://localhost:8080}"

test_url() {
    local url="$1"
    local expected="${2:-200}"
    local desc="${3:-$url}"
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null || echo "000")
    if [ "$code" = "$expected" ]; then
        pass "$desc (HTTP $code)"
    else
        fail "$desc (expected HTTP $expected, got $code)"
    fi
}

test_json() {
    local url="$1"
    local desc="${2:-$url}"
    local response
    response=$(curl -s "$url" 2>/dev/null || echo "")
    if echo "$response" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
        pass "$desc (valid JSON)"
    else
        fail "$desc (invalid JSON: ${response:0:100})"
    fi
}

# ── Standalone Tests ────────────────────────────────────────────────

test_standalone() {
    echo ""
    echo "=== Standalone Deployment Smoke Tests ==="
    echo "Base URL: $BASE_URL"
    echo ""

    # Core pages
    test_url "$BASE_URL/" 200 "Dashboard page"
    test_url "$BASE_URL/schedule" 200 "Schedule page"
    test_url "$BASE_URL/games" 200 "Games page"
    test_url "$BASE_URL/practices" 200 "Practices page"
    test_url "$BASE_URL/player-development" 200 "Player Development page"
    test_url "$BASE_URL/practice-playlists" 200 "Practice Playlists page"
    test_url "$BASE_URL/film" 200 "Film Tool page"
    test_url "$BASE_URL/settings" 200 "Settings page"
    test_url "$BASE_URL/status" 200 "Status page"
    test_url "$BASE_URL/debug" 200 "Debug page"

    # API endpoints
    test_json "$BASE_URL/api/dashboard" "Dashboard API"
    test_json "$BASE_URL/api/seasons" "Seasons API"
    test_json "$BASE_URL/api/scheduled_games" "Scheduled Games API"
    test_json "$BASE_URL/api/games" "Games API"
    test_json "$BASE_URL/api/clips" "Clips API"
    test_json "$BASE_URL/api/playlists" "Playlists API"
    test_json "$BASE_URL/api/players" "Players API"
    test_json "$BASE_URL/api/resource-status" "Resource Status API"

    # API write test
    echo ""
    echo "=== API Write Test ==="
    SEASON_RESP=$(curl -s -X POST "$BASE_URL/api/seasons" \
        -H "Content-Type: application/json" \
        -d '{"name":"Smoke Test","start_date":"2025-01-01","end_date":"2025-12-31"}' 2>/dev/null)
    SEASON_ID=$(echo "$SEASON_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null || echo "")
    if [ -n "$SEASON_ID" ]; then
        pass "Created test season (id=$SEASON_ID)"
        # Clean up
        curl -s -X DELETE "$BASE_URL/api/seasons/$SEASON_ID" >/dev/null 2>&1
        pass "Deleted test season"
    else
        fail "Failed to create test season"
    fi

    # Systemd service check
    echo ""
    echo "=== Service Check ==="
    if systemctl is-active --quiet liberty-basketball-analysis 2>/dev/null; then
        pass "Systemd service is active"
    else
        skip "Systemd service not running (may be expected in dev)"
    fi
}

# ── Container Tests ─────────────────────────────────────────────────

test_container() {
    echo ""
    echo "=== Container Deployment Smoke Tests ==="

    if ! command -v docker &>/dev/null; then
        skip "Docker not installed"
        return
    fi

    if docker compose -f "$REPO_DIR/docker-compose.yml" ps --format json 2>/dev/null | grep -q "running"; then
        pass "Container is running"
        # Run tests through container
        test_standalone
    else
        skip "No running containers"
    fi
}

# ── Main ─────────────────────────────────────────────────────────────

echo "Liberty Basketball Analysis — Smoke Tests"
echo "=========================================="

case "${2:-standalone}" in
    standalone) test_standalone ;;
    container)  test_container ;;
    all)
        test_standalone
        test_container
        ;;
    *)
        echo "Usage: bash smoke_test.sh [base-url] [standalone|container|all]"
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo "Results: ${PASS} passed, ${FAIL} failed"
echo "=========================================="

[ "$FAIL" -eq 0 ] && exit 0 || exit 1
