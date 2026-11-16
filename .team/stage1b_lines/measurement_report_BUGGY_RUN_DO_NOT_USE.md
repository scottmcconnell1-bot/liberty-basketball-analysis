# Stage 1b Court Lines Measurement Report

Approach (A): painted-line detection plus an NFHS geometric fit. Each frame was fitted independently. No interpolation, no tracking, and no learned model. Thresholds were frozen on the calibration frames before the 60 measurement frames were measured.

## Aggregate Results

| Game | Frames | Success | Rate | Median error (px) | Half-court Y mean (ft) | Court length mean (ft) |
|------|--------|---------|------|-------------------|------------------------|------------------------|
| adrian | 20 | 0 | 0.0% | N/A | N/A | N/A |
| notus_a1 | 20 | 0 | 0.0% | N/A | N/A | N/A |
| notus_a | 20 | 0 | 0.0% | N/A | N/A | N/A |

## Per-Frame Table

| Game | Frame | Segments | Lines | Fit error (px) | Success | Half-court Y (ft) | Court length (ft) | Keypoint floor points | Keypoint H valid |
|------|-------|----------|-------|----------------|---------|-------------------|-------------------|-----------------------|------------------|
| adrian | 0 | 28 | 0 | None | False | None | None | 6 | False |
| adrian | 4873 | 28 | 0 | None | False | None | None | 7 | False |
| adrian | 9746 | 28 | 0 | None | False | None | None | 6 | False |
| adrian | 14619 | 28 | 0 | None | False | None | None | 0 | False |
| adrian | 19492 | 28 | 0 | None | False | None | None | 9 | False |
| adrian | 24365 | 28 | 0 | None | False | None | None | 6 | False |
| adrian | 29238 | 28 | 0 | None | False | None | None | 0 | False |
| adrian | 34111 | 28 | 0 | None | False | None | None | 8 | False |
| adrian | 38984 | 28 | 0 | None | False | None | None | 0 | False |
| adrian | 43857 | 28 | 0 | None | False | None | None | 0 | False |
| adrian | 48730 | 28 | 0 | None | False | None | None | 9 | False |
| adrian | 53603 | 28 | 0 | None | False | None | None | 6 | False |
| adrian | 58476 | 28 | 0 | None | False | None | None | 6 | False |
| adrian | 63349 | 28 | 0 | None | False | None | None | 8 | False |
| adrian | 68222 | 28 | 0 | None | False | None | None | 6 | False |
| adrian | 73095 | 28 | 0 | None | False | None | None | 6 | False |
| adrian | 77968 | 28 | 0 | None | False | None | None | 8 | False |
| adrian | 82841 | 28 | 0 | None | False | None | None | 6 | False |
| adrian | 87714 | 28 | 0 | None | False | None | None | 6 | False |
| adrian | 92587 | 28 | 0 | None | False | None | None | 7 | False |
| notus_a1 | 0 | 28 | 0 | None | False | None | None | 6 | False |
| notus_a1 | 5047 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a1 | 10094 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a1 | 15141 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a1 | 20188 | 28 | 0 | None | False | None | None | 7 | False |
| notus_a1 | 25235 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a1 | 30282 | 28 | 0 | None | False | None | None | 5 | False |
| notus_a1 | 35329 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a1 | 40376 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a1 | 45423 | 28 | 0 | None | False | None | None | 6 | False |
| notus_a1 | 50470 | 28 | 0 | None | False | None | None | 7 | False |
| notus_a1 | 55517 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a1 | 60564 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a1 | 65611 | 28 | 0 | None | False | None | None | 6 | False |
| notus_a1 | 70658 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a1 | 75705 | 28 | 0 | None | False | None | None | 6 | False |
| notus_a1 | 80752 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a1 | 85799 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a1 | 90846 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a1 | 95893 | 28 | 0 | None | False | None | None | 6 | False |
| notus_a | 0 | 28 | 0 | None | False | None | None | 6 | False |
| notus_a | 4682 | 28 | 0 | None | False | None | None | 8 | False |
| notus_a | 9364 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a | 14046 | 28 | 0 | None | False | None | None | 6 | False |
| notus_a | 18728 | 28 | 0 | None | False | None | None | 2 | False |
| notus_a | 23410 | 28 | 0 | None | False | None | None | 6 | False |
| notus_a | 28092 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a | 32774 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a | 37456 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a | 42138 | 28 | 0 | None | False | None | None | 6 | False |
| notus_a | 46820 | 28 | 0 | None | False | None | None | 6 | False |
| notus_a | 51502 | 28 | 0 | None | False | None | None | 2 | False |
| notus_a | 56184 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a | 60866 | 28 | 0 | None | False | None | None | 7 | False |
| notus_a | 65548 | 28 | 0 | None | False | None | None | 4 | False |
| notus_a | 70230 | 28 | 0 | None | False | None | None | 6 | False |
| notus_a | 74912 | 28 | 0 | None | False | None | None | 6 | False |
| notus_a | 79594 | 28 | 0 | None | False | None | None | 0 | False |
| notus_a | 84276 | 28 | 0 | None | False | None | None | 6 | False |
| notus_a | 88958 | 28 | 0 | None | False | None | None | 0 | False |

## Comparison with Stage 1 Keypoints

- **adrian**: both succeed 0, lines succeed / keypoints fail 0, keypoints succeed / lines fail 16, both fail 4.
- **notus_a1**: both succeed 0, lines succeed / keypoints fail 0, keypoints succeed / lines fail 8, both fail 12.
- **notus_a**: both succeed 0, lines succeed / keypoints fail 0, keypoints succeed / lines fail 11, both fail 9.

Stage 1 used a homography only when at least 4 keypoints were found; the keypoint model did not compute a homography in Stage 1, so the keypoint H column is a conservative comparison.

## Pass-Gate Check

- FAIL - Adrian >= 80% success (0.0%)
- FAIL - Adrian court lengths physically plausible (mean 84-100 ft) (no successful length measurements)
- FAIL - Notus A1 >= 70% success (0.0%)
- FAIL - Notus A1 half-court Y within 40.75 +/- 2.0 ft (N/A)
- FAIL - Notus A1 median fit error <= 1.5 px (N/A)
- FAIL - Notus A >= 70% success (0.0%)
- FAIL - Notus A half-court Y within 2.0 ft of Notus A1 (N/A)

Verdict: approach (A) does not meet the Stage 2 gate unless every line above says PASS. The measured numbers are reported without retuning.
