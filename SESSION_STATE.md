# Session State - Basketball Analysis
Status: Idle
Current Best Score: 24/31 (Notus 1st Quarter)
Details: 7 makes missed, 0 misses called makes.
Diagnosis: Finished. The seven makes and the failed trials are in OLLAMA.md. Nearest-box remains the best score. ByteTrack was 21/31 with 1 false make. DeepSORT was 22/31. An earlier window and the interpolation trials did not beat 24/31.
Next Step: Scott allowed writing a candidate ball weights file on 2026-10-20. None has been written yet. Score it with validate_ball_weights.py. Do not copy it over models/ball_detector.pt. Do not rerun the detector trials. Interpolation and a wider column were rejected. See DETECTOR_PROPOSAL_REJECTION.md.
