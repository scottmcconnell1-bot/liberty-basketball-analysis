import os
import csv
import sys
from datetime import datetime

# --- CONFIGURATION ---
INPUT_CSV = "review_results.csv"
REPORT_OUTPUT = "dataset_contamination_report.md"
IMAGE_DIR = "ball_dataset_v2/images"

# --- TOLERANCE SPECIFICATIONS ---
GOOD_LABELS = {"accepted", "ball", "yes", "y", "good"}
BAD_LABELS = {"rejected", "not_ball", "no", "n", "bad"}
UNCERTAIN_LABELS = {"uncertain", "skipped", "unknown"}

def compile_contamination_report():
    # 1. Calculate Total Dataset Size based on the local directory asset footprint
    total_dataset_files = 0
    if os.path.exists(IMAGE_DIR):
        total_dataset_files = len([
            f for f in os.listdir(IMAGE_DIR) 
            if f.lower().endswith(('.png', '.jpg', '.jpeg'))
        ])
    else:
        print(f"Warning: IMAGE_DIR '{IMAGE_DIR}' not found. Total dataset calculation skipped.")

    if not os.path.exists(INPUT_CSV):
        print(f"Error: Target data missing. Could not find '{INPUT_CSV}'.")
        sys.exit(1)

    # Initialize tracking structures
    total_audited_rows = 0
    accepted_count = 0
    rejected_count = 0
    uncertain_count = 0
    
    good_samples = []
    bad_samples = []
    uncertain_samples = []

    # Read and parse review logs stringently
    with open(INPUT_CSV, mode='r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            print(f"Error: '{INPUT_CSV}' is empty or missing a header row.")
            sys.exit(1)
            
        for row_idx, row in enumerate(reader, start=2):
            if not row:
                continue
            if len(row) < 2:
                print(f"Warning: Skipping malformed row {row_idx}.")
                continue
                
            img_file = row[0].strip()
            raw_status = row[1].strip().lower()
            
            # Skip entries that haven't been reviewed by the human yet
            if not raw_status:
                continue
                
            total_audited_rows += 1
            
            # Map input flexibly using matching sets
            if raw_status in GOOD_LABELS:
                accepted_count += 1
                good_samples.append(img_file)
            elif raw_status in BAD_LABELS:
                rejected_count += 1
                bad_samples.append(img_file)
            elif raw_status in UNCERTAIN_LABELS:
                uncertain_count += 1
                uncertain_samples.append(img_file)
            else:
                # Handle unexpected inputs gracefully by grouping into uncertain
                uncertain_count += 1
                uncertain_samples.append(f"{img_file} (Fuzzy status parsed: '{raw_status}')")

    # Calculate remaining subset balance metrics
    rows_remaining = max(0, total_dataset_files - total_audited_rows)

    # Compute statistical distributions against what was actually reviewed
    if total_audited_rows > 0:
        contamination_rate = (rejected_count / total_audited_rows) * 100
        accuracy_rate = (accepted_count / total_audited_rows) * 100
        uncertain_rate = (uncertain_count / total_audited_rows) * 100
    else:
        contamination_rate = accuracy_rate = uncertain_rate = 0.0

    # Compile the Markdown payload
    md = []
    md.append("# Dataset Contamination Report")
    md.append(f"**Generated On:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md.append(f"**Source Audit Ledger:** `{INPUT_CSV}`")
    
    md.append("\n## Progress Tracking Metrics")
    md.append(f"- **Total Dataset Footprint (Images):** {total_dataset_files}")
    md.append(f"- **Rows Reviewed (Audited):** {total_audited_rows}")
    md.append(f"- **Rows Remaining (Unreviewed):** {rows_remaining}")
    
    md.append("\n## Contamination Metrics (Reviewed Subset)")
    md.append(f"- **Valid Features (GOOD):** {accepted_count} ({accuracy_rate:.2f}%)")
    md.append(f"- **Mislabeled Features (BAD):** {rejected_count} ({contamination_rate:.2f}%)")
    md.append(f"- **Uncertain Features:** {uncertain_count} ({uncertain_rate:.2f}%)")
    
    md.append("\n## Data Integrity Status")
    if total_audited_rows == 0:
        md.append("AWAITING DATA: No reviewed rows have been detected yet to compile an integrity status evaluation.")
    elif contamination_rate >= 50.0:
        md.append("CRITICAL SEVERITY: Extreme dataset contamination detected. The background noise and mislabeled classes dominate the verified samples. The current feature representations are heavily compromised.")
    elif contamination_rate >= 15.0:
        md.append("MODERATE SEVERITY: Significant contamination present. Noise artifacts are infiltrating the label parameters. Bounding-box pruning and dataset purification are highly recommended.")
    else:
        md.append("NOMINAL SEVERITY: Dataset integrity is within acceptable parameters. Minor contamination detected, but base feature layouts are structurally stable.")

    md.append("\n## Detailed Classification Ledger")
    
    md.append("\n### BAD (Mislabeled / Contaminated Image Files)")
    if bad_samples:
        for item in sorted(bad_samples):
            md.append(f"- {item}")
    else:
        md.append("_No contaminated frames identified._")

    md.append("\n### GOOD (Valid Label Image Files)")
    if good_samples:
        for item in sorted(good_samples):
            md.append(f"- {item}")
    else:
        md.append("_No valid frames identified._")

    md.append("\n### UNCERTAIN / SKIPPED")
    if uncertain_samples:
        for item in sorted(uncertain_samples):
            md.append(f"- {item}")
    else:
        md.append("_No uncertain frames flagged._")

    # Write utility outputs safely to disk
    with open(REPORT_OUTPUT, mode='w', encoding='utf-8') as out_f:
        out_f.write("\n".join(md) + "\n")

    print(f"Summary processing complete. Metrics exported to '{REPORT_OUTPUT}'.")

if __name__ == "__main__":
    compile_contamination_report()
