# Bird's Eye (Top-Down) Perspective Transform Architecture
## Homography-Based Court Mapping for Gym-Consistency Problem

**Status:** Design Phase — For Gemini Prototyping
**Author:** Hermes (Architect)
**Date:** 2026-10-21 (revised post-Muse audit)
**Review Gate:** Must pass Muse veto before Cursor implements

---

## 1. Problem Statement

The current pipeline uses **sideline camera coordinates** (image pixels) for all make/miss logic. This fails on Notus Q1 because:
- Different camera angle (Notus gym vs Adrian gym)
- Different lighting/exposure affecting detector confidence
- Different court markings visibility affecting hoop/key detection
- The `hoop_x`, `hoop_y`, `hoop_w` in image pixels are **not comparable** across gyms

**Solution:** Map every detection into a **standardized top-down court coordinate system** (feet from basket, floor plane Z=0) using a homography. The make/miss rules then operate in **court space**, not pixel space.

---

## 2. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PIPELINE OVERVIEW                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  RAW VIDEO FRAME                                                    │
│       │                                                             │
│       ▼                                                             │
│  ┌──────────────────┐    CALIBRATION PHASE (once per gym/session)  │
│  │ DETECT KEY POINTS │ ──────────────────────────────────────────▶ │
│  │ (FLOOR-PLANE ONLY:│       1. Detect 4+ court corners/lines      │
│  │  baseline, FT,    │       2. Map to known NFHS floor dimensions │
│  │  lane, 3-pt arc)  │       3. Compute H (3x3 homography matrix)  │
│  └────────┬─────────┘       4. Save H to calibration JSON          │
│           │                                                         │
│           ▼                                                         │
│  ┌──────────────────┐    RUNTIME (per frame)                       │
│  │ TRANSFORM ALL    │ ──────────────────────────────────────────▶  │
│  │ DETECTIONS via H │       For each ball/hoop/player detection:   │
│  └────────┬─────────┘       (x_ft, y_ft) = H @ (u_px, v_px, 1)    │
│           │                                                         │
│           ▼                                                         │
│  ┌──────────────────┐    MAKE/MISS LOGIC (UNCHANGED SEMANTICS)     │
│  │ RUN EXISTING     │ ──────────────────────────────────────────▶  │
│  │ RULES IN COURT   │       column_ratio, drift, net_depth, etc.   │
│  │ SPACE            │       now use COURT coordinates (feet)       │
│  └──────────────────┘                                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Calibration Strategy (Answering Question 1)

### 3.1 Reference Court Model — NFHS Floor Plane (Z=0)

**Origin:** Basket center projected to floor, **(0, 0) ft**  
**Axes:** +X = right from basket perspective, +Y = toward midcourt  
**All points below are on the floor (Z=0).** No rim, backboard, or 3D points.

| Court Element | Court Coordinates (ft) | Notes |
|---------------|------------------------|-------|
| **Basket center (floor)** | (0, 0) | Origin — projection of rim center to floor |
| **Baseline** | y = -4 | 4 ft behind basket (backboard at baseline) |
| **Free-throw line** | y = +15 | 15 ft from basket toward midcourt |
| **Lane lines** | x = ±6 | 12 ft wide lane, runs from baseline to FT line |
| **Lane corners (4 pts)** | (±6, -4), (±6, +15) | Baseline-lane & FT-lane intersections |
| **Sideline at baseline** | x = ±25 | Court width 50 ft |
| **Sideline at FT line** | x = ±25 | Parallel sidelines |
| **3-pt arc** | x² + y² = 19.75² | Radius 19.75 ft from basket, y ≥ -4 |
| **3-pt arc ∩ sideline** | (±22, y_arc) | Where arc meets sideline (y ≈ +11.5 ft) |
| **Midcourt** | y = +38 | Half-court (84/2 - 4 = 38 ft from basket) |

**Key correction from audit:** FT line (+15) and baseline (-4) are on **opposite sides of origin**. Both were negative in v1.

### 3.2 Image-Side Correspondence Points — FLOOR PLANE ONLY

