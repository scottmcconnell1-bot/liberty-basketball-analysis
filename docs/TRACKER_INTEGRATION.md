TRACKER_INTEGRATION

This file documents the tracker wrapper added to the project. It explains how
it works, how to install optional dependencies, and how to use it inside the
project's existing .venv.

Overview
--------

A new wrapper was added at src/tracker_wrapper.py. It exposes two functions:

- initialize(tracker_name='bytetrack', device='cpu', config={}):
    Initializes a module-level tracker instance. By default it prefers ByteTrack
    (attempts multiple common import names). If ByteTrack is not importable or
    fails to initialize, the wrapper automatically falls back to
    deep_sort_realtime. If deep_sort_realtime is also not available, a small
    builtin centroid tracker is used as a final fallback.

- track_frames(detections_per_frame) -> list of dict:
    Accepts a list of frames where each frame is a list of detection dicts. A
    detection dict must include at minimum:
      - detection_id: any hashable identifier (used to map inputs to outputs)
      - bbox: [x1,y1,x2,y2]
    The function returns a list (one entry per frame) of dicts mapping
    detection_id -> tracker_id assigned by the active backend.

Supported backends
------------------

1) ByteTrack (preferred):
   - The wrapper attempts to import common ByteTrack package names (bytetrack,
     bytetrack_pytorch, etc.) and attempts multiple construction and update
     signatures. ByteTrack is fast but may require native builds or extra
     dependencies.

2) deep_sort_realtime (fallback):
   - A pure-Python DeepSort implementation that's straightforward to install
     via pip: pip install deep_sort_realtime

3) Simple centroid tracker (final fallback):
   - Built-in minimal centroid tracker used when neither ByteTrack nor
     deep_sort_realtime is available. Useful for development and unit tests.

Installation
------------

Inside the repository root, activate the project's venv:

    source .venv/bin/activate

To prefer ByteTrack, install one of the common distributions. Note: ByteTrack
variants may require CUDA/toolchain setup if you want GPU acceleration. A
commonly-used package is bytetrack-pytorch (if available) or the official
ByteTrack repository instructions.

A convenient fallback that avoids native compilation:

    pip install deep_sort_realtime

If you want both, install both packages. The wrapper will prefer ByteTrack but
fall back to deep_sort_realtime automatically if ByteTrack import fails.

Requirements file
-----------------

The project's requirements.txt has not been aggressively changed. For
developers who rely on the fallback, add the following to requirements-dev.txt
or append to requirements.txt with a safe comment:

# Optional tracking backends (ByteTrack preferred; deep_sort_realtime is a
# pure-Python fallback):
# deep_sort_realtime>=1.3.1  # lightweight Python DeepSort implementation
# bytetrack or bytetrack-pytorch  # optional; many variants exist, follow their docs

Usage example
-------------

from src.tracker_wrapper import initialize, track_frames

# initialize (default prefers ByteTrack)
initialize(tracker_name='bytetrack', device='cpu', config={'max_age':30})

# prepare synthetic frames
frames = [
    [ {'detection_id':'f0_1', 'bbox':[10,10,50,100], 'score':0.9 } ],
    [ {'detection_id':'f1_1', 'bbox':[12,12,52,102], 'score':0.92 } ],
]

mappings = track_frames(frames)
# mappings is a list per-frame: e.g. [ {'f0_1': 1}, {'f1_1': 1} ]

Notes and troubleshooting
-------------------------
- If ByteTrack import fails with complex errors, use the fallback by installing
  deep_sort_realtime. The wrapper prints logs indicating which backend was
  successfully initialized.
- The wrapper attempts to be tolerant to differences in backend package
  interfaces, but not all 3rd-party package layouts are supported. If you
  encounter an unrecognized ByteTrack layout, prefer deep_sort_realtime or
  file an issue with the project.

