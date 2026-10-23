import cv2
import json
import os
import sys
from typing import List, Dict, Any, Tuple

# Predefined standard court keypoint labels (Z=0 floor plane)
DEFAULT_KEYPOINTS = [
    "ft_line_left",
    "ft_line_right",
    "baseline_left",
    "baseline_right"
]

clicked_points = []
display_image = None
scale_factor = 1.0
current_label_idx = 0

def mouse_callback(event, x, y, flags, param):
    global clicked_points, display_image, scale_factor, current_label_idx
    if event == cv2.EVENT_LBUTTONDOWN:
        if current_label_idx >= len(DEFAULT_KEYPOINTS):
            print("[INFO] All predefined keypoints selected. Press 'S' to save or 'R' to reset.")
            return
        label = DEFAULT_KEYPOINTS[current_label_idx]
        orig_u, orig_v = float(x / scale_factor), float(y / scale_factor)
        clicked_points.append({"name": label, "image_xy": [round(orig_u, 2), round(orig_v, 2)]})
        print(f"[CLICKED] {label} -> Original Image: ({orig_u:.2f}, {orig_v:.2f})")
        cv2.circle(display_image, (x, y), 6, (0, 255, 0), -1)
        cv2.putText(display_image, f"{current_label_idx + 1}. {label}", (x + 10, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
        current_label_idx += 1
        cv2.imshow("Court Point Picker", display_image)

def run_picker(image_path: str, output_path: str = "manual_calibration.json"):
    global display_image, scale_factor, clicked_points, current_label_idx
    if not os.path.exists(image_path):
        print(f"[ERROR] Image not found: {image_path}"); return
    orig_img = cv2.imread(image_path)
    if orig_img is None:
        print(f"[ERROR] Failed to load image: {image_path}"); return
    orig_h, orig_w = orig_img.shape[:2]
    scale_factor = min(1280 / orig_w, 720 / orig_h, 1.0)
    disp_w, disp_h = int(orig_w * scale_factor), int(orig_h * scale_factor)
    display_image = cv2.resize(orig_img, (disp_w, disp_h), interpolation=cv2.INTER_AREA)
    cv2.namedWindow("Court Point Picker")
    cv2.setMouseCallback("Court Point Picker", mouse_callback)
    print("=" * 60 + "\nBASKETBALL COURT MANUAL POINT PICKER\n" + "=" * 60)
    print("1. Click points in order: FT Left, FT Right, Baseline Left, Baseline Right\n2. 'S': Save | 'R': Reset | 'Q': Quit")
    while True:
        cv2.imshow("Court Point Picker", display_image)
        key = cv2.waitKey(20) & 0xFF
        if key == ord('s') or key == ord('S'):
            with open(output_path, 'w') as f: json.dump(clicked_points, f, indent=2)
            print(f"[SUCCESS] Saved points to {output_path}"); break
        elif key == ord('r') or key == ord('R'):
            clicked_points, current_label_idx = [], 0
            display_image = cv2.resize(orig_img, (disp_w, disp_h), interpolation=cv2.INTER_AREA)
            print("[RESET] Points cleared.")
        elif key == ord('q') or key == ord('Q') or key == 27:
            break
    cv2.destroyAllWindows()

if __name__ == "__main__":
    target_image = sys.argv[1] if len(sys.argv) > 1 else "calibration_frame.png"
    run_picker(target_image)
