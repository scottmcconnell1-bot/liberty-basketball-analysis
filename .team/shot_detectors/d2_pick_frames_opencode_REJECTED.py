"""D2 frame picker: build a 600-frame labelled training set for the ball detector.

Spec: .team/specs/22_d2_label_job_spec.md (VETTED, Muse AGREE).
Output (outside repo): C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_frames/
"""
import cv2
import json
import os
import random
import sys
from pathlib import Path

import numpy as np
from ultralytics import YOLO

REPO = Path("C:/Users/scott/Documents/liberty-basketball-analysis")
UPLOADS = REPO / "uploads"
OUT_DIR = Path("C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_frames")
BODD_PATH = Path("C:/Users/scott/AppData/Local/Temp/BODD_yolov8n_0001.pt")
V6_PATH = Path("C:/Users/scott/AppData/Local/Temp/ball_net_runs/v6/weights/best.pt")
HOLDOUT_PATH = REPO / ".team/specs/holdout_names.json"

FILMS = [
    ("LIBERTY_A_v_HSB_H1_20260809_221334", "LIBERTY_A_v_HSB_H1_20260809_221334.mp4"),
    ("LIBERTY_A_v_HSB_H_20260809_221334", "LIBERTY_A_v_HSB_H_20260809_221334.mp4"),
    ("LIBERTY_A_v_RIMROCK_H_20260809_221334", "LIBERTY_A_v_RIMROCK_H_20260809_221334.mp4"),
    ("LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334", "LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334.mp4"),
    ("LIBERTY_H_v_IDAHO_CITY_A_20260809_221334", "LIBERTY_H_v_IDAHO_CITY_A_20260809_221334.mp4"),
    ("LIBERTY_H_v_RIVERSTONE_A_20260809_221334", "LIBERTY_H_v_RIVERSTONE_A_20260809_221334.mp4"),
    ("LIBERTY_H_v_NOTUS_A_20260809_221334", "LIBERTY_H_v_NOTUS_A_20260809_221334.mp4"),
]

STRIDE = 25
BODD_CONF = 0.12
BODD_IMGSZ = 960
V6_CONF = 0.28
V6_IMGSZ = 640
CROP_X = 260
CROP_Y_UP = 200
CROP_Y_DOWN = 240
ZONE_H = 3.0   # * hoop_w
ZONE_UP = 4.0  # * hoop_w
ZONE_DOWN = 300
SEED = 42
TOTAL_TARGET = 600
NOTUS_A_HOLDOUT_MS = [232300, 606900, 981500, 1356100, 1730700, 2105300,
                      2479900, 2854500, 3229100, 3603700]
EXCLUSION_FRAMES = 5  # seconds * fps


def in_zone(cx, cy, hoop_x, hoop_y, hoop_w):
    if abs(cx - hoop_x) > ZONE_H * hoop_w:
        return False
    if cy < hoop_y - ZONE_UP * hoop_w:
        return False
    if cy > hoop_y + ZONE_DOWN:
        return False
    return True


def median_hoop(boxes):
    xs = [b[0] for b in boxes]
    ys = [b[1] for b in boxes]
    ws = [b[2] for b in boxes]
    hs = [b[3] for b in boxes]
    return (float(np.median(xs)), float(np.median(ys)),
            float(np.median(ws)), float(np.median(hs)))


