#!/usr/bin/env python3
"""
Temporal Consistency Filter Benchmark
======================================
Tests whether temporal motion/track consistency can reject static
court-marking false positives while preserving ball recall.

Approach:
1. Run ball_detector (conf=0.25) on all 138 benchmark frames.
2. Link detections across consecutive frames into tracks using
   greedy nearest-neighbor matching (max pixel distance).
3. Score tracks by lifespan, motion, and consistency.
4. Apply temporal filters; evaluate on v2 stratified split.

Filters tested:
- baseline: no temporal filtering (all conf>=0.25 detections)
- temporal_len2: detections in tracks of length >= 2
- temporal_len3: detections in tracks of length >= 3
- temporal_mov2: detections in tracks with >= 2 frames AND non-zero motion

Primary metric: held-out v2 test F1 with recall >= 0.95.
"""
import os, csv, cv2, math, re, random
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '2'

import numpy as np

# ── Config ──
CONF = 0.25
IOU_THRESHOLD = 0.5
RANDOM_SEED = 42
FRAMES_DIR = 'benchmark/frames'
LABELS_DIR = 'benchmark/labels'
OUT_DIR = 'benchmark'
OVERLAYS_DIR = os.path.join(OUT_DIR, 'temporal_overlays')
CONTACT_SHEET_PATH = os.path.join(OUT_DIR, 'temporal_contact_sheet.jpg')
os.makedirs(OVERLAYS_DIR, exist_ok=True)

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

# ── Load manifest and split ──
print("=== Loading manifest and split ===")
with open(os.path.join(OUT_DIR, 'manifest.csv')) as f:
    manifest = {r['fname']: r for r in csv.DictReader(f)}

with open(os.path.join(OUT_DIR, 'classifier_split_v2.csv')) as f:
    v2_split = {r['frame']: r['split'] for r in csv.DictReader(f)}

train_fnames = sorted([f for f, s in v2_split.items() if s == 'train'])
test_fnames = sorted([f for f, s in v2_split.items() if s == 'test'])
all_fnames = sorted(manifest.keys())

print(f"Frames: {len(all_fnames)} total, {len(train_fnames)} train, {len(test_fnames)} test")

# ── Determine frame ordering for temporal tracking ──
# Frames need a temporal sequence number. We extract this from filenames.
# neg_NNN_fYYYYY.jpg -> video NNN, frame YYYYY
# pos_train/val_frame_NNN.jpg -> sequential index NNN

def parse_temporal_key(fname):
    """Return (video_id, frame_num) for temporal ordering."""
    m = re.match(r'neg_(\d+)_f(\d+)', fname)
    if m:
        return (f"neg_{m.group(1)}", int(m.group(2)))
    m = re.match(r'pos_(train|val)_frame_(\d+)', fname)
    if m:
        return (f"pos_{m.group(1)}", int(m.group(2)))
    return (fname, 0)

# Build temporal sequences: group frames by video, sorted by frame number
from collections import defaultdict
video_sequences = defaultdict(list)
for fname in all_fnames:
    vid, fnum = parse_temporal_key(fname)
    video_sequences[vid].append((fnum, fname))

for vid in video_sequences:
    video_sequences[vid].sort()

# Build a global frame index for consecutive-frame lookups
frame_to_global_idx = {}
global_idx_to_frame = {}
idx = 0
for vid in sorted(video_sequences.keys()):
    for fnum, fname in video_sequences[vid]:
        frame_to_global_idx[fname] = idx
        global_idx_to_frame[idx] = fname
        idx += 1

# Build next-frame mapping (only within same video)
next_frame = {}
prev_frame = {}
for vid in video_sequences:
    frames = [fname for _, fname in video_sequences[vid]]
    for i in range(len(frames) - 1):
        next_frame[frames[i]] = frames[i + 1]
        prev_frame[frames[i + 1]] = frames[i]

print(f"Videos: {len(video_sequences)}, total frames: {idx}")

# ── Run detector on all frames ──
print("\n=== Running ball detector ===")
from ultralytics import YOLO
model = YOLO('models/ball_detector.pt')

frame_detections = {}  # frame -> list of {cx, cy, conf, w, h, px_cx, px_cy}

