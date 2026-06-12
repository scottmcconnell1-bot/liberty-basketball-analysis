#!/usr/bin/env python3
"""
Detector audit: precision/recall on manually labeled frames.

For each of 20 labeled frames:
1. Run detector at imgsz 320 and 480 at MUCH higher conf (0.1+)
2. Check if ANY detection overlaps the ground truth ball
3. Record: TP, FP, FN, IoU of best match

Usage: python3 audit_detector.py [label_file]

Label format (CSV): frame,x,y  (ball center in original frame coordinates)
If no label file, extracts 20 evenly spaced frames for manual review.
"""
import os, sys, time, csv
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['OMP_NUM_THREADS'] = '1'

import cv2
import numpy as np
from ultralytics import YOLO

VIDEO_1080P = '/tmp/clip_1080p.mp4'
VIDEO_720P = '/tmp/clip_720p.mp4'
MODEL = 'ball_finetune/runs/finetune2/weights/best.pt'
OUT_DIR = 'pipeline_output/detector_audit'
os.makedirs(OUT_DIR, exist_ok=True)

# Detection thresholds to test
CONFS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
IMSZS = [320, 480, 640]

IOU_THRESHOLD = 0.3  # Detection counts as TP if IoU with GT > this

def iou(box1, box2):
    """IoU between two boxes in (x1,y1,x2,y2) format."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2-x1) * (y2-y1)
    area1 = (box1[2]-box1[0]) * (box1[3]-box1[1])
    area2 = (box2[2]-box2[0]) * (box2[3]-box2[1])
    return inter / (area1 + area2 - inter)

def circle_to_box(cx, cy, radius=15):
    """Convert center+radius to box for IoU computation."""
    return (cx-radius, cy-radius, cx+radius, cy+radius)

def read_labels(path):
    """Read ground truth labels from CSV: frame,x,y"""
    labels = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            frame = int(row['frame'])
            x, y = float(row['x']), float(row['y'])
            labels[frame] = (x, y)
    return labels

def run_detector(m, frame, imgsz, conf):
    """Run YOLO and return list of (x1,y1,x2,y2,conf) detections."""
    r = m.predict(frame, imgsz=imgsz, conf=conf, iou=0.3, verbose=False)[0]
    detections = []
    if r.boxes is not None:
        for box in r.boxes:
            cls_name = m.names[int(box.cls[0])]
            if cls_name == 'Ball':
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cf = float(box.conf[0])
                detections.append((x1, y1, x2, y2, cf))
    return detections

def evaluate_frame(m, frame, frame_num, gt_center, imgsz, conf):
    """Evaluate single frame. Returns dict with TP/FP/FN/IoU."""
    detections = run_detector(m, frame, imgsz, conf)
    
    if gt_center is None:
        # No ball in frame — any detection is FP
        return {
            'tp': 0, 'fp': len(detections), 'fn': 0,
            'best_iou': 0, 'n_det': len(detections),
            'best_conf': max((d[4] for d in detections), default=0)
        }
    
    gt_box = circle_to_box(gt_center[0], gt_center[1], radius=20)
    
    # Find best IoU match
    best_iou = 0
    best_conf = 0
    tp = 0
    for det in detections:
        det_box = (det[0], det[1], det[2], det[3])
        i = iou(gt_box, det_box)
        if i > best_iou:
            best_iou = i
            best_conf = det[4]
    
    if best_iou >= IOU_THRESHOLD:
        tp = 1
        fp = len(detections) - 1  # extra detections are false positives
    else:
        fp = len(detections)
    
    fn = 1 - tp
    
    return {
        'tp': tp, 'fp': fp, 'fn': fn,
        'best_iou': best_iou, 'n_det': len(detections),
        'best_conf': best_conf
    }

def save_audit_frame(frame, frame_num, gt_center, detections, imgsz, conf, source):
    """Save annotated frame for visual review."""
    annotated = frame.copy()
    
    # Draw ground truth (blue)
    if gt_center:
        cv2.circle(annotated, (int(gt_center[0]), int(gt_center[1])), 20, (255, 0, 0), 2)
        cv2.putText(annotated, 'GT', (int(gt_center[0])-15, int(gt_center[1])-25),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 1)
    
    # Draw detections (green=TP IoU>0.3, red=FP)
    gt_box = circle_to_box(gt_center[0], gt_center[1], 20) if gt_center else None
    for det in detections:
        det_box = (det[0], det[1], det[2], det[3])
        is_tp = False
        if gt_box:
            i = iou(gt_box, det_box)
            is_tp = i >= IOU_THRESHOLD
        
        color = (0, 255, 0) if is_tp else (0, 0, 255)
        cv2.rectangle(annotated, (int(det[0]), int(det[1])), (int(det[2]), int(det[3])), color, 2)
        cv2.putText(annotated, f'{det[4]:.3f}', (int(det[0]), int(det[1])-5),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)
    
    cv2.putText(annotated, f'{source} imgsz={imgsz} conf={conf:.2f}', (10, 30),
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    
    filename = f'{OUT_DIR}/audit_{source}_f{frame_num:04d}_i{imgsz}_c{conf:.2f}.jpg'
    cv2.imwrite(filename, annotated)
    return filename


if __name__ == '__main__':
    label_file = sys.argv[1] if len(sys.argv) > 1 else None
    
    m = YOLO(MODEL, verbose=False)
    print(f"Model loaded")
    
    # Extract 20 evenly spaced frames from 1080p clip
    cap = cv2.VideoCapture(VIDEO_1080P)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_indices = [int(i * total / 20) for i in range(20)]
    
    frames_1080p = {}
    for fi in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ret, frame = cap.read()
        if ret:
            frames_1080p[fi] = frame
    cap.release()
    
    # Read labels if provided, else output frames for manual labeling
    labels_1080p = {}
    if label_file and os.path.exists(label_file):
        labels_1080p = read_labels(label_file)
        print(f"Loaded {len(labels_1080p)} ground truth labels")
    else:
        # Save frames for manual labeling
        print("No label file. Saving frames for manual labeling...")
        for fi, frame in frames_1080p.items():
            cv2.imwrite(f'{OUT_DIR}/label_frame_{fi:04d}.jpg', frame)
        
        # Create empty label template
        with open(f'{OUT_DIR}/labels_template.csv', 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['frame', 'x', 'y', 'note'])
            for fi in frame_indices:
                writer.writerow([fi, '', '', ''])
        print(f"Saved 20 frames to {OUT_DIR}/ for manual labeling")
        print(f"Label template: {OUT_DIR}/labels_template.csv")
        print(f"Fill in x,y ball coordinates and re-run:")
        print(f"  python3 {sys.argv[0]} {OUT_DIR}/labels_template.csv")
        sys.exit(0)
    
    # Run evaluation
    results = []
    
    for source, video in [('1080p', VIDEO_1080P), ('720p', VIDEO_720P)]:
        cap = cv2.VideoCapture(video)
        
        for fi in sorted(frames_1080p.keys()):
            if source == '1080p':
                frame = frames_1080p[fi]
            else:
                cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
                ret, frame = cap.read()
                if not ret:
                    continue
            
            gt = labels_1080p.get(fi, None)
            
            for imgsz in IMSZS:
                for conf in CONFS:
                    t0 = time.time()
                    dets = run_detector(m, frame, imgsz, conf)
                    elapsed = time.time() - t0
                    
                    tp = fp = fn = 0
                    best_iou = 0
                    
                    if gt:
                        gt_box = circle_to_box(gt[0], gt[1], 20)
                        for det in dets:
                            i = iou(gt_box, (det[0], det[1], det[2], det[3]))
                            if i > best_iou:
                                best_iou = i
                        
                        if best_iou >= IOU_THRESHOLD:
                            tp = 1
                            fp = len(dets) - 1
                        else:
                            fp = len(dets)
                        fn = 1 - tp
                    else:
                        fp = len(dets)
                    
                    result = {
                        'source': source, 'frame': fi, 'imgsz': imgsz, 'conf': conf,
                        'tp': tp, 'fp': fp, 'fn': fn, 'best_iou': best_iou,
                        'n_det': len(dets), 'time_s': elapsed
                    }
                    results.append(result)
                    
                    # Save annotated frame for highest conf that has detections
                    if len(dets) > 0 and conf >= 0.10 and fi % 5 == 0:
                        save_audit_frame(frame, fi, gt, dets, imgsz, conf, source)
        
        cap.release()
    
    # Summary
    df = __import__('pandas').DataFrame(results)
    df.to_csv(f'{OUT_DIR}/precision_recall.csv', index=False)
    
    print(f"\n{'='*70}")
    print(f"DETECTOR PRECISION/RECALL AUDIT")
    print(f"{'='*70}")
    print(f"GT frames labeled: {sum(1 for fi in frames_1080p if fi in labels_1080p)}")
    print(f"IoU threshold: {IOU_THRESHOLD}")
    
    for source in ['1080p', '720p']:
        for imgsz in IMSZS:
            print(f"\n--- {source} imgsz={imgsz} ---")
            print(f"{'Conf':<7} {'TP':<5} {'FP':<5} {'FN':<5} {'Prec':<7} {'Recall':<7} {'F1':<7} {'mIoU':<7}")
            print("-" * 60)
            
            for conf in CONFS:
                sub = df[(df['source']==source) & (df['imgsz']==imgsz) & (df['conf']==conf)]
                tp = sub['tp'].sum()
                fp = sub['fp'].sum()
                fn = sub['fn'].sum()
                prec = tp / (tp + fp) if (tp + fp) > 0 else 0
                recall = tp / (tp + fn) if (tp + fn) > 0 else 0
                f1 = 2 * prec * recall / (prec + recall) if (prec + recall) > 0 else 0
                miou = sub[sub['best_iou'] > 0]['best_iou'].mean() if (sub['best_iou'] > 0).any() else 0
                
                print(f"{conf:.2f}    {tp:<5} {fp:<5} {fn:<5} {prec:.3f}   {recall:.3f}   {f1:.3f}   {miou:.3f}")
    
    # Also average time per frame
    print(f"\n--- INFERENCE TIME ---")
    for source in ['1080p', '720p']:
        for imgsz in IMSZS:
            sub = df[(df['source']==source) & (df['imgsz']==imgsz)]
            avg_t = sub['time_s'].mean()
            print(f"  {source} imgsz={imgsz}: {avg_t:.3f}s avg")
    
    print(f"\nAudit frames saved to {OUT_DIR}/")
    print(f"Full results: {OUT_DIR}/precision_recall.csv")
    print("DONE")
