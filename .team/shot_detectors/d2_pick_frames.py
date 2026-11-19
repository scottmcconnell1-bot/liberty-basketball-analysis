"""D2 frame picker: pick 600 frames from 7 untagged films for Scott to label.

Spec: .team/specs/22_d2_label_job_spec.md (v2, VETTED by Claude Code, Muse AGREE).
Rewritten 2026-11-01 by Claude Code (Scott: "Yes" to fixing OpenCode's rejected version,
kept as d2_pick_frames_opencode_REJECTED.py). Nothing here trains a model or reads ground truth.

Output (outside the repo, never committed or published):
    C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_frames/
        <film stem>_frNNNNNN.jpg   600 crops, native size, JPEG quality 90
        frames.json                600 entries: film, frame_number, time_seconds, crop_box
        label.html                 labelling page; frames are embedded, so it opens from the folder
        pick_log.json              why each frame was picked (SEEN / LOST, hoop, ball) for the checks
"""
import json
import random
import sys
from pathlib import Path

import numpy as np

REPO = Path("C:/Users/scott/Documents/liberty-basketball-analysis")
UPLOADS = REPO / "uploads"
OUT_DIR = Path("C:/Users/scott/Documents/Liberty_Shot_Outputs/d2_frames")
BODD_PATH = Path("C:/Users/scott/AppData/Local/Temp/BODD_yolov8n_0001.pt")
V6_PATH = Path("C:/Users/scott/AppData/Local/Temp/ball_net_runs/v6/weights/best.pt")
HOLDOUT_PATH = REPO / ".team/specs/holdout_names.json"

# Spec section 1: exactly these 7 films, in this order (the first 5 get 86 frames).
FILMS = [
    "LIBERTY_A_v_HSB_H1_20260809_221334.mp4",
    "LIBERTY_A_v_HSB_H_20260809_221334.mp4",
    "LIBERTY_A_v_RIMROCK_H_20260809_221334.mp4",
    "LIBERTY_H_v_GARDEN_VALLEY_A_20260809_221334.mp4",
    "LIBERTY_H_v_IDAHO_CITY_A_20260809_221334.mp4",
    "LIBERTY_H_v_RIVERSTONE_A_20260809_221334.mp4",
    "LIBERTY_H_v_NOTUS_A_20260809_221334.mp4",
]
HOLDOUT_FILM = "LIBERTY_H_v_NOTUS_A_20260809_221334.mp4"
# Never read (build set, holdout source, tagged unseen check).
EXCLUDED_FILMS = {"LIBERTY_H_v_NOTUS_A1_20260809_221334.mp4", "nfhs_gam0a66d85e12.mp4"}

STRIDE = 25                 # spec 2
BODD_CONF, BODD_IMGSZ = 0.12, 960
V6_CONF, V6_IMGSZ = 0.28, 640   # spec 3 (keep_ball_detections.py line 24)
CROP_LEFT_RIGHT, CROP_ABOVE, CROP_BELOW = 260, 200, 240
ZONE_HOOP_WIDTHS_H, ZONE_ABOVE_HOOP_WIDTHS, ZONE_BELOW_PX = 3.0, 4.0, 300
WINDOW_BEFORE, WINDOW_AFTER = 10, 30    # pass 2 reads moment-10 .. moment+30
LOST_FRAMES = 8
MIN_GAP = 3
HOLDOUT_SECONDS = 5
SEED = 42
TOTAL_TARGET = 600


def stem(film):
    return film[:-4] if film.endswith(".mp4") else film


def crop_name(film, frame_number):
    return f"{stem(film)}_fr{int(frame_number):06d}.jpg"


# --------------------------------------------------------------------------- geometry
def in_zone(x, y, hoop_x, hoop_y, hoop_w):
    """D1 near-hoop zone, full-frame coordinates (keep_ball_detections.py 166-173)."""
    if abs(x - hoop_x) > ZONE_HOOP_WIDTHS_H * hoop_w:
        return False
    return hoop_y - ZONE_ABOVE_HOOP_WIDTHS * hoop_w <= y <= hoop_y + ZONE_BELOW_PX