| Point ID | Court Coords (ft, Z=0) | Image Detection Method |
|----------|------------------------|------------------------|
| `baseline_left` | (-25, -4) | Baseline ∩ left sideline |
| `baseline_right` | (25, -4) | Baseline ∩ right sideline |
| `ft_left` | (-6, +15) | FT line ∩ left lane line |
| `ft_right` | (6, +15) | FT line ∩ right lane line |
| `lane_baseline_left` | (-6, -4) | Lane line ∩ baseline |
| `lane_baseline_right` | (6, -4) | Lane line ∩ baseline |
| `sideline_ft_left` | (-25, +15) | Sideline ∩ FT line extension |
| `sideline_ft_right` | (25, +15) | Sideline ∩ FT line extension |
| `three_pt_left` | (-22, +11.5) | 3-pt arc ∩ left sideline (approx) |
| `three_pt_right` | (22, +11.5) | 3-pt arc ∩ right sideline (approx) |

**EXCLUDED (non-planar):** `basket_center` (rim is 10 ft above floor), `backboard_*` (vertical), any 3D point.

**Minimum:** 4 non-collinear floor points. **Target:** 8-10 floor points. RANSAC with reprojection error < 2 px.

### 3.3 Calibration Trigger & Persistence

- **Per-gym, per-session:** Calibrate on first "dead ball / zoom-out / free-throw" frame where **floor lines** are visible
- **Save to:** `calibrations/{gym_id}_homography.json`
  ```json
  {
    "gym_id": "notus_gym",
    "H_img2court": [[...], [...], [...]],  // 3x3: image px → court ft
    "H_court2img": [[...], [...], [...]],  // inverse
    "court_model": "NFHS",
    "reference_points": [
      {"name": "ft_left", "court_ft": [-6, 15], "image_px": [342, 512], "confidence": 0.92},
      ...
    ],
    "scale_x_ft_per_px_at_hoop": 0.0312,  // ∂x_ft/∂u_px at basket projection
    "scale_y_ft_per_px_at_hoop": 0.0298,  // ∂y_ft/∂v_px at basket projection
    "calibrated_at_frame": 1234,
    "calibrated_at_timestamp_ms": 45000
  }
  ```
- **Re-calibrate if:** `FrameCourtMemory.zoom` changes >15% or `pan_dx` > 100px

### 3.4 Integration with `FrameCourtMemory`

`FrameCourtMemory` already tracks: `key`, `detected_hoop`, `zoom`, `dead_ball`, `pan_dx`.

**New field:** `homography: np.ndarray | None` — 3×3 H matrix for this session/gym.

When `observe()` detects dead-ball/zoom-out with visible floor lines → `calibrate_homography()` → store H.

---

## 4. Ball Coordinate Transformation (Answering Question 2)

### 4.1 Transform Function

```python
def image_to_court(H: np.ndarray, u: float, v: float) -> Tuple[float, float]:
    """
    Apply homography: court_ft = H @ image_px_homogeneous
    H maps (u, v, 1) → (x_ft, y_ft, w)  →  (x_ft/w, y_ft/w)
    """
    pt = np.array([u, v, 1.0], dtype=np.float32)
    pt_court = H @ pt
    if pt_court[2] != 0:
        return (pt_court[0] / pt_court[2], pt_court[1] / pt_court[2])
    return (0.0, 0.0)
```

### 4.2 What Gets Transformed

| Data | Current Space | New Space | Usage in Rules |
|------|---------------|-----------|----------------|
| Ball track `(frame, u, v)` | Image pixels | Court feet (x, y) | Crossing, column_ratio, drift |
| Hoop `(hoop_x, hoop_y, hoop_w)` | Image pixels | Court feet (x, y) + **diameter_ft** | All threshold comparisons |
| BODD track `(frame, u, v)` | Image pixels | Court feet (x, y) | Short-make continuation |
| **Vertical thresholds** (80px, 180px, 20px) | Pixels (v-direction) | **Feet (y-direction)** via `scale_y` | Column zone, drift, bounce |
| **Horizontal thresholds** (hoop_w ratios, 60px jump) | Pixels (u-direction) | **Feet (x-direction)** via `scale_x` | Crossing tolerance, box jump |

### 4.3 Directional Scale Factors at Hoop (Critical Fix)

