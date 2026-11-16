import sys, json
sys.path.insert(0, r"C:/Users/scott/AppData/Local/Temp/claude/9519414f725d5b3e/1ad6458c-fdef-4ea9-acfc-295e30fb4711/scratchpad")
from adrian48 import *
S = r"C:/Users/scott/AppData/Local/Temp/claude/9519414f725d5b3e/1ad6458c-fdef-4ea9-acfc-295e30fb4711/scratchpad"
BLANK = 0.04


def train():
    meta = json.load(open(f"{S}/train48_meta.json")); lab = json.load(open(f"{S}/labels48_train_adrian.json"))
    cap = cv2.VideoCapture(D.U + D.FILMS["adrian"][0]); X, y = [], []
    for k, v in lab.items():
        cap.set(cv2.CAP_PROP_POS_MSEC, meta[int(k)]["t_ms"]); ok, fr = cap.read()
        cv = cell_vecs(D.clock_crop(fr, "adrian"))
        if v.startswith("."):
            X.append(cv[2][1]); y.append(v[1])
        else:
            X.append(cv[2][1]); y.append(v[0]); X.append(cv[3][1]); y.append(v[1])
    return np.array(X), np.array(y)


def read_cells(crop, X, y):
    """-> ('mss', seconds) | ('sst', tenths) | (None, None)"""
    cv = cell_vecs(crop)
    nn = lambda v: str(y[np.argmin(((X - v) ** 2).sum(axis=1))])
    if cv[2][0] < BLANK:
        return None, None
    if cv[3][0] >= BLANK:
        return "mss", int(nn(cv[2][1])) * 10 + int(nn(cv[3][1]))
    return "sst", int(nn(cv[2][1]))
