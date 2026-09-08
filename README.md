<div align="center">

# ☁️ MyDrive

### High-Performance, Self-Hosted Private Cloud Storage & Media Streaming

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-WAL%20Mode-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-40%20Passed-brightgreen?logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

*A modern, lightweight Google-Drive-style personal cloud drive designed for 100% data sovereignty. Runs smoothly on standard Linux servers, Docker, Raspberry Pi, macOS, Windows WSL, and Android phones (Termux + Debian PRoot) with zero root requirements.*

[Key Features](#-key-features) • [Quick Start](#-quick-start) • [Docker Deployment](#-docker-deployment) • [Android Termux Guide](#-android-termux-guide) • [Security](#-security--privacy-architecture) • [API Reference](#-api-reference) • [PDF Manual](#-user--administrator-manual-pdf)

</div>

---

## 📖 Overview

**MyDrive** is an enterprise-grade, self-hosted file management and media streaming server. It gives you the convenience, speed, and elegance of commercial cloud drives like Google Drive or Dropbox without compromising your privacy, subjecting you to monthly subscription fees, or leaking telemetry to third parties.

Whether deployed on a dedicated homelab server, a cloud VPS behind an Nginx reverse proxy, or directly inside an Android smartphone as an ultra-portable 24/7 pocket server, MyDrive provides an adaptive, touch-optimized single-page interface with real-time resumable uploads, instant video seeking, encrypted password-protected link sharing, and strict role-based access control.

---

## ✨ Key Features

### 🗂️ Intuitive File & Folder Management
- **Single Page Application (SPA):** Fast, reactive Vanilla JavaScript (ES6+) frontend without heavy runtime frameworks.
- **Drag & Drop:** Upload files and nested folder hierarchies directly from your desktop file manager.
- **Breadcrumb Navigation & Tree Traversal:** Instant directory traversal with URL-synced breadcrumbs and fluid back/forward navigation.
- **Organization Tools:** Star/favorite critical files, batch select, rename, move, copy, and search instantly.
- **Two-Stage Recycle Bin:** Trashed files are isolated in safe storage with instant single-click restoration or permanent purging.
- **Archive Extraction & Bundling:** Stream entire directories as `.zip` archives on the fly with Unicode and emoji preservation.

### ⚡ Resumable Chunked Streaming Upload Engine
- **Memory-Safe Uploads:** Large multi-gigabyte files are sliced into 4MB binary chunks and streamed directly to disk, completely preventing RAM spikes or Out-Of-Memory (OOM) crashes on low-resource hardware.
- **Auto-Resume on Network Drops:** If a connection drops mid-upload, simply re-uploading checks existing chunks on the server and resumes from the exact interruption offset with zero data corruption.
- **Real-Time Progress Drawer:** Floating upload dock showing active items, percentage, instantaneous transfer speed (MB/s), and estimated time to completion (ETA).

### 🎬 Universal In-Browser Media & Document Previews
- **Video & Audio Streaming:** Native streaming for MP4, WebM, MKV, MP3, WAV, and OGG using `HTTP 206 Partial Content (Range requests)`. Scrub or skip through multi-hour movies instantly without waiting for the full file to buffer.
- **Image Lightbox:** High-resolution image viewer (PNG, JPG, WebP, SVG, GIF, AVIF, HEIC) with pan, pinch-to-zoom, and slideshow controls.
- **Integrated PDF Reader:** In-browser document viewer with zoom, page navigation, and text selection.
- **Code & Markdown Viewer:** Built-in viewer for text, Markdown, Python, JavaScript, JSON, YAML, HTML, CSS, and shell scripts.

### 🔗 Public & Protected Link Sharing
- **Self-Contained Share Links:** Share any file or folder with external recipients who do not have an account.
- **Password Protection:** Protect confidential documents with a custom passphrase before access is granted.
- **Expiration Timers:** Automatically revoke share links after 1 Hour, 1 Day, 7 Days, 30 Days, or keep them active permanently.
- **Download-Only Restriction:** Prevent in-browser rendering for sensitive material, forcing direct download.
- **Live Telemetry & Revocation:** Track access counts and revoke active share links instantly from the dashboard.

### 📇 Contacts Management & Phone Address Book Sync
- **Direct Phone Contact Picker:** Sync contacts directly from your smartphone or tablet using the native Web Contact Picker API (`navigator.contacts.select`) without installing extra native apps.
- **Comprehensive vCard & CSV Support:** Bi-directional import and export with RFC 6350 standard vCard (`.vcf`) files and smart-header CSV spreadsheets.
- **Manual Contact Creator:** Clean, responsive modal for manual entry with name, phone, email, notes, company, job title, and favorite status.
- **Actionable Cards & List View:** Click-to-call (`tel:`) and click-to-email (`mailto:`) links, search filtering across all contact fields, instant star toggling, and bulk deletion.
- **Privacy & Storage Isolation:** Address books are strictly partitioned per user account with zero external cloud telemetry.

### 📱 Smartphone, Mobile & Tablet Optimization
- **Safe-Area Inset Handling:** Full support for modern phone notches, Dynamic Islands, and curved mobile status bars (`viewport-fit=cover`).
- **Compact Adaptive Header:** Fits the hamburger drawer toggle, fluid search bar, theme toggle, and profile avatar seamlessly down to 320px screens.
- **Floating Action Button (FAB):** Quick touch-accessible bottom action button on mobile/tablets (`≤ 1024px`) triggering a mobile bottom action sheet.
- **Multi-Touch Gestures:** Native pinch-to-zoom (`0.5x` to `4.0x`), double-tap zoom (`1x` / `2x`), pull-down to dismiss, and swipe navigation between items.
- **Long-Press Multi-Select:** Touch-and-hold any file card or list row for 500ms to trigger multi-item selection with haptic vibration feedback.

### 👥 Multi-User System & Role-Based Access Control (RBAC)
- **Role Hierarchy:** Distinct `admin` and `user` privileges.
- **Storage Quota Enforcement:** Administrators can allocate specific storage quotas (e.g., 5GB, 50GB, or unlimited) per user. Quotas are strictly enforced in real time during file uploads and folder creations.
- **User Management Dashboard:** Create accounts, toggle active/suspended status, reset user passwords, and view storage allocations.
- **Storage Namespace Isolation:** Each user's files and metadata are strictly partitioned within isolated directory trees (`data/storage/users/<user_id>`).
- **User Profiles:** Custom avatar uploads, display names, email addresses, and self-service password changes.

### 🛡️ Enterprise-Grade Security
- **Argon2id Password Hashing:** State-of-the-art password security with unique cryptographic salts. Plaintext passwords are never saved.
- **Canonical Path Traversal Defense:** All filesystem operations pass through `resolve_safe_path()` which resolves canonical realpaths with `os.path.realpath()` to eliminate directory traversal (`../`) and symlink breakout exploits.
- **Double-Submit CSRF Protection:** Cryptographically signed anti-forgery tokens validate all state-changing HTTP mutations (`POST`, `PUT`, `DELETE`).
- **HttpOnly SameSite Session Cookies:** Session tokens cannot be accessed by client-side scripts, protecting against XSS session theft.
- **Brute-Force Rate Limiting:** Dynamic lockout engine monitors failed authentication attempts per IP and username, applying temporary lockouts after 5 consecutive failures.
- **Audit Logging:** Comprehensive administrative logs recording user logins, account updates, file operations, and setting modifications.

---

## 🏛️ System Architecture

```
                                    CLIENTS
                 (Desktop Browser / Tablet / Smartphone / Smart TV)
                                        │
                                        ▼
                  REVERSE PROXY / TUNNEL (Optional, Recommended)
                   (Nginx with TLS / Cloudflare Zero-Trust Tunnel)
                                        │
                                        ▼
                                 FASTAPI SERVER
                               (Python 3.10-3.14)
                   ┌────────────────────┴────────────────────┐
                   ▼                                         ▼
            HTTP & REST API                           SECURITY ENGINE
         • Chunked Upload Pipeline                 • Argon2id Password Hashing
         • Range Request Streamer                  • Canonical Path Validator
         • Session & Share Controller              • CSRF & Rate Limiter
                   │                                         │
                   ▼                                         ▼
            STORAGE MANAGER                          SQLITE DATABASE
      (Isolated Userspace Storage)                 (WAL Mode + Pragmas)
    • data/storage/users/<id>/                  • User accounts & quotas
    • data/uploads_temp/                        • File metadata & stars
    • data/trash/<id>/                          • Share tokens & sessions
    • data/avatars/                             • Audit logs & rate limits
```

---

## 🚀 Quick Start

### Prerequisites
- **Python:** 3.10 or newer (tested up to 3.14)
- **Git**

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/mydrive.git
   cd mydrive
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment settings:**
   ```bash
   cp .env.example .env
   ```
   *(Optional) Edit `.env` to customize port, host, storage directory, or session secrets.*

5. **Initialize database schema:**
   ```bash
   python3 -m app.database
   ```

6. **Start the development/production server:**
   ```bash
   python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080
   ```

7. **Access the web interface:**
   Open your browser and navigate to:
   ```
   http://localhost:8080
   ```
   On first launch, MyDrive automatically guides you through the **Initial System Setup Wizard** to create your primary administrator account.

---

## 🐳 Docker Deployment

MyDrive includes a production-ready `Dockerfile` and `docker-compose.yml` for effortless containerized deployment.

### Using Docker Compose (Recommended)

1. **Clone and enter the directory:**
   ```bash
   git clone https://github.com/your-username/mydrive.git
   cd mydrive
   ```

2. **Launch container in background:**
   ```bash
   docker compose up -d
   ```

3. **Check container status and logs:**
   ```bash
   docker compose ps
   docker compose logs -f
   ```

4. **Stop the container:**
   ```bash
   docker compose down
   ```

All databases, user files, uploads, and avatars persist reliably in the `./data` volume mount.

---

## 📱 Android Termux Guide (24/7 Pocket Server)

MyDrive was specifically engineered to run in userspace on an Android device via **Termux** and **Debian PRoot** without requiring root permissions, Docker, or native Linux kernel privileges.

### Step 1: In Termux (Android Native Terminal)
```bash
# 1. Grant Android storage access
termux-setup-storage

# 2. Acquire wake-lock to prevent CPU sleep when screen is locked
termux-wake-lock

# 3. Install proot-distro and Debian
pkg update && pkg install -y proot-distro
proot-distro install debian

# 4. Enter Debian PRoot environment
proot-distro login debian
```

### Step 2: In Debian PRoot
```bash
# Clone or transfer MyDrive to your home directory
cd ~
git clone https://github.com/your-username/mydrive.git
cd mydrive

# Run the automated userspace installer
bash scripts/install.sh

# Start the background daemon
bash scripts/start.sh
```

### Step 3: Critical Android Battery Configuration
Android will kill background services aggressively unless unrestricted:
1. Go to Android **Settings** → **Apps** → **Termux** → **Battery**.
2. Select **"Unrestricted"** (turn off battery optimization).
3. Open Android's Recent Apps view and **Pin / Lock** Termux.

---

## 🌐 Remote Access & Network Topologies

| Access Method | URL Example | Description |
| :--- | :--- | :--- |
| **Localhost Loopback** | `http://127.0.0.1:8080` | Direct local access on the host device. |
| **Local Wi-Fi / LAN** | `http://<HOST_IP>:8080` | High-speed local transfer across devices on the same Wi-Fi router. |
| **Cloudflare Tunnel** | `https://*.trycloudflare.com` | Encrypted global HTTPS access without router port forwarding or public IP. |
| **Tailscale / WireGuard** | `http://100.x.y.z:8080` | Secure P2P encrypted virtual mesh network across your authorized devices. |
| **Reverse Proxy (Nginx)** | `https://drive.yourdomain.com` | Production TLS setup with custom domain and automatic Let's Encrypt certificates. |

### Global Access via Cloudflare Tunnel (Zero Port-Forwarding)
To access your MyDrive instance from anywhere in the world without opening router firewall ports:
```bash
# Download cloudflared binary
curl -sSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o cloudflared
chmod +x cloudflared

# Launch tunnel
./cloudflared tunnel --url http://127.0.0.1:8080
```
Cloudflare will output a public HTTPS URL (e.g., `https://random-subdomain.trycloudflare.com`) accessible from any browser worldwide.

---

## ⚙️ Configuration (.env)

All settings are configured via environment variables or a `.env` file in the project root:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `APP_NAME` | `MyDrive` | Brand name displayed across the UI. |
| `HOST` | `0.0.0.0` | Network binding interface (`0.0.0.0` for all interfaces, `127.0.0.1` for local only). |
| `PORT` | `8080` | Port for the HTTP web server. |
| `DEBUG` | `false` | Enable verbose debugging mode. |
| `STORAGE_ROOT` | `data/storage` | Path for stored files (supports absolute paths or external mount points). |
| `DATABASE_PATH` | `data/mydrive.db` | Path to SQLite database file. |
| `TEMP_UPLOAD_DIR` | `data/uploads_temp` | Staging folder for chunked uploads. |
| `TRASH_DIR` | `data/trash` | Storage directory for recycled files. |
| `AVATARS_DIR` | `data/avatars` | Directory storing user profile pictures. |
| `SESSION_SECRET` | *(Random 32-byte hex)* | Cryptographic key used to sign session cookies. |
| `CSRF_SECRET` | *(Random 32-byte hex)* | Secret key used to generate double-submit CSRF tokens. |
| `COOKIE_SECURE` | `false` | Set to `true` when serving over HTTPS/SSL. |
| `MAX_UPLOAD_SIZE` | `10737418240` | Maximum upload size per file in bytes (default: 10 GB). |
| `CHUNK_SIZE` | `4194304` | Upload slice chunk size in bytes (default: 4 MB). |
| `DEFAULT_USER_QUOTA_BYTES` | `5368709120` | Storage quota for self-registered users in bytes (default: 5 GB, 0 = unlimited). |
| `RATE_LIMIT_LOGIN_ATTEMPTS` | `5` | Maximum failed login attempts before temporary lockout. |
| `RATE_LIMIT_LOCKOUT_MINUTES` | `15` | Duration of brute-force lockout window. |

---

## 🛠️ Management Scripts

Convenient shell scripts located in `scripts/` automate daily operational workflows:

```bash
# Start server in background detached (using setsid)
bash scripts/start.sh

# Check process PID, memory usage, and live health endpoint
bash scripts/status.sh

# Gracefully terminate background process
bash scripts/stop.sh

# Stop and restart server daemon
bash scripts/restart.sh

# Create an atomic SQLite WAL backup and storage archive in data/backups/
bash scripts/backup.sh

# Pull latest code and apply migrations
bash scripts/update.sh
```

---

## 📡 API Reference

MyDrive provides a full REST API for programmatic automation and headless integrations:

### Authentication
- `GET /api/auth/setup-status` — Check if initial admin setup is required.
- `POST /api/auth/setup` — Initialize primary administrator account.
- `POST /api/auth/login` — Authenticate and receive session cookies.
- `POST /api/auth/logout` — Revoke session and clear cookies.
- `GET /api/auth/me` — Retrieve current authenticated user profile.

### Files & Folders
- `GET /api/files` — List files and subfolders in a directory path.
- `POST /api/files/folder` — Create a new folder.
- `POST /api/files/rename` — Rename file or directory.
- `POST /api/files/move` — Move item to a new directory.
- `POST /api/files/copy` — Duplicate item to destination.
- `POST /api/files/trash` — Move item to recycle bin.
- `POST /api/files/restore` — Restore item from trash.
- `DELETE /api/files/permanent` — Permanently purge file.
- `GET /api/files/download` — Download file or streamed folder `.zip`.
- `GET /api/files/preview` — Stream file content with HTTP 206 range seeking support.

### Chunked Uploads
- `POST /api/upload/init` — Initialize chunked upload session.
- `POST /api/upload/chunk` — Upload a 4MB binary chunk slice.
- `POST /api/upload/finish` — Assemble verified chunks into destination file.
- `POST /api/upload/cancel` — Cancel active upload and purge temp slices.

### Link Sharing
- `POST /api/shares/create` — Generate public/protected share link.
- `GET /api/shares/list` — List active user share links.
- `DELETE /api/shares/{token}` — Revoke share link.
- `GET /s/{token}` — Public share landing page.
- `POST /api/shares/{token}/verify` — Authenticate password-protected share.

### Contacts & Address Book
- `GET /api/contacts` — List and search contacts with pagination and starred filter.
- `POST /api/contacts` — Create a single contact.
- `POST /api/contacts/batch` — Batch import contacts (e.g., from mobile Contact Picker API).
- `GET /api/contacts/{id}` — Retrieve detailed contact record.
- `PATCH /api/contacts/{id}` — Update contact information.
- `POST /api/contacts/{id}/star` — Toggle starred/favorite status.
- `DELETE /api/contacts/{id}` — Delete contact record.
- `POST /api/contacts/delete-batch` — Batch delete multiple contacts.
- `POST /api/contacts/import-file` — Import contacts from vCard (`.vcf`) or spreadsheet (`.csv`).
- `GET /api/contacts/export/vcf` — Export all contacts to RFC 6350 `.vcf` file.
- `GET /api/contacts/export/csv` — Export all contacts to spreadsheet `.csv` file.

### Administration & Telemetry
- `GET /api/users` — List system users (Admin only).
- `POST /api/users` — Provision new user with quota (Admin only).
- `PATCH /api/users/{id}` — Modify user role, quota, or status (Admin only).
- `GET /api/audit` — Query audit event logs (Admin only).
- `GET /api/storage` — Detailed storage usage breakdown and metrics.

---

## 🧪 Automated Testing Suite

MyDrive includes 40 automated unit and integration tests covering security, authentication, quota limits, chunked uploads, contact import/export, file streaming, and Unicode filename handling:

```bash
# Run full test suite with pytest
pytest -v
```

All tests execute inside isolated temporary sandboxes with automated teardown to ensure zero modification to live data.

---

## 📄 User & Administrator Manual (PDF)

A complete, beautifully formatted printable PDF manual is included in the root directory:
- **File:** `MyDrive_User_Manual.pdf`

To regenerate or customize the PDF manual using ReportLab:
```bash
python3 generate_manual_pdf.py
```

---

## 🔒 Security & Privacy Architecture

- **Zero Data Leakage:** No personal files, databases, or secrets are tracked in this repository. All user data is isolated in `.gitignore`.
- **Timing Attack Mitigation:** Password verification uses constant-time string comparisons.
- **Strict Path Sandboxing:** Prevents symlink breakouts, null-byte injections, and path traversal attacks.
- **Strict Content-Type Sniffing:** Prevents MIME-confusion attacks during file uploads.

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.
