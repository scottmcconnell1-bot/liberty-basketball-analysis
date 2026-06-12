# Dataset Contamination Report
**Generated On:** 2026-06-09 19:02:16
**Source Audit Ledger:** `review_results.csv`

## Progress Tracking Metrics
- **Total Dataset Footprint (Images):** 108
- **Rows Reviewed (Audited):** 18
- **Rows Remaining (Unreviewed):** 90

## Contamination Metrics (Reviewed Subset)
- **Valid Features (GOOD):** 11 (61.11%)
- **Mislabeled Features (BAD):** 7 (38.89%)
- **Uncertain Features:** 0 (0.00%)

## Data Integrity Status
MODERATE SEVERITY: Significant contamination present. Noise artifacts are infiltrating the label parameters. Bounding-box pruning and dataset purification are highly recommended.

## Detailed Classification Ledger

### BAD (Mislabeled / Contaminated Image Files)
- frame_014.jpg
- frame_020.jpg
- frame_032.jpg
- frame_035.jpg
- frame_071.jpg
- frame_079.jpg
- frame_100.jpg

### GOOD (Valid Label Image Files)
- frame_025.jpg
- frame_028.jpg
- frame_034.jpg
- frame_051.jpg
- frame_052.jpg
- frame_054.jpg
- frame_070.jpg
- frame_090.jpg
- frame_092.jpg
- frame_096.jpg
- frame_101.jpg

### UNCERTAIN / SKIPPED
_No uncertain frames flagged._
