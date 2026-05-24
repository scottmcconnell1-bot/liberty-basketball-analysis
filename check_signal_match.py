#!/usr/bin/env python3
import pandas as pd
import numpy as np

# Load signal file
signals = pd.read_csv('/home/monk-admin/PROJECTS/liberty-basketball-analysis/signal_full.csv')
signal_frames = signals[signals['signal'] > 0][['frame', 'timestamp_ms', 'signal']].copy()
signal_frames['time_s'] = signal_frames['timestamp_ms'] / 1000.0
print('Signal frames (one-hand=1, both-hands=2):')
print(signal_frames.to_string(index=False))
print()

# Load our detected attempt peaks from the last run
attempts = pd.read_csv('/home/monk-admin/PROJECTS/liberty-basketball-analysis/final_events_signal_refined.csv')
attempts = attempts[['attempt_id', 'frame', 'time_s', 'peak_frame', 'peak_y_px']].copy()
print('Detected attempt peaks (from ball trajectory):')
print(attempts.to_string(index=False))
print()

# For each signal, find the closest attempt peak within +/- 1 second
window_sec = 1.0
window_frames = window_sec * 3.75  # approx
matches = []
for _, sig in signal_frames.iterrows():
    sig_frame = sig['frame']
    sig_time = sig['time_s']
    sig_type = sig['signal']
    # find attempts within window
    mask = (attempts['frame'] >= sig_frame - window_frames) & (attempts['frame'] <= sig_frame + window_frames)
    close = attempts[mask]
    if not close.empty:
        # pick the closest
        close = close.copy()
        close['diff'] = np.abs(close['frame'] - sig_frame)
        closest = close.loc[close['diff'].idxmin()]
        matches.append({
            'signal_frame': sig_frame,
            'signal_time': sig_time,
            'signal_type': sig_type,
            'matched_attempt': closest['attempt_id'],
            'matched_frame': closest['frame'],
            'matched_time': closest['time_s'],
            'frame_diff': closest['diff'],
            'time_diff': np.abs(closest['time_s'] - sig_time)
        })
    else:
        matches.append({
            'signal_frame': sig_frame,
            'signal_time': sig_time,
            'signal_type': sig_type,
            'matched_attempt': None,
            'matched_frame': None,
            'matched_time': None,
            'frame_diff': None,
            'time_diff': None
        })

print(f'Signal matching within {window_sec}s:')
for m in matches:
    if m['matched_attempt'] is not None:
        print(f"Signal {m['signal_type']} at frame {m['signal_frame']} ({m['signal_time']:.1f}s) -> matched attempt {m['matched_attempt']} at frame {m['matched_frame']} ({m['matched_time']:.1f}s), diff {m['frame_diff']:.1f} frames ({m['time_diff']:.1f}s)")
    else:
        print(f"Signal {m['signal_type']} at frame {m['signal_frame']} ({m['signal_time']:.1f}s) -> NO MATCH")