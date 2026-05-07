#!/bin/bash
# deploy_production.sh — Production deployment script for Liberty Basketball Analysis
# Usage: sudo bash deploy_production.sh [install|start|stop|restart|status|logs]

set -e

REPO_DIR="/opt/liberty-basketball-analysis"
SERVICE_NAME="liberty-basketball-analysis"
NGINX_CONF="deploy/nginx-liberty-basketball-analysis.conf"
NGINX_SITE="/etc/nginx/sites-available/${SERVICE_NAME}"
NGINX_LINK="/etc/nginx/sites-enabled/${SERVICE_NAME}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Install ──────────────────────────────────────────────────────────

install() {
    log "Starting production installation..."

    # Check root
    if [ "$EUID" -ne 0 ]; then
        error "Please run as root: sudo bash deploy_production.sh install"
    fi

    # Install system dependencies
    log "Installing system dependencies..."
    apt-get update -qq
    apt-get install -y -qq nginx ffmpeg python3-venv

    # Create directory
    mkdir -p "$REPO_DIR"
    mkdir -p "$REPO_DIR/logs"
    mkdir -p "$REPO_DIR/uploads"

    # Copy repo if not already there
    if [ ! -f "$REPO_DIR/app.py" ]; then
        error "Please copy the project to $REPO_DIR first"
    fi

    # Set up venv
    if [ ! -d "$REPO_DIR/.venv" ]; then
        log "Creating virtual environment..."
        python3 -m venv "$REPO_DIR/.venv"
    fi

    log "Installing Python dependencies..."
    "$REPO_DIR/.venv/bin/pip" install --upgrade pip -q
    "$REPO_DIR/.venv/bin/pip" install -r "$REPO_DIR/requirements.txt" -q
    "$REPO_DIR/.venv/bin/pip" install gunicorn -q

    # Initialize DB
    log "Initializing database..."
    cd "$REPO_DIR"
    "$REPO_DIR/.venv/bin/python" -c "from app import app, init_db; ctx = app.app_context(); ctx.push(); init_db(); ctx.pop()"

    # Set permissions
    log "Setting permissions..."
    chown -R www-data:www-data "$REPO_DIR"
    chmod -R 755 "$REPO_DIR"

    # Install systemd service
    log "Installing systemd service..."
    sed "s/REPLACE_WITH_SERVER_USER/www-data/g" "$REPO_DIR/deploy/liberty-basketball-analysis.service" > "/etc/systemd/system/${SERVICE_NAME}.service"
    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"

    # Install nginx config
    log "Installing nginx configuration..."
    cp "$REPO_DIR/$NGINX_CONF" "$NGINX_SITE"
    # Remove default site if it exists
    [ -f "/etc/nginx/sites-enabled/default" ] && rm -f "/etc/nginx/sites-enabled/default"
    ln -sf "$NGINX_SITE" "$NGINX_LINK"
    nginx -t && systemctl reload nginx || warn "nginx config test failed — check manually"

    log "Installation complete!"
    log "Start with: sudo bash deploy_production.sh start"
    log "Then access: http://<server-ip>/"
}

# ── Start ────────────────────────────────────────────────────────────

start() {
    log "Starting ${SERVICE_NAME}..."
    systemctl start "$SERVICE_NAME"
    systemctl start nginx
    log "Started. Check status: sudo bash deploy_production.sh status"
}

# ── Stop ─────────────────────────────────────────────────────────────

stop() {
    log "Stopping ${SERVICE_NAME}..."
    systemctl stop "$SERVICE_NAME"
    log "Stopped."
}

# ── Restart ──────────────────────────────────────────────────────────

restart() {
    log "Restarting ${SERVICE_NAME}..."
    systemctl restart "$SERVICE_NAME"
    log "Restarted."
}

# ── Status ───────────────────────────────────────────────────────────

status() {
    echo "=== Systemd Service ==="
    systemctl status "$SERVICE_NAME" --no-pager || true
    echo ""
    echo "=== nginx ==="
    systemctl status nginx --no-pager || true
    echo ""
    echo "=== Port 8080 ==="
    ss -tlnp | grep 8080 || echo "Nothing on 8080"
    echo ""
    echo "=== Port 80 ==="
    ss -tlnp | grep ':80 ' || echo "Nothing on 80"
}

# ── Logs ─────────────────────────────────────────────────────────────

logs() {
    echo "=== Gunicorn Error Log ==="
    tail -50 "$REPO_DIR/logs/gunicorn-error.log" 2>/dev/null || echo "No error log yet"
    echo ""
    echo "=== Gunicorn Access Log ==="
    tail -50 "$REPO_DIR/logs/gunicorn-access.log" 2>/dev/null || echo "No access log yet"
    echo ""
    echo "=== Systemd Journal ==="
    journalctl -u "$SERVICE_NAME" --no-pager -n 50 2>/dev/null || true
}

# ── Main ─────────────────────────────────────────────────────────────

case "${1:-help}" in
    install)  install ;;
    start)    start ;;
    stop)     stop ;;
    restart)  restart ;;
    status)   status ;;
    logs)     logs ;;
    *)
        echo "Usage: sudo bash deploy_production.sh {install|start|stop|restart|status|logs}"
        exit 1
        ;;
esac