for fname in all_fnames:
    fpath = os.path.join(FRAMES_DIR, fname)
    results = model(fpath, conf=CONF, verbose=False)
    dets = []
    for r in results:
        if r.boxes is None:
            continue
        h, w = r.orig_shape[:2]
        for box in r.boxes:
            if int(box.cls) != 0:  # class 0 = ball
                continue
            conf = float(box.conf)
            if conf < CONF:
                continue
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
            cx = ((x1 + x2) / 2) / w
            cy = ((y1 + y2) / 2) / h
            bw = (x2 - x1) / w
            bh = (y2 - y1) / h
            px_cx = int((x1 + x2) / 2)
            px_cy = int((y1 + y2) / 2)
            dets.append({
                'cx': cx, 'cy': cy, 'conf': conf,
                'w': bw, 'h': bh,
                'px_cx': px_cx, 'px_cy': px_cy,
            })
    frame_detections[fname] = dets

total_dets = sum(len(d) for d in frame_detections.values())
print(f"Total detections at conf>={CONF}: {total_dets}")
print(f"Frames with detections: {sum(1 for d in frame_detections.values() if d)}/{len(all_fnames)}")

# ── Build tracks via greedy nearest-neighbor matching ──
print("\n=== Building temporal tracks ===")

MAX_MATCH_DIST = 0.05  # max normalized centroid distance for matching

class Track:
    _next_id = 0
    def __init__(self):
        self.id = Track._next_id
        Track._next_id += 1
        self.detections = []  # [(frame, det_idx, cx, cy, conf, px_cx, px_cy)]
        self.frames = []

    def last_pos(self):
        if not self.detections:
            return None
        d = self.detections[-1]
        return (d[2], d[3])  # cx, cy

    def add(self, frame, det_idx, cx, cy, conf, px_cx, px_cy):
        self.detections.append((frame, det_idx, cx, cy, conf, px_cx, px_cy))
        self.frames.append(frame)

    def lifespan(self):
        return len(self.detections)

    def total_motion(self):
        """Total centroid displacement across track."""
        if len(self.detections) < 2:
            return 0.0
        dx = self.detections[-1][2] - self.detections[0][2]
        dy = self.detections[-1][3] - self.detections[0][3]
        return math.sqrt(dx*dx + dy*dy)

    def max_step_motion(self):
        """Maximum single-step centroid displacement."""
        if len(self.detections) < 2:
            return 0.0
        max_step = 0.0
        for i in range(1, len(self.detections)):
            dx = self.detections[i][2] - self.detections[i-1][2]
            dy = self.detections[i][3] - self.detections[i-1][3]
            step = math.sqrt(dx*dx + dy*dy)
            if step > max_step:
                max_step = step
        return max_step

    def avg_conf(self):
        if not self.detections:
            return 0.0
        return sum(d[4] for d in self.detections) / len(self.detections)


# Process each video sequence independently
all_tracks = []
active_tracks = []  # tracks currently being extended

for vid in sorted(video_sequences.keys()):
    frames_in_video = [fname for _, fname in video_sequences[vid]]

    for fname in frames_in_video:
        dets = frame_detections.get(fname, [])

        if not dets:
            # No detections: all active tracks end
            all_tracks.extend(active_tracks)
            active_tracks = []
            continue

        # Match detections to active tracks
        matched_track = [None] * len(dets)
        matched_det = [None] * len(active_tracks)
        used_dets = set()

        # Greedy matching by distance
        matches = []
        for ti, track in enumerate(active_tracks):
            last_pos = track.last_pos()
            if last_pos is None:
                continue
            for di, det in enumerate(dets):
                if di in used_dets:
                    continue
                dx = det['cx'] - last_pos[0]
                dy = det['cy'] - last_pos[1]
                dist = math.sqrt(dx*dx + dy*dy)
                if dist <= MAX_MATCH_DIST:
                    matches.append((dist, ti, di))

        matches.sort()

        for dist, ti, di in matches:
            if matched_det[ti] is not None or di in used_dets:
                continue
            matched_det[ti] = di
            matched_track[di] = ti
            used_dets.add(di)

        # Extend matched tracks
        for ti, track in enumerate(active_tracks):
            if matched_det[ti] is not None:
                di = matched_det[ti]
                det = dets[di]
                track.add(fname, di, det['cx'], det['cy'], det['conf'],
                         det['px_cx'], det['px_cy'])

        # Unmatched tracks end
        new_active = []
        for ti, track in enumerate(active_tracks):
            if matched_det[ti] is None:
                all_tracks.append(track)
            else:
                new_active.append(track)
        active_tracks = new_active

        # Unmatched detections start new tracks
        for di, det in enumerate(dets):
            if di not in used_dets:
                track = Track()
                track.add(fname, di, det['cx'], det['cy'], det['conf'],
                         det['px_cx'], det['px_cy'])
                active_tracks.append(track)

