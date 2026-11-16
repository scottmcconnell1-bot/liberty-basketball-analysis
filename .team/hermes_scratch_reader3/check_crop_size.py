import cv2
from pathlib import Path
crops_dir = Path('data/roi/notus_crops')
for f in crops_dir.glob('*.png'):
    img = cv2.imread(str(f))
    print(f'{f.name}: {img.shape}')
    break