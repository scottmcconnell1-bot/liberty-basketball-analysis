# Homography Integration Plan for ai_bridge.py (REVISED)
## Mechanical Line-by-Line Mapping of Real Code to Court-Space Logic

**Status:** Integration Design — For Muse Audit → Gemini Draft → Cursor Implement
**Author:** Hermes (Architect)
**Date:** 2026-10-21
**Prerequisite:** court_homography.py (VETTED, use exactly as-is)

---

## 1. Vetted Module Adoption — Use Exactly As-Is

The file `court_homography.py` is **vetted and frozen**. Do not re-implement. Import and use:

```python
from court_homography import (
    compute_homography,
    image_to_court,
    get_directional_scales_at_hoop,
    apply_homography_to_tracks,
    CourtReferencePoint
)
```

**Signature of `apply_homography_to_tracks` (fixed):**
```python
def apply_homography_to_tracks(tracks: List[Dict], H: np.ndarray) -> List[Dict]:
    """
    Transforms tracks using per-track hoop positions for scale computation.
    Injects: _court_scale_x, _court_scale_y, _hoop_radius_ft
    Returns new list; originals unmodified.
    """
```

**Key behavior:**
- Uses **per-track hoop** for scale computation (line 76-79)
- Carries `hoop[3]` (area) verbatim without scaling (line 84)
- Uses `float64` throughout
- Does **NOT** inject threshold dict — we add that in our wrapper

---

## 2. Exhaustive Constant Mapping (Mechanical Grep of Real ai_bridge.py)

### 2.1 Unitless Ratios (NO SCALING — identical in court space)

| Constant | Location | Use As-Is |
|----------|----------|-----------|
| `0.55` | Lines 917, 920, 1007, 1022, 1024, 1139, 900 | `CROSS_TOL_RATIO` |
| `0.6` | Lines 926, 1073, 1118, 1268 | `COLUMN_RATIO` |
| `0.43` | Lines 1215, 1222 | `DRIFT_RATIO` (note: doc says 0.40, code uses 0.43) |
| `0.40` | Lines 930, 933, 1085 | `CAME_BACK_RATIO` |
| `0.70` | Line 1085 | `CAME_BACK_LATER` |
| `0.85` | Line 1228 | `X_AT_180_RATIO` |
| `0.95` | Line 1270 | `BODD_COL_RATIO` |
| `0.5` | Line 1086 | `COL_RATIO_MIN` |
| `0.65` | Line 867 (short_track) | `SHORT_END_RATIO` |
| `1.0` | Line 876 (short_track) | `BAND_WIDTH_RATIO` |
| `0.85` | Lines 881, 884 (short_track) | `FALLING_WIDTH_RATIO` |
| `0.15` | Line 881 (short_track) | `FALLING_END_W_RATIO` |
| `0.20` | Line 886 (short_track) | `SHORT_END_W_RATIO` |
| `1.15` | court_memory.py line 189 | `RIM_R_RATIO` (core, not in ai_bridge) |

### 2.5 Unitless/Unscaled Literals (INTENTIONALLY LEFT ALONE)

These literals appear in the rule section but are **not thresholds** — they are frame counts, array indices, exponents, or loop bounds. Do not scale or inject.

| Constant | Location | Reason |
|----------|----------|--------|
| `8` | Line 1016 (`min(i + 9, ...)`) | Frame window count (8 samples for crossing) |
| `9` | Line 1016 | Loop bound (8 samples + 1) |
| `3` | Lines 1052, 1076, 1080 | Minimum point counts for column/deep checks |
| `2` | Line 1175 | Frame gap threshold for tracker swap |
| `1` | Line 1113 (`max(1, ...)`) | Frame gap floor |
| `0.5` | Line 1114 (`**0.5`) | Square root exponent (Euclidean distance) |
| `2` | Lines 1114, 1172 (`**2`) | Square exponent (Euclidean distance) |
| `1` | Line 1237 (`max_depth = -1`) | Sentinel value |
| `1` | Line 1277, 1279, 1281 | Counter increments |
| `1` | Line 1113 (`max(1, ...)`) | Frame gap minimum |
| `24` | Line 1050 comment | Target score (not a threshold) |
| `111` | Lines 1292, 1294, 1297 | Total track count (not a threshold) |
| `85` | Lines 1293, 1296 | Target score (not a threshold) |
| `21` | Lines 1293, 1296 | Target missed makes (not a threshold) |
| `5` | Lines 1293, 1296 | Target false makes (not a threshold) |
| `100` | Lines 1294, 1297 | 100% target (not a threshold) |

