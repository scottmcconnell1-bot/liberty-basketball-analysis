import cv2
import numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent
crop_dir = ROOT / 'data/roi/notus_crops'
crops = sorted(crop_dir.glob('*.png'))

for crop_path in crops[:3]:
    img = cv2.imread(str(crop_path))
    print(f"{crop_path.name}: shape={img.shape}, dtype={img.dtype}")
    # Check if it's the full frame or a crop
    # The ROI expects 1280x720, but we get 640x1120 (rotated?)
    # 1120x640 would be 1280x720 scaled by 0.875
    # But 640x1120 is 720x1280 transposed
    
# Let's check the first crop more carefully
img = cv2.imread(str(crops[0]))
print(f"\nFirst crop: {crops[0].name}")
print(f"  Shape: {img.shape} (H, W, C)")
print(f"  Min/Max pixel: {img.min()}/{img.max()}")
print(f"  Mean: {img.mean():.1f}")

# The ROI coordinates are around x=1000-1200, y=600
# But the image is only 1120 wide and 640 tall
# So these crops must be the scoreboard region already cropped
# Let's see what's in the image - check the right side
right_side = img[:, 800:]
print(f"  Right side (x>800) shape: {right_side.shape}")
print(f"  Right side mean: {right_side.mean():.1f}")

# Check if scoreboard is on the right
# The ROI has home tens at x=1031, away tens at x=1197
# In a 1120 wide image, x=1031 is near the right edge
# Let's crop the scoreboard region from this image
# Scoreboard region roughly: x=1000-1250, y=550-650 in original 1280x720
# Scaled to 1120x640: x=875-1094, y=489-578
# But x=1094 > 1120, so maybe different scaling

# Actually 1120/1280 = 0.875, 640/720 = 0.889
# So x=1031*0.875 = 902, y=614*0.889 = 546
# x=1197*0.875 = 1047, y=613*0.889 = 545
# These fit in 1120x640!

print(f"\nScaled coordinates for 1120x640:")
for x in [1031, 1057, 1197, 1223]:
    print(f"  x={x} -> {int(x*0.875)}")
for y in [614, 613, 615, 614]:
    print(f"  y={y} -> {int(y*0.889)}")

# Let's extract using scaled coordinates
scale_x = 1120 / 1280
scale_y = 640 / 720
print(f"\nScale: x={scale_x:.4f}, y={scale_y:.4f}")

# Test on first crop
boxes = {
    'home_tens': [1031, 614, 25, 29],
    'home_ones': [1057, 613, 26, 30],
    'away_tens': [1197, 613, 26, 30],
    'away_ones': [1223, 613, 26, 30],
}
for name, (x, y, w, h) in boxes.items():
    sx, sy = int(x * scale_x), int(y * scale_y)
    sw, sh = int(w * scale_x), int(h * scale_y)
    crop = img[sy:sy+sh, sx:sx+sw]
    print(f"  {name}: box=({sx},{sy},{sw},{sh}) crop_shape={crop.shape} mean={crop.mean():.1f}")