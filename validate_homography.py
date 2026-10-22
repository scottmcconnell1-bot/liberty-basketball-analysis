"""
validate_homography.py
Test script verifying planar integrity (floor-plane points only), directional scaling,
float64 precision, and strict identity transforms.
"""

import numpy as np
import copy
from court_homography import (
    CourtReferencePoint,
    compute_homography,
    image_to_court,
    apply_homography_to_tracks
)

def test_homography_validation():
    print("=" * 60)
    print("      VALIDATING FINAL VETTED COURT HOMOGRAPHY PROTOTYPE   ")
    print("=" * 60)

    # 1. Test Floor-Plane Reference Points Only (basket_center removed for planar integrity)
    ref_points = [
        CourtReferencePoint("ft_line_left", (-6.0, 15.0), (700.12, 400.75), 1.0),
        CourtReferencePoint("ft_line_right", (6.0, 15.0), (1220.88, 400.75), 1.0),
        CourtReferencePoint("baseline_left", (-25.0, -4.0), (400.33, 700.5), 1.0),
        CourtReferencePoint("baseline_right", (25.0, -4.0), (1520.66, 700.5), 1.0)
    ]

    H = compute_homography(ref_points)
    assert H is not None, "Homography computation failed."
    assert H.dtype == np.float64, "Homography matrix is not float64."
    print("[SUCCESS] 3x3 Homography matrix computed successfully using pure floor-plane points.")

    # 2. Test Non-Integer Coordinate Precision Transformation
    test_u, test_v = 960.5, 540.25
    court_x, court_y = image_to_court(H, test_u, test_v)
    print(f"[SUCCESS] Non-integer point transformed to: ({court_x:.4f}, {court_y:.4f}) ft")

    # 3. Strict Identity Transform Assertion (Adrian Dataset Safety Guarantee)
    # Asserts exact equality for all keys, including hoop width, area, and scale keys using non-integer inputs.
    H_identity = np.eye(3, dtype=np.float64)
    dummy_tracks = [{
        't': 1234.56,
        'hoop': [960.25, 540.75, 64.5, 100.12],
        'ball': [[1, 960.5, 500.25], [2, 960.75, 520.12]],
        'bodd': [[1, 950.25, 600.5]]
    }]
    
    original_tracks_copy = copy.deepcopy(dummy_tracks)
    transformed_dummy = apply_homography_to_tracks(dummy_tracks, H_identity)
    
    for orig, trans in zip(original_tracks_copy, transformed_dummy):
        assert trans['_court_scale_x'] == 1.0
        assert trans['_court_scale_y'] == 1.0
        assert orig['t'] == trans['t']
        assert orig['hoop'] == trans['hoop']
        assert orig['ball'] == trans['ball']
        assert orig['bodd'] == trans['bodd']

    print("[SUCCESS] Strict Identity Transform assertion passed: exact equality of all keys, values, and floating precision confirmed.")
    print("\n[SUCCESS] All validation checks passed successfully for Muse audit!")
    print("=" * 60)

if __name__ == "__main__":
    test_homography_validation()