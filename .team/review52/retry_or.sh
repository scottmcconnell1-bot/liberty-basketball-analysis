#!/usr/bin/env bash
# retry Hermes 52c (model fallback) and Muse 52b v2 until both done or 8 rounds (~6 min apart)
L=/mnt/c/Users/scott/Documents/liberty-basketball-analysis; R=$L/.team/review52
export PATH="$HOME/.local/bin:$PATH"; cd $L
for round in 1 2 3 4 5 6 7 8; do
  if [ ! -f $L/.team/specs/52c_first_shot_sequence_prereg.md ]; then
    for m in recursive/flint-v1.0:free google/gemma-4-31b-it:free nvidia/nemotron-3.5-super-vl:free thinkingmachines/inkling:free; do
      bash $L/.team/run_hermes_model.sh $m $R/prompt_hermes_spec52c_seqfix.txt $R/hermes_spec52c_r${round}.txt
      [ -f $L/.team/specs/52c_first_shot_sequence_prereg.md ] && grep -q "PREREG WRITTEN" $R/hermes_spec52c_r${round}.txt && { echo "52c ok $m r$round" >> $R/retry_or.log; break; }
    done
  fi
  if ! grep -q "\[muse\] VERDICT" $R/muse_spec52b_v2.txt 2>/dev/null; then
    bash $L/.team/run_muse_or.sh $R/prompt_muse_spec52b_v2.txt $L $R/muse_spec52b_v2.txt
  fi
  if [ -f $L/.team/specs/52c_first_shot_sequence_prereg.md ] && grep -q "\[muse\] VERDICT" $R/muse_spec52b_v2.txt; then echo "ALL DONE r$round $(date +%H:%M)" >> $R/retry_or.log; exit 0; fi
  echo "round $round not done $(date +%H:%M)" >> $R/retry_or.log; sleep 360
done
echo "GAVE UP $(date +%H:%M)" >> $R/retry_or.log; exit 3
