#!/usr/bin/env bash
# Run the end-to-end suite against a REAL server: a scratch gunicorn on 127.0.0.1:8090 with its
# own SQLite file and upload folder, so nothing touches the production DB. The server spawns the
# real analysis worker, so the CV stack must be installed in .venv (CPU is fine; ~1-2 min).
#
#   bash scripts/run_e2e_live.sh            # default: real analysis of a 12 s clip
#   KEEP=1 bash scripts/run_e2e_live.sh     # leave the scratch server running afterwards
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PORT="${PORT:-8090}"
WORK="$(mktemp -d -t liberty-e2e-live-XXXX)"
export LIBERTY_DATABASE="$WORK/e2e.db"
export LIBERTY_UPLOAD_FOLDER="$WORK/uploads"
export LIBERTY_COACH_PASSWORD="e2e-coach-pass"
export LIBERTY_DEBUG=0
mkdir -p "$LIBERTY_UPLOAD_FOLDER"
.venv/bin/python -c "from app import app; from helpers import ensure_db; c=app.app_context(); c.push(); ensure_db(); c.pop()"
.venv/bin/gunicorn --workers 2 --bind "127.0.0.1:$PORT" --timeout 600 app:app > "$WORK/gunicorn.log" 2>&1 &
GPID=$!
trap '[ "${KEEP:-0}" = 1 ] || kill $GPID 2>/dev/null || true' EXIT
for i in $(seq 1 40); do curl -sf "http://127.0.0.1:$PORT/status" >/dev/null && break; sleep 0.5; done
echo "scratch server on :$PORT  db=$LIBERTY_DATABASE  uploads=$LIBERTY_UPLOAD_FOLDER"
LIBERTY_E2E_BASE_URL="http://127.0.0.1:$PORT" LIBERTY_E2E_DB="$LIBERTY_DATABASE" LIBERTY_E2E_UPLOADS="$LIBERTY_UPLOAD_FOLDER" \
  .venv/bin/python -m pytest tests/e2e -q -p no:cacheprovider "$@"
RC=$?
# confirmed stat books are written into the repo tree by design; drop the e2e ones
rm -f "$ROOT"/data/stat_books/confirmed/e2e*.json
echo "log: $WORK/gunicorn.log"
exit $RC