### 2.2 Vertical Pixel Thresholds (SCALE_Y)

| Constant | Location | Court Variable | Formula |
|----------|----------|----------------|---------|
| `10` | Line 900 (detect_dynamic_entry) | `DYNAMIC_ENTRY_FT` | `10 * scale_y` |
| `20` | Line 1115 | `UPWARD_JUMP_FT` | `20 * scale_y` |
| `40` | Lines 880, 884 (short_track) | `FALLING_VERT_FT` | `40 * scale_y` |
| `50` | Line 1133 | `BALL_STARTS_BELOW_FT` | `50 * scale_y` |
| `70` | Line 875 (short_track) | `BAND_VERT_RANGE_FT` | `70 * scale_y` |
| `80` | Lines 1070, 1079, 1136, 1197 | `COL_ZONE_START_FT` | `80 * scale_y` |
| `100` | Line 1140 | `NEAR_RIM_START_FT` | `100 * scale_y` |
| `150` | Line 886 (short_track) | `SHORT_MAX_Y_FT` | `150 * scale_y` |
| `180` | Lines 1047, 1155, 1199, 1264 | `COL_ZONE_END_FT` | `180 * scale_y` |
| `200` | Line 1118 | `THROUGH_DEPTH_FT` | `200 * scale_y` |

### 2.3 Euclidean Distances (GEOMETRIC MEAN SCALE = √(scale_x × scale_y))

| Constant | Location | Court Variable | Formula |
|----------|----------|----------------|---------|
| `60` | Line 1124 | `MAX_JUMP_FT` | `60 * √(scale_x * scale_y)` |
| `100` | Line 1184 | `SPATIAL_GAP_FT` | `100 * √(scale_x * scale_y)` |

**Rationale:** `jump = √(dx² + dy²)` and `spatial_gap = √(dx² + dy²)` combine horizontal and vertical pixel distances. In court space: `jump_ft = √((dx·scale_x)² + (dy·scale_y)²)`. For isotropic approximation at the hoop, use geometric mean scale.

### 2.4 Velocity Threshold (GEOMETRIC MEAN SCALE)

| Constant | Location | Court Variable | Formula |
|----------|----------|----------------|---------|
| `12` | Line 1119 | `SLOW_VEL_FT_PER_FRAME` | `12 * √(scale_x * scale_y)` |

**Rationale:** `slow = jump / gap <= 12` where jump is Euclidean px/frame. In court space: jump_ft/frame, so threshold scales by geometric mean.

---

## 3. Integration Wrapper (Thin, Non-Breaking)

