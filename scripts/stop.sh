#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PID_FILE="$ROOT_DIR/data/app.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "MyDrive is not running (PID file missing)."
    exit 0
fi

PID=$(cat "$PID_FILE" 2>/dev/null)
if [ -z "$PID" ]; then
    echo "PID file is empty. Removing."
    rm -f "$PID_FILE"
    exit 0
fi

if ! kill -0 "$PID" 2>/dev/null; then
    echo "Process $PID is not running. Removing stale PID file."
    rm -f "$PID_FILE"
    exit 0
fi

echo "Stopping MyDrive (PID: $PID)..."
kill "$PID" 2>/dev/null || true

for i in {1..20}; do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "[✓] MyDrive stopped gracefully."
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 0.5
done

echo "[!] Process did not exit in 10s. Forcing kill..."
kill -9 "$PID" 2>/dev/null || true
rm -f "$PID_FILE"
echo "[✓] MyDrive terminated."
