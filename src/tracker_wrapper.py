"""
tracker_wrapper.py

Provides a small, robust wrapper around production-grade multi-object trackers.

API:
  initialize(tracker_name='bytetrack', device='cpu', config={})
    - Attempts to initialize a tracker backend. Preferred backend is ByteTrack
      (try imports from common package names). If ByteTrack imports fail, this
      will automatically fall back to deep_sort_realtime. If neither package is
      available, a bundled lightweight centroid tracker is used as a final
      fallback.

  track_frames(detections_per_frame) -> list[dict]
    - detections_per_frame: list of frames, each frame is a list of detection dicts
      A detection dict should contain at minimum:
        - 'detection_id': unique id for the input detection (user-provided)
        - 'bbox': [x1, y1, x2, y2]  (pixel coordinates)
        - optional: 'score' (float), 'class' (str)

    - Returns: a list (one per frame) of dicts mapping detection_id -> tracker_id

Notes:
  - This wrapper avoids hard failures during import and logs which backend is
    active. Code that uses this wrapper should accept that tracker IDs are
    integers and stable within a single call to track_frames.

This file intentionally tries a number of possible ByteTrack import names. If
you're installing trackers system-wide or into the project's .venv, prefer
ByteTrack (fast, accurate). If ByteTrack is difficult to build on your system,
install deep_sort_realtime which is a pure-Python fallback with fewer
installation requirements.

"""

from typing import List, Dict, Any, Optional
import sys
import traceback

# Module-level tracker instance used by initialize/track_frames
_TRACKER = None
_BACKEND_NAME = None


class TrackerInterface:
    """Minimal interface wrapper that our implementations follow.

    Concrete implementations must provide an "update" method accepting a list
    of detection dicts (with 'bbox' etc.) and returning a list of tracks where
    each track exposes 'track_id' and 'bbox' at minimum.
    """

    def update(self, detections: List[Dict[str, Any]]):
        raise NotImplementedError


class _SimpleCentroidTracker(TrackerInterface):
    """A tiny centroid-based tracker used as a final fallback. Stable and
    predictable for unit tests and environments without native trackers.

    This tracker creates integer track IDs starting at 1 and matches by nearest
    centroid with a small max_distance threshold. It does not implement
    advanced features like re-identification or motion models.
    """

    def __init__(self, max_distance: float = 80.0):
        self.max_distance = float(max_distance)
        self.tracks = {}  # track_id -> {'centroid': (x,y)}
        self.next_id = 1

    def _centroid(self, bbox):
        x1, y1, x2, y2 = bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def update(self, detections: List[Dict[str, Any]]):
        # detections: list of dict with 'bbox' and 'detection_id'
        assignments = []
        assigned_tracks = {}

        for det in detections:
            bbox = det.get('bbox')
            if bbox is None:
                continue
            cx, cy = self._centroid(bbox)
            # find nearest existing track
            best_id = None
            best_dist = None
            for t_id, t in self.tracks.items():
                tx, ty = t['centroid']
                dist = ((cx - tx) ** 2 + (cy - ty) ** 2) ** 0.5
                if dist <= self.max_distance and (best_dist is None or dist < best_dist):
                    best_dist = dist
                    best_id = t_id
            if best_id is not None:
                # assign to existing
                self.tracks[best_id]['centroid'] = (cx, cy)
                assignments.append({'track_id': int(best_id), 'bbox': bbox, 'detection_id': det.get('detection_id')})
                assigned_tracks[best_id] = True
            else:
                # new track
                t_id = self.next_id
                self.next_id += 1
                self.tracks[t_id] = {'centroid': (cx, cy)}
                assignments.append({'track_id': int(t_id), 'bbox': bbox, 'detection_id': det.get('detection_id')})
                assigned_tracks[t_id] = True

        # Note: we do not remove old tracks (simple lifetime), keeping IDs stable
        return assignments