```python
# In ai_bridge.py (Hermes section), BEFORE run_saved_v6_rule

import math
from court_homography import (
    apply_homography_to_tracks,
    get_directional_scales_at_hoop,
    image_to_court,
)


def _inject_thresholds(track: Dict, scale_x: float, scale_y: float) -> Dict:
    """
    Inject converted thresholds into a single track dict.
    Uses per-track scale (from apply_homography_to_tracks).
    """
    geo_scale = math.sqrt(scale_x * scale_y)
    
    th = {
        # Ratios (unitless)
        'cross_tol_ratio': 0.55,
        'column_ratio': 0.6,
        'drift_ratio': 0.43,
        'came_back_ratio': 0.40,
        'came_back_later': 0.70,
        'x_at_180_ratio': 0.85,
        'bodd_col_ratio': 0.95,
        'col_ratio_min': 0.5,
        'short_end_ratio': 0.65,
        'band_width_ratio': 1.0,
        'falling_width_ratio': 0.85,
        'falling_end_w_ratio': 0.15,
        'short_end_w_ratio': 0.20,
        
        # Vertical (scale_y)
        'dynamic_entry_ft': 10.0 * scale_y,
        'upward_jump_ft': 20.0 * scale_y,
        'falling_vert_ft': 40.0 * scale_y,
        'ball_starts_below_ft': 50.0 * scale_y,
        'band_vert_range_ft': 70.0 * scale_y,
        'col_zone_start_ft': 80.0 * scale_y,
        'near_rim_start_ft': 100.0 * scale_y,
        'short_max_y_ft': 150.0 * scale_y,
        'col_zone_end_ft': 180.0 * scale_y,
        'through_depth_ft': 200.0 * scale_y,
        
        # Euclidean (geometric mean)
        'max_jump_ft': 60.0 * geo_scale,
        'spatial_gap_ft': 100.0 * geo_scale,
        'slow_vel_ft_per_frame': 12.0 * geo_scale,
        
        # Metadata
        '_court_scale_x': scale_x,
        '_court_scale_y': scale_y,
        '_geo_scale': geo_scale,
    }
    
    track['_thresholds'] = th
    return track


def _prepare_tracks_for_rule(
    tracks: List[Dict],
    H: Optional[np.ndarray],
    hoop_img_xy: Optional[Tuple[float, float]]
) -> List[Dict]:
    """
    If H provided: transform to court space + inject thresholds.
    If H not provided: return tracks unchanged (Adrian pixel space).
    """
    if H is None or hoop_img_xy is None:
        return tracks  # Pixel space — Adrian baseline preserved exactly
    
    # Vetted transform (uses per-track hoop for scale)
    court_tracks = apply_homography_to_tracks(tracks, H)
    
    # Inject thresholds using per-track scales
    for track in court_tracks:
        scale_x = track['_court_scale_x']
        scale_y = track['_court_scale_y']
        _inject_thresholds(track, scale_x, scale_y)
    
    return court_tracks
```

---

## 4. Modified `run_saved_v6_rule` — Signature & Entry Point

```python
def run_saved_v6_rule(
    tag_timestamps: List[float],
    v6_tracks_path: str = "/mnt/c/Users/scott/AppData/Local/Temp/v6_tracks.json",
    homography: Optional[np.ndarray] = None,          # NEW
    hoop_img_xy: Optional[Tuple[float, float]] = None  # NEW
) -> Dict[str, Any]:
    """
    Run the EXACT 85-score rule on SAVED v6 tracks, then add 100% fixes.
    
    If homography AND hoop_img_xy are BOTH provided, tracks are transformed
    to court space with injected thresholds. If NEITHER provided, pixel space.
    Raises ValueError if exactly one is provided.
    """
    # ─── STRICT ARGUMENT HANDLING ───
    if (homography is None) != (hoop_img_xy is None):
        raise ValueError(
            "homography and hoop_img_xy must be both provided or both omitted"
        )
    # ────────────────────────────────
    
    import json
    
    with open(v6_tracks_path) as f:
        saved_tracks = json.load(f)
    
    # ─── PRE-TRANSFORM (once) ───
    saved_tracks = _prepare_tracks_for_rule(saved_tracks, homography, hoop_img_xy)
    # ─────────────────────────────
    
    # ... REST OF FUNCTION: replace every constant with th.get('key', default) ...
```

---

## 5. Per-Tag Threshold Extraction (Inside Loop)

