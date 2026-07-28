"""Fine-tune ball detector with reduced memory usage."""
import cv2, numpy as np, os, random
from ultralytics import YOLO

VIDEO = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/uploads/Liberty_Vs_Riverstone_Q1.webm'
MODELS = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/models'
OUT = '/home/monk-admin/PROJECTS/liberty-basketball-analysis/ball_finetune'

# Training data already exists from previous run
print("Using existing training data...")
train_imgs = len(os.listdir(OUT+'/images/train'))
val_imgs = len(os.listdir(OUT+'/images/val'))
print("Train: %d, Val: %d" % (train_imgs, val_imgs))

# Fine-tune with minimal memory
print("\nStarting fine-tuning (low memory config)...")
model = YOLO(MODELS + '/ball_detector.pt')

results = model.train(
    data=OUT + '/data.yaml',
    epochs=15,
    imgsz=320,       # Smaller images = less memory
    batch=1,         # Minimal batch
    device='cpu',
    patience=5,
    save=True,
    project=OUT + '/runs',
    name='finetune2',
    pretrained=True,
    optimizer='AdamW',
    lr0=0.0001,
    augment=True,
    mosaic=0.0,      # Disable mosaic (saves memory)
    flipud=0.0,
    fliplr=0.5,
    scale=0.1,
    shear=0,
    degrees=0,
    workers=0,       # No multiprocessing
    cache=False,     # Don't cache images
)

print("\nFine-tuning complete!")
print("Best weights:", results.save_dir + '/weights/best.pt')
