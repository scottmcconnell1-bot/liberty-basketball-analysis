import sys, json
sys.path.insert(0, r"C:/Users/scott/AppData/Local/Temp/claude/9519414f725d5b3e/1ad6458c-fdef-4ea9-acfc-295e30fb4711/scratchpad")
sys.path.insert(0, r"C:/Users/scott/Documents/liberty-basketball-analysis/.team/shot_detectors")
from knn48 import *
from game_session import parse_clock
f = sys.argv[1]
X, y, _ = train("home", json.load(open(f"{S}/labels48_train_home.json")))
cap = cv2.VideoCapture(U + FILMS[f][0]); fps = cap.get(5); step = int(round(fps)); half = step // 2
out, i = [], 0
while cap.grab():
    if i % step == 0 or (i % step == half and out):
        ok, fr = cap.retrieve()
        if ok:
            s = read(clock_crop(fr, f), X, y)
            if i % step == 0:
                out.append({"t_ms": int(round(i / fps * 1000)), "read": s, "clock_s": parse_clock(s), "read2": None})
            else:
                out[-1]["read2"] = s
    i += 1
json.dump(out, open(f"{S}/home_raw48_{f}.json", "w"))
print(f, len(out))