```python
for tag_ts in valid_timestamps:
    is_make_true = ground_truth.get(tag_ts, False)
    track = track_by_time[tag_ts]
    
    # ─── THRESHOLD EXTRACTION (every iteration, per-track scales) ───
    th = track.get('_thresholds', {})
    
    # Ratios
    CROSS_TOL_RATIO    = th.get('cross_tol_ratio', 0.55)
    COLUMN_RATIO       = th.get('column_ratio', 0.6)
    DRIFT_RATIO        = th.get('drift_ratio', 0.43)
    CAME_BACK_RATIO    = th.get('came_back_ratio', 0.40)
    CAME_BACK_LATER    = th.get('came_back_later', 0.70)
    X_AT_180_RATIO     = th.get('x_at_180_ratio', 0.85)
    BODD_COL_RATIO     = th.get('bodd_col_ratio', 0.95)
    COL_RATIO_MIN      = th.get('col_ratio_min', 0.5)
    SHORT_END_RATIO    = th.get('short_end_ratio', 0.65)
    BAND_WIDTH_RATIO   = th.get('band_width_ratio', 1.0)
    FALLING_WIDTH_RATIO = th.get('falling_width_ratio', 0.85)
    FALLING_END_W_RATIO = th.get('falling_end_w_ratio', 0.15)
    SHORT_END_W_RATIO  = th.get('short_end_w_ratio', 0.20)
    
    # Vertical (scale_y)
    DYNAMIC_ENTRY      = th.get('dynamic_entry_ft', 10.0)
    UPWARD_JUMP        = th.get('upward_jump_ft', 20.0)
    FALLING_VERT       = th.get('falling_vert_ft', 40.0)
    BALL_STARTS_BELOW  = th.get('ball_starts_below_ft', 50.0)
    BAND_VERT_RANGE    = th.get('band_vert_range_ft', 70.0)
    COL_ZONE_START     = th.get('col_zone_start_ft', 80.0)
    NEAR_RIM_START     = th.get('near_rim_start_ft', 100.0)
    SHORT_MAX_Y        = th.get('short_max_y_ft', 150.0)
    COL_ZONE_END       = th.get('col_zone_end_ft', 180.0)
    THROUGH_DEPTH      = th.get('through_depth_ft', 200.0)
    
    # Euclidean (geo_scale)
    MAX_JUMP           = th.get('max_jump_ft', 60.0)
    SPATIAL_GAP        = th.get('spatial_gap_ft', 100.0)
    SLOW_VEL           = th.get('slow_vel_ft_per_frame', 12.0)
    # ────────────────────────────────────────────────────────────────
    
    hoop = track['hoop']
    hoop_x, hoop_y, hoop_w, hoop_area = hoop
    ...
```

---

## 6. Constant Replacement Map (Every Occurrence in Rule Loop)

| Original Code | Replacement |
|---------------|-------------|
| `0.55 * hoop_w` | `CROSS_TOL_RATIO * hoop_w` |
| `0.6 * hoop_w` | `COLUMN_RATIO * hoop_w` |
| `0.43` (drift) | `DRIFT_RATIO` |
| `0.40` (came_back) | `CAME_BACK_RATIO` |
| `0.70` (came_back later) | `CAME_BACK_LATER` |
| `0.85 * hoop_w` | `X_AT_180_RATIO * hoop_w` |
| `0.95` (bodd_ratio) | `BODD_COL_RATIO` |
| `0.5` (col_ratio_min) | `COL_RATIO_MIN` |
| `180` (net depth) | `COL_ZONE_END` |
| `80` (column start) | `COL_ZONE_START` |
| `60` (max jump) | `MAX_JUMP` |
| `50` (ball starts below) | `BALL_STARTS_BELOW` |
| `100` (near rim start) | `NEAR_RIM_START` |
| `200` (through depth) | `THROUGH_DEPTH` |
| `20` (upward jump) | `UPWARD_JUMP` |
| `5` (bounce up) | `5.0 * th.get('_court_scale_y', 1.0)` |
| `10` (dynamic entry) | `DYNAMIC_ENTRY` |
| `100` (tracker swap) | `SPATIAL_GAP` |
| `12` (slow velocity) | `SLOW_VEL` |
| `70` (band range, short_track) | `BAND_VERT_RANGE` |
| `40` (falling, short_track) | `FALLING_VERT` |
| `150` (short max_y) | `SHORT_MAX_Y` |
| `0.65` (short end_w) | `SHORT_END_RATIO` |
| `0.20` (short end_w) | `SHORT_END_W_RATIO` |
| `0.85` (falling width) | `FALLING_WIDTH_RATIO` |
| `0.15` (falling end_w) | `FALLING_END_W_RATIO` |

**Specific line-by-line replacements in rule loop:**