# Close remaining active tracks
all_tracks.extend(active_tracks)

print(f"Total tracks: {len(all_tracks)}")
track_lens = [t.lifespan() for t in all_tracks]
print(f"Track lengths: min={min(track_lens)}, max={max(track_lens)}, "
      f"mean={sum(track_lens)/len(track_lens):.2f}")
print(f"  len=1: {sum(1 for l in track_lens if l==1)}, "
      f"len=2: {sum(1 for l in track_lens if l==2)}, "
      f"len>=3: {sum(1 for l in track_lens if l>=3)}")

# ── Build detection -> track mapping ──
det_track_map = {}  # (frame, det_idx) -> track
for track in all_tracks:
    for frame, det_idx, cx, cy, conf, px_cx, px_cy in track.detections:
        det_track_map[(frame, det_idx)] = track

# ── Define filter variants ──
def passes_temporal_len2(frame, det_idx):
    track = det_track_map.get((frame, det_idx))
    if track is None:
        return False
    return track.lifespan() >= 2

def passes_temporal_len3(frame, det_idx):
    track = det_track_map.get((frame, det_idx))
    if track is None:
        return False
    return track.lifespan() >= 3

def passes_temporal_mov2(frame, det_idx):
    track = det_track_map.get((frame, det_idx))
    if track is None:
        return False
    return track.lifespan() >= 2 and track.total_motion() > 0.001

VARIANTS = [
    ('baseline', lambda f, d: True),
    ('temporal_len2', passes_temporal_len2),
    ('temporal_len3', passes_temporal_len3),
    ('temporal_mov2', passes_temporal_mov2),
]

# ── Load GT ──
def load_gt(lp):
    boxes = []
    if os.path.exists(lp):
        with open(lp) as f:
            for l in f:
                parts = l.strip().split()
                if len(parts) == 5:
                    boxes.append(tuple(float(x) for x in parts[1:]))
    return boxes

def iou_yolo(b1, b2):
    cx1, cy1, w1, h1 = b1
    cx2, cy2, w2, h2 = b2
    x1, y1, x2, y2 = cx1-w1/2, cy1-h1/2, cx1+w1/2, cy1+h1/2
    x3, y3, x4, y4 = cx2-w2/2, cy2-h2/2, cx2+w2/2, cy2+h2/2
    xi, yi, xj, yj = max(x1, x3), max(y1, y3), min(x2, x4), min(y2, y4)
    if xj <= xi or yj <= yi:
        return 0.
    return (xj-xi)*(yj-yi) / (w1*h1 + w2*h2 - (xj-xi)*(yj-yi))

def match_measure(dets, gt_boxes):
    matched = set()
    for gt in gt_boxes:
        best_i, best_j = 0, -1
        for j, det in enumerate(dets):
            if j in matched:
                continue
            i = iou_yolo(gt, (det['cx'], det['cy'], det['w'], det['h']))
            if i > best_i:
                best_i, best_j = i, j
        if best_i >= IOU_THRESHOLD:
            matched.add(best_j)
    tp = len(matched)
    return tp, len(dets) - tp, len(gt_boxes) - tp

def compute_metrics(tp, fp, fn):
    p = tp/(tp+fp) if tp+fp > 0 else 0
    r = tp/(tp+fn) if tp+fn > 0 else 0
    f = 2*p*r/(p+r) if p+r > 0 else 0
    return round(p, 4), round(r, 4), round(f, 4)

# ── Evaluate ──
print("\n=== Evaluating temporal filters ===")

all_results = []
per_frame_results = []
per_track_results = []

