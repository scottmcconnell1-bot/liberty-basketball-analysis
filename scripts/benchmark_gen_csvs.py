#!/usr/bin/env python3
"""Generate benchmark result CSVs. Run in background due to CPU inference time."""
import os, csv
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '2'
from ultralytics import YOLO
import cv2, numpy as np

FRAMES_DIR = 'benchmark/frames'
LABELS_DIR = 'benchmark/labels'

print("Loading models...")
model_base = YOLO('yolov8n.pt', verbose=False)
model_ft = YOLO('models/ball_detector.pt', verbose=False)
print("Done.")

def iou_yolo(b1, b2):
    cx1,cy1,w1,h1 = b1; cx2,cy2,w2,h2 = b2
    x1,y1,x2,y2 = cx1-w1/2, cy1-h1/2, cx1+w1/2, cy1+h1/2
    x3,y3,x4,y4 = cx2-w2/2, cy2-h2/2, cx2+w2/2, cy2+h2/2
    xi,yi,xj,yj = max(x1,x3),max(y1,y3),min(x2,x4),min(y2,y4)
    if xj<=xi or yj<=yi: return 0.
    return (xj-xi)*(yj-yi)/(w1*h1+w2*h2-(xj-xi)*(yj-yi))

def load_gt(p):
    boxes = []
    if os.path.exists(p):
        with open(p) as f:
            for l in f:
                parts = l.strip().split()
                if len(parts)==5: boxes.append(tuple(float(x) for x in parts[1:]))
    return boxes

def run_det(model, frame, conf, classes=None):
    kwargs = dict(imgsz=640, conf=conf, verbose=False)
    if classes: kwargs['classes'] = classes
    dets = []
    for r in model(frame, **kwargs):
        if r.boxes is not None:
            for box in r.boxes:
                x1,y1,x2,y2 = box.xyxy[0].tolist()
                cf = float(box.conf[0])
                hf,wf = frame.shape[:2]
                dets.append((((x1+x2)/2)/wf, ((y1+y2)/2)/hf, (x2-x1)/wf, (y2-y1)/hf, cf))
    return dets

def eval_frame(gt, dets, iou_thresh=0.5):
    if len(gt)==0: return 0, len(dets), 0
    if len(dets)==0: return 0, 0, len(gt)
    matched=set(); tp=0
    for g in gt:
        best_i,best_j=0,-1
        for j,d in enumerate(dets):
            if j in matched: continue
            i=iou_yolo(g,d[:4])
            if i>best_i: best_i,best_j=i,j
        if best_i>=iou_thresh: tp+=1; matched.add(best_j)
    return tp, len(dets)-len(matched), len(gt)-tp

frame_files = sorted([f for f in os.listdir(FRAMES_DIR) if f.endswith('.jpg')])
CONF_SWEEP = [0.05, 0.15]

all_results = []
summary_results = []

for model_name, model, classes in [('base_yolov8n_class32', model_base, [32]), ('finetuned_ball_detector', model_ft, [0])]:
    for conf_thresh in CONF_SWEEP:
        total_tp,total_fp,total_fn = 0,0,0
        for i, fname in enumerate(frame_files):
            frame = cv2.imread(os.path.join(FRAMES_DIR, fname))
            if frame is None: continue
            gt_boxes = load_gt(os.path.join(LABELS_DIR, fname.replace('.jpg','.txt')))
            dets = run_det(model, frame, conf_thresh, classes)
            tp,fp,fn = eval_frame(gt_boxes, dets)
            total_tp+=tp; total_fp+=fp; total_fn+=fn
            all_results.append({
                'frame': fname, 'model': model_name,
                'conf_thresh': conf_thresh,
                'gt_boxes': len(gt_boxes), 'n_dets': len(dets),
                'tp': tp, 'fp': fp, 'fn': fn,
                'best_conf': max([d[4] for d in dets], default=0),
            })
            if (i+1) % 20 == 0:
                print(f"  {model_name} conf={conf_thresh:.2f}: {i+1}/{len(frame_files)}")
        prec = total_tp/(total_tp+total_fp) if (total_tp+total_fp)>0 else 0
        recall = total_tp/(total_tp+total_fn) if (total_tp+total_fn)>0 else 0
        f1 = 2*prec*recall/(prec+recall) if (prec+recall)>0 else 0
        summary_results.append({
            'model': model_name, 'conf_thresh': conf_thresh,
            'tp': total_tp, 'fp': total_fp, 'fn': total_fn,
            'precision': round(prec,4), 'recall': round(recall,4), 'f1': round(f1,4),
        })
        print(f'{model_name} conf={conf_thresh:.2f}: TP={total_tp} FP={total_fp} FN={total_fn} P={prec:.4f} R={recall:.4f}')

with open('benchmark/results_summary.csv','w',newline='') as f:
    w = csv.DictWriter(f, fieldnames=['model','conf_thresh','tp','fp','fn','precision','recall','f1'])
    w.writeheader(); w.writerows(summary_results)

with open('benchmark/results_perframe.csv','w',newline='') as f:
    w = csv.DictWriter(f, fieldnames=['frame','model','conf_thresh','gt_boxes','n_dets','tp','fp','fn','best_conf'])
    w.writeheader(); w.writerows(all_results)

print(f'Written: benchmark/results_summary.csv ({len(summary_results)} rows)')
print(f'Written: benchmark/results_perframe.csv ({len(all_results)} rows)')
print("DONE")
