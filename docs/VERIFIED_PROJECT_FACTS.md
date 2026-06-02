Dataset: ball_dataset

Status: VERIFIED

Location:
/home/monk-admin/PROJECTS/liberty-basketball-analysis/ball_dataset

Images: 5

Labels: 5

Pairing:
frame_001.jpg ↔ frame_001.txt
frame_002.jpg ↔ frame_002.txt
frame_003.jpg ↔ frame_003.txt
frame_004.jpg ↔ frame_004.txt
frame_005.jpg ↔ frame_005.txt

Annotation Format:
YOLO

Classes Observed:
Class 0 only

Annotations:
1 bounding box per image

Label Integrity:
No empty labels observed.

Verified

- Liberty basketball project contains multiple model files.
- finetune2/weights/best.pt exists.
- finetune2/weights/last.pt exists.
- Several prior training-run models exist.
- YOLO base models exist in the repository.

Unverified

- Which model is currently designated as active.
- Whether any model has been evaluated on Liberty data.
- Which model performs best.

- 
Verified

- finetune2 used:
  - epochs = 15
  - imgsz = 320
  - dataset = ball_finetune/data.yaml

- args.yaml records:
  - classes = null
  - names = null

- finetune2 produced zero precision, recall, and mAP metrics throughout the recorded epochs.