def run_bodd(model, frame):
    res = model(frame, conf=BODD_CONF, imgsz=BODD_IMGSZ, verbose=False)
    boxes = []
    for r in res:
        for b in r.boxes:
            cls = int(b.cls[0])
            name = model.names[cls]
            if name == "hoop":
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                boxes.append(((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1))
    return boxes


def run_v6(model, crop):
    res = model(crop, conf=V6_CONF, imgsz=V6_IMGSZ, verbose=False)
    out = []
    for r in res:
        for b in r.boxes:
            cls = int(b.cls[0])
            name = model.names[cls]
            if name == "basketball":
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                out.append(((x1 + x2) / 2, (y1 + y2) / 2))
    return out


def crop_box(hoop_x, hoop_y, fw, fh):
    x0 = max(0, int(hoop_x) - CROP_X)
    x1 = min(fw, int(hoop_x) + CROP_X)
    y0 = max(0, int(hoop_y) - CROP_Y_UP)
    y1 = min(fh, int(hoop_y) + CROP_Y_DOWN)
    return x0, y0, x1, y1


def process_film(stem, filename, bodd, v6):
    path = UPLOADS / filename
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"  {stem}: fps={fps} total={total}", flush=True)

    # holdout exclusion for Notus A
    excluded = set()
    if "NOTUS_A_" in stem and "NOTUS_A1" not in stem:
        for ms in NOTUS_A_HOLDOUT_MS:
            hf = int(round(ms * fps / 1000.0))
            for d in range(-EXCLUSION_FRAMES * int(fps), EXCLUSION_FRAMES * int(fps) + 1):
                excluded.add(hf + d)

    # Pass 1: stride
    moments = []  # list of (frame_idx, hoop_x, hoop_y, hoop_w, hoop_h)
    frame_idx = 0
    while frame_idx < total:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ok, frame = cap.read()
        if not ok:
            frame_idx += STRIDE
            continue
        hboxes = run_bodd(bodd, frame)
        if hboxes:
            hx, hy, hw, hh = median_hoop(hboxes)
            fh, fw = frame.shape[:2]
            x0, y0, x1, y1 = crop_box(hx, hy, fw, fh)
            crop = frame[y0:y1, x0:x1]
            balls = run_v6(v6, crop)
            # adjust ball coords to full frame
            has_zone = False
            for (cx, cy) in balls:
                if in_zone(cx + x0, cy + y0, hx, hy, hw):
                    has_zone = True
                    break
            if has_zone:
                moments.append((frame_idx, hx, hy, hw, hh))
        frame_idx += STRIDE

    print(f"    pass1 moments: {len(moments)}", flush=True)

    # Pass 2: per-moment windows
    candidates = []  # list of dicts: frame_number, status (SEEN/LOST), hoop, crop_box
    # track seen/lost per moment
    for (mframe, hx, hy, hw, hh) in moments:
        start = max(0, mframe - 10)
        end = min(total, mframe + 31)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        last_seen_offset = None  # offset within window (0..)
        # read sequentially
        frames_list = []
        for i in range(start, end):
            ok, frame = cap.read()
            if not ok:
                break
            frames_list.append((i, frame))
        # classify
        # first pass: determine SEEN frames
        seen_flags = []
        for (i, frame) in frames_list:
            fh, fw = frame.shape[:2]
            x0, y0, x1, y1 = crop_box(hx, hy, fw, fh)
            crop = frame[y0:y1, x0:x1]
            balls = run_v6(v6, crop)
            is_seen = False
            for (cx, cy) in balls:
                if in_zone(cx + x0, cy + y0, hx, hy, hw):
                    is_seen = True
                    break
            seen_flags.append(is_seen)

        # LOST = one of first 8 frames after last SEEN with no ball in zone
        # identify lost frames
        last_seen_idx = None
        for idx, sf in enumerate(seen_flags):
            if sf:
                last_seen_idx = idx
        # mark lost: frames after a seen where not seen and within 8 frames of last seen
        lost_flags = [False] * len(seen_flags)
        # compute per-frame: a frame is LOST if not seen and there is a seen frame within previous 8 and no seen in between
        # simpler: for each idx not seen, if exists seen at j with j < idx <= j+8 and no seen in (j, idx): lost
        for idx in range(len(seen_flags)):
            if seen_flags[idx]:
                continue
            # find nearest previous seen
            prev_seen = None
            for j in range(idx - 1, max(-1, idx - 9), -1):
                if j >= 0 and seen_flags[j]:
                    prev_seen = j
                    break
            if prev_seen is not None:
                # ensure no seen between prev_seen and idx
                ok_lost = True
                for k in range(prev_seen + 1, idx):
                    if seen_flags[k]:
                        ok_lost = False
                        break
                if ok_lost and (idx - prev_seen) <= 8:
                    lost_flags[idx] = True

        for (idx, (i, frame)) in enumerate(frames_list):
            if i in excluded:
                continue
            if not (seen_flags[idx] or lost_flags[idx]):
                continue
            fh, fw = frame.shape[:2]
            x0, y0, x1, y1 = crop_box(hx, hy, fw, fh)
            status = "SEEN" if seen_flags[idx] else "LOST"
            candidates.append({
                "film_stem": stem,
                "film": filename,
                "frame_number": i,
                "time_seconds": round(i / fps, 4),
                "crop_box": [x0, y0, x1, y1],
                "status": status,
                "hoop": [float(hx), float(hy), float(hw), float(hh)],
            })
    cap.release()
    return fps, total, candidates


