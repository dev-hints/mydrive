#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "   MyDrive Installation (PRoot Userspace) "
echo "=========================================="

cd "$ROOT_DIR"

# 1. Check Python
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is not installed."
    echo "In Debian PRoot, run: apt update && apt install -y python3 python3-pip"
    exit 1
fi

echo "[✓] Python $(python3 --version) detected."

# 2. Install pip if missing
if ! python3 -m pip --version >/dev/null 2>&1; then
    echo "[!] pip not found for python3. Attempting user bootstrap..."
    curl -sSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    python3 /tmp/get-pip.py --user --break-system-packages
    rm -f /tmp/get-pip.py
fi

echo "[✓] Pip $(python3 -m pip --version | awk '{print $2}') ready."

# 3. Install Python dependencies
echo "[*] Installing Python packages from requirements.txt..."
python3 -m pip install --user --break-system-packages -r "$ROOT_DIR/requirements.txt"
echo "[✓] Python dependencies installed."

# 4. Create directories
echo "[*] Creating data and storage directories..."
mkdir -p "$ROOT_DIR/data/storage"
mkdir -p "$ROOT_DIR/data/uploads_temp"
mkdir -p "$ROOT_DIR/data/trash"
mkdir -p "$ROOT_DIR/data/avatars"
mkdir -p "$ROOT_DIR/data/backups"

# 5. Generate .env if missing
if [ ! -f "$ROOT_DIR/.env" ]; then
    echo "[*] Generating .env configuration with cryptographically secure secrets..."
    python3 -c "
import secrets

session_secret = secrets.token_hex(32)
csrf_secret = secrets.token_hex(32)

env_content = f'''APP_NAME=MyDrive
HOST=0.0.0.0
PORT=8080
DEBUG=false
STORAGE_ROOT=data/storage
DATABASE_PATH=data/mydrive.db
TEMP_UPLOAD_DIR=data/uploads_temp
TRASH_DIR=data/trash
AVATARS_DIR=data/avatars
SESSION_SECRET={session_secret}
CSRF_SECRET={csrf_secret}
COOKIE_SECURE=false
MAX_UPLOAD_SIZE=10737418240
CHUNK_SIZE=4194304
SESSION_LIFETIME_DAYS=30
RATE_LIMIT_LOGIN_ATTEMPTS=5
RATE_LIMIT_LOCKOUT_MINUTES=15
SHOW_HIDDEN_FILES=false
ENABLE_DOCS=false
LOG_LEVEL=INFO
'''
with open('$ROOT_DIR/.env', 'w') as f:
    f.write(env_content)
"
    echo "[✓] .env generated."
else
    echo "[✓] .env configuration exists."
fi

# 6. Initialize database
echo "[*] Initializing SQLite database schema..."
python3 -m app.database
echo "[✓] Database initialized."

# 7. Health Check
echo "[*] Verifying core modules..."
python3 -c "from app.main import app; from app.storage import storage_manager; print('Application integrity check passed.')"

echo ""
echo "=========================================="
echo "   Installation completed successfully!   "
echo "=========================================="
echo "To start the server in background:"
echo "   bash scripts/start.sh"
echo ""
echo "To check server status:"
echo "   bash scripts/status.sh"
echo ""
echo "To stop the server:"
echo "   bash scripts/stop.sh"
echo "=========================================="