```python
# Line 1024: if horiz_dist <= 0.55 * hoop_w:
if horiz_dist <= CROSS_TOL_RATIO * hoop_w:

# Line 1073: if horiz_dist <= 0.6 * hoop_w:
if horiz_dist <= COLUMN_RATIO * hoop_w:

# Line 1085: came_back = (widths[widest] - later) >= 0.40 and later <= 0.70
came_back = (widths[widest] - later) >= CAME_BACK_RATIO and later <= CAME_BACK_LATER

# Line 1086: if column_ratio < 0.5 and not came_back:
if column_ratio < COL_RATIO_MIN and not came_back:

# Line 1115: upward = pt2[2] < pt1[2] - 20
upward = pt2[2] < pt1[2] - UPWARD_JUMP

# Line 1118: through = (pt1[2] - hoop_y) >= 200 and abs(pt1[1] - hoop_x) <= 0.6 * hoop_w
through = (pt1[2] - hoop_y) >= THROUGH_DEPTH and abs(pt1[1] - hoop_x) <= COLUMN_RATIO * hoop_w

# Line 1124: if max_jump > 60:
if max_jump > MAX_JUMP:

# Line 1133: if first_ball_y > hoop_y + 50:
if first_ball_y > hoop_y + BALL_STARTS_BELOW:

# Line 1136: fell_on = ... >= 80
fell_on = bool(ball) and (max(pt[2] for pt in ball) - ball[0][2]) >= COL_ZONE_START

# Line 1140: and ball[0][2] <= hoop_y + 100
and ball[0][2] <= hoop_y + NEAR_RIM_START

# Line 1155: floor_frames = [pt for pt in bodd_before_ball if pt[2] - hoop_y > 180]
floor_frames = [pt for pt in bodd_before_ball if pt[2] - hoop_y > COL_ZONE_END]

# Line 1184: if max_frame_gap <= 3 and spatial_gap > 100:
if max_frame_gap <= 3 and spatial_gap > SPATIAL_GAP:

# Line 1197: if x_at_80 is None and y_rel >= 80:
if x_at_80 is None and y_rel >= COL_ZONE_START:

# Line 1199: if y_rel >= 180:
if y_rel >= COL_ZONE_END:

# Line 1222: if sideways > 0.43:
if sideways > DRIFT_RATIO:

# Line 1228: if dist_at_180 > 0.85 * hoop_w and not came_back:
if dist_at_180 > X_AT_180_RATIO * hoop_w and not came_back:

# Line 1248: if y_rel < max_depth - 5:
if y_rel < max_depth - (5.0 * th.get('_court_scale_y', 1.0)):

# Line 1119: slow = jump / gap <= 12 and not upward
slow = jump / gap <= SLOW_VEL and not upward
```

---

## 7. Updated Helper Functions

### 7.1 `detect_dynamic_entry_crossing` (Line 891-903)

```python
def detect_dynamic_entry_crossing(combined_track, hoop_x, hoop_y, hoop_w, thresholds=None):
    if not combined_track or len(combined_track) < 2:
        return None
    first_x = combined_track[0][1]
    first_y = combined_track[0][2]
    
    if thresholds is None:
        DYNAMIC_ENTRY = 10.0
        CROSS_TOL_RATIO = 0.55
    else:
        DYNAMIC_ENTRY = thresholds.get('dynamic_entry_ft', 10.0)
        CROSS_TOL_RATIO = thresholds.get('cross_tol_ratio', 0.55)
    
    if first_y >= hoop_y - DYNAMIC_ENTRY and abs(first_x - hoop_x) <= CROSS_TOL_RATIO * hoop_w:
        if combined_track[1][2] > first_y:
            return 0
    return None
```

**Call site (line 1034):**
```python
cross_idx = detect_dynamic_entry_crossing(combined, hoop_x, hoop_y, hoop_w, track.get('_thresholds'))
```

### 7.2 `short_track_stays_in_net` (Line 856-888)

