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

# Half-court mode: any two points on the center line, far apart. Saved next to the
# lane points above; those four are kept.
HALFCOURT_KEYPOINTS = [
    "halfcourt_a",
    "halfcourt_b"
]

# Lane points in floor feet (origin = hoop center, +Y toward midcourt). NFHS: the rim
# is 5.25 ft in from the baseline, the free-throw line 19 ft from the baseline, and
# the lane 12 ft wide. These are the same in every gym; court length is not.
LANE_COURT_XY = {
    "ft_line_left": (-6.0, 13.75),
    "ft_line_right": (6.0, 13.75),
    "baseline_left": (-6.0, -5.25),
    "baseline_right": (6.0, -5.25),
}

clicked_points = []
display_image = None
scale_factor = 1.0
current_label_idx = 0
active_labels = DEFAULT_KEYPOINTS
saved_points = []

def mouse_callback(event, x, y, flags, param):
    global clicked_points, display_image, scale_factor, current_label_idx
    if event == cv2.EVENT_LBUTTONDOWN:
        if current_label_idx >= len(active_labels):
            print("[INFO] All predefined keypoints selected. Press 'S' to save or 'R' to reset.")
            return
        label = active_labels[current_label_idx]
        orig_u, orig_v = float(x / scale_factor), float(y / scale_factor)
        clicked_points.append({"name": label, "image_xy": [round(orig_u, 2), round(orig_v, 2)]})
        print(f"[CLICKED] {label} -> Original Image: ({orig_u:.2f}, {orig_v:.2f})")
        cv2.circle(display_image, (x, y), 6, (0, 255, 0), -1)
        cv2.putText(display_image, f"{current_label_idx + 1}. {label}", (x + 10, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
        current_label_idx += 1
        cv2.imshow("Court Point Picker", display_image)

def report_half_court(points: List[Dict[str, Any]]) -> None:
    """Prints this gym's measured half court and the court length it implies."""
    from court_homography import CourtReferencePoint, compute_homography
    from ai_bridge import half_court_y_from_image_points, HOOP_TO_BASELINE_FT

    by_name = {p["name"]: p["image_xy"] for p in points}
    refs = [CourtReferencePoint(n, LANE_COURT_XY[n], tuple(by_name[n]), 1.0)
            for n in LANE_COURT_XY if n in by_name]
    H = compute_homography(refs)
    if H is None:
        print("[WARN] Need all four lane points in the file to measure half court.")
        return
    center = [tuple(by_name[n]) for n in HALFCOURT_KEYPOINTS if n in by_name]
    half_court_y = half_court_y_from_image_points(H, center)
    if half_court_y is None:
        print("[WARN] Half-court clicks are not where a high-school half court can be. Run again and re-click.")
        return
    court_length = 2.0 * (half_court_y + HOOP_TO_BASELINE_FT)
    print(f"[MEASURED] Half court is {half_court_y:.2f} ft from the hoop "
          f"(about a {court_length:.1f} ft court).")


def run_picker(image_path: str, output_path: str = "manual_calibration.json", halfcourt: bool = False):
    global display_image, scale_factor, clicked_points, current_label_idx, active_labels, saved_points
    active_labels = HALFCOURT_KEYPOINTS if halfcourt else DEFAULT_KEYPOINTS
    saved_points = []
    if halfcourt:
        if not os.path.exists(output_path):
            print(f"[ERROR] {output_path} not found. Click the four lane points first."); return
        with open(output_path) as f:
            saved_points = [p for p in json.load(f) if p["name"] not in HALFCOURT_KEYPOINTS]
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
    if halfcourt:
        print("1. Click two points on the HALF-COURT line, far apart\n2. 'S': Save | 'R': Reset | 'Q': Quit")
    else:
        print("1. Click points in order: FT Left, FT Right, Baseline Left, Baseline Right\n2. 'S': Save | 'R': Reset | 'Q': Quit")
    while True:
        cv2.imshow("Court Point Picker", display_image)
        key = cv2.waitKey(20) & 0xFF
        if key == ord('s') or key == ord('S'):
            if halfcourt and len(clicked_points) < len(HALFCOURT_KEYPOINTS):
                print("[INFO] Click both half-court points before saving."); continue
            with open(output_path, 'w') as f: json.dump(saved_points + clicked_points, f, indent=2)
            print(f"[SUCCESS] Saved points to {output_path}")
            if halfcourt:
                report_half_court(saved_points + clicked_points)
            break
        elif key == ord('r') or key == ord('R'):
            clicked_points, current_label_idx = [], 0
            display_image = cv2.resize(orig_img, (disp_w, disp_h), interpolation=cv2.INTER_AREA)
            print("[RESET] Points cleared.")
        elif key == ord('q') or key == ord('Q') or key == 27:
            break
    cv2.destroyAllWindows()

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--halfcourt"]
    target_image = args[0] if args else "calibration_frame.png"
    run_picker(target_image, halfcourt="--halfcourt" in sys.argv[1:])
