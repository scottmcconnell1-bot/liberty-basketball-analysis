"""Adrian board: fixed digit cells. cells 0..3; dot fixed between cell1 and cell2."""
import sys
sys.path.insert(0, r"C:/Users/scott/AppData/Local/Temp/claude/9519414f725d5b3e/1ad6458c-fdef-4ea9-acfc-295e30fb4711/scratchpad")
import digits48 as D
import cv2, numpy as np
D.FILMS["adrian"] = (D.FILMS["adrian"][0], D.FILMS["adrian"][1], (0.24, 0.80, 0.0, 0.28))
CELLS = [(28, 78), (92, 141), (182, 232), (247, 296)]
Y0, Y1 = 10, 82


def mask(crop):
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    m = ((hsv[..., 2] > 110) & (hsv[..., 1] > 90) & (hsv[..., 0] >= 5) & (hsv[..., 0] <= 40)).astype(np.uint8)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))


def cell_vecs(crop):
    m = mask(crop)
    out = []
    for x0, x1 in CELLS:
        g = m[Y0:Y1, x0:x1].astype(np.float32)
        out.append((g.mean(), cv2.resize(g, (12, 20), interpolation=cv2.INTER_AREA).ravel()))
    return out


def draw(crop):
    t = crop.copy()
    for x0, x1 in CELLS:
        cv2.rectangle(t, (x0, Y0), (x1, Y1), (0, 255, 0), 1)
    return t