for vname, vfilter in VARIANTS:
    for sname in ['train', 'test', 'all']:
        ttp, tfp, tfn, trm, nf = 0, 0, 0, 0, 0
        for fname in all_fnames:
            split = v2_split.get(fname, 'unknown')
            if sname == 'train' and split != 'train':
                continue
            if sname == 'test' and split != 'test':
                continue

            dets = frame_detections.get(fname, [])
            if not dets and not load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt'))):
                continue

            gt = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))

            if vname == 'baseline':
                kept = dets
                removed = []
            else:
                kept = []
                removed = []
                for di, det in enumerate(dets):
                    if vfilter(fname, di):
                        kept.append(det)
                    else:
                        removed.append(det)

            tp, fp, fn = match_measure(kept, gt)
            ttp += tp
            tfp += fp
            tfn += fn
            trm += len(removed)
            nf += 1

            per_frame_results.append({
                'variant': vname,
                'split': sname,
                'frame': fname,
                'n_det_before': len(dets),
                'n_removed': len(removed),
                'n_det_after': len(kept),
                'tp': tp, 'fp': fp, 'fn': fn,
            })

        p, r, f = compute_metrics(ttp, tfp, tfn)
        all_results.append({
            'variant': vname,
            'split': sname,
            'frames': nf,
            'tp': ttp, 'fp': tfp, 'fn': tfn,
            'precision': p, 'recall': r, 'f1': f,
            'total_removed': trm,
        })
        tag = f"[{sname:5s}]" if sname != 'all' else "[ ALL ]"
        print(f"  {vname:20s} {tag}: TP={ttp:3d} FP={tfp:3d} FN={tfn:2d} "
              f"P={p:.4f} R={r:.4f} F1={f:.4f} removed={trm:3d} ({nf} frames)")

# ── Save results CSVs ──
print("\n=== Saving results ===")

with open(os.path.join(OUT_DIR, 'temporal_results.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'variant', 'split', 'frames', 'tp', 'fp', 'fn',
        'precision', 'recall', 'f1', 'total_removed'])
    writer.writeheader()
    writer.writerows(all_results)
print(f"Written: {OUT_DIR}/temporal_results.csv")

with open(os.path.join(OUT_DIR, 'temporal_per_frame.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'variant', 'split', 'frame', 'n_det_before', 'n_removed',
        'n_det_after', 'tp', 'fp', 'fn'])
    writer.writeheader()
    writer.writerows(per_frame_results)
print(f"Written: {OUT_DIR}/temporal_per_frame.csv")

# ── Save per-track data ──
track_rows = []
for track in all_tracks:
    split = v2_split.get(track.frames[0], 'unknown') if track.frames else 'unknown'
    track_rows.append({
        'track_id': track.id,
        'lifespan': track.lifespan(),
        'total_motion': round(track.total_motion(), 6),
        'max_step_motion': round(track.max_step_motion(), 6),
        'avg_conf': round(track.avg_conf(), 6),
        'start_frame': track.frames[0] if track.frames else '',
        'end_frame': track.frames[-1] if track.frames else '',
        'split': split,
        'passes_len2': track.lifespan() >= 2,
        'passes_len3': track.lifespan() >= 3,
        'passes_mov2': track.lifespan() >= 2 and track.total_motion() > 0.001,
    })

with open(os.path.join(OUT_DIR, 'temporal_tracks.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'track_id', 'lifespan', 'total_motion', 'max_step_motion',
        'avg_conf', 'start_frame', 'end_frame', 'split',
        'passes_len2', 'passes_len3', 'passes_mov2'])
    writer.writeheader()
    writer.writerows(track_rows)
print(f"Written: {OUT_DIR}/temporal_tracks.csv ({len(track_rows)} tracks)")

# ── Save per-detection scores with track info ──
det_rows = []
for fname in all_fnames:
    dets = frame_detections.get(fname, [])
    for di, det in enumerate(dets):
        track = det_track_map.get((fname, di))
        track_id = track.id if track else -1
        lifespan = track.lifespan() if track else 0
        total_motion = track.total_motion() if track else 0.0
        det_rows.append({
            'frame': fname,
            'det_idx': di,
            'split': v2_split.get(fname, 'unknown'),
            'cx': round(det['cx'], 6),
            'cy': round(det['cy'], 6),
            'conf': round(det['conf'], 6),
            'px_cx': det['px_cx'],
            'px_cy': det['px_cy'],
            'track_id': track_id,
            'track_lifespan': lifespan,
            'track_total_motion': round(total_motion, 6),
            'passes_len2': lifespan >= 2,
            'passes_len3': lifespan >= 3,
            'passes_mov2': lifespan >= 2 and total_motion > 0.001,
        })

with open(os.path.join(OUT_DIR, 'temporal_detection_scores.csv'), 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'frame', 'det_idx', 'split', 'cx', 'cy', 'conf',
        'px_cx', 'px_cy', 'track_id', 'track_lifespan',
        'track_total_motion', 'passes_len2', 'passes_len3', 'passes_mov2'])
    writer.writeheader()
    writer.writerows(det_rows)
print(f"Written: {OUT_DIR}/temporal_detection_scores.csv ({len(det_rows)} detections)")

