#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "Updating MyDrive..."
cd "$ROOT_DIR"

if [ -d ".git" ]; then
    echo "[*] Pulling latest git changes..."
    git pull || true
fi

echo "[*] Updating Python dependencies..."
python3 -m pip install --user --break-system-packages -r requirements.txt

echo "[*] Running database migrations..."
python3 -m app.database

echo "[✓] Update completed successfully."
