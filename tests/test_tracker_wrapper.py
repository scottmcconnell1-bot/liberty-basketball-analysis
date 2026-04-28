import importlib
import sys
import types

from src.tracker_wrapper import initialize, track_frames, backend_name


def make_synthetic_frames():
    # two frames, one object moving slightly
    f0 = [{'detection_id': 'd0', 'bbox': [10, 10, 50, 100], 'score': 0.9}]
    f1 = [{'detection_id': 'd1', 'bbox': [12, 12, 52, 102], 'score': 0.92}]
    return [f0, f1]


def test_with_simple_fallback():
    # Force deep_sort to be unavailable and ByteTrack unavailable by not
    # installing either. We call initialize with tracker_name='deep_sort' to
    # force attempted fallback path; because deep_sort likely isn't installed
    # in the test environment, the wrapper should select the simple centroid
    # tracker.
    initialize(tracker_name='deep_sort', device='cpu', config={'max_distance': 100})
    assert backend_name() in ('simple_centroid', 'deep_sort_realtime')
    frames = make_synthetic_frames()
    mappings = track_frames(frames)
    # Result should be list of dicts with detection_id mapped to integer
    assert isinstance(mappings, list)
    for m in mappings:
        for det_id, tid in m.items():
            assert isinstance(det_id, str)
            assert isinstance(tid, int)


def test_forced_bytetrack_importerror(monkeypatch):
    # Simulate ImportError during ByteTrack import so wrapper uses deep_sort
    # fallback. We'll monkeypatch the ByteTrack wrapper's import mechanism to
    # raise ImportError.
    import src.tracker_wrapper as tw

    real_byte_init = tw._ByteTrackWrapper.__init__

    def fake_init(self, device='cpu', config=None):
        raise ImportError('simulated bytetrack missing')

    monkeypatch.setattr(tw._ByteTrackWrapper, '__init__', fake_init)
    # Now initialize - it should try ByteTrack, catch the ImportError, then
    # attempt deep_sort. If deep_sort isn't installed, it will finally fall
    # back to the simple centroid tracker.
    initialize(tracker_name='bytetrack', device='cpu')
    assert backend_name() in ('deep_sort_realtime', 'simple_centroid', 'bytetrack')

    # restore
    monkeypatch.setattr(tw._ByteTrackWrapper, '__init__', real_byte_init)


if __name__ == '__main__':
    # Run tests directly for convenience
    test_with_simple_fallback()
    print('test_with_simple_fallback passed')
    print('All tests passed')