```python
def get_directional_scales_at_hoop(H: np.ndarray, hoop_img: Tuple[float, float]) -> Tuple[float, float]:
    """
    Compute LOCAL scale factors at the basket projection point.
    Returns (scale_x_ft_per_px, scale_y_ft_per_px)
    Uses Jacobian of homography: J = ∂(x,y)/∂(u,v)
    """
    u, v = hoop_img
    eps = 1.0  # 1 pixel perturbation
    
    # Homogeneous coordinates
    p0 = np.array([u, v, 1.0], dtype=np.float32)
    pu = np.array([u + eps, v, 1.0], dtype=np.float32)
    pv = np.array([u, v + eps, 1.0], dtype=np.float32)
    
    # Project to court
    c0 = H @ p0; c0 = c0[:2] / c0[2]
    cu = H @ pu; cu = cu[:2] / cu[2]
    cv = H @ pv; cv = cv[:2] / cv[2]
    
    # Scale factors: court ft per image px
    scale_x = abs(cu[0] - c0[0]) / eps  # ∂x_ft/∂u_px
    scale_y = abs(cv[1] - c0[1]) / eps  # ∂y_ft/∂v_px
    
    return (scale_x, scale_y)
```

### 4.4 Threshold Conversion — PER-DIRECTION

| Pixel Threshold | Direction | Court Threshold | Formula |
|-----------------|-----------|-----------------|---------|
| `0.55 * hoop_w_px` (crossing horiz tolerance) | Horizontal (u) | `0.55 * hoop_diameter_ft` | Ratio — unitless, **unchanged** |
| `0.6 * hoop_w_px` (column check) | Horizontal (u) | `0.6 * hoop_diameter_ft` | Ratio — unitless, **unchanged** |
| `0.43` (drift veto) | Horizontal (u) | `0.43` | Ratio — unitless, **unchanged** |
| `80 px` (column zone start) | **Vertical (v)** | `80 * scale_y` ft | **scale_y only** |
| `180 px` (column zone end / drift measure) | **Vertical (v)** | `180 * scale_y` ft | **scale_y only** |
| `60 px` (max ball box jump) | **Horizontal (u)** | `60 * scale_x` ft | **scale_x only** |
| `20 px` (upward bounce) | **Vertical (v)** | `20 * scale_y` ft | **scale_y only** |
| `hoop_w_px` (diameter) | Horizontal (u) | `hoop_w_px * scale_x` ft | **scale_x only** |

**Hoop diameter in feet:** `hoop_diameter_ft = track['hoop'][2] * scale_x`  
**Hoop radius in feet:** `hoop_radius_ft = hoop_diameter_ft / 2`

All ratio thresholds (0.55, 0.6, 0.43) are **pure numbers** — no conversion needed.

---

## 5. Integration with `run_saved_v6_rule` (Answering Question 3)

### 5.1 Non-Invasive Integration — Pre-Transform Tracks

**Principle:** `run_saved_v6_rule` signature and logic **unchanged**. Tracks are transformed **before** calling it.

```python
def apply_homography_to_tracks(
    tracks: List[Dict], 
    H: np.ndarray, 
    hoop_img_xy: Tuple[float, float]
) -> List[Dict]:
    """
    Transform track coordinates from image pixels to court feet.
    Returns NEW list; original tracks unmodified.
    """
    scale_x, scale_y = get_directional_scales_at_hoop(H, hoop_img_xy)
    hoop_ft = image_to_court(H, hoop_img_xy[0], hoop_img_xy[1])
    hoop_diameter_ft = tracks[0]['hoop'][2] * scale_x  # hoop[2] = width_px (diameter)
    hoop_radius_ft = hoop_diameter_ft / 2.0
    
    transformed = []
    for track in tracks:
        new_track = track.copy()
        
        # Hoop: [x_ft, y_ft, diameter_ft, area]
        new_track['hoop'] = [
            hoop_ft[0], hoop_ft[1], hoop_diameter_ft, track['hoop'][3]
        ]
        
        # Ball: [(frame, x_ft, y_ft), ...]
        new_track['ball'] = [
            [frame, *image_to_court(H, x, y)] for frame, x, y in track.get('ball', [])
        ]
        
        # BODD: [(frame, x_ft, y_ft), ...]
        new_track['bodd'] = [
            [frame, *image_to_court(H, x, y)] for frame, x, y in track.get('bodd', [])
        ]
        
        # Metadata for downstream use (not read by run_saved_v6_rule)
        new_track['_court_scale_x'] = scale_x
        new_track['_court_scale_y'] = scale_y
        new_track['_hoop_radius_ft'] = hoop_radius_ft
        new_track['_hoop_diameter_ft'] = hoop_diameter_ft
        
        transformed.append(new_track)
    return transformed
```

