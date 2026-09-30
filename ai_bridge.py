"""Sandbox for Hermes and other open-source experiments.

The core sequence does not import this module. A make on the film is still
`ball_through_rim` or `net_moved_after_shot` in the core. Methods below are
experiments. They are not the game count. Hand results back with
`validated_stats`, which returns JSON and sets applied_to_core to false.
"""

import json
import math
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
import cv2
import numpy as np

@dataclass
class DetectionData:
    """Standardized detection data contract"""
    frame_number: int
    timestamp_ms: float
    object_class: str  # 'person' or 'ball'
    confidence: float
    x_center: float
    y_center: float
    width: float
    height: float
    tracker_id: Optional[int] = None
    jersey_read: Optional[str] = None
    jersey_confidence: Optional[float] = None

@dataclass
class TrackingData:
    """Standardized tracking output"""
    detection_id: int
    tracker_id: int
    frame_number: int
    timestamp_ms: float

@dataclass 
class PossessionData:
    """Standardized possession output"""
    frame_number: int
    player_id: str  # cluster_id or similar stable identifier
    has_ball: bool
    ball_distance: float

@dataclass
class ShotData:
    """Standardized shot detection output"""
    timestamp_ms: float
    peak_frame: int
    ball_rise: float
    lateral_travel: float
    peak_x: float
    peak_y: float
    secondary_pass: bool = False

@dataclass
class MakeMissData:
    """Standardized make/miss output"""
    shot_timestamp_ms: float
    is_make: bool
    confidence: float
    detection_method: str  # 'rim_net', 'net_motion', 'hybrid'

