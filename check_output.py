import json
with open('/mnt/c/Users/scott/Documents/Liberty_Shot_Outputs/d2_frames/frames.json') as f:
    data = json.load(f)

from collections import Counter
counts = Counter(d['film'] for d in data)
print('Per-film counts:')
for film, count in counts.items():
    print(f'  {film}: {count}')
print(f'Total: {len(data)}')

# Check Notus A frames against holdout frames
notus_a_frames = [d['frame_number'] for d in data if 'NOTUS_A' in d['film'] and 'NOTUS_A1' not in d['film']]
print(f'\nNotus A frames: {len(notus_a_frames)}')

# Holdout timestamps from holdout_names.json
holdout_ms = [232300, 606900, 981500, 1356100, 1730700, 2105300, 2479900, 2854500, 3229100, 3603700]
fps = 25  # Notus A is 25 fps
holdout_frames = [int(round(ms * fps / 1000)) for ms in holdout_ms]
print(f'Holdout frames (computed): {holdout_frames}')

# Check exclusion
exclusion = 5 * fps  # 125 frames
print(f'Exclusion window: ±{exclusion} frames')

violations = []
for nf in notus_a_frames:
    for hf in holdout_frames:
        if abs(nf - hf) <= exclusion:
            violations.append((nf, hf, abs(nf - hf)))

if violations:
    print('VIOLATIONS (frame within 125 of holdout):')
    for v in violations:
        print(f'  Frame {v[0]} near holdout {v[1]} (dist={v[2]})')
else:
    print('No holdout violations - all Notus A frames > 125 frames from holdout')