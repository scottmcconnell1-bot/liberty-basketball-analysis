# Negative Result: Color-Based Optical Flow Under Court-Homogeneous Chromatic Conditions

**Date:** 2026-05-28
**Version:** v35 visual audit

## Summary
Color-based optical flow (OF) tracking using HSV thresholding (H: 2-32, S >= 10) was used to generate dense bidirectional trajectory tracks for shot event visualization. The tracks were visually inspected and found to be tracking court-colored pixels, not the basketball.

## Hypothesis
The basketball has a distinct orange color (H: 10-20, S: 100-250) that can be separated from the court background using HSV thresholding, enabling dense OF tracking.

## Evidence Against
1. **HSV measurement at ball position:** Ball at (241, 507) in F236 has HSV ≈ (24.0, 19.0, 99.0). Court floor at (240, 500) has BGR ≈ (92, 98, 99), HSV ≈ (24, 18, 99). These are nearly identical.
2. **Saturation overlap:** The `check_color` threshold (2 <= H <= 32, S >= 10) matches 100% of pixels in a ±10px region around the confirmed ball position. The entire court floor passes.
3. **OF drift:** Optical flow locked onto high-textured stable regions (court lines, player jerseys) rather than the ball, producing tracks that wander across the full frame.
4. **Verification:** 9 out of 10 "shot events" were visually confirmed as non-shots (free throw lineups, inbound passes, dribbling, referee with ball). The color-OF tracks had no semantic relationship to basketball content.

## Root Cause
The court floor and basketball occupy overlapping HSV manifolds in this footage. The saturation channel provides no discriminative power (both the ball and court have S ≈ 15-25 in the V-S plane). The hue channel marginally separates them (ball H ≈ 20-24, court H ≈ 15-20) but the variance within each class exceeds the difference between them.

## Implications
1. **Color-based ball tracking is not viable** for this camera setup. The v14 YOLO-based detector is the only reliable source of ball positions.
2. **Dense synthetic trajectories (spline, OF) are anti-helpful** when the underlying signal is sparse. Smoothness is not evidence.
3. **Gap structure is a feature, not a bug.** The pattern of missing NN detections encodes:
   - Occlusion regime (paint shots disappear into bodies)
   - Visibility range (perimeter shots may have longer unoccluded paths)
   - Shot traffic density
4. **Trajectory features computed from sparse NN detections** (v35/v36) are less precise but semantically valid. Precision must be sacrificed for correctness.

## Follow-up Architecture Decision
All trajectory feature computation going forward must:
- Use **NN detections only** (no color-OF expansion)
- Compute **gap structure features** (mean_gap, max_gap, visibility_ratio, pre/post anchor visibility)
- Track **detection confidence** separately from **trajectory certainty**
- Use **physically-constrained interpolation only** (ballistic curvature, max acceleration, basket-directed motion) if interpolation is needed at all

## Related
- v34: Local backward emergence features (color-OF based, same issue)
- v35: Re-ran OF with correct v14 seeds — still wandered
- v35c: Switched to NN-only positions for visualization
- v36: Adds gap structure features, formalizes confidence dimensions