### 5.2 Modified `run_saved_v6_rule` — Optional Parameters Only

```python
def run_saved_v6_rule(
    tag_timestamps: List[float],
    v6_tracks_path: str = DEFAULT_PATH,
    homography: Optional[np.ndarray] = None,      # NEW: optional
    hoop_img_xy: Optional[Tuple[float, float]] = None  # NEW: optional
) -> Dict[str, Any]:
    with open(v6_tracks_path) as f:
        saved_tracks = json.load(f)
    
    # Transform to court space IF homography provided
    if homography is not None and hoop_img_xy is not None:
        saved_tracks = apply_homography_to_tracks(saved_tracks, homography, hoop_img_xy)
    
    # ... REST OF FUNCTION 100% UNCHANGED ...
    # It reads hoop[2] as "hoop width", ball[i][1:] as x,y — now in feet
```

### 5.3 Adrian Set Preservation — Strict Identity Test

**Adrian tracks are NEVER transformed.** They stay in pixel space (homography=None).

**Identity Test (must pass exactly):**
```python
def test_adrian_identity_transform():
    """H=I, hoop_img=(960,540) → court tracks MUST equal pixel tracks exactly."""
    H_identity = np.eye(3, dtype=np.float32)
    hoop_img = (960.0, 540.0)
    
    with open("v6_tracks.json") as f:
        original = json.load(f)
    
    transformed = apply_homography_to_tracks(original, H_identity, hoop_img)
    
    for orig, trans in zip(original, transformed):
        # Exact float equality on ALL keys
        assert trans['hoop'][0] == orig['hoop'][0]  # x
        assert trans['hoop'][1] == orig['hoop'][1]  # y
        assert trans['hoop'][2] == orig['hoop'][2]  # width (diameter)
        assert trans['hoop'][3] == orig['hoop'][3]  # area
        
        for (_, ox, oy), (_, tx, ty) in zip(orig.get('ball', []), trans.get('ball', [])):
            assert tx == ox and ty == oy
        
        for (_, ox, oy), (_, tx, ty) in zip(orig.get('bodd', []), trans.get('bodd', [])):
            assert tx == ox and ty == oy
        
        # Metadata must match expected identity values
        assert trans['_court_scale_x'] == 1.0
        assert trans['_court_scale_y'] == 1.0
        assert trans['_hoop_radius_ft'] == orig['hoop'][2] / 2.0
        assert trans['_hoop_diameter_ft'] == orig['hoop'][2]
    
    # Score must be identical
    result_px = run_saved_v6_rule(adrian_ts, "v6_tracks.json")
    result_ct = run_saved_v6_rule(adrian_ts, "v6_tracks.json", H_identity, hoop_img)
    assert result_px == result_ct  # dict equality
```

---

## 6. Calibration Implementation Plan (For Gemini)

### 6.1 Module: `court_homography.py`

