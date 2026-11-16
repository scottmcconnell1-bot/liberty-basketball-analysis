import cv2
import numpy as np
from pathlib import Path

ROOT = Path('.')
crops_dir = ROOT / 'data/roi/notus_crops'

# Check all Game A1 crops for home_tens HSV
g1_h_tens = [902, 545, 21, 25]
g1_h_ones = [924, 544, 22, 26]

print("=== All Game A1 crops: home_tens HSV ===")
for f in sorted(crops_dir.glob('notus_A1_*.png')):
    img = cv2.imread(str(f))
    x, y, w, h = g1_h_tens
    crop = img[y:y+h, x:x+w]
    if crop.size == 0:
        print(f"  {f.name}: EMPTY")
        continue
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h_vals = hsv[:,:,0].flatten()
    s_vals = hsv[:,:,1].flatten()
    v_vals = hsv[:,:,2].flatten()
    low_red = ((h_vals >= 0) & (h_vals <= 12) & (s_vals > 90) & (v_vals > 120)).sum()
    high_red = ((h_vals >= 165) & (h_vals <= 180) & (s_vals > 90) & (v_vals > 120)).sum()
    total = len(h_vals)
    print(f"  {f.name}: H=({h_vals.min()}-{h_vals.max()}, mean={h_vals.mean():.1f}) S=({s_vals.min()}-{s_vals.max()}, mean={s_vals.mean():.1f}) V=({v_vals.min()}-{v_vals.max()}, mean={v_vals.mean():.1f}) red_pct={(low_red+high_red)/total*100:.1f}%")

print("\n=== All Game A1 crops: home_ones HSV ===")
for f in sorted(crops_dir.glob('notus_A1_*.png')):
    img = cv2.imread(str(f))
    x, y, w, h = g1_h_ones
    crop = img[y:y+h, x:x+w]
    if crop.size == 0:
        print(f"  {f.name}: EMPTY")
        continue
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h_vals = hsv[:,:,0].flatten()
    s_vals = hsv[:,:,1].flatten()
    v_vals = hsv[:,:,2].flatten()
    low_red = ((h_vals >= 0) & (h_vals <= 12) & (s_vals > 90) & (v_vals > 120)).sum()
    high_red = ((h_vals >= 165) & (h_vals <= 180) & (s_vals > 90) & (v_vals > 120)).sum()
    total = len(h_vals)
    print(f"  {f.name}: H=({h_vals.min()}-{h_vals.max()}, mean={h_vals.mean():.1f}) S=({s_vals.min()}-{s_vals.max()}, mean={s_vals.mean():.1f}) V=({v_vals.min()}-{v_vals.max()}, mean={v_vals.mean():.1f}) red_pct={(low_red+high_red)/total*100:.1f}%")

print("\n=== All Game A crops: home_tens HSV ===")
g2_h_tens = [903, 546, 19, 24]
g2_h_ones = [925, 545, 20, 25]
for f in sorted(crops_dir.glob('notus_A_*.png')):
    img = cv2.imread(str(f))
    x, y, w, h = g2_h_tens
    crop = img[y:y+h, x:x+w]
    if crop.size == 0:
        print(f"  {f.name}: EMPTY")
        continue
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h_vals = hsv[:,:,0].flatten()
    s_vals = hsv[:,:,1].flatten()
    v_vals = hsv[:,:,2].flatten()
    low_red = ((h_vals >= 0) & (h_vals <= 12) & (s_vals > 90) & (v_vals > 120)).sum()
    high_red = ((h_vals >= 165) & (h_vals <= 180) & (s_vals > 90) & (v_vals > 120)).sum()
    total = len(h_vals)
    print(f"  {f.name}: H=({h_vals.min()}-{h_vals.max()}, mean={h_vals.mean():.1f}) S=({s_vals.min()}-{s_vals.max()}, mean={s_vals.mean():.1f}) V=({v_vals.min()}-{v_vals.max()}, mean={v_vals.mean():.1f}) red_pct={(low_red+high_red)/total*100:.1f}%")

print("\n=== All Game A crops: home_ones HSV ===")
for f in sorted(crops_dir.glob('notus_A_*.png')):
    img = cv2.imread(str(f))
    x, y, w, h = g2_h_ones
    crop = img[y:y+h, x:x+w]
    if crop.size == 0:
        print(f"  {f.name}: EMPTY")
        continue
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h_vals = hsv[:,:,0].flatten()
    s_vals = hsv[:,:,1].flatten()
    v_vals = hsv[:,:,2].flatten()
    low_red = ((h_vals >= 0) & (h_vals <= 12) & (s_vals > 90) & (v_vals > 120)).sum()
    high_red = ((h_vals >= 165) & (h_vals <= 180) & (s_vals > 90) & (v_vals > 120)).sum()
    total = len(h_vals)
    print(f"  {f.name}: H=({h_vals.min()}-{h_vals.max()}, mean={h_vals.mean():.1f}) S=({s_vals.min()}-{s_vals.max()}, mean={s_vals.mean():.1f}) V=({v_vals.min()}-{v_vals.max()}, mean={v_vals.mean():.1f}) red_pct={(low_red+high_red)/total*100:.1f}%")