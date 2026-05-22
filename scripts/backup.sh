#!/usr/bin/env bash
# backup.sh — Incremental project backup to the `backups` branch on GitHub.
#
# Uses a local bare mirror of the backups branch to avoid re-cloning the full
# repo every run. Each backup fetches only incremental changes, rsyncs the
# current project state, commits, and pushes.
#
# Includes uploads/ (excludes .git, .venv, __pycache__, model files).
# Model files (*.pt, *.pth, etc.) are auto-downownloaded by ultralytics if missing.

set -euo pipefail

PROJECT_DIR="/home/monk-admin/PROJECTS/liberty-basketball-analysis"
BACKUP_DIR="/home/monk-admin/liberty-backup-tmp"
MIRROR_DIR="/home/monk-admin/liberty-backup-mirror"
BACKUP_BRANCH="backups"
REMOTE="git@github.com:scottmcconnell1-bot/liberty-basketball-analysis.git"
TIMESTAMP=$(date +"%Y-%m-%d-%H%M")
TAG="backup/${TIMESTAMP}"
LOG_FILE="${PROJECT_DIR}/scripts/backup.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

cleanup() {
    rm -rf "$BACKUP_DIR"
}
trap cleanup EXIT

log "=== Starting backup: $TAG ==="

# 0. Ensure local bare mirror exists (one-time setup)
if [ ! -d "$MIRROR_DIR" ]; then
    log "Creating local bare mirror of $BACKUP_BRANCH..."
    git clone --bare --branch "$BACKUP_BRANCH" --single-branch "$REMOTE" "$MIRROR_DIR" 2>&1 | tee -a "$LOG_FILE"
    log "Bare mirror created."
fi

# 1. Fetch latest from remote into the local mirror (incremental — fast)
log "Fetching latest into local mirror..."
git -C "$MIRROR_DIR" fetch origin "$BACKUP_BRANCH" --prune 2>&1 | tee -a "$LOG_FILE"

# 2. Clean up any leftover temp directory
rm -rf "$BACKUP_DIR"

# 3. Clone from the LOCAL mirror (instant — no network)
log "Cloning from local mirror..."
git clone --branch "$BACKUP_BRANCH" --single-branch "file://$MIRROR_DIR" "$BACKUP_DIR" 2>&1 | tee -a "$LOG_FILE"

# 4. Add the real remote so we can push
cd "$BACKUP_DIR"
git remote set-url origin "$REMOTE"

# 5. Rsync current project into the clone (exclude .git, .venv, etc.)
log "Syncing current project state..."
rsync -a \
    --exclude='.git' \
    --exclude='.venv' \
    --exclude='venv' \
    --exclude='env' \
    --exclude='__pycache__' \
    --exclude='.pytest_cache' \
    --exclude='*.pyc' \
    --exclude='*.pyo' \
    --exclude='*.so' \
    --exclude='.DS_Store' \
    --exclude='*.db-shm' \
    --exclude='*.db-wal' \
    --exclude='*.pt' \
    --exclude='*.pth' \
    --exclude='*.onnx' \
    --exclude='*.bin' \
    --exclude='*.weights' \
    "$PROJECT_DIR/" "$BACKUP_DIR/"

# 6. Stage everything
git add -A

# 7. Check if there's anything to commit
if git diff --cached --quiet; then
    log "No changes since last backup. Skipping."
    log "=== Backup complete (no changes) ==="
    exit 0
fi

# 8. Commit
CHANGES=$(git diff --cached --stat | tail -1)
git commit -m "backup: $TIMESTAMP — $CHANGES" --no-verify

# 9. Tag
git tag "$TAG"

# 10. Pull-merge-push to handle concurrent backups from multiple sources
log "Pulling latest from origin/$BACKUP_BRANCH before push..."
git pull origin "$BACKUP_BRANCH" --no-verify --rebase 2>&1 | tee -a "$LOG_FILE" || {
    log "Pull failed — attempting rebase resolution..."
    git rebase --abort 2>/dev/null || true
    git reset --hard "origin/$BACKUP_BRANCH" 2>&1 | tee -a "$LOG_FILE"
    # Re-apply our changes on top
    rsync -a \
        --exclude='.git' \
        --exclude='.venv' \
        --exclude='venv' \
        --exclude='env' \
        --exclude='__pycache__' \
        --exclude='.pytest_cache' \
        --exclude='*.pyc' \
        --exclude='*.pyo' \
        --exclude='*.so' \
        --exclude='.DS_Store' \
        --exclude='*.db-shm' \
        --exclude='*.db-wal' \
        --exclude='*.pt' \
        --exclude='*.pth' \
        --exclude='*.onnx' \
        --exclude='*.bin' \
        --exclude='*.weights' \
        "$PROJECT_DIR/" "$BACKUP_DIR/"
    git add -A
    CHANGES=$(git diff --cached --stat | tail -1)
    git commit -m "backup: $TIMESTAMP — $CHANGES (rebased)" --no-verify 2>&1 | tee -a "$LOG_FILE" || true
}

# 11. Push branch and tag
log "Pushing to origin/$BACKUP_BRANCH ..."
git push origin "$BACKUP_BRANCH" --no-verify 2>&1 | tee -a "$LOG_FILE"
git push origin "$TAG" --no-verify 2>&1 | tee -a "$LOG_FILE"

# 12. Update the local mirror with the new push
git -C "$MIRROR_DIR" fetch origin "$BACKUP_BRANCH" --prune 2>&1 | tee -a "$LOG_FILE" || true

log "=== Backup complete: $TAG ==="
