"""Goal-directed skeleton walk from digit toward a target tip."""
from pathlib import Path
import cv2
import numpy as np
from playbook_sheet_align import (
    analyze_sheet_image, find_court_bbox, _stroke_mask, _morph_skeleton,
    _svg_to_crop, _crop_to_svg, _poly_len_svg, classify_polyline_mark,
    _mid_raw_ink_fraction, _ink_mask_no_close,
)

def walk_toward(walkable, start, goal, max_steps=1500):
    ch, cw = walkable.shape[:2]
    sx, sy = start
    gx, gy = goal
    # snap start/goal to walkable
    def snap(x,y,r=25):
        best=None
        for yy in range(max(0,y-r), min(ch,y+r+1)):
            for xx in range(max(0,x-r), min(cw,x+r+1)):
                if walkable[yy,xx]:
                    d=(xx-x)**2+(yy-y)**2
                    if best is None or d<best[0]:
                        best=(d,xx,yy)
        return (best[1], best[2]) if best else None
    s = snap(*start); g = snap(*goal)
    if not s or not g:
        return []
    sx,sy = s; gx,gy = g
    visited = np.zeros_like(walkable, dtype=np.uint8)
    # Dijkstra-ish: prefer progress toward goal
    import heapq
    heap = [(0.0, 0.0, sx, sy, None)]  # (cost, dist_traveled, x, y, parent_key)
    parents = {}
    best_cost = { (sx,sy): 0.0 }
    found = None
    nbrs = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
    steps = 0
    while heap and steps < max_steps * 20:
        cost, dist, x, y, _ = heapq.heappop(heap)
        if (x,y) in parents and parents[(x,y)] is not None and best_cost.get((x,y), 1e9) < cost:
            continue
        if (x - gx)**2 + (y - gy)**2 <= 9:
            found = (x,y); break
        steps += 1
        for dx,dy in nbrs:
            nx,ny = x+dx, y+dy
            if nx<0 or ny<0 or nx>=cw or ny>=ch: continue
            if walkable[ny,nx]==0: continue
            step = (dx*dx+dy*dy)**0.5
            # heuristic: remaining distance
            remain = ((nx-gx)**2+(ny-gy)**2)**0.5
            ncost = dist + step + 0.15 * remain  # lightly guided
            # Actually use dist+step as g, remain as h
            gcost = dist + step
            fcost = gcost + remain
            key=(nx,ny)
            if gcost < best_cost.get(key, 1e18):
                best_cost[key]=gcost
                parents[key]=(x,y)
                heapq.heappush(heap, (fcost, gcost, nx, ny, key))
    if not found:
        # take closest reached
        if not best_cost:
            return []
        found = min(best_cost.keys(), key=lambda k: (k[0]-gx)**2+(k[1]-gy)**2)
    # reconstruct
    path=[found]
    cur=found
    while cur != (sx,sy):
        cur = parents.get(cur)
        if cur is None:
            break
        path.append(cur)
    path.append((sx,sy))
    path.reverse()
    return path

p = Path("uploads/bulk_imports/d125785a44474042b13589e9aadeca4f/page_0122.png")
pos = analyze_sheet_image(p)["positions"]
gray = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2GRAY)
x0,y0,x1,y1 = find_court_bbox(gray)
crop = gray[y0:y1, x0:x1]
ch,cw = crop.shape[:2]
stroke = _stroke_mask(crop)
skel = _morph_skeleton(stroke)
walkable = cv2.bitwise_or(skel, cv2.dilate(skel, np.ones((3,3),np.uint8),1))

o1 = _svg_to_crop(pos["o1"], cw, ch)
o2 = _svg_to_crop(pos["o2"], cw, ch)
elbow = _svg_to_crop({"x":296.4,"y":96.7}, cw, ch)
corner = _svg_to_crop({"x":422.4,"y":64.6}, cw, ch)

for name, a, b in (("dribble", o1, elbow), ("cut", o2, corner), ("pass", elbow, corner)):
    path = walk_toward(walkable, a, b)
    if len(path)<3:
        print(name, "FAIL", len(path)); continue
    svg=[_crop_to_svg(x,y,cw,ch) for x,y in path]
    if name=="dribble":
        svg[0]={"x":pos["o1"]["x"],"y":pos["o1"]["y"]}
        svg[-1]={"x":296.4,"y":96.7}
    elif name=="cut":
        svg[0]={"x":pos["o2"]["x"],"y":pos["o2"]["y"]}
        svg[-1]={"x":422.4,"y":64.6}
    plen=_poly_len_svg(svg)
    disp=((svg[-1]["x"]-svg[0]["x"])**2+(svg[-1]["y"]-svg[0]["y"])**2)**0.5
    kind=classify_polyline_mark(crop, svg)
    mid=_mid_raw_ink_fraction(crop, svg, svg[0], svg[-1])
    print(f"{name}: n={len(path)} len={plen:.1f} disp={disp:.1f} ratio={plen/max(disp,1):.2f} kind={kind} mid={mid:.2f}")

# Also try with raw closed less - use only raw dilated
raw=_ink_mask_no_close(crop)
walk2=cv2.dilate(raw, np.ones((3,3),np.uint8),1)
print("--- using raw dilate ---")
for name, a, b in (("dribble", o1, elbow), ("cut", o2, corner), ("pass", elbow, corner)):
    path = walk_toward(walk2, a, b)
    if len(path)<3:
        print(name, "FAIL", len(path)); continue
    svg=[_crop_to_svg(x,y,cw,ch) for x,y in path]
    plen=_poly_len_svg(svg)
    disp=((svg[-1]["x"]-svg[0]["x"])**2+(svg[-1]["y"]-svg[0]["y"])**2)**0.5
    kind=classify_polyline_mark(crop, svg)
    mid=_mid_raw_ink_fraction(crop, svg, svg[0], svg[-1])
    print(f"{name}: n={len(path)} len={plen:.1f} disp={disp:.1f} ratio={plen/max(disp,1):.2f} kind={kind} mid={mid:.2f}")