def crop_box(hoop_x, hoop_y, frame_w, frame_h):
    """D1 crop, clamped exactly as keep_ball_detections.crop_bounds (lines 191-199)."""
    x0 = int(max(0, hoop_x - CROP_LEFT_RIGHT))
    y0 = int(max(0, hoop_y - CROP_ABOVE))
    x1 = int(min(frame_w, hoop_x + CROP_LEFT_RIGHT))
    y1 = int(min(frame_h, hoop_y + CROP_BELOW))
    return x0, y0, x1, y1


def median_hoop(boxes):
    """Median x, y, w, h of every hoop box in one frame (spec 2 step 3)."""
    arr = np.array(boxes, dtype=float)
    return tuple(float(v) for v in np.median(arr, axis=0))


# --------------------------------------------------------------------------- holdout
def holdout_frames(fps, holdout_path=HOLDOUT_PATH, film=HOLDOUT_FILM):
    """Holdout frame numbers for one film, read from holdout_names.json (binding note, spec 1):
    round(ms x fps / 1000) with the film's own fps. Entries are [tag, name, ms]."""
    rows = json.loads(Path(holdout_path).read_text(encoding="utf-8"))
    key = stem(film)
    frames = [int(round(ms * fps / 1000.0)) for tag, _name, ms in rows if tag.endswith(key)]
    return sorted(frames)


def near_holdout(frame_number, holdout, fps):
    """True when the frame is NOT more than 5 x fps frames from a holdout frame."""
    limit = HOLDOUT_SECONDS * fps
    return any(abs(frame_number - h) <= limit for h in holdout)


# --------------------------------------------------------------------------- SEEN / LOST
def classify_window(seen_flags):
    """Spec 3 pass 2 step 3. SEEN = ball in the zone. LOST = one of the first 8 frames after
    the LAST SEEN frame of the window (none of them can be SEEN, since it is the last).
    Returns a list of (index, status, last_seen_index) for the SEEN and LOST frames."""
    seen = [i for i, s in enumerate(seen_flags) if s]
    out = [(i, "SEEN", i) for i in seen]
    if seen:
        last = seen[-1]
        for i in range(last + 1, min(len(seen_flags), last + 1 + LOST_FRAMES)):
            out.append((i, "LOST", last))
    return out


