#!/usr/bin/env bash
# backup.sh — Project backup to the `backups` branch on GitHub.
#
# Pushes the current project state (excluding .git, .venv, model files, etc.)
# to the backups branch. Each backup is a separate commit.

set -euo pipefail

PROJECT_DIR="/home/monk-admin/PROJECTS/liberty-basketball-analysis"
BACKUP_DIR="/home/monk-admin/liberty-backup-tmp"
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
rm -rf "$BACKUP_DIR"

# Clone the backups branch, ignoring LFS errors
log "Cloning ${BACKUP_BRANCH} branch..."
set +e
git clone --branch "$BACKUP_BRANCH" --single-branch "$REMOTE" "$BACKUP_DIR" 2>&1 | tee -a "$LOG_FILE"
CLONE_EXIT=$?
set -e

# If clone had LFS errors, fix them by removing LFS state
if [ $CLONE_EXIT -ne 0 ] || [ -f "$BACKUP_DIR/.git/lfs/logs/"*.log 2>/dev/null ]; then
    log "Clone had issues — cleaning up LFS state..."
    cd "$BACKUP_DIR"
    # Remove LFS hooks and config
    git lfs uninstall 2>/dev/null || true
    rm -f .git/hooks/pre-push 2>/dev/null || true
    rm -rf .git/lfs 2>/dev/null || true
    # Reset working tree from HEAD (skip LFS smudge)
    GIT_LFS_SKIP_SMUDGE=1 git reset --hard HEAD 2>&1 | tee -a "$LOG_FILE" || {
        log "Reset failed — re-cloning with LFS skip..."
        cd /home/monk-admin
        rm -rf "$BACKUP_DIR"
        GIT_LFS_SKIP_SMUDGE=1 git clone --branch "$BACKUP_BRANCH" --single-branch "$REMOTE" "$BACKUP_DIR" 2>&1 | tee -a "$LOG_FILE"
    }
fi

cd "$BACKUP_DIR"

# Ensure LFS is disabled
git lfs uninstall 2>/dev/null || true
rm -f .git/hooks/pre-push 2>/dev/null || true

# Remove old tracked files (we'll re-add from current project)
git rm -rf . --quiet 2>/dev/null || true

# Rsync current project into the clone
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
    --exclude='*.npy' \
    --exclude='*.pkl' \
    "$PROJECT_DIR/" "$BACKUP_DIR/"

# Stage everything
git add -A

# Check if there's anything to commit
if git diff --cached --quiet; then
    log "No changes since last backup. Skipping."
    log "=== Backup complete (no changes) ==="
    exit 0
fi

# Commit
CHANGES=$(git diff --cached --stat | tail -1)
git commit -m "backup: $TIMESTAMP — $CHANGES" --no-verify

# Tag
git tag "$TAG"

# Push branch and tag
log "Pushing to origin/${BACKUP_BRANCH} ..."
git push origin "$BACKUP_BRANCH" --no-verify --force 2>&1 | tee -a "$LOG_FILE"
git push origin "$TAG" --no-verify 2>&1 | tee -a "$LOG_FILE"

log "=== Backup complete: $TAG ==="
