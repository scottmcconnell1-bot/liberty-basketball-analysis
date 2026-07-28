#!/bin/bash
# Basketball tunnel watchdog - auto-restarts cloudflared if it dies
while true; do
    if ! pgrep -f "cloudflared tunnel --url http://localhost:8081" > /dev/null 2>&1; then
        echo "$(date): Tunnel down, restarting..." >> /tmp/tunnel-watchdog.log
        nohup cloudflared tunnel --url http://localhost:8081 > /tmp/basketball-tunnel.log 2>&1 &
        sleep 10
        URL=$(grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' /tmp/basketball-tunnel.log | head -1)
        if [ -n "$URL" ]; then
            echo "$(date): Tunnel restarted at $URL" >> /tmp/tunnel-watchdog.log
        fi
    fi
    sleep 30
done
