#!/usr/bin/env bash
# New film -> candidates, contact sheets, clips (NO model output). Label the sheets BEFORE running ensemble_predict.py.
# Usage (Git Bash, repo root):  bash .team/mm_clip/new_film.sh <film_id> <uploads/video.mp4>
# Steps: rim_first_finder base run (GPU env) -> candidates.py -> moving_ball.py -> contact sheets -> extract_clips.py (unlabelled)
set -euo pipefail
export MSYS_NO_PATHCONV=1
F="$1"; V="$2"
G=/c/Users/scott/.venvs/liberty-gpu/Scripts/python.exe
P=.venv/Scripts/python.exe
RF=C:/Users/scott/Documents/Liberty_Shot_Outputs/rim_first/run_new_$F
C=C:/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/cand5
O=C:/Users/scott/Documents/Liberty_Shot_Outputs/mm_clip/new/$F
mkdir -p "$O"
E=$($P -I -c "import cv2;c=cv2.VideoCapture('$V');print(int(c.get(7)/c.get(5)*1000)-1000)")
FPS=$($P -I -c "import cv2;c=cv2.VideoCapture('$V');print(c.get(5))")
echo "[$F] finder 0-$E ms (fps $FPS) $(date +%H:%M)"
$G .team/shot_detectors/rim_first_finder.py --video "$V" --start-ms 0 --end-ms "$E" \
  --bodd "C:/Users/scott/AppData/Local/Temp/BODD_yolov8n_0001.pt" \
  --v6 "C:/Users/scott/AppData/Local/Temp/ball_net_runs/v6/weights/best.pt" \
  --out-dir "$RF" --ft-off > "$O/finder.log" 2>&1
$P .team/mm_clip/candidates.py "$C/$F.json" "$FPS" "$RF/moments.json" "$RF/frames.json" | tail -1
$P .team/mm_clip/moving_ball.py "$C/$F.json" "$RF/frames.json" "$C/${F}_mv.json" | tail -1
N=$($P -I -c "import json;print(len(json.load(open('$C/${F}_mv.json'))['moments']))")
for a in $(seq 0 5 $((N - 1))); do
  $P .team/mm_clip/contact_sheet.py "$C/${F}_mv.json" "$V" "$O/sheets" "$a" $((a + 5)) > /dev/null
done
$P .team/mm_clip/extract_clips.py "$F" "$C/${F}_mv.json" "$V" none "$O/$F.npz" | tail -1
echo "[$F] done $(date +%H:%M): $N candidates; sheets in $O/sheets; label them BEFORE ensemble_predict.py"
