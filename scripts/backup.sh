#!/usr/bin/env bash
# backup.sh — Full project backup to the `backups` branch on GitHub.
#
# Creates a temporary copy of the project in /home (which has 36GB free),
# initializes a fresh git repo, commits everything (including uploads/ and
# model files), and force-pushes to origin/backups.
#
# Safe to run while the main project is actively being worked on — we never
# touch the main project's .git or working directory.

set -euo pipefail

PROJECT_DIR="/home/monk-admin/PROJECTS/liberty-basketball-analysis"
BACKUP_DIR="/home/monk-admin/liberty-backup-tmp"
BACKUP_BRANCH="backups"
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

# 2. Copy the project (exclude .git, .venv, __pycache__)
log "Copying project to $BACKUP_DIR ..."
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

# 3. Initialize a fresh git repo
cd "$BACKUP_DIR"
git init
git config user.email "backup@liberty.local"
git config user.name "Liberty Backup"

# 4. Add remote (use the same SSH key as the main repo)
git remote add origin git@github.com:scottmcconnell1-bot/liberty-basketball-analysis.git

# 5. Create a permissive .gitignore (only exclude noise, NOT uploads/models)
cat > .gitignore << 'GITIGNORE'
__pycache__/
.venv/
venv/
env/
*.py[cod]
*.so
.pytest_cache/
.DS_Store
*.db-shm
*.db-wal
GITIGNORE

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

# 10. Force-push to origin backups branch
log "Pushing to origin/$BACKUP_BRANCH ..."
git push origin HEAD:"$BACKUP_BRANCH" --force --no-verify 2>&1 | tee -a "$LOG_FILE"
git push origin "$TAG" --no-verify 2>&1 | tee -a "$LOG_FILE"

log "=== Backup complete: $TAG ==="
