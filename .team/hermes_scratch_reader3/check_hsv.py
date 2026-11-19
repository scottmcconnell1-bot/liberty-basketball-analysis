import cv2
import numpy as np
from pathlib import Path

ROOT = Path('.')
crops_dir = ROOT / 'data/roi/notus_crops'

# Load one crop from each game
crop1 = cv2.imread(str(crops_dir / 'notus_A1_04_1817s.png'))  # Home=10, Away=15
crop2 = cv2.imread(str(crops_dir / 'notus_A_00_187s.png'))     # Home=5, Away=2

print(f"Crop 1 shape: {crop1.shape}")
print(f"Crop 2 shape: {crop2.shape}")

# Game A1 boxes (scaled)
g1_h_tens = [902, 545, 21, 25]
g1_h_ones = [924, 544, 22, 26]
g1_a_tens = [1047, 544, 22, 26]
g1_a_ones = [1070, 544, 22, 26]

# Game A boxes (scaled)
g2_h_tens = [903, 546, 19, 24]
g2_h_ones = [925, 545, 20, 25]
g2_a_tens = [1049, 546, 19, 24]
g2_a_ones = [1071, 545, 20, 25]

def analyze_box(img, box, name):
    x, y, w, h = box
    crop = img[y:y+h, x:x+w]
    if crop.size == 0:
        print(f"  {name}: EMPTY CROP")
        return
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h_vals = hsv[:,:,0].flatten()
    s_vals = hsv[:,:,1].flatten()
    v_vals = hsv[:,:,2].flatten()
    print(f"  {name}: H=({h_vals.min()}-{h_vals.max()}, mean={h_vals.mean():.1f}) S=({s_vals.min()}-{s_vals.max()}, mean={s_vals.mean():.1f}) V=({v_vals.min()}-{v_vals.max()}, mean={v_vals.mean():.1f})")
    # Check red mask conditions
    low_red = ((h_vals >= 0) & (h_vals <= 12) & (s_vals > 90) & (v_vals > 120)).sum()
    high_red = ((h_vals >= 165) & (h_vals <= 180) & (s_vals > 90) & (v_vals > 120)).sum()
    total = len(h_vals)
    print(f"    Red mask matches: low={low_red}, high={high_red}, total={total}, pct={(low_red+high_red)/total*100:.1f}%")

print("\n=== Game A1 (notus_A1_04_1817s) ===")
analyze_box(crop1, g1_h_tens, "home_tens")
analyze_box(crop1, g1_h_ones, "home_ones")
analyze_box(crop1, g1_a_tens, "away_tens")
analyze_box(crop1, g1_a_ones, "away_ones")

print("\n=== Game A (notus_A_00_187s) ===")
analyze_box(crop2, g2_h_tens, "home_tens")
analyze_box(crop2, g2_h_ones, "home_ones")
analyze_box(crop2, g2_a_tens, "away_tens")
analyze_box(crop2, g2_a_ones, "away_ones")

# Also check the full score cell regions
print("\n=== Full score cells ===")
g1_home_cell = [1029*1120//1280, 611*640//720, 56*1120//1280, 34*640//720]
g1_away_cell = [1195*1120//1280, 611*640//720, 56*1120//1280, 34*640//720]
g2_home_cell = [1030*1120//1280, 612*640//720, 53*1120//1280, 33*640//720]
g2_away_cell = [1197*1120//1280, 612*640//720, 53*1120//1280, 33*640//720]

print(f"Game A1 home cell: {g1_home_cell}")
print(f"Game A1 away cell: {g1_away_cell}")
print(f"Game A home cell: {g2_home_cell}")
print(f"Game A away cell: {g2_away_cell}")

analyze_box(crop1, g1_home_cell, "A1_home_cell")
analyze_box(crop1, g1_away_cell, "A1_away_cell")
analyze_box(crop2, g2_home_cell, "A2_home_cell")
analyze_box(crop2, g2_away_cell, "A2_away_cell")