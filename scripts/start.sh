#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$ROOT_DIR/data/app.pid"
LOG_FILE="$ROOT_DIR/data/app.log"

cd "$ROOT_DIR"

if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "MyDrive is already running (PID: $OLD_PID)."
        exit 0
    else
        rm -f "$PID_FILE"
    fi
fi

# Read HOST and PORT from .env if available
HOST=$(grep -E "^HOST=" "$ROOT_DIR/.env" 2>/dev/null | cut -d '=' -f2 | tr -d ' "\r')
PORT=$(grep -E "^PORT=" "$ROOT_DIR/.env" 2>/dev/null | cut -d '=' -f2 | tr -d ' "\r')

HOST=${HOST:-127.0.0.1}
PORT=${PORT:-8080}

echo "Starting MyDrive server on http://${HOST}:${PORT}..."
mkdir -p "$ROOT_DIR/data"

# Use setsid to detach cleanly from PRoot pseudo-terminal
setsid python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT" < /dev/null >> "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

# Wait up to 10 seconds to verify startup
for i in {1..20}; do
    if ! kill -0 "$NEW_PID" 2>/dev/null; then
        echo "ERROR: Server failed to start. Check $LOG_FILE:"
        tail -n 20 "$LOG_FILE"
        rm -f "$PID_FILE"
        exit 1
    fi
    CHECK_HOST="$HOST"
    [ "$CHECK_HOST" = "0.0.0.0" ] && CHECK_HOST="127.0.0.1"
    if curl -s "http://${CHECK_HOST}:${PORT}/health" >/dev/null 2>&1; then
        echo "[✓] MyDrive started successfully!"
        echo "    PID:  $NEW_PID"
        echo "    URL:  http://${HOST}:${PORT}"
        echo "    Logs: $LOG_FILE"
        exit 0
    fi
    sleep 0.5
done

echo "[*] Server process started (PID: $NEW_PID)."
exit 0
