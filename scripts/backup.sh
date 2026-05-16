#!/usr/bin/env bash
# backup.sh — Full project backup to the `backups` branch on GitHub.
#
# Clones the existing backups branch, rsyncs in the current project state,
# commits, and pushes. Preserves full history for rollback capability.
# Includes uploads/ and model files (excludes .git, .venv, __pycache__).
#
# Safe to run while the main project is actively being worked on — we never
# touch the main project's .git or working directory.

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

# 1. Clean up any leftover temp directory
rm -rf "$BACKUP_DIR"

# 2. Clone the existing backups branch (or init fresh if it doesn't exist)
log "Cloning existing backups branch..."
if git clone --branch "$BACKUP_BRANCH" --single-branch "$REMOTE" "$BACKUP_DIR" 2>/dev/null; then
    log "Cloned existing backups branch."
else
    log "No existing backups branch — initializing fresh repo."
    mkdir -p "$BACKUP_DIR"
    cd "$BACKUP_DIR"
    git init
    git config user.email "backup@liberty.local"
    git config user.name "Liberty Backup"
    git remote add origin "$REMOTE"
fi

# 3. Rsync current project into the clone (exclude .git, .venv, etc.)
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
    "$PROJECT_DIR/" "$BACKUP_DIR/"

# 4. Stage everything
cd "$BACKUP_DIR"
git add -A

# 5. Check if there's anything to commit
if git diff --cached --quiet; then
    log "No changes since last backup. Skipping."
    log "=== Backup complete (no changes) ==="
    exit 0
fi

# 6. Commit
CHANGES=$(git diff --cached --stat | tail -1)
git commit -m "backup: $TIMESTAMP — $CHANGES" --no-verify

# 7. Tag
git tag "$TAG"

# 8. Push (normal push — no force, preserves history)
log "Pushing to origin/$BACKUP_BRANCH ..."
git push origin "$BACKUP_BRANCH" --no-verify 2>&1 | tee -a "$LOG_FILE"
git push origin "$TAG" --no-verify 2>&1 | tee -a "$LOG_FILE"

log "=== Backup complete: $TAG ==="