class _DeepSortWrapper(TrackerInterface):
    """Wrapper around deep_sort_realtime.DeepSort tracker. Keeps our
    TrackInterface so track_frames can remain backend-agnostic.

    This wrapper lazily imports deep_sort_realtime so import-time failures are
    visible to the parent initializer.
    """

    def __init__(self, device: str = 'cpu', config: Optional[Dict[str, Any]] = None):
        # lazy import
        try:
            # deep_sort_realtime exposes a helper class under deepsort_tracker
            from deep_sort_realtime.deepsort_tracker import DeepSort
        except Exception:
            # try alternate import path
            from deep_sort_realtime import DeepSort
        self._ds = DeepSort(max_age=config.get('max_age', 30) if config else 30,
                            n_init=config.get('n_init', 3) if config else 3,
                            nn_budget=config.get('nn_budget', 100) if config else 100)

    def _to_deepsort_format(self, detections: List[Dict[str, Any]]):
        # DeepSort expects a list of tuples/lists: [x1,y1,x2,y2, score, class]
        out = []
        for d in detections:
            bbox = d.get('bbox')
            score = float(d.get('score', 1.0))
            cls = d.get('class', 0)
            if bbox is None:
                continue
            out.append([bbox[0], bbox[1], bbox[2], bbox[3], score, cls])
        return out

    def update(self, detections: List[Dict[str, Any]]):
        formatted = self._to_deepsort_format(detections)
        tracks = self._ds.update_tracks(formatted, frame=None)
        # update_tracks returns list of Track objects with .track_id and .to_tlbr()
        assignments = []
        for trk in tracks:
            if not trk.is_confirmed():
                continue
            tid = int(trk.track_id)
            tlbr = trk.to_tlbr()
            # try to match to original detection by bbox intersection (best-effort)
            matched_det_id = None
            for d in detections:
                if _iou_bbox(d.get('bbox'), tlbr) > 0.5:
                    matched_det_id = d.get('detection_id')
                    break
            assignments.append({'track_id': tid, 'bbox': tlbr, 'detection_id': matched_det_id})
        return assignments


class _ByteTrackWrapper(TrackerInterface):
    """Wrapper around a ByteTrack implementation. We try to be flexible with
    import names and available classes so the wrapper works across common
    packaging variations.
    """

    def __init__(self, device: str = 'cpu', config: Optional[Dict[str, Any]] = None):
        # Try multiple possible ByteTrack import paths
        bt = None
        tried = []
        # Common package names to attempt
        candidates = ['bytetrack', 'bytetrack_pytorch', 'bytetrax', 'bytetrack_pytorch']
        for name in candidates:
            try:
                bt = __import__(name)
                break
            except Exception as e:
                tried.append((name, repr(e)))
        if bt is None:
            # Try specific class imports (some packages expose BYTETracker)
            try:
                from yolox.tracker.byte_tracker import BYTETracker
                bt = {'BYTETracker': BYTETracker}
            except Exception:
                raise ImportError('ByteTrack import failed; attempted: %s' % tried)

        # Create a tracker instance depending on discovered module layout
        if hasattr(bt, 'BYTETracker'):
            BYTETracker = getattr(bt, 'BYTETracker')
            # signature for BYTETracker often: BYTETracker(opt, frame_rate)
            # but building tracker instance requires config objects in many
            # distributions; we'll try a minimal instantiation and otherwise
            # fail loudly so the caller can fallback.
            try:
                # some packages expose a default config dict/class
                self._bt = BYTETracker(config or {}, fps=config.get('fps', 30) if config else 30)
            except Exception:
                # try alternate constructor (opt)
                try:
                    self._bt = BYTETracker(config or {})
                except Exception:
                    raise
        elif hasattr(bt, 'Tracker'):
            TrackerCls = getattr(bt, 'Tracker')
            self._bt = TrackerCls(device=device, **(config or {}))
        else:
            # If import returned a module object (like bytetrack) inspect it
            # for common factory function names
            if hasattr(bt, 'create_tracker'):
                self._bt = bt.create_tracker(device=device, **(config or {}))
            else:
                raise ImportError('Unrecognized ByteTrack package layout; cannot construct tracker')

    def update(self, detections: List[Dict[str, Any]]):
        # ByteTrack update signature varies; we try to call a couple of common
        # methods: update() or track() or step(). We convert our detections to
        # [x1,y1,x2,y2,score]
        dets = []
        for d in detections:
            bbox = d.get('bbox')
            if bbox is None:
                continue
            score = float(d.get('score', 1.0))
            dets.append([bbox[0], bbox[1], bbox[2], bbox[3], score])

        # Try common method names
        if hasattr(self._bt, 'update'):
            tracks = self._bt.update(dets)
        elif hasattr(self._bt, 'track'):
            tracks = self._bt.track(dets)
        elif hasattr(self._bt, 'step'):
            tracks = self._bt.step(dets)
        else:
            raise RuntimeError('Underlying ByteTrack object has no known update/track method')

        # Standardize output: expect an iterable of track objects/tuples
        assignments = []
        for t in tracks:
            # Accept either tuple/list (x1,y1,x2,y2,track_id) or object with .track_id and .tlbr()
            if isinstance(t, (list, tuple)) and len(t) >= 5:
                x1, y1, x2, y2, tid = t[0], t[1], t[2], t[3], int(t[4])
                assignments.append({'track_id': tid, 'bbox': [x1, y1, x2, y2], 'detection_id': None})
            else:
                tid = getattr(t, 'track_id', getattr(t, 'id', None))
                if tid is None:
                    continue
                if hasattr(t, 'tlbr'):
                    bbox = t.tlbr()
                elif hasattr(t, 'to_tlbr'):
                    bbox = t.to_tlbr()
                else:
                    bbox = None
                assignments.append({'track_id': int(tid), 'bbox': bbox, 'detection_id': None})
        return assignments