```python
# court_homography.py
import numpy as np
import cv2
import json
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, asdict

@dataclass
class CourtReferencePoint:
    name: str
    court_xy: Tuple[float, float]   # feet, Z=0 floor plane, origin = basket center
    image_xy: Tuple[float, float]   # pixels (u, v)
    confidence: float

@dataclass
class GymCalibration:
    gym_id: str
    H_img2court: np.ndarray         # 3x3 image px → court ft
    H_court2img: np.ndarray         # 3x3 court ft → image px
    court_model: str                # "NFHS"
    reference_points: List[CourtReferencePoint]
    scale_x_at_hoop: float          # ft/px horizontal at basket
    scale_y_at_hoop: float          # ft/px vertical at basket
    calibrated_at_frame: int
    calibrated_at_ms: float

NFHS_FLOOR_POINTS = {
    "baseline_left":      (-25.0, -4.0),
    "baseline_right":     (25.0, -4.0),
    "ft_left":            (-6.0, 15.0),
    "ft_right":           (6.0, 15.0),
    "lane_baseline_left": (-6.0, -4.0),
    "lane_baseline_right": (6.0, -4.0),
    "sideline_ft_left":   (-25.0, 15.0),
    "sideline_ft_right":  (25.0, 15.0),
    # 3-pt arc intersections (optional, harder to detect)
    # "three_pt_left":      (-22.0, 11.5),
    # "three_pt_right":     (22.0, 11.5),
}

def detect_floor_keypoints(frame: np.ndarray, court_memory: FrameCourtMemory) -> List[CourtReferencePoint]:
    """
    Detect FLOOR-PLANE keypoints only (Z=0).
    Uses: Hough lines for baseline/sidelines/lane/FT, intersections for corners.
    NO rim, NO backboard, NO 3D points.
    """
    pass

def compute_homography(ref_points: List[CourtReferencePoint]) -> Optional[np.ndarray]:
    """
    cv2.findHomography with RANSAC.
    Input: court_xy (ft) → image_xy (px).
    Returns H_img2court (3x3) or None if <4 inliers.
    """
    if len(ref_points) < 4:
        return None
    src = np.array([p.court_xy for p in ref_points], dtype=np.float32)  # court ft
    dst = np.array([p.image_xy for p in ref_points], dtype=np.float32)  # image px
    H, mask = cv2.findHomography(src, dst, cv2.RANSAC, 2.0)  # court→image
    if H is None or mask.sum() < 4:
        return None
    return np.linalg.inv(H)  # return image→court

def calibrate_gym(video_path: str, gym_id: str, court_memory: FrameCourtMemory) -> Optional[GymCalibration]:
    """Find calibration frame, detect floor keypoints, compute H, save, return GymCalibration."""
    pass

def load_calibration(gym_id: str) -> Optional[GymCalibration]:
    """Load from calibrations/{gym_id}_homography.json"""
    pass
```

### 6.2 Floor Keypoint Detectors (Z=0 Only)

| Keypoint | Detector |
|----------|----------|
| Baseline corners | Hough lines on court mask → baseline (horizontal) ∩ sidelines (vertical) |
| FT line corners | Hough lines → FT line (horizontal) ∩ lane lines (vertical) |
| Lane-baseline corners | Lane lines (from `court_memory.key`) ∩ baseline |
| Sideline-FT corners | Sidelines (vertical) ∩ FT line (horizontal) |

**Use `court_memory.key` (KeyPolygon)** — it already tracks the lane rectangle in image pixels. Its 4 corners = `lane_baseline_left`, `lane_baseline_right`, `ft_left`, `ft_right`.

**Sidelines & baseline:** Detect via color masking (court surface) + Hough lines, or template match known court markings.

---

## 7. Validation Protocol (For Muse Audit)

### 7.1 Success Criteria

| Criterion | Threshold |
|-----------|-----------|
| Adrian Q1-Q3 (111 tracks) **pixel space** | 99 right, 0 false makes, ≤12 makes missed |
| Adrian **identity transform** (H=I) | **Exact dict equality** on all track keys + score |
| Notus Q1 (31 tracks) **court space** | >24 right, 0 false makes |
| Notus Q1 **court space** | ≤6 makes missed |
| Calibration reprojection error | <2 px RMS on floor reference points |

### 7.2 Test Script