```python
def short_track_stays_in_net(net_depth_frames, bodd, ball, hoop_x, hoop_y, hoop_w, thresholds=None):
    if thresholds is None:
        SHORT_END_RATIO = 0.65
        BAND_WIDTH_RATIO = 1.0
        FALLING_WIDTH_RATIO = 0.85
        FALLING_END_W_RATIO = 0.15
        SHORT_END_W_RATIO = 0.20
        BAND_VERT_RANGE = 70.0
        FALLING_VERT = 40.0
        SHORT_MAX_Y = 150.0
        COL_ZONE_END = 180.0
    else:
        SHORT_END_RATIO = thresholds.get('short_end_ratio', 0.65)
        BAND_WIDTH_RATIO = thresholds.get('band_width_ratio', 1.0)
        FALLING_WIDTH_RATIO = thresholds.get('falling_width_ratio', 0.85)
        FALLING_END_W_RATIO = thresholds.get('falling_end_w_ratio', 0.15)
        SHORT_END_W_RATIO = thresholds.get('short_end_w_ratio', 0.20)
        BAND_VERT_RANGE = thresholds.get('band_vert_range_ft', 70.0)
        FALLING_VERT = thresholds.get('falling_vert_ft', 40.0)
        SHORT_MAX_Y = thresholds.get('short_max_y_ft', 150.0)
        COL_ZONE_END = thresholds.get('col_zone_end_ft', 180.0)
    
    max_y = max(pt[2] for pt in net_depth_frames) - hoop_y
    end_w = abs(net_depth_frames[-1][1] - hoop_x) / hoop_w
    if end_w > SHORT_END_RATIO:
        return False
    last_ball_frame = ball[-1][0] if ball else -1
    after = [pt for pt in (bodd or []) if pt[0] > last_ball_frame]

    def width(pt):
        return abs(pt[1] - hoop_x) / hoop_w

    band = [pt for pt in after if max_y < (pt[2] - hoop_y) <= max_y + BAND_VERT_RANGE]
    if band and min(width(pt) for pt in band) > BAND_WIDTH_RATIO:
        return False
    if after:
        y0 = after[0][2]
        falling = [pt for pt in after if pt[2] > y0 + FALLING_VERT]
        if falling and min(width(pt) for pt in falling) > FALLING_WIDTH_RATIO and end_w > FALLING_END_W_RATIO:
            return False
    in_column_fall = bool(after) and any(
        pt[2] > after[0][2] + FALLING_VERT and width(pt) <= FALLING_WIDTH_RATIO for pt in after
    )
    if max_y < SHORT_MAX_Y and end_w > SHORT_END_W_RATIO and not in_column_fall:
        return False
    return True
```

**Call site (line 1255):**
```python
if not short_track_stays_in_net(net_depth_frames, bodd, ball, hoop_x, hoop_y, hoop_w, track.get('_thresholds')):
```

---

## 8. Deep Identity Guarantee Test

```python
def test_adrian_identity_transform():
    """
    H=I (identity homography) must produce numerically-identical tracks and scores.
    Every track has unique hoop position — test ALL tracks, not just first.
    Uses np.isclose with tight tolerance for floating-point metadata.
    """
    import json
    import numpy as np
    
    H_identity = np.eye(3, dtype=np.float64)  # float64 per vetted module
    hoop_img = (0.0, 0.0)  # arbitrary; scale_x=scale_y=1.0 at origin
    
    with open("v6_tracks.json") as f:
        original = json.load(f)
    
    # Transform
    transformed = _prepare_tracks_for_rule(original, H_identity, hoop_img)
    
    # Numerical equality on ALL keys for ALL tracks
    for orig, trans in zip(original, transformed):
        # Hoop (unique per track) — exact equality expected
        assert trans['hoop'][0] == orig['hoop'][0]  # x
        assert trans['hoop'][1] == orig['hoop'][1]  # y
        assert trans['hoop'][2] == orig['hoop'][2]  # width (diameter)
        assert trans['hoop'][3] == orig['hoop'][3]  # area (verbatim)
        
        # Ball points — exact equality expected
        for (_, ox, oy), (_, tx, ty) in zip(orig.get('ball', []), trans.get('ball', [])):
            assert tx == ox and ty == oy
        
        # BODD points — exact equality expected
        for (_, ox, oy), (_, tx, ty) in zip(orig.get('bodd', []), trans.get('bodd', [])):
            assert tx == ox and ty == oy
        
        # Injected metadata — use tight tolerance for float64 computation artifacts
        assert np.isclose(trans['_court_scale_x'], 1.0, atol=1e-12)
        assert np.isclose(trans['_court_scale_y'], 1.0, atol=1e-12)
        assert np.isclose(trans['_hoop_radius_ft'], orig['hoop'][2] / 2.0, atol=1e-12)
        assert np.isclose(trans['_thresholds']['_court_scale_x'], 1.0, atol=1e-12)
        assert np.isclose(trans['_thresholds']['_court_scale_y'], 1.0, atol=1e-12)
        assert np.isclose(trans['_thresholds']['_geo_scale'], 1.0, atol=1e-12)
        # All thresholds equal hardcoded defaults (tolerance for float arithmetic)
        assert np.isclose(trans['_thresholds']['col_zone_start_ft'], 80.0, atol=1e-9)
        assert np.isclose(trans['_thresholds']['col_zone_end_ft'], 180.0, atol=1e-9)
        assert np.isclose(trans['_thresholds']['max_jump_ft'], 60.0, atol=1e-9)
        assert np.isclose(trans['_thresholds']['spatial_gap_ft'], 100.0, atol=1e-9)
        assert np.isclose(trans['_thresholds']['slow_vel_ft_per_frame'], 12.0, atol=1e-9)
        # ... all 27 threshold keys with atol=1e-9
    
    # Score dict exact equality (integers, no tolerance needed)
    adrian_ts = [t['t'] for t in original]
    r1 = run_saved_v6_rule(adrian_ts, "v6_tracks.json")
    r2 = run_saved_v6_rule(adrian_ts, "v6_tracks.json", H_identity, hoop_img)
    assert r1 == r2  # Every key, every value
```

