#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="$ROOT_DIR/data/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/mydrive_backup_${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "=========================================="
echo "          MyDrive Backup Utility          "
echo "=========================================="

cd "$ROOT_DIR"

if [ ! -f "data/mydrive.db" ]; then
    echo "ERROR: SQLite database data/mydrive.db does not exist."
    exit 1
fi

echo "[*] Creating atomic SQLite backup..."
python3 -c "
import sqlite3
source = sqlite3.connect('$ROOT_DIR/data/mydrive.db')
dest = sqlite3.connect('$ROOT_DIR/data/backup_temp.db')
source.backup(dest)
dest.close()
source.close()
"

echo "[*] Archiving database, environment configuration, and logs..."
tar -czf "$BACKUP_FILE" -C "$ROOT_DIR" \
    --transform="s|data/backup_temp.db|mydrive.db|" \
    data/backup_temp.db \
    .env

rm -f "$ROOT_DIR/data/backup_temp.db"

BACKUP_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
echo "[✓] Backup created successfully!"
echo "    Archive: $BACKUP_FILE ($BACKUP_SIZE)"
echo "    Contains: SQLite database + .env secrets"
echo "=========================================="
