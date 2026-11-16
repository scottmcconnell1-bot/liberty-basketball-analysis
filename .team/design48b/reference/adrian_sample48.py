import sys, json
sys.path.insert(0, r"C:/Users/scott/AppData/Local/Temp/claude/9519414f725d5b3e/1ad6458c-fdef-4ea9-acfc-295e30fb4711/scratchpad")
from adrian_read48 import *
X, y = train()
cap = cv2.VideoCapture(D.U + D.FILMS["adrian"][0]); fps = cap.get(5); step = int(round(fps))
out, i, half = [], 0, step // 2
while cap.grab():
    if i % step == 0:
        ok, fr = cap.retrieve()
        if ok:
            f, v = read_cells(D.clock_crop(fr, "adrian"), X, y)
            out.append({"t_ms": int(round(i / fps * 1000)), "fmt": f, "v": v, "fmt2": None, "v2": None})
    elif i % step == half and out:
        ok, fr = cap.retrieve()
        if ok:
            out[-1]["fmt2"], out[-1]["v2"] = read_cells(D.clock_crop(fr, "adrian"), X, y)
    i += 1
json.dump(out, open(f"{S}/adrian_raw48.json", "w"))
print(len(out), "samples")