### 8.1 Baseline Anchor Test (Mandatory)

```python
def test_adrian_baseline_preserved():
    """
    The new code WITHOUT homography arguments must produce the EXACT
    Adrian baseline score: 99/111 right, 12 makes missed, 0 misses called makes.
    This runs before any Notus court-space test.
    """
    with open("v6_tracks.json") as f:
        original = json.load(f)
    
    adrian_ts = [t['t'] for t in original]
    result = run_saved_v6_rule(adrian_ts, "v6_tracks.json")  # No homography args
    
    # Exact baseline from OLLAMA.md
    assert result['right'] == 99
    assert result['makes_missed'] == 12
    assert result['misses_called_makes'] == 0
    assert result['total_tags'] == 111
    assert result['applied_to_core'] is False
```

---

## 9. Validation Checklist (For Muse)

| Check | Method |
|-------|--------|
| Vetted `court_homography.py` used without modification | Import only; no re-implementation |
| All 27+ constants mapped | Mechanical grep + table above |
| Euclidean constants (60, 100, 12) use geometric mean scale | `geo_scale = √(scale_x * scale_y)` |
| Vertical constants use scale_y | 10 constants mapped |
| Ratios unchanged | 13 ratios mapped |
| Unitless/unscaled literals identified & left alone | Table in §2.5 |
| Strict argument handling | `ValueError` if XOR |
| Deep identity test | Per-track hoop equality + full score dict equality (np.isclose for metadata) |
| Baseline anchor test | Adrian 99/111, 12 missed, 0 false makes WITHOUT homography |
| `short_track_stays_in_net` updated | Thresholds param passed |
| `detect_dynamic_entry_crossing` updated | Thresholds param passed |
| `applied_to_core` remains False | Unchanged |
| No float32 | Vetted module uses float64; we match |

---

## 10. Files to Modify

| File | Changes |
|------|---------|
| `ai_bridge.py` | 1. Import from `court_homography`<br>2. Add `_inject_thresholds`, `_prepare_tracks_for_rule`<br>3. Update `run_saved_v6_rule` signature + entry transform + threshold extraction + constant replacement<br>4. Update `detect_dynamic_entry_crossing` + `short_track_stays_in_net` signatures + threshold usage |
| `gemini-upload/ai_bridge.py` | Copy for Gemini prototyping |
| `gemini-upload/validate_integration.py` | New: runs identity test + Notus improvement test |

---

## 11. Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Missed constant in 300-line loop | Systematic grep + table above covers every numeric literal in rule section |
| Per-track scale variation | Vetted `apply_homography_to_tracks` computes scale per-track; we use those |
| Float64 vs float32 | Vetted module uses float64; we use float64 throughout |
| Notus homography missing | Caller handles; our function requires both args or neither |

---

**END OF REVISED INTEGRATION PLAN**

*This plan mechanically maps every constant in the real `ai_bridge.py` to the correct scale. Uses vetted `court_homography.py` exactly. No skeleton code — ready for Muse veto check.*