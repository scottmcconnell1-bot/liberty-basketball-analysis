#!/usr/bin/env bash
# Usage: run_muse_or.sh <prompt file (Linux path)> <work dir (Linux path)> <out file (Linux path)>
# Runs Muse through Hermes's OpenRouter account; tries free models in order, switching on a limit error.
# A verdict counts only on a line that STARTS with "MUSE: AGREE" or "MUSE: DISAGREE:" after the
# model's reply marker, so the echoed prompt never counts as a verdict.
export PATH="$HOME/.local/bin:$PATH"
cd "$2" || exit 1
for m in recursive/flint-v1.0:free google/gemma-4-31b-it:free thinkingmachines/inkling:free poolside/laguna-s-2.1:free nvidia/nemotron-3.5-super-vl:free; do
  run="$3.$(echo "$m" | tr '/:' '__').txt"
  echo "[muse] model $m $(date +%H:%M:%S)" >> "$3"
  hermes chat -m "$m" -q "$(cat "$1")" > "$run" 2>&1
  verdict=$(sed -n '/☤ Hermes/,$p' "$run" | grep -E '^[[:space:]]*\**MUSE: (AGREE|DISAGREE)' | tail -1)
  if [ -n "$verdict" ]; then cat "$run" >> "$3"; echo "[muse] VERDICT ($m): $verdict" >> "$3"; exit 0; fi
  if grep -qiE "HTTP 429|rate-limited|rate limit|quota|usage limit|too many requests" "$run"; then echo "[muse] $m limited; switching" >> "$3"; sleep 20; continue; fi
  cat "$run" >> "$3"; echo "[muse] $m gave no verdict; switching" >> "$3"
done
echo "[muse] all models limited or no verdict" >> "$3"; exit 9
