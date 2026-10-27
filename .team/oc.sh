#!/usr/bin/env bash
# Usage: oc.sh <model> <out file> <prompt...>
# Runs opencode; if it has not reached the model within 120 s, kills it and retries (3 tries).
model="$1"; out="$2"; shift 2
for try in 1 2 3; do
  log=".team/oc_log_$$_$try.txt"
  opencode run --print-logs -m "$model" "$@" > "$out" 2> "$log" &
  pid=$!
  started=no
  for i in $(seq 1 60); do
    if grep -q "llm runtime selected" "$log" 2>/dev/null; then started=yes; break; fi
    if ! kill -0 $pid 2>/dev/null; then started=yes; break; fi
    sleep 2
  done
  if [ "$started" = yes ]; then wait $pid; rc=$?; echo "[oc.sh] $model try $try finished rc=$rc at $(date +%H:%M:%S)"; exit $rc; fi
  echo "[oc.sh] $model try $try stuck at startup; killing and retrying at $(date +%H:%M:%S)"
  taskkill //F //T //PID $(ps -W | awk -v p=$pid '$1==p{print $4}') >/dev/null 2>&1; kill $pid 2>/dev/null
  taskkill //F //IM opencode.exe >/dev/null 2>&1
done
echo "[oc.sh] $model failed to start after 3 tries"; exit 9
