#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$ROOT_DIR/data/app.pid"

HOST=$(grep -E "^HOST=" "$ROOT_DIR/.env" 2>/dev/null | cut -d '=' -f2 | tr -d ' "')
PORT=$(grep -E "^PORT=" "$ROOT_DIR/.env" 2>/dev/null | cut -d '=' -f2 | tr -d ' "')
HOST=${HOST:-127.0.0.1}
PORT=${PORT:-8080}

echo "=========================================="
echo "         MyDrive Server Status            "
echo "=========================================="

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "Status:   RUNNING (PID: $PID)"
        echo "URL:      http://${HOST}:${PORT}"
        
        CHECK_HOST="$HOST"
        [ "$CHECK_HOST" = "0.0.0.0" ] && CHECK_HOST="127.0.0.1"
        HEALTH_RES=$(curl -s --max-time 3 "http://${CHECK_HOST}:${PORT}/health" 2>/dev/null || echo "")
        if [ -n "$HEALTH_RES" ]; then
            echo "Health:   $HEALTH_RES"
        else
            echo "Health:   Unable to connect to http://${HOST}:${PORT}/health"
        fi
    else
        echo "Status:   STOPPED (stale PID file exists)"
    fi
else
    echo "Status:   STOPPED"
fi

echo "=========================================="
