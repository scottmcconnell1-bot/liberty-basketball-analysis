#!/bin/bash
# backup.sh — Backup Liberty Basketball Analysis data
# Usage: bash backup.sh [backup|restore|list] [backup-file]

set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${REPO_DIR}/backups"
DB_FILE="${REPO_DIR}/film_analysis.db"
UPLOADS_DIR="${REPO_DIR}/uploads"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/liberty-backup-${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

case "${1:-help}" in
    backup)
        echo "[BACKUP] Creating backup: $BACKUP_FILE"
        tar -czf "$BACKUP_FILE" \
            -C "$REPO_DIR" \
            film_analysis.db \
            uploads/ \
            2>/dev/null
        echo "[BACKUP] Done. Size: $(du -h "$BACKUP_FILE" | cut -f1)"
        echo "[BACKUP] To restore: bash backup.sh restore $BACKUP_FILE"
        ;;

    restore)
        RESTORE_FILE="${2:-}"
        if [ -z "$RESTORE_FILE" ]; then
            echo "Usage: bash backup.sh restore <backup-file>"
            echo "Available backups:"
            ls -la "$BACKUP_DIR"/*.tar.gz 2>/dev/null || echo "  (none)"
            exit 1
        fi
        if [ ! -f "$RESTORE_FILE" ]; then
            echo "Error: File not found: $RESTORE_FILE"
            exit 1
        fi
        echo "[RESTORE] Restoring from: $RESTORE_FILE"
        echo "[RESTORE] Backing up current data first..."
        tar -czf "${BACKUP_DIR}/pre-restore-${TIMESTAMP}.tar.gz" \
            -C "$REPO_DIR" \
            film_analysis.db \
            uploads/ \
            2>/dev/null || true
        tar -xzf "$RESTORE_FILE" -C "$REPO_DIR"
        echo "[RESTORE] Done. Restart the app to pick up changes."
        ;;

    list)
        echo "Available backups:"
        ls -la "$BACKUP_DIR"/*.tar.gz 2>/dev/null || echo "  (none)"
        ;;

    *)
        echo "Usage: bash backup.sh {backup|restore|list} [backup-file]"
        exit 1
        ;;
esac