def pick_frames(all_candidates, quotas):
    """Pick per-film quota frames: half SEEN half LOST, >=3 frames apart within window,
    seeded random. Returns list of candidate dicts."""
    rng = random.Random(SEED)
    # group by film
    by_film = {}
    for c in all_candidates:
        by_film.setdefault(c["film_stem"], []).append(c)

    picked = []
    for stem, quota in quotas.items():
        cands = by_film.get(stem, [])
        seen = [c for c in cands if c["status"] == "SEEN"]
        lost = [c for c in cands if c["status"] == "LOST"]
        half = quota // 2
        # if short, fill from other
        n_seen_target = min(half, len(seen))
        n_lost_target = min(quota - n_seen_target, len(lost))
        # adjust if one short
        if n_seen_target + n_lost_target < quota:
            # fill from whichever has more
            rem = quota - (n_seen_target + n_lost_target)
            # try seen
            extra_seen = min(rem, len(seen) - n_seen_target)
            n_seen_target += extra_seen
            rem -= extra_seen
            extra_lost = min(rem, len(lost) - n_lost_target)
            n_lost_target += extra_lost
            rem -= extra_lost
            # if still short, take any remaining candidates
            if rem > 0:
                others = [c for c in cands if c not in seen[:n_seen_target] and c not in lost[:n_lost_target]]
                # just take first rem
                pass

        # sample with >=3 frame separation within each status group, then combine
        def sample_group(group, n):
            if n <= 0 or not group:
                return []
            # sort by frame
            g = sorted(group, key=lambda c: c["frame_number"])
            chosen = []
            # greedy with spacing: pick uniformly at random among eligible
            remaining = list(g)
            while len(chosen) < n and remaining:
                rng.shuffle(remaining)
                # pick first that is >=3 away from all chosen
                progress = False
                for c in list(remaining):
                    if all(abs(c["frame_number"] - cc["frame_number"]) >= 3 for cc in chosen):
                        chosen.append(c)
                        remaining.remove(c)
                        progress = True
                        if len(chosen) >= n:
                            break
                if not progress:
                    # relax: take any
                    if remaining:
                        chosen.append(remaining.pop(0))
                    else:
                        break
            return chosen

        chosen_seen = sample_group(seen, n_seen_target)
        chosen_lost = sample_group(lost, n_lost_target)
        chosen = chosen_seen + chosen_lost
        # if short, top up from any remaining candidates
        if len(chosen) < quota:
            remaining_all = [c for c in cands if c not in chosen]
            rng.shuffle(remaining_all)
            for c in remaining_all:
                if len(chosen) >= quota:
                    break
                chosen.append(c)
        # if too many, trim
        chosen = chosen[:quota]
        picked.extend(chosen)
    return picked


def compute_quotas(yields):
    # yields: dict stem -> count of candidates
    # base 85/86: first 5 films 86, last 2 85? spec: 600/7=85 rem 5 -> first 5 get 86
    film_order = [f[0] for f in FILMS]
    base = {film_order[i]: (86 if i < 5 else 85) for i in range(7)}
    # shortfall redistribution
    # if a film yields fewer than quota, take all, redistribute shortfall
    quotas = dict(base)
    # adjust for yields
    # First pass: cap quotas at yields
    for s in film_order:
        if yields.get(s, 0) < quotas[s]:
            quotas[s] = yields.get(s, 0)
    # redistribute shortfall
    total_now = sum(quotas.values())
    shortfall = TOTAL_TARGET - total_now
    if shortfall > 0:
        # distribute to films that have spare capacity, round-robin
        # capacity = yields - quotas
        changed = True
        while shortfall > 0 and changed:
            changed = False
            for s in film_order:
                cap = yields.get(s, 0) - quotas[s]
                if cap > 0 and shortfall > 0:
                    quotas[s] += 1
                    shortfall -= 1
                    changed = True
    # if still short (not enough candidates), leave as is
    # trim if over (shouldn't happen)
    return quotas


def make_label_html():
    return r'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>D2 Label</title>