class BasketballStatsAdapter:
    """
    Adapter layer that handles OpenCode/Cursor computer vision logic
    while maintaining strict interface with core pipeline
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.frame_times = []  # For VFR handling
        self.last_frame_time = 0
        self.tracker_state = {}  # For ID synchronization
        self.next_tracker_id = 1
        
    def process_video_frame(self, frame: np.ndarray, frame_number: int, 
                          timestamp_ms: float) -> List[DetectionData]:
        """
        Process raw video frame and return standardized detections
        Handles variable frame rate issues
        """
        # Store timing info for VFR compensation
        self.frame_times.append((frame_number, timestamp_ms))
        if len(self.frame_times) > 30:  # Keep rolling window
            self.frame_times.pop(0)
            
        # Core detection would happen here via YOLO models
        # This is where OpenCode/Cursor would plug in their models
        # For now, return empty list - core pipeline handles actual detection
        detections = []
        
        return detections
    
    def synchronize_tracker_ids(self, raw_detections: List[Dict]) -> List[TrackingData]:
        """
        Solves Tracking ID De-synchronization problem
        Maintains stable IDs across occlusions and player crossings
        """
        tracking_results = []
        
        for det in raw_detections:
            # Use spatial features + appearance for ID association
            detection_id = det.get('id')
            centroid = (det.get('x_center', 0), det.get('y_center', 0))
            features = self._extract_features(det)
            
            # Find best match in current tracker state
            best_match_id = self._find_best_tracker_match(centroid, features)
            
            if best_match_id is None:
                # Assign new ID
                best_match_id = self.next_tracker_id
                self.next_tracker_id += 1
                
            # Update tracker state
            self.tracker_state[best_match_id] = {
                'centroid': centroid,
                'features': features,
                'last_seen': det.get('frame_number', 0),
                'age': self.tracker_state.get(best_match_id, {}).get('age', 0) + 1
            }
            
            tracking_results.append(TrackingData(
                detection_id=detection_id,
                tracker_id=best_match_id,
                frame_number=det.get('frame_number', 0),
                timestamp_ms=det.get('timestamp_ms', 0.0)
            ))
            
        # Clean up old trackers
        self._cleanup_trackers()
        
        return tracking_results
    
    def detect_ball_hoop_interaction(self, ball_positions: List[Tuple[float, float, int]], 
                                   hoop_position: Tuple[float, float],
                                   frame_width: int, frame_height: int) -> List[MakeMissData]:
        """
        Solves Strict Bounding Box Collisions problem
        Uses trajectory vector line intersection instead of exact box overlap
        """
        results = []
        
        if len(ball_positions) < 2:
            return results
            
        hoop_x, hoop_y = hoop_position
        hoop_radius = self.config.get('hoop_radius', 75.0)  # pixels
        
        # Analyze ball trajectory segments
        for i in range(len(ball_positions) - 1):
            x1, y1, f1 = ball_positions[i]
            x2, y2, f2 = ball_positions[i + 1]
            
            # Create trajectory vector from current to next position
            dx = x2 - x1
            dy = y2 - y1
            
            # Check if line segment intersects hoop circle
            if self._line_circle_intersection(
                (x1, y1), (x2, y2), (hoop_x, hoop_y), hoop_radius):
                
                # Additional validation: check if it's a shooting motion
                if self._is_shooting_motion(ball_positions, i, hoop_position):
                    # Determine if it's a make or miss
                    make_data = self._classify_shot_outcome(
                        ball_positions, i, hoop_position, frame_width, frame_height)
                    if make_data:
                        results.append(make_data)
                        
        return results
    
    def compensate_variable_framerate(self, nominal_fps: float) -> float:
        """
        Solves Vanishing Frame Frame-Rate Desync
        Returns time-compensated FPS for threshold calculations
        """
        if len(self.frame_times) < 2:
            return nominal_fps
            
        # Calculate actual time between first and last frame in window
        first_frame, first_time = self.frame_times[0]
        last_frame, last_time = self.frame_times[-1]
        
        frame_delta = last_frame - first_frame
        time_delta = (last_time - first_time) / 1000.0  # Convert to seconds
        
        if time_delta > 0:
            actual_fps = frame_delta / time_delta
            # Return smoothed FPS to avoid jitter
            return (actual_fps + nominal_fps) / 2.0
            
        return nominal_fps
    
    def _extract_features(self, detection: Dict) -> Dict[str, float]:
        """Extract appearance features for tracker association"""
        features = {}
        # In a real implementation, this would extract HOG, color histograms, etc.
        # For now, use basic geometric features
        features['aspect_ratio'] = detection.get('width', 1) / max(detection.get('height', 1), 1)
        features['area'] = detection.get('width', 0) * detection.get('height', 0)
        features['confidence'] = detection.get('confidence', 0.0)
        return features
    
    def _find_best_tracker_match(self, centroid: Tuple[float, float], 
                                features: Dict[str, float]) -> Optional[int]:
        """Find best existing tracker for this detection"""
        best_id = None
        best_score = float('inf')
        max_distance = self.config.get('max_tracker_distance', 100.0)
        
        for tracker_id, state in self.tracker_state.items():
            # Skip if tracker is too old
            age_penalty = min(state.get('age', 0) * 0.1, 2.0)
            
            # Distance cost
            prev_centroid = state.get('centroid', (0, 0))
            distance = math.sqrt(
                (centroid[0] - prev_centroid[0])**2 + 
                (centroid[1] - prev_centroid[1])**2
            )
            
            # Feature similarity cost (simplified)
            feature_cost = 0.0
            if 'aspect_ratio' in features and 'aspect_ratio' in state.get('features', {}):
                feature_cost += abs(features['aspect_ratio'] - state['features']['aspect_ratio'])
                
            total_cost = distance + age_penalty + feature_cost
            
            if total_cost < max_distance and total_cost < best_score:
                best_score = total_cost
                best_id = tracker_id
                
        return best_id
    
    def _cleanup_trackers(self, max_age: int = 30):
        """Remove trackers that haven't been seen recently"""
        current_frame = max([state['last_seen'] for state in self.tracker_state.values()], default=0)
        to_remove = []
        
        for tracker_id, state in self.tracker_state.items():
            if current_frame - state['last_seen'] > max_age:
                to_remove.append(tracker_id)
                
        for tracker_id in to_remove:
            del self.tracker_state[tracker_id]
    
    def _line_circle_intersection(self, p1: Tuple[float, float], p2: Tuple[float, float],
                                 circle_center: Tuple[float, float], radius: float) -> bool:
        """Check if line segment intersects circle"""
        x1, y1 = p1
        x2, y2 = p2
        cx, cy = circle_center
        
        # Vector from p1 to p2
        dx = x2 - x1
        dy = y2 - y1
        
        # Vector from p1 to circle center
        fx = cx - x1
        fy = cy - y1
        
        # Solve quadratic equation for intersection
        a = dx*dx + dy*dy
        b = 2*(fx*dx + fy*dy)
        c = fx*fx + fy*fy - radius*radius
        
        discriminant = b*b - 4*a*c
        
        if discriminant < 0:
            return False  # No intersection
            
        # Check if intersection points are within segment
        discriminant = math.sqrt(discriminant)
        t1 = (-b - discriminant) / (2*a)
        t2 = (-b + discriminant) / (2*a)
        
        return (0 <= t1 <= 1) or (0 <= t2 <= 1)
    
    def _is_shooting_motion(self, ball_positions: List[Tuple[float, float, int]], 
                           start_index: int, hoop_position: Tuple[float, float]) -> bool:
        """Determine if ball motion looks like a shot toward hoop"""
        if start_index + 2 >= len(ball_positions):
            return False
            
        # Get trajectory leading up to potential shot
        x1, y1, _ = ball_positions[start_index]
        x2, y2, _ = ball_positions[start_index + 1]
        x3, y3, _ = ball_positions[start_index + 2]
        
        hoop_x, hoop_y = hoop_position
        
        # Check if ball is moving generally toward hoop
        vec_to_hoop1 = (hoop_x - x1, hoop_y - y1)
        vec_to_hoop2 = (hoop_x - x2, hoop_y - y2)
        vec_to_hoop3 = (hoop_x - x3, hoop_y - y3)
        
        # Motion vectors
        motion1 = (x2 - x1, y2 - y1)
        motion2 = (x3 - x2, y3 - y2)
        
        # Dot product to check alignment (simplified)
        dot1 = motion1[0]*vec_to_hoop1[0] + motion1[1]*vec_to_hoop1[1]
        dot2 = motion2[0]*vec_to_hoop2[0] + motion2[1]*vec_to_hoop2[1]
        
        return dot1 > 0 and dot2 > 0  # Moving toward hoop
    
    def _classify_shot_outcome(self, ball_positions: List[Tuple[float, float, int]], 
                              start_index: int, hoop_position: Tuple[float, float],
                              frame_width: int, frame_height: int) -> Optional[MakeMissData]:
        """Classify whether shot resulted in make or miss"""
        # This would use net detector, rim detector, or trajectory analysis
        # For now, return a basic classification
        
        hoop_x, hoop_y = hoop_position
        
        # Find peak height of ball trajectory around the shot
        peak_y = float('inf')
        peak_index = start_index
        
        # Look at frames around the intersection point
        look_ahead = min(10, len(ball_positions) - start_index - 1)
        for i in range(start_index, start_index + look_ahead + 1):
            if i < len(ball_positions):
                _, y, _ = ball_positions[i]
                if y < peak_y:
                    peak_y = y
                    peak_index = i
        
        if peak_index >= len(ball_positions):
            return None
            
        peak_x, peak_y, peak_frame = ball_positions[peak_index]
        
        # Simple classification: if ball goes below hoop level after peak, likely made
        # This is simplistic - real implementation would use net/rim detectors
        frames_after_peak = ball_positions[peak_index+1:peak_index+6] if peak_index+1 < len(ball_positions) else []
        
        below_hoop_count = sum(1 for _, y, _ in frames_after_peak if y > hoop_y + 20)
        total_after = len(frames_after_peak)
        
        is_make = below_hoop_count > (total_after * 0.3) if total_after > 0 else False
        
        # Calculate metrics
        if start_index < len(ball_positions):
            start_x, start_y, _ = ball_positions[start_index]
            ball_rise = start_y - peak_y  # Negative y is up in image coords
            lateral_travel = abs(peak_x - start_x)
        else:
            ball_rise = 0
            lateral_travel = 0
            
        return MakeMissData(
            shot_timestamp_ms=ball_positions[start_index][2] if start_index < len(ball_positions) else 0,
            is_make=is_make,
            confidence=0.7,  # Placeholder
            detection_method='trajectory_analysis'
        )

def validated_stats(payload: dict) -> dict:
    """JSON object for the core. Nothing here is applied to the film count."""
    if not isinstance(payload, dict):
        raise TypeError("stats payload must be a dict")
    stats = json.loads(json.dumps(payload, default=str))
    return {"source": "ai_bridge", "applied_to_core": False, "stats": stats}


def create_adapter_from_config(config_path: str = None) -> BasketballStatsAdapter:
    """Factory function to create adapter with configuration"""
    import json
    import os
    
    config = {}
    if config_path and os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
            
    return BasketballStatsAdapter(config)

# Example usage for OpenCode/Cursor:
# adapter = BasketballStatsAdapter()
# detections = adapter.process_video_frame(frame, frame_num, timestamp_ms)
# tracking = adapter.synchronize_tracker_ids(raw_yolo_detections)
# makes_misses = adapter.detect_ball_hoop_interaction(ball_track, hoop_pos, width, height)