```python
# validate_homography.py
def test_adrian_unchanged():
    result = run_saved_v6_rule(adrian_ts, "v6_tracks.json")
    assert result['right'] == 99 and result['misses_called_makes'] == 0

def test_adrian_identity_transform():
    H_identity = np.eye(3, dtype=np.float32)
    hoop_img = (960.0, 540.0)
    
    with open("v6_tracks.json") as f:
        original = json.load(f)
    transformed = apply_homography_to_tracks(original, H_identity, hoop_img)
    
    for o, t in zip(original, transformed):
        assert t['hoop'][0] == o['hoop'][0]
        assert t['hoop'][1] == o['hoop'][1]
        assert t['hoop'][2] == o['hoop'][2]
        assert t['hoop'][3] == o['hoop'][3]
        for (_, ox, oy), (_, tx, ty) in zip(o.get('ball', []), t.get('ball', [])):
            assert tx == ox and ty == oy
        for (_, ox, oy), (_, tx, ty) in zip(o.get('bodd', []), t.get('bodd', [])):
            assert tx == ox and ty == oy
        assert t['_court_scale_x'] == 1.0
        assert t['_court_scale_y'] == 1.0
        assert t['_hoop_radius_ft'] == o['hoop'][2] / 2.0
        assert t['_hoop_diameter_ft'] == o['hoop'][2]
    
    r1 = run_saved_v6_rule(adrian_ts, "v6_tracks.json")
    r2 = run_saved_v6_rule(adrian_ts, "v6_tracks.json", H_identity, hoop_img)
    assert r1 == r2

def test_notus_improvement():
    calib = load_calibration("notus_gym")
    result = run_saved_v6_rule(notus_ts, "notus_q1_v6_tracks.json", 
                               calib.H_img2court, calib.reference_hoop_img)
    assert result['right'] > 24 and result['misses_called_makes'] == 0
```

---

## 8. File Structure

```
liberty-basketball-analysis/
├── ai_bridge.py                 # Hermes: apply_homography_to_tracks(), optional params
├── court_homography.py          # NEW: calibration + transform (Gemini prototypes)
├── court_memory.py              # Unchanged
├── calibrations/
│   ├── notus_gym_homography.json
│   └── adrian_gym_homography.json  # identity (H=I) for testing
├── gemini-upload/
│   ├── court_homography.py
│   └── validate_homography.py
└── docs/architecture/
    └── BIRDS_EYE_HOMOGRAPHY_DESIGN.md
```

---

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Floor lines not visible on Notus | Medium | High | Fallback: 4-corner baseline/sideline only; else pixel space |
| Scale varies across court (perspective) | High | Medium | Local scale at hoop only — all rules operate at hoop |
| Camera bump mid-game | Low | High | Re-calibrate on every dead-ball/zoom-out frame |
| Adrian regression | Low | Critical | Identity test enforces exact equality; Adrian never transformed |
| Notus court-space ≤ pixel-space | Medium | Medium | Abandon; pixel baseline remains |

---

## 10. Next Steps (For Gemini)

1. Prototype `court_homography.py` with synthetic test: known NFHS floor points → known image points → verify H recovers court coords within 0.1 ft
2. Implement `detect_floor_keypoints()` using `court_memory.key` (lane) + Hough lines (baseline/sidelines/FT)
3. Write `validate_homography.py` with the three strict tests above
4. Test on Notus Q1 video: find calibration frame, compute H, transform tracks, score
5. Deliver to Muse for veto check before Cursor integration

---

## 11. Appendix: Corrected Coordinate System

```
COURT SPACE (Top-Down, Feet, Origin = Basket Center, Z=0 Floor Plane)
          
          +Y (toward midcourt)
           |
     38 ft ●─────────────────────────────● (midcourt)
           │                             │
           │                             │
     15 ft ●───────────────●─────────────●  ← FREE-THROW LINE (y=+15)
           │   LANE 12ft   │             │
           │   (x=±6)      │             │
           │               │             │
      0 ft ●───────────────●─────────────●  ← BASKET CENTER (0,0)
           │   LANE        │             │
           │   (x=±6)      │             │
      -4 ft ●───────────────●─────────────●  ← BASELINE (y=-4)
           │               │             │
           ▼
          -Y (behind basket)

X range: -25 ft (left sideline) to +25 ft (right sideline)
3-pt arc: x² + y² = 19.75² for y ≥ -4

IMAGE SPACE (Pixels, Origin = Top-Left)
(0,0) ●──────────────────► +u (right)
      │
      │
      ▼
     +v (down)

HOMOGRAPHY H_img2court: [u, v, 1]ᵗ → [x_ft, y_ft, 1]ᵗ (up to scale)
```

---

**END OF REVISED DESIGN DOCUMENT**

*Fixed per Muse audit: (1) FT line at +15, baseline at -4 (opposite sides of origin); (2) Only Z=0 floor points in homography; (3) Separate scale_x/scale_y for horizontal/vertical thresholds; (4) Strict identity test with exact float equality on all track keys including metadata.*