# small helper
def _iou_bbox(a, b):
    # a and b are [x1,y1,x2,y2]
    if a is None or b is None:
        return 0.0
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    if inter_x2 < inter_x1 or inter_y2 < inter_y1:
        return 0.0
    inter = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    a_area = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    b_area = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = a_area + b_area - inter
    if union <= 0:
        return 0.0
    return inter / union


def initialize(tracker_name: str = 'bytetrack', device: str = 'cpu', config: Optional[Dict[str, Any]] = None):
    """Initialize the module-level tracker instance.

    tracker_name: 'bytetrack' (preferred) or 'deep_sort' to force fallback.
    device: 'cpu' or 'cuda'
    config: backend-specific config dictionary
    """
    global _TRACKER, _BACKEND_NAME
    _TRACKER = None
    _BACKEND_NAME = None

    if tracker_name.lower() == 'deep_sort':
        # attempt deep_sort import first
        try:
            _TRACKER = _DeepSortWrapper(device=device, config=config)
            _BACKEND_NAME = 'deep_sort_realtime'
            print('[tracker_wrapper] Using deep_sort_realtime backend')
            return
        except Exception as e:
            print('[tracker_wrapper] deep_sort_realtime initialization failed, falling back to simple tracker: %s' % repr(e))
            traceback.print_exc()
            _TRACKER = _SimpleCentroidTracker(max_distance=(config.get('max_distance', 80) if config else 80))
            _BACKEND_NAME = 'simple_centroid'
            print('[tracker_wrapper] Using simple centroid fallback')
            return

    # Preferred: try ByteTrack
    try:
        _TRACKER = _ByteTrackWrapper(device=device, config=config)
        _BACKEND_NAME = 'bytetrack'
        print('[tracker_wrapper] Using ByteTrack backend')
        return
    except Exception as e:
        print('[tracker_wrapper] ByteTrack initialization failed, will attempt deep_sort_realtime fallback: %s' % repr(e))
        # print traceback for debugging
        traceback.print_exc()

    # Try deep_sort_realtime
    try:
        _TRACKER = _DeepSortWrapper(device=device, config=config)
        _BACKEND_NAME = 'deep_sort_realtime'
        print('[tracker_wrapper] Using deep_sort_realtime backend')
        return
    except Exception as e:
        print('[tracker_wrapper] deep_sort_realtime initialization failed, using simple centroid fallback: %s' % repr(e))
        traceback.print_exc()
        _TRACKER = _SimpleCentroidTracker(max_distance=(config.get('max_distance', 80) if config else 80))
        _BACKEND_NAME = 'simple_centroid'
        print('[tracker_wrapper] Using simple centroid fallback')


def track_frames(detections_per_frame: List[List[Dict[str, Any]]]) -> List[Dict[Any, int]]:
    """Track a stream of frames.

    detections_per_frame: list of frames, each frame is a list of detection dicts
    Returns: list (per frame) of dict mapping detection_id -> tracker_id
    """
    if _TRACKER is None:
        raise RuntimeError('Tracker not initialized. Call initialize() first.')

    results = []
    for frame_idx, frame_dets in enumerate(detections_per_frame):
        # The underlying trackers often expect only bbox+score/class. We pass
        # along detection_id as metadata so we can map results back.
        assignments = _TRACKER.update(frame_dets or [])
        # assignments: list of dict with 'track_id', 'bbox', 'detection_id'
        mapping = {}
        for a in assignments:
            det_id = a.get('detection_id')
            tid = a.get('track_id')
            if det_id is None:
                # some trackers don't return the matched detection id. In that
                # case we do our best: attempt to match returned bbox to an
                # input detection by IoU.
                best_det = None
                best_iou = 0.0
                for d in frame_dets:
                    iou = _iou_bbox(d.get('bbox'), a.get('bbox'))
                    if iou > best_iou:
                        best_iou = iou
                        best_det = d
                if best_det is not None:
                    det_id = best_det.get('detection_id')
            if det_id is not None and tid is not None:
                mapping[det_id] = int(tid)
        results.append(mapping)
    return results


def backend_name():
    return _BACKEND_NAME
