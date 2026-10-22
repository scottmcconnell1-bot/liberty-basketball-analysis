"""
court_homography.py
Revised calibration and coordinate transformation module using OpenCV homography.
Enforces float64 precision, directional scaling, floor-plane mapping, inlier gates, and area protection.
"""

import numpy as np
import cv2
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass

@dataclass
class CourtReferencePoint:
    name: str
    court_xy: Tuple[float, float]   # Floor-plane feet (X, Y), origin = basket center (0,0), +Y toward midcourt
    image_xy: Tuple[float, float]   # Pixel coordinates (u, v)
    confidence: float

def compute_homography(ref_points: List[CourtReferencePoint]) -> Optional[np.ndarray]:
    """
    Computes the 3x3 homography matrix mapping image pixels to floor-plane court coordinates in float64.
    Enforces an inlier gate: if sum(mask) < 4, returns None.
    """
    if len(ref_points) < 4:
        return None

    image_pts = np.array([pt.image_xy for pt in ref_points], dtype=np.float64)
    court_pts = np.array([pt.court_xy for pt in ref_points], dtype=np.float64)

    H, mask = cv2.findHomography(image_pts, court_pts, cv2.RANSAC, 3.0)
    if H is None or mask is None:
        return None
    
    # Check RANSAC inlier count
    if np.sum(mask) < 4:
        return None

    return H.astype(np.float64)

def image_to_court(homography: np.ndarray, x_img: float, y_img: float) -> Tuple[float, float]:
    """
    Transforms a single image pixel coordinate (x_img, y_img) to court coordinates in feet (X, Y) using float64.
    """
    pt = np.array([float(x_img), float(y_img), 1.0], dtype=np.float64)
    pt_court = homography @ pt
    if pt_court[2] != 0:
        return (float(pt_court[0] / pt_court[2]), float(pt_court[1] / pt_court[2]))
    return (0.0, 0.0)

def get_directional_scales_at_hoop(homography: np.ndarray, hoop_img: Tuple[float, float]) -> Tuple[float, float]:
    """
    Computes independent directional feet-per-pixel scale factors (scale_x, scale_y) at the hoop location.
    """
    eps = 1.0
    p0 = np.array([float(hoop_img[0]), float(hoop_img[1]), 1.0], dtype=np.float64)
    px = np.array([float(hoop_img[0]) + eps, float(hoop_img[1]), 1.0], dtype=np.float64)
    py = np.array([float(hoop_img[0]), float(hoop_img[1]) + eps, 1.0], dtype=np.float64)
    
    c0 = homography @ p0; c0 = c0[:2] / c0[2]
    cx = homography @ px; cx = cx[:2] / cx[2]
    cy = homography @ py; cy = cy[:2] / cy[2]
    
    scale_x = float(np.linalg.norm(cx - c0) / eps)
    scale_y = float(np.linalg.norm(cy - c0) / eps)
    return scale_x, scale_y

def apply_homography_to_tracks(tracks: List[Dict], H: np.ndarray) -> List[Dict]:
    """
    Transforms track coordinates from image pixels to court feet using homography H and directional scaling.
    Carries over hoop area verbatim without scaling.
    """
    transformed = []
    for track in tracks:
        new_track = track.copy()
        
        hoop = track.get('hoop', [0.0, 0.0, 0.0, 0.0])
        hoop_img_xy = (float(hoop[0]), float(hoop[1]))
        
        scale_x, scale_y = get_directional_scales_at_hoop(H, hoop_img_xy)
        hoop_ft_x, hoop_ft_y = image_to_court(H, hoop_img_xy[0], hoop_img_xy[1])
        
        hoop_diameter_ft = float(hoop[2]) * scale_x
        # Carry over the area (hoop[3]) verbatim from the original track without scaling
        hoop_area_verbatim = float(hoop[3]) if len(hoop) > 3 else 0.0
        
        new_track['hoop'] = [
            float(hoop_ft_x),
            float(hoop_ft_y),
            float(hoop_diameter_ft),
            hoop_area_verbatim
        ]
        
        if 'ball' in new_track:
            new_track['ball'] = [
                [int(frame), float(image_to_court(H, x, y)[0]), float(image_to_court(H, x, y)[1])] 
                for frame, x, y in new_track['ball']
            ]
            
        if 'bodd' in new_track:
            new_track['bodd'] = [
                [int(frame), float(image_to_court(H, x, y)[0]), float(image_to_court(H, x, y)[1])] 
                for frame, x, y in new_track['bodd']
            ]
            
        new_track['_court_scale_x'] = float(scale_x)
        new_track['_court_scale_y'] = float(scale_y)
        new_track['_hoop_radius_ft'] = float(hoop_diameter_ft / 2.0)
        transformed.append(new_track)
        
    return transformed