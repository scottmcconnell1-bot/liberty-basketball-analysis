import os
import csv
import sys
import shutil

# --- CONFIGURATION ---
INPUT_CSV = "review_reconciliation.csv"
SRC_IMAGE_DIR = "ball_dataset_v2/images"
SRC_LABEL_DIR = "ball_dataset_v2/labels"
DST_DIR = "cleaned_dataset"
SUMMARY_CSV = "cleanup_summary.csv"

# --- STATUS LABELS MAPPING ---
GOOD_STATUSES = {"accepted", "ball", "yes", "y", "good", "confirmed ball"}
BAD_STATUSES = {"rejected", "not_ball", "no", "n", "bad", "confirmed not_ball"}

def find_image_by_frame_id(image_dir, frame_id):
    """Scan directory for any file matching frame_id regardless of extension."""
    valid_extensions = {'.jpg', '.jpeg', '.png'}
    target_base = frame_id.strip()
    if not os.path.exists(image_dir):
        return None
    for f in os.listdir(image_dir):
        base, ext = os.path.splitext(f)
        if base == target_base and ext.lower() in valid_extensions:
            return f
    return None

def run_dataset_cleanup():
    # 1. Verification of baseline assets
    if not os.path.exists(INPUT_CSV):
        print(f"Error: Required source file '{INPUT_CSV}' not found.")
        sys.exit(1)

    if not os.path.exists(SRC_IMAGE_DIR) or not os.path.exists(SRC_LABEL_DIR):
        print(f"Error: Base dataset directory structure missing.\nImages: {SRC_IMAGE_DIR}\nLabels: {SRC_LABEL_DIR}")
        sys.exit(1)

    # 2. Establish isolated destination paths
    dst_images = os.path.join(DST_DIR, "images")
    dst_labels = os.path.join(DST_DIR, "labels")
    os.makedirs(dst_images, exist_ok=True)
    os.makedirs(dst_labels, exist_ok=True)

    # Counters
    copied_count = 0
    excluded_count = 0
    unreviewed_count = 0
    malformed_count = 0

    summary_rows = []

    # 3. Read reconciliation records and execute migrations
    with open(INPUT_CSV, mode='r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            print(f"Error: '{INPUT_CSV}' contains no readable data rows.")
            sys.exit(1)

        for row_idx, row in enumerate(reader, start=2):
            if not row:
                continue
            if len(row) < 2:
                print(f"Warning: Row {row_idx} is malformed. Skipping.")
                malformed_count += 1
                continue

            frame_id = row[0].strip()
            review_status = row[1].strip().lower()
            lbl_filename = f"{frame_id}.txt"
            src_lbl_path = os.path.join(SRC_LABEL_DIR, lbl_filename)

            # Resolve the correct image file dynamically
            img_filename = find_image_by_frame_id(SRC_IMAGE_DIR, frame_id)

            if review_status in GOOD_STATUSES:
                if img_filename:
                    src_img_path = os.path.join(SRC_IMAGE_DIR, img_filename)
                    shutil.copy2(src_img_path, os.path.join(dst_images, img_filename))
                    if os.path.exists(src_lbl_path):
                        shutil.copy2(src_lbl_path, os.path.join(dst_labels, lbl_filename))
                    else:
                        with open(os.path.join(dst_labels, lbl_filename), 'w') as _: pass
                    copied_count += 1
                    summary_rows.append([frame_id, "ball", review_status])
                else:
                    print(f"Warning: No image found for '{frame_id}' (row {row_idx}).")
                    malformed_count += 1

            elif review_status in BAD_STATUSES:
                excluded_count += 1
                summary_rows.append([frame_id, "ball", review_status])

            else:
                unreviewed_count += 1
                summary_rows.append([frame_id, "ball", "unreviewed"])

    # 4. Write output cleanup_summary.csv
    with open(SUMMARY_CSV, mode='w', newline='', encoding='utf-8') as out_f:
        writer = csv.writer(out_f)
        writer.writerow(["frame_id", "original_label", "review_status"])
        writer.writerows(summary_rows)

    # Print summary
    print("\n=============================================")
    print("      DATASET PURIFICATION UTILITY COMPLETE   ")
    print("=============================================")
    print(f"  Confirmed Ball Assets Migrated: {copied_count}")
    print(f"  Confirmed Not_Ball Assets Excluded: {excluded_count}")
    print(f"  Unreviewed Assets Skipped: {unreviewed_count}")
    print(f"  Missing / Malformed Assets Skipped: {malformed_count}")
    print(f"  Output Folder: {DST_DIR}/")
    print(f"  Cleanup Ledger: {SUMMARY_CSV}")
    print("=============================================\n")

if __name__ == "__main__":
    run_dataset_cleanup()
