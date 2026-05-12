#!/bin/bash
# Track Cloudflare tunnel URL changes
# Stores the last known URL and reports when it changes

STATE_FILE="/home/monk-admin/.cloudflared/last_tunnel_url"
LOG_FILE="/var/log/cloudflared.log"

# Get current tunnel URL from cloudflared logs
CURRENT_URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG_FILE" | tail -1)

if [ -z "$CURRENT_URL" ]; then
    echo "ERROR: Could not find tunnel URL in logs"
    exit 1
fi

# Read last known URL
LAST_URL=""
if [ -f "$STATE_FILE" ]; then
    LAST_URL=$(cat "$STATE_FILE")
fi

# Check if changed
if [ "$CURRENT_URL" != "$LAST_URL" ]; then
    echo "TUNNEL_URL_CHANGED"
    echo "OLD: $LAST_URL"
    echo "NEW: $CURRENT_URL"
    # Save new URL
    echo "$CURRENT_URL" > "$STATE_FILE"
else
    echo "TUNNEL_URL_UNCHANGED"
    echo "URL: $CURRENT_URL"
fi
