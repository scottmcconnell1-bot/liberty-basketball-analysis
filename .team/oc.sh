#!/usr/bin/env bash
# Usage: oc.sh <model> <out file> <prompt...>
# Runs opencode with the given model first, then the other free models in order:
# OpenCode Zen free models, then Ollama cloud (gemma4, beam; separate free limits), then local nemotron-3-nano:30b (no limit, slow).
# - Startup watchdog: if it has not reached the model within 120 s, kill and retry (3 tries per model).
# - Limit watchdog: opencode does not exit on "Free usage limit reached" / 429; it hangs. When the
#   log shows a limit error, kill it and move to the next free model.
first="$1"; out="$2"; shift 2
models="$first"
for m in opencode/deepseek-v4.1-flash-free opencode/mimo-v2.6-flash-free opencode/nemotron-3.5-super-vl-free opencode/glm-5.3-flash-free opencode/flint-40b-free opencode/beam-free ollama/gpt-oss:120b-cloud ollama/gemma4:cloud ollama/beam:cloud ollama/nemotron-3-nano:30b; do
  [ "$m" != "$first" ] && models="$models $m"
done
LIMIT_RE='Free usage limit reached|HTTP 429|rate limit|too many requests|quota'
killall_oc() { taskkill //F //T //PID "$(ps -W | awk -v p="$1" '$1==p{print $4}')" >/dev/null 2>&1; kill "$1" 2>/dev/null; taskkill //F //IM opencode.exe >/dev/null 2>&1; }
for model in $models; do
  for try in 1 2 3; do
    log=".team/oc_log_$$_${try}.txt"
    opencode run --print-logs -m "$model" "$@" > "$out" 2> "$log" &
    pid=$!
    started=no
    for i in $(seq 1 60); do
      if grep -q "llm runtime selected" "$log" 2>/dev/null; then started=yes; break; fi
      if ! kill -0 $pid 2>/dev/null; then started=yes; break; fi
      sleep 2
    done
    if [ "$started" != yes ]; then
      echo "[oc.sh] $model try $try stuck at startup; killing and retrying at $(date +%H:%M:%S)"
      killall_oc $pid; continue
    fi
    limited=no
    while kill -0 $pid 2>/dev/null; do
      if grep -qaE "$LIMIT_RE" "$log" 2>/dev/null; then limited=yes; killall_oc $pid; break; fi
      sleep 5
    done
    wait $pid 2>/dev/null; rc=$?
    if [ "$limited" = yes ] || grep -qaE "$LIMIT_RE" "$log" 2>/dev/null; then
      echo "[oc.sh] $model LIMITED at $(date +%H:%M:%S); switching to next free model"; break
    fi
    echo "[oc.sh] $model try $try finished rc=$rc at $(date +%H:%M:%S)"; exit $rc
  done
done
echo "[oc.sh] every free model limited or failed to start"; exit 9
