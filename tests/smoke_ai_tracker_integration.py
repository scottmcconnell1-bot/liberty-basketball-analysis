import os
import sqlite3
import tempfile
from ai_analyzer import run_ai_analysis, TRACKER_ENABLED

# This smoke test runs ai_analyzer on synthetic frames by creating a tiny video
# using OpenCV with a few solid-color frames and ensures at least one detection
# gets a tracker_id assigned when the tracker wrapper is available.

def create_dummy_video(path, num_frames=10, width=320, height=240):
    import cv2
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(path, fourcc, 10.0, (width, height))
    for i in range(num_frames):
        # create a synthetic frame with a white circle (ball) and a rectangle (person) shifting position
        frame = 255 * (i % 2) * (np.ones((height, width, 3), dtype='uint8'))
        # draw a ball
        cv2.circle(frame, (50 + i*5, 60), 10, (0,255,255), -1)
        # draw a person-like blob
        cv2.rectangle(frame, (150 + i*2, 50), (170 + i*2, 150), (0,0,255), -1)
        out.write(frame)
    out.release()


def test_smoke_tracker_integration():
    import numpy as np
    tmpdir = tempfile.mkdtemp()
    video_path = os.path.join(tmpdir, 'dummy.mp4')
    db_path = os.path.join(tmpdir, 'test.db')
    game_id = 'test_game_001'

    # init a minimal DB schema
    conn = sqlite3.connect(db_path)
    with open(os.path.join(os.path.dirname(__file__), '..', 'schema.sql'), 'r') as f:
        conn.executescript(f.read())
    conn.commit()
    conn.close()

    create_dummy_video(video_path, num_frames=8)

    # Run analyzer (TRACKER_ENABLED will control whether tracker runs)
    run_ai_analysis(db_path, video_path, game_id)

    # Inspect DB for tracker ids
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM detections')
    total = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM detections WHERE tracker_id IS NOT NULL')
    with_tracker = cur.fetchone()[0]
    conn.close()

    print(f"Smoke test: total detections={total}, with_tracker={with_tracker}")
    # We expect at least one detection overall. If tracker is enabled and available,
    # we expect at least one tracker_id assigned.
    assert total > 0, 'No detections were written by ai_analyzer'
    if TRACKER_ENABLED:
        assert with_tracker > 0, 'Tracker enabled but no tracker_id values were assigned'


if __name__ == '__main__':
    test_smoke_tracker_integration()
    print('SMOKE TEST COMPLETE')