# ── Generate overlays ──
print("\n=== Generating overlays ===")
# Color palette for tracks
def track_color(track_id):
    """Generate a distinct color for a track."""
    random.seed(track_id * 7 + 13)
    return tuple(random.randint(80, 255) for _ in range(3))

# For each variant, generate overlays for test frames with removals
for vname, vfilter in VARIANTS[1:]:  # skip baseline
    ov_count = 0
    for fname in sorted(test_fnames):
        dets = frame_detections.get(fname, [])
        if not dets:
            continue

        gt = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg', '.txt')))

        kept = []
        removed = []
        for di, det in enumerate(dets):
            if vfilter(fname, di):
                kept.append(det)
            else:
                removed.append(det)

        if not removed:
            continue

        frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
        if frame is None:
            continue
        h, w = frame.shape[:2]
        out = frame.copy()

        # Draw removed detections (red X)
        for det in removed:
            cv2.drawMarker(out, (det['px_cx'], det['px_cy']),
                          (0, 0, 255), cv2.MARKER_TILTED_CROSS, 14, 2)

        # Draw kept detections (green circle) with track coloring
        for di, det in enumerate(dets):
            if vfilter(fname, di):
                track = det_track_map.get((fname, di))
                color = track_color(track.id) if track else (0, 255, 0)
                cv2.circle(out, (det['px_cx'], det['px_cy']), 8, color, 2)
                if track:
                    cv2.putText(out, f't{track.id}',
                               (det['px_cx'] + 10, det['px_cy'] - 5),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

        # Draw GT boxes
        for box in gt:
            cx, cy, bw, bh = box
            cv2.rectangle(out,
                         (int((cx-bw/2)*w), int((cy-bh/2)*h)),
                         (int((cx+bw/2)*w), int((cy+bh/2)*h)),
                         (0, 255, 0), 2)

        # Labels
        cv2.putText(out, f'{vname}: -{len(removed)}', (5, 15),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        cv2.putText(out, f'[TEST] {fname[:20]}', (5, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)

        cv2.imwrite(os.path.join(OVERLAYS_DIR, f'{vname}_{fname}'), out)
        ov_count += 1

    print(f"  {vname}: {ov_count} overlays")

# ── Generate contact sheet ──
print("\n=== Generating contact sheet ===")
# Collect overlay images for test frames, one row per variant
overlay_files = sorted([f for f in os.listdir(OVERLAYS_DIR) if f.endswith('.jpg')])
if overlay_files:
    # Read all overlay images
    overlay_imgs = []
    labels = []
    current_variant = None
    for f in overlay_files:
        parts = f.replace('.jpg', '').split('_', 1)
        variant = parts[0] if parts else f
        if variant != current_variant:
            labels.append(variant)
            current_variant = variant
        else:
            labels.append('')
        img = cv2.imread(os.path.join(OVERLAYS_DIR, f))
        if img is not None:
            # Resize to uniform width
            target_w = 320
            scale = target_w / img.shape[1]
            img = cv2.resize(img, (target_w, int(img.shape[0] * scale)))
            overlay_imgs.append(img)

    if overlay_imgs:
        # Grid layout: max 4 columns
        max_cols = 4
        rows = math.ceil(len(overlay_imgs) / max_cols)
        # Pad to fill grid
        while len(overlay_imgs) < rows * max_cols:
            overlay_imgs.append(np.zeros_like(overlay_imgs[0]))
            labels.append('')

        # Add label bands
        label_h = 20
        labeled_imgs = []
        for img, lbl in zip(overlay_imgs, labels):
            band = np.zeros((label_h, img.shape[1], 3), dtype=np.uint8)
            if lbl:
                cv2.putText(band, lbl, (3, 14),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
            labeled_imgs.append(np.vstack([band, img]))

        # Build rows
        row_imgs = []
        for r in range(rows):
            row = labeled_imgs[r*max_cols:(r+1)*max_cols]
            # Pad heights to match
            max_h = max(img.shape[0] for img in row)
            padded = []
            for img in row:
                if img.shape[0] < max_h:
                    pad = np.zeros((max_h - img.shape[0], img.shape[1], 3), dtype=np.uint8)
                    img = np.vstack([img, pad])
                padded.append(img)
            row_imgs.append(np.hstack(padded))

        contact_sheet = np.vstack(row_imgs)
        cv2.imwrite(CONTACT_SHEET_PATH, contact_sheet)
        print(f"Written: {CONTACT_SHEET_PATH} ({len(overlay_files)} overlays)")

print("\nDONE — Temporal consistency benchmark complete")