<style>
body{font-family:sans-serif;margin:20px;}
#img{max-width:90vw;max-height:60vh;border:1px solid #ccc;}
button{min-height:48px;min-width:96px;margin:6px;font-size:16px;}
#progress{font-size:18px;margin:10px 0;}
#boxinfo{margin:10px 0;}
canvas{cursor:crosshair;border:1px solid #999;}
</style></head><body>
<h2>D2 Ball Labelling</h2>
<div id="progress"></div>
<img id="img" src="" alt="crop"/>
<div>
  <button id="noball">No ball</button>
  <button id="back">Back</button>
  <button id="next">Next</button>
  <button id="export">Export labels</button>
  <button id="clear">Clear box</button>
</div>
<div id="boxinfo">Box: none</div>
<script>
let frames=[]; let labels={}; let idx=0; let box=null; let dragging=false; let sx=0,sy=0;
const img=document.getElementById('img');
async function load(){
  const r=await fetch('frames.json'); frames=await r.json();
  const saved=localStorage.getItem('d2_labels');
  if(saved){try{labels=JSON.parse(saved);}catch(e){}}
  show();
}
function show(){
  const f=frames[idx];
  img.src=f.frame? f.frame : (f.film+'_fr'+String(f.frame_number).padStart(6,'0')+'.jpg');
  // build filename
  img.src=f.film.replace('.mp4','')+'_fr'+String(f.frame_number).padStart(6,'0')+'.jpg';
  document.getElementById('progress').textContent=(idx+1)+' of '+frames.length;
  const l=labels[img.src];
  if(l && l.boxes && l.boxes.length){ box=l.boxes[0]; document.getElementById('boxinfo').textContent='Box: '+JSON.stringify(box);}
  else { box=null; document.getElementById('boxinfo').textContent='Box: none';}
}
function saveLabel(){
  const f=frames[idx];
  const name=f.film.replace('.mp4','')+'_fr'+String(f.frame_number).padStart(6,'0')+'.jpg';
  const boxes = box? [box] : [];
  labels[name]={frame:name,boxes:boxes,class:'basketball'};
  localStorage.setItem('d2_labels',JSON.stringify(labels));
}
img.addEventListener('mousedown',e=>{
  const rect=img.getBoundingClientRect();
  const scaleX=img.naturalWidth/rect.width;
  const scaleY=img.naturalHeight/rect.height;
  sx=(e.clientX-rect.left)*scaleX; sy=(e.clientY-rect.top)*scaleY;
  dragging=true; box=[sx,sy,0,0];
});
img.addEventListener('mousemove',e=>{
  if(!dragging) return;
  const rect=img.getBoundingClientRect();
  const scaleX=img.naturalWidth/rect.width;
  const scaleY=img.naturalHeight/rect.height;
  const cx=(e.clientX-rect.left)*scaleX; const cy=(e.clientY-rect.top)*scaleY;
  box=[Math.min(sx,cx),Math.min(sy,cy),Math.abs(cx-sx),Math.abs(cy-sy)];
});
img.addEventListener('mouseup',()=>{ dragging=false; if(box){ document.getElementById('boxinfo').textContent='Box: '+JSON.stringify(box.map(v=>Math.round(v))); } saveLabel();});
document.getElementById('noball').onclick=()=>{ box=null; saveLabel(); document.getElementById('boxinfo').textContent='Box: none (no ball)';};
document.getElementById('clear').onclick=()=>{ box=null; saveLabel(); document.getElementById('boxinfo').textContent='Box: none';};
document.getElementById('back').onclick=()=>{ if(idx>0){saveLabel(); idx--; show();}};
document.getElementById('next').onclick=()=>{ if(idx<frames.length-1){saveLabel(); idx++; show();}};
document.getElementById('export').onclick=()=>{
  const arr=frames.map(f=>{
    const name=f.film.replace('.mp4','')+'_fr'+String(f.frame_number).padStart(6,'0')+'.jpg';
    const l=labels[name];
    const boxes = (l && l.boxes) ? l.boxes : [];
    return {frame:name, boxes:boxes, class:'basketball'};
  });
  const blob=new Blob([JSON.stringify(arr,null,2)],{type:'application/json'});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='labels.json'; a.click();
  alert('Move labels.json into the d2_frames folder.');
};
load();
</script></body></html>'''


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    bodd = YOLO(str(BODD_PATH))
    v6 = YOLO(str(V6_PATH))

    all_candidates = []
    yields = {}
    for stem, filename in FILMS:
        print(f"Processing {stem}...", flush=True)
        fps, total, cands = process_film(stem, filename, bodd, v6)
        all_candidates.extend(cands)
        yields[stem] = len(cands)
        print(f"  candidates: {len(cands)}", flush=True)

    quotas = compute_quotas(yields)
    print("Quotas:", quotas, flush=True)
    print("Total candidates:", len(all_candidates), flush=True)

    picked = pick_frames(all_candidates, quotas)
    print("Picked:", len(picked), flush=True)

    # save crops + frames.json
    frames_meta = []
    for c in picked:
        src_path = UPLOADS / c["film"]
        cap = cv2.VideoCapture(str(src_path))
        cap.set(cv2.CAP_PROP_POS_FRAMES, c["frame_number"])
        ok, frame = cap.read()
        cap.release()
        if not ok:
            print("  WARN: could not read frame", c["film"], c["frame_number"], flush=True)
            continue
        x0, y0, x1, y1 = c["crop_box"]
        crop = frame[y0:y1, x0:x1]
        fname = c["film"].replace(".mp4", "") + f"_fr{c['frame_number']:06d}.jpg"
        cv2.imwrite(str(OUT_DIR / fname), crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
        frames_meta.append({
            "film": c["film"],
            "frame_number": c["frame_number"],
            "time_seconds": c["time_seconds"],
            "crop_box": c["crop_box"],
        })

    with open(OUT_DIR / "frames.json", "w") as f:
        json.dump(frames_meta, f, indent=2)

    with open(OUT_DIR / "label.html", "w") as f:
        f.write(make_label_html())

    print(f"Done. {len(frames_meta)} frames written to {OUT_DIR}", flush=True)


if __name__ == "__main__":
    main()
