#!/usr/bin/env bash
# backup_v2.sh — Liberty Basketball Analysis project backup
# Backs up source assets to timestamped tar.gz archives.
# Retention: 14 daily + 4 weekly, auto-pruned.

set -euo pipefail

# --- CONFIGURATION ---
PROJECT_DIR="/home/monk-admin/PROJECTS/liberty-basketball-analysis"
BACKUP_ROOT="$PROJECT_DIR/backup"
DAILY_DIR="$BACKUP_ROOT/daily"
WEEKLY_DIR="$BACKUP_ROOT/weekly"
LOG_FILE="$BACKUP_ROOT/backup.log"
DAILY_RETENTION=14
WEEKLY_RETENTION=4

TIMESTAMP=$(date +"%Y-%m-%d_%H%M")
DAILY_ARCHIVE="$DAILY_DIR/${TIMESTAMP}.tar.gz"

# --- FUNCTIONS ---
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# --- DAILY BACKUP ---
log "=== Starting daily backup: $TIMESTAMP ==="

mkdir -p "$DAILY_DIR" "$WEEKLY_DIR"

# Use --warning=no-file-changed because the project directory is active
# (Flask logs, backup log, etc. change during archive creation).
# Exit code 2 = fatal error, exit code 1 = files changed (acceptable).
set +e
tar -czf "$DAILY_ARCHIVE" \
    -C "$PROJECT_DIR" \
    --warning=no-file-changed \
    --exclude='backup' \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='venv_repair' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='logs' \
    --exclude='runs' \
    --exclude='pipeline_output' \
    --exclude='eval_output' \
    --exclude='ball_finetune/runs' \
    --exclude='sample_frames_det' \
    --exclude='sample_frames_hough' \
    --exclude='sample_frames_blob_vis' \
    --exclude='sample_frames_blob' \
    --exclude='sample_frames' \
    --exclude='sample_frames_yolov8s_hoop_filtered' \
    --exclude='sample_frames_filtered' \
    --exclude='sample_frames_colour_size' \
    --exclude='sample_frames_roi' \
    --exclude='sample_frames_hoop_scaled' \
    --exclude='sample_frames_hoop_scaled_v2' \
    --exclude='sample_frames_color_roi' \
    --exclude='motion_vis' \
    --exclude='motion_vis_mid' \
    --exclude='v3_vis' \
    --exclude='v5_vis' \
    --exclude='v7_vis' \
    --exclude='v8_vis' \
    --exclude='pretrained_test_output' \
    --exclude='dataset_review_pages/review_images' \
    --exclude='dataset_review_pages/review_images_45' \
    --exclude='dataset_review_pages/review_images_unreviewed' \
    --exclude='videos' \
    --exclude='uploads' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='*.so' \
    --exclude='__pycache__' \
    .
TAR_EXIT=$?
set -e

if [ $TAR_EXIT -eq 2 ]; then
    log "FATAL: tar exited with code 2 (unrecoverable error)"
    rm -f "$DAILY_ARCHIVE"
    exit 1
elif [ $TAR_EXIT -eq 1 ]; then
    log "WARNING: tar exited with code 1 (files changed during read) — archive may be slightly inconsistent but usable"
elif [ $TAR_EXIT -ne 0 ]; then
    log "FATAL: tar exited with code $TAR_EXIT"
    rm -f "$DAILY_ARCHIVE"
    exit 1
fi

ARCHIVE_SIZE=$(du -sh "$DAILY_ARCHIVE" | cut -f1)
log "Archive created: $DAILY_ARCHIVE ($ARCHIVE_SIZE)"

# --- VERIFY ARCHIVE INTEGRITY ---
if tar -tzf "$DAILY_ARCHIVE" > /dev/null 2>&1; then
    FILE_COUNT=$(tar -tzf "$DAILY_ARCHIVE" | wc -l)
    log "Integrity check passed: $FILE_COUNT files in archive"
else
    log "ERROR: Archive integrity check FAILED"
    rm -f "$DAILY_ARCHIVE"
    exit 1
fi

# --- WEEKLY BACKUP (Sundays only) ---
DAY_OF_WEEK=$(date +%u)  # 7 = Sunday
if [ "$DAY_OF_WEEK" -eq 7 ]; then
    WEEKLY_ARCHIVE="$WEEKLY_DIR/${TIMESTAMP}.tar.gz"
    log "Today is Sunday — creating weekly backup"
    cp "$DAILY_ARCHIVE" "$WEEKLY_ARCHIVE"
    log "Weekly archive: $WEEKLY_ARCHIVE"
fi

# --- RETENTION: prune old daily backups ---
DAILY_DELETED=$(find "$DAILY_DIR" -maxdepth 1 -name "*.tar.gz" -mtime +$DAILY_RETENTION | wc -l)
find "$DAILY_DIR" -maxdepth 1 -name "*.tar.gz" -mtime +$DAILY_RETENTION -delete 2>/dev/null || true
log "Pruned $DAILY_DELETED daily backup(s) older than $DAILY_RETENTION days"

# --- RETENTION: prune old weekly backups ---
WEEKLY_DELETED=$(find "$WEEKLY_DIR" -maxdepth 1 -name "*.tar.gz" -mtime +$((WEEKLY_RETENTION * 7)) | wc -l)
find "$WEEKLY_DIR" -maxdepth 1 -name "*.tar.gz" -mtime +$((WEEKLY_RETENTION * 7)) -delete 2>/dev/null || true
log "Pruned $WEEKLY_DELETED weekly backup(s) older than $WEEKLY_RETENTION weeks"

# --- SUMMARY ---
DAILY_COUNT=$(find "$DAILY_DIR" -maxdepth 1 -name "*.tar.gz" | wc -l)
WEEKLY_COUNT=$(find "$WEEKLY_DIR" -maxdepth 1 -name "*.tar.gz" | wc -l)
TOTAL_BACKUP_SIZE=$(du -sh "$BACKUP_ROOT" | cut -f1)

log "=== Backup complete ==="
log "Daily archives: $DAILY_COUNT | Weekly archives: $WEEKLY_COUNT | Total backup size: $TOTAL_BACKUP_SIZE"