# --------------------------------------------------------------------------- models
def run_bodd(model, frame):
    pred = model.predict(frame, conf=BODD_CONF, imgsz=BODD_IMGSZ, verbose=False)[0]
    boxes = []
    if pred.boxes is None:
        return boxes
    for b in pred.boxes:
        if model.names[int(b.cls[0])] == "hoop":
            x1, y1, x2, y2 = [float(v) for v in b.xyxy[0]]
            boxes.append(((x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1))
    return boxes


def zone_ball(model, frame, hoop):
    """Run v6 on the D1 crop; return the first ball centre (full frame) inside the zone, or None."""
    hx, hy, hw, _hh = hoop
    fh, fw = frame.shape[:2]
    x0, y0, x1, y1 = crop_box(hx, hy, fw, fh)
    pred = model.predict(frame[y0:y1, x0:x1], conf=V6_CONF, imgsz=V6_IMGSZ, verbose=False)[0]
    if pred.boxes is None:
        return None
    for b in pred.boxes:
        if model.names[int(b.cls[0])] != "basketball":
            continue
        bx1, by1, bx2, by2 = [float(v) for v in b.xyxy[0]]
        cx, cy = (bx1 + bx2) / 2 + x0, (by1 + by2) / 2 + y0   # crop -> full frame
        if in_zone(cx, cy, hx, hy, hw):
            return [round(cx, 1), round(cy, 1)]
    return None


# --------------------------------------------------------------------------- per film
def process_film(film, bodd, v6, log=print):
    import cv2

    cap = cv2.VideoCapture(str(UPLOADS / film))
    if not cap.isOpened():
        raise SystemExit(f"STOP: cannot open {film}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fw, fh = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    holdout = holdout_frames(fps) if film == HOLDOUT_FILM else []
    log(f"  {film}: fps={fps} total={total} holdout={holdout}")

    # Pass 1: every 25th frame (0, 25, 50, ...), read sequentially; grab() skips the 24 between.
    moments = []
    for idx in range(0, total, STRIDE):
        ok, frame = cap.read()
        if not ok:
            break
        hoops = run_bodd(bodd, frame)
        if hoops:
            hoop = median_hoop(hoops)
            if zone_ball(v6, frame, hoop) is not None:
                moments.append((idx, hoop))
        for _ in range(STRIDE - 1):
            if not cap.grab():
                break
    log(f"    pass 1 moments: {len(moments)}")

    # Pass 2: one seek to moment-10, then sequential reads to moment+30, same hoop, no smoothing.
    cands, used = [], set()
    for m, hoop in moments:
        start, end = max(0, m - WINDOW_BEFORE), min(total - 1, m + WINDOW_AFTER)
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        flags, balls = [], []
        for _ in range(start, end + 1):
            ok, frame = cap.read()
            if not ok:
                break
            ball = zone_ball(v6, frame, hoop)
            flags.append(ball is not None)
            balls.append(ball)
        box = list(crop_box(hoop[0], hoop[1], fw, fh))
        for i, status, last in classify_window(flags):
            fn = start + i
            if fn in used or (holdout and near_holdout(fn, holdout, fps)):
                continue   # overlapping windows: first window wins
            used.add(fn)
            cands.append({
                "film": film, "frame_number": fn, "time_seconds": round(fn / fps, 4),
                "crop_box": box, "status": status, "window_start": start,
                "seen_frame": start + last, "hoop": [round(v, 2) for v in hoop],
                "ball": balls[i] if status == "SEEN" else balls[last],
            })
    cap.release()
    log(f"    candidates: {len(cands)} "
        f"(SEEN {sum(c['status'] == 'SEEN' for c in cands)}, LOST {sum(c['status'] == 'LOST' for c in cands)})")
    return fps, cands


# --------------------------------------------------------------------------- quotas + pick
def base_quotas():
    """600 / 7 = 85 rem 5: the first 5 films get 86 (spec 3)."""
    per, rem = divmod(TOTAL_TARGET, len(FILMS))
    return {f: per + (1 if i < rem else 0) for i, f in enumerate(FILMS)}


def compute_quotas(yields):
    """Spec 3: a film short of its quota gives all it has; the shortfall is spread evenly
    over films that still have spare frames (round robin in film order)."""
    quotas = {f: min(q, yields.get(f, 0)) for f, q in base_quotas().items()}
    short = TOTAL_TARGET - sum(quotas.values())
    while short > 0:
        spare = [f for f in FILMS if yields.get(f, 0) > quotas[f]]
        if not spare:
            break
        for f in spare:
            if short == 0:
                break
            quotas[f] += 1
            short -= 1
    return quotas


def pick_film(cands, quota, rng):
    """Half SEEN, half LOST (fill from the other kind if one runs short), every picked frame
    at least 3 frames from every other picked frame of the film, seeded sampling."""
    def take(pool, n, chosen):
        pool = sorted(pool, key=lambda c: c["frame_number"])
        rng.shuffle(pool)
        got = []
        for c in pool:
            if len(got) >= n:
                break
            if all(abs(c["frame_number"] - o) >= MIN_GAP for o in chosen):
                got.append(c)
                chosen.add(c["frame_number"])
        return got

    seen = [c for c in cands if c["status"] == "SEEN"]
    lost = [c for c in cands if c["status"] == "LOST"]
    chosen = set()
    want_seen = quota // 2
    got = take(seen, want_seen, chosen)
    got += take(lost, quota - len(got), chosen)
    if len(got) < quota:   # LOST ran short: fill from SEEN
        rest = [c for c in seen if c["frame_number"] not in chosen]
        got += take(rest, quota - len(got), chosen)
    return sorted(got, key=lambda c: c["frame_number"])


def pick_frames(all_cands, quotas):
    rng = random.Random(SEED)
    picked = []
    for film in FILMS:
        film_cands = [c for c in all_cands if c["film"] == film]
        got = pick_film(film_cands, quotas.get(film, 0), rng)
        if len(got) != quotas.get(film, 0):
            raise SystemExit(f"STOP: {film} gave {len(got)} frames 3 apart, quota {quotas.get(film)}")
        picked += got
    return picked


# --------------------------------------------------------------------------- spec 6 checks
def verify(picked, quotas, fps_by_film, holdout, repick=None):
    """The 8 checks of spec section 6 (+ the 3-frame gap). Returns a list of failures."""
    bad = []
    films = [c["film"] for c in picked]
    # 1 + 7: only the 7 films, none of the excluded ones
    for f in set(films):
        if f not in FILMS or f in EXCLUDED_FILMS:
            bad.append(f"1/7 film not allowed: {f}")
    # 2: Notus A frames more than 5 x fps from every holdout frame
    if HOLDOUT_FILM in films and len(holdout) != 10:
        bad.append(f"2 expected 10 holdout frames, got {len(holdout)}")
    for c in picked:
        if c["film"] == HOLDOUT_FILM and near_holdout(c["frame_number"], holdout, fps_by_film[HOLDOUT_FILM]):
            bad.append(f"2 holdout neighbour: {c['frame_number']}")
    # 3: exactly 600
    if len(picked) != TOTAL_TARGET:
        bad.append(f"3 picked {len(picked)}, need {TOTAL_TARGET}")
    # 4: same seed, same list
    if repick is not None:
        key = lambda cs: [(c["film"], c["frame_number"], tuple(c["crop_box"])) for c in cs]
        if key(picked) != key(repick):
            bad.append("4 seed 42 run twice gave different lists")
    # 5: per-film counts match the quota rule, quotas sum to 600
    if sum(quotas.values()) != TOTAL_TARGET:
        bad.append(f"5 quotas sum to {sum(quotas.values())}")
    for f in FILMS:
        if films.count(f) != quotas.get(f, 0):
            bad.append(f"5 {f}: {films.count(f)} picked, quota {quotas.get(f, 0)}")
    for c in picked:
        hx, hy, hw, _ = c["hoop"]
        # 6: a v6 ball in the D1 zone in the moment it was picked (SEEN), or the LOST tail
        if c["status"] == "SEEN" and not (c["ball"] and in_zone(c["ball"][0], c["ball"][1], hx, hy, hw)):
            bad.append(f"6 SEEN without a zone ball: {c['film']} {c['frame_number']}")
        # 8: every LOST frame is 1..8 frames after a SEEN frame that had a zone ball
        if c["status"] == "LOST":
            gap = c["frame_number"] - c["seen_frame"]
            if not (1 <= gap <= LOST_FRAMES) or not (c["ball"] and in_zone(c["ball"][0], c["ball"][1], hx, hy, hw)):
                bad.append(f"8 LOST not 1-8 after a SEEN: {c['film']} {c['frame_number']}")
        if c["status"] not in ("SEEN", "LOST"):
            bad.append(f"6 unknown status {c['status']}")
    # 3-frame gap within a film
    for f in FILMS:
        fr = sorted(c["frame_number"] for c in picked if c["film"] == f)
        if any(b - a < MIN_GAP for a, b in zip(fr, fr[1:])):
            bad.append(f"gap: {f} has frames closer than {MIN_GAP}")
    return bad


# --------------------------------------------------------------------------- page
LABEL_PAGE = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>D2 Ball Labels</title>
<style>
body{font-family:system-ui,sans-serif;margin:16px;background:#fff;color:#111}
#stage{position:relative;display:inline-block;touch-action:none;user-select:none;-webkit-user-select:none}
#img{display:block;max-width:calc(100vw - 32px);max-height:65vh;border:1px solid #888;cursor:crosshair}
#box{position:absolute;border:2px solid #e00;pointer-events:none;display:none}
button{min-height:48px;min-width:96px;margin:6px 6px 0 0;font-size:16px}
#progress{font-size:20px;margin:8px 0}
#state{margin:8px 0;font-size:16px}
.help{color:#555;font-size:14px}
</style></head><body>
<div id="progress"></div>
<div id="stage"><img id="img" alt="crop" draggable="false"><div id="box"></div></div>
<div id="state"></div>
<div>
  <button id="back">&larr; Back</button><button id="next">Next &rarr;</button>
  <button id="noball">No ball</button><button id="clear">Clear</button>
  <button id="export">Export labels</button>
</div>
<p class="help">Drag a box around the ball, or press No ball. Left/Right arrow keys = Back/Next.
Labels are kept in this browser. Export saves labels.json to Downloads; move it into the d2_frames folder.</p>
<script>
const FRAMES = __FRAMES__;
const KEY = 'd2_labels_v2';
let labels = {};
try { labels = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { labels = {}; }
let idx = 0, drag = null;
const img = document.getElementById('img'), boxEl = document.getElementById('box');
const name = (f) => f.film.replace(/\.mp4$/, '') + '_fr' + String(f.frame_number).padStart(6, '0') + '.jpg';
function store() { try { localStorage.setItem(KEY, JSON.stringify(labels)); } catch (e) {} }
function done() { return FRAMES.filter((f) => labels[name(f)]).length; }
function drawBox(b) {
  if (!b || !img.naturalWidth) { boxEl.style.display = 'none'; return; }
  const s = img.clientWidth / img.naturalWidth;
  Object.assign(boxEl.style, { display: 'block', left: b[0] * s + 'px', top: b[1] * s + 'px', width: b[2] * s + 'px', height: b[3] * s + 'px' });
}
function show() {
  const n = name(FRAMES[idx]), l = labels[n];
  img.src = n;
  document.getElementById('progress').textContent = (idx + 1) + ' of ' + FRAMES.length + '  (labelled ' + done() + ')';
  document.getElementById('state').textContent = !l ? 'Not labelled yet' : l.boxes.length ? 'Ball box: ' + l.boxes[0].join(', ') : 'No ball';
  drawBox(l && l.boxes[0]);
}
img.onload = () => { const l = labels[name(FRAMES[idx])]; drawBox(l && l.boxes[0]); };
function pt(e) {
  const r = img.getBoundingClientRect(), s = img.naturalWidth / r.width;
  return [Math.max(0, Math.min(img.naturalWidth, (e.clientX - r.left) * s)), Math.max(0, Math.min(img.naturalHeight, (e.clientY - r.top) * s))];
}
img.addEventListener('pointerdown', (e) => { e.preventDefault(); img.setPointerCapture(e.pointerId); drag = pt(e); });
img.addEventListener('pointermove', (e) => {
  if (!drag) return; const p = pt(e);
  drawBox([Math.min(drag[0], p[0]), Math.min(drag[1], p[1]), Math.abs(p[0] - drag[0]), Math.abs(p[1] - drag[1])]);
});
img.addEventListener('pointerup', (e) => {
  if (!drag) return; const p = pt(e), a = drag; drag = null;
  const b = [Math.min(a[0], p[0]), Math.min(a[1], p[1]), Math.abs(p[0] - a[0]), Math.abs(p[1] - a[1])].map(Math.round);
  if (b[2] < 3 || b[3] < 3) { show(); return; }   // a tap, not a box
  labels[name(FRAMES[idx])] = { boxes: [b] }; store(); show();
});
img.addEventListener('pointercancel', () => { drag = null; show(); });
function go(d) { const n = idx + d; if (n >= 0 && n < FRAMES.length) { idx = n; show(); } }
document.getElementById('back').onclick = () => go(-1);
document.getElementById('next').onclick = () => go(1);
document.getElementById('noball').onclick = () => { labels[name(FRAMES[idx])] = { boxes: [] }; store(); show(); };
document.getElementById('clear').onclick = () => { delete labels[name(FRAMES[idx])]; store(); show(); };
document.addEventListener('keydown', (e) => { if (e.key === 'ArrowLeft') go(-1); if (e.key === 'ArrowRight') go(1); });
document.getElementById('export').onclick = () => {
  const out = FRAMES.filter((f) => labels[name(f)]).map((f) => ({ frame: name(f), boxes: labels[name(f)].boxes, class: 'basketball' }));
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 2)], { type: 'application/json' }));
  a.download = 'labels.json'; document.body.appendChild(a); a.click(); a.remove();
  alert(out.length + ' of ' + FRAMES.length + ' frames labelled and exported (unlabelled frames are left out).\n' +
        'labels.json is in your Downloads folder: move it into the d2_frames folder.');
};
show();
</script></body></html>
"""


def make_label_html(frames_meta):
    """Frames are embedded in the page: a page opened from a folder (file://) cannot fetch
    frames.json in Chrome (CORS), which is why OpenCode's page loaded blank."""
    data = json.dumps(frames_meta).replace("</", "<\\/")
    return LABEL_PAGE.replace("__FRAMES__", data)


# --------------------------------------------------------------------------- main
def save_crops(picked, out_dir):
    """Re-read each picked frame the way pass 2 read it (seek to the window start, then
    sequential reads) so the saved crop is the frame that was classified."""
    import cv2

    for film in FILMS:
        rows = sorted((c for c in picked if c["film"] == film), key=lambda c: c["frame_number"])
        if not rows:
            continue
        cap = cv2.VideoCapture(str(UPLOADS / film))
        by_window = {}
        for c in rows:
            by_window.setdefault(c["window_start"], []).append(c)
        for start, cs in sorted(by_window.items()):
            cap.set(cv2.CAP_PROP_POS_FRAMES, start)
            want = {c["frame_number"]: c for c in cs}
            for fn in range(start, max(want) + 1):
                ok, frame = cap.read()
                if not ok:
                    raise SystemExit(f"STOP: cannot read {film} frame {fn}")
                if fn in want:
                    x0, y0, x1, y1 = want[fn]["crop_box"]
                    cv2.imwrite(str(out_dir / crop_name(film, fn)), frame[y0:y1, x0:x1],
                                [cv2.IMWRITE_JPEG_QUALITY, 90])
        cap.release()


def main():
    from ultralytics import YOLO

    out_dir = OUT_DIR
    if out_dir.exists() and any(out_dir.iterdir()):
        raise SystemExit(f"STOP: {out_dir} is not empty; move the old output aside first")
    out_dir.mkdir(parents=True, exist_ok=True)
    log_f = open(out_dir.parent / "d2_run_v2.log", "a", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        log_f.write(msg + "\n")
        log_f.flush()

    bodd, v6 = YOLO(str(BODD_PATH)), YOLO(str(V6_PATH))
    if "hoop" not in bodd.names.values():
        raise SystemExit("STOP: BODD model has no hoop class")
    all_cands, fps_by_film = [], {}
    for film in FILMS:
        log(f"Film {FILMS.index(film) + 1} of 7: {film}")
        fps, cands = process_film(film, bodd, v6, log)
        fps_by_film[film] = fps
        all_cands += cands
    yields = {f: sum(c["film"] == f for c in all_cands) for f in FILMS}
    quotas = compute_quotas(yields)
    log(f"Yields: {yields}")
    log(f"Quotas: {quotas}")
    picked = pick_frames(all_cands, quotas)
    repick = pick_frames(all_cands, quotas)
    holdout = holdout_frames(fps_by_film[HOLDOUT_FILM])
    bad = verify(picked, quotas, fps_by_film, holdout, repick)
    if bad:
        for b in bad:
            log("CHECK FAILED: " + b)
        raise SystemExit("STOP: spec 6 checks failed; nothing written")
    log("Spec 6 checks: all passed")

    save_crops(picked, out_dir)
    meta = [{k: c[k] for k in ("film", "frame_number", "time_seconds", "crop_box")} for c in picked]
    (out_dir / "frames.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (out_dir / "pick_log.json").write_text(json.dumps(picked, indent=1), encoding="utf-8")
    (out_dir / "label.html").write_text(make_label_html(meta), encoding="utf-8")
    jpgs = len(list(out_dir.glob("*.jpg")))
    if jpgs != TOTAL_TARGET or len(meta) != TOTAL_TARGET:
        raise SystemExit(f"STOP: wrote {jpgs} crops and {len(meta)} entries, need {TOTAL_TARGET}")
    log(f"Done. {TOTAL_TARGET} crops + frames.json + label.html in {out_dir}. Stop for Scott to label.")


if __name__ == "__main__":
    sys.exit(main())
