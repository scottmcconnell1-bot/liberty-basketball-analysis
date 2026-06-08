"""
Map the 18 court keypoints to the tactical court diagram.
The abdullahtarek tactical_view_converter defines 16 key_points on a 300x161 court (28m x 15m).
The model detects 18 keypoints. We need to figure out which is which.

Keypoint indices from tactical_view_converter.key_points (16 points):
  0: (0, 0)                          - top-left corner
  1: (0, 35)                         - left sideline top
  2: (0, 60)                         - left free-throw area top
  3: (0, 78)                         - left free-throw line
  4: (0, 104)                        - left baseline top
  5: (0, 161)                        - bottom-left corner
  6: (150, 161)                      - bottom center (baseline midpoint)
  7: (150, 0)                        - top center (midcourt)
  8: (85, 60)                        - left free-throw line top
  9: (85, 78)                        - left free-throw line bottom
  10: (300, 161)                     - bottom-right corner
  11: (300, 104)                     - right baseline top
  12: (300, 78)                      - right free-throw line
  13: (300, 60)                      - right free-throw area top
  14: (300, 35)                      - right sideline top
  15: (300, 0)                       - top-right corner
  16: (215, 60)                      - right free-throw line top
  17: (215, 78)                      - right free-throw line bottom

That's 18 keypoints! Perfect match.
"""
import cv2
import numpy as np
from ultralytics import YOLO

# The 18 tactical court keypoints in diagram coords (pixel positions on 300x161 court image)
TACTICAL_KEYPOINTS = [
    (0, 0),           # 0: top-left
    (0, 35),          # 1: left sideline top (~35/161 * 15m = 3.26m from top)
    (0, 60),          # 2: left FT area top
    (0, 78),          # 3: left FT line
    (0, 104),         # 4: left baseline top
    (0, 161),         # 5: bottom-left
    (150, 161),       # 6: bottom center
    (150, 0),         # 7: top center
    (85, 60),         # 8: left FT line top
    (85, 78),         # 9: left FT line bottom
    (300, 161),       # 10: bottom-right
    (300, 104),       # 11: right baseline top
    (300, 78),        # 12: right FT line
    (300, 60),        # 13: right FT area top
    (300, 35),        # 14: right sideline top
    (300, 0),         # 15: top-right
    (215, 60),        # 16: right FT line top
    (215, 78),        # 17: right FT line bottom
]

# Court dimensions
TACTICAL_W = 300
TACTICAL_H = 161
COURT_W_METERS = 28
COURT_H_METERS = 15

# Basket is at 4ft (1.22m) from baseline in high school
# In our tactical view, baseline is at y=161 (bottom), so basket is at:
# 1.22m / 15m * 161 = ~13px from bottom = y = 161 - 13 = 148
# But actually for high school, the rim is 4ft from the baseline
# Let's compute: COURT_H_METERS = 15, so 1px = 15/161 meters
# 4ft = 1.2192m, so from baseline: 1.2192 / (15/161) = 13.05px
# Basket x is centered: 150
# Basket y from bottom: 13px, i.e. y = 161 - 13 = 148

BASKET_Y_FROM_BASELINE_PX = 1.2192 / (COURT_H_METERS / TACTICAL_H)  # ~13px
BASKET_TACTICAL = np.array([150, TACTICAL_H - BASKET_Y_FROM_BASELINE_PX])
print(f"Tactical basket position: {BASKET_TACTICAL}")

# Three-point line: 19ft 9in (6.02m) from basket center
# In tactical px: 6.02 / (COURT_H_METERS/TACTICAL_H) = 64.6px from basket
# That puts the 3PT line at y = 148 - 64.6 = 83.4 from bottom, or y = 148 - 64.6 = 83.4
THREE_PT_DIST_PX = 6.02 / (COURT_H_METERS / TACTICAL_H)
THREE_PT_LINE_Y = BASKET_TACTICAL[1] - THREE_PT_DIST_PX  # distance from basket toward top
print(f"3PT line tactical y: {THREE_PT_LINE_Y:.1f}")
print(f"Basket tactical y: {BASKET_TACTICAL[1]:.1f}")
