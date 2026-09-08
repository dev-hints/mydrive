import sys
import os
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Two-pass canvas to dynamically compute and display total page count."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Header (shown on pages > 1)
        if self._pageNumber > 1:
            self.drawString(54, 752, "MyDrive — Self-Hosted Private Cloud System Manual")
            self.drawRightString(612 - 54, 752, "Production & Architecture Guide")
            self.setStrokeColor(colors.HexColor("#e2e8f0"))
            self.setLineWidth(0.5)
            self.line(54, 744, 612 - 54, 744)

        # Footer (all pages)
        page_text = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(612 - 54, 34, page_text)
        self.drawString(54, 34, "MyDrive • Self-Hosted • Zero-Telemetry • Cross-Platform")
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(54, 44, 612 - 54, 44)

        self.restoreState()

def build_pdf(filename):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Typography styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=colors.HexColor('#0f172a'),
        spaceAfter=4
    )

    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#2563eb'),
        spaceAfter=12
    )

    h1_style = ParagraphStyle(
        'H1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor('#1e40af'),
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'H2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#0f172a'),
        spaceBefore=9,
        spaceAfter=4,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#334155'),
        spaceAfter=5
    )

    bullet_style = ParagraphStyle(
        'Bullet',
        parent=body_style,
        leftIndent=12,
        spaceAfter=3
    )

    code_style = ParagraphStyle(
        'CodeBlock',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor('#0f172a'),
        backColor=colors.HexColor('#f1f5f9'),
        borderPadding=6,
        spaceBefore=4,
        spaceAfter=6
    )

    callout_style = ParagraphStyle(
        'Callout',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#1e3a8a'),
        backColor=colors.HexColor('#eff6ff'),
        borderColor=colors.HexColor('#bfdbfe'),
        borderWidth=1,
        borderPadding=7,
        spaceBefore=5,
        spaceAfter=6
    )

    story = []

    # Title & Header
    story.append(Paragraph("MyDrive Private Cloud", title_style))
    story.append(Paragraph("Comprehensive User, Administrator & Multi-Device Operations Manual", subtitle_style))
    story.append(Paragraph("<b>Architecture:</b> FastAPI • SQLite (WAL) • Vanilla ES6+ SPA • Multi-User • Touch/Mobile Optimized", body_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2563eb'), spaceAfter=10))

    # Quick Access Reference Box
    quick_data = [
        [Paragraph("<b>DEPLOYMENT / LOCATION</b>", body_style), Paragraph("<b>CONNECTION ADDRESS</b>", body_style), Paragraph("<b>MODE</b>", body_style)],
        [Paragraph("<b>Local Device Loopback</b>", body_style), Paragraph("<code>http://127.0.0.1:8080</code>", code_style), Paragraph("Localhost loopback", body_style)],
        [Paragraph("<b>Local Network (Wi-Fi / LAN)</b>", body_style), Paragraph("<code>http://&lt;HOST_IP&gt;:8080</code>", code_style), Paragraph("Direct Gigabit LAN", body_style)],
        [Paragraph("<b>Cloudflare Zero-Trust Tunnel</b>", body_style), Paragraph("<code>https://&lt;your-tunnel&gt;.trycloudflare.com</code>", code_style), Paragraph("Encrypted WAN Tunnel", body_style)],
        [Paragraph("<b>Tailscale / WireGuard Mesh</b>", body_style), Paragraph("<code>http://100.x.y.z:8080</code>", code_style), Paragraph("Private P2P Overlay", body_style)],
    ]
    t_quick = Table(quick_data, colWidths=[150, 210, 144])
    t_quick.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    story.append(t_quick)
    story.append(Spacer(1, 8))

    # Section 1: System Overview & Core Capabilities
    story.append(Paragraph("1. System Overview & Core Capabilities", h1_style))
    story.append(Paragraph(
        "MyDrive is a modern, lightweight, self-hosted private cloud storage system with a clean Google-Drive-like user experience. "
        "Engineered with zero third-party telemetry, MyDrive gives you 100% data sovereignty. It can be deployed on standard Linux servers, "
        "Docker containers, Raspberry Pis, macOS, Windows WSL, and Android phones running Termux with Debian PRoot without root permissions.",
        body_style
    ))
    story.append(Paragraph("<b>Key Features:</b>", h2_style))
    story.append(Paragraph("• <b>Multi-User System:</b> Role-based access control (Admin vs User), user provisioning, quota limits, and per-user storage isolation.", bullet_style))
    story.append(Paragraph("• <b>Resumable Chunked Uploads:</b> Upload large multi-gigabyte files split into 4MB slices with real-time speed, ETA, and auto-resume.", bullet_style))
    story.append(Paragraph("• <b>In-Browser Media Streaming:</b> Stream audio and video using HTTP 206 Partial Content with instantaneous seeking.", bullet_style))
    story.append(Paragraph("• <b>Rich File Previews:</b> Integrated lightbox for photos, full PDF reader, and syntax-highlighted code and markdown viewer.", bullet_style))
    story.append(Paragraph("• <b>Secure Sharing:</b> Generate public or password-protected links with optional expiration dates and download-only flags.", bullet_style))
    story.append(Paragraph("• <b>Touch & Mobile Optimized:</b> Floating Action Button (FAB), bottom action sheets, safe-area inset support, pinch-to-zoom, and gestures.", bullet_style))
    story.append(Paragraph("• <b>Enterprise Security:</b> Argon2id hashing, CSRF tokens, HttpOnly SameSite cookies, brute-force lockout, and canonical path traversal defense.", bullet_style))
    story.append(Paragraph("• <b>Audit Logging:</b> Full administrative activity history tracking logins, file updates, shares, and system modifications.", bullet_style))

    # Section 2: Deployment & Server Execution
    story.append(Paragraph("2. Deployment & Installation Guide", h1_style))
    story.append(Paragraph("<b>Option A: Native Linux / Python Environment</b>", h2_style))
    story.append(Paragraph(
        "# Clone repository & install dependencies<br/>"
        "git clone &lt;repository-url&gt; mydrive && cd mydrive<br/>"
        "python3 -m venv venv && source venv/bin/activate<br/>"
        "pip install -r requirements.txt<br/><br/>"
        "# Generate environment configuration & initialize database<br/>"
        "cp .env.example .env<br/>"
        "python3 -m app.database<br/><br/>"
        "# Start server<br/>"
        "python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8080",
        code_style
    ))

    story.append(Paragraph("<b>Option B: Docker & Docker Compose</b>", h2_style))
    story.append(Paragraph(
        "# Build and launch container in background<br/>"
        "docker compose up -d<br/>"
        "# Check logs<br/>"
        "docker compose logs -f",
        code_style
    ))

    story.append(Paragraph("<b>Option C: Android Termux + Debian PRoot (24/7 Phone Cloud)</b>", h2_style))
    story.append(Paragraph(
        "1. In Termux, run <code>termux-setup-storage</code> and <code>termux-wake-lock</code>.<br/>"
        "2. Enter Debian: <code>proot-distro login debian</code>.<br/>"
        "3. Navigate to mydrive and run: <code>bash scripts/install.sh</code>.<br/>"
        "4. Start background service: <code>bash scripts/start.sh</code> (starts Uvicorn detached with setsid).<br/>"
        "5. Disable Android battery optimization for Termux (Settings → Apps → Termux → Battery → Unrestricted).",
        body_style
    ))

    # Section 3: First-Run Setup & Navigation
    story.append(Paragraph("3. First-Run Setup & User Onboarding", h1_style))
    story.append(Paragraph(
        "<b>Zero-Config Initial Admin Setup:</b> On first launch, visiting the app automatically detects an unconfigured database and "
        "displays the <b>Initial System Setup Wizard</b>. You will be prompted to create the primary administrator account. "
        "Passwords must be at least 8 characters long and are hashed with <b>Argon2id</b>. Once configured, the setup wizard is permanently locked.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Interface Layout:</b><br/>"
        "• <b>Header:</b> Hamburger toggle, adaptive search bar with instant query matching, light/dark/system theme toggle, and profile avatar menu.<br/>"
        "• <b>Sidebar:</b> '+ New' button (Upload File, Upload Folder, New Folder), navigation (My Drive, Recent, Starred, Shared Links, Trash), and live storage meter.<br/>"
        "• <b>Content Area:</b> Interactive breadcrumb trail, multi-select toolbar, Grid/List view switcher, and file gallery.<br/>"
        "• <b>Mobile Floating Action Button (FAB):</b> On screens &le; 1024px, a quick FAB at the bottom right triggers a mobile bottom sheet for easy uploads.",
        body_style
    ))

    # Section 4: File Management & Upload Engine
    story.append(Paragraph("4. Core Operations & Chunked Upload Engine", h1_style))
    story.append(Paragraph(
        "<b>Large File Chunked Uploads:</b> Standard browser uploads fail or crash low-memory devices on files larger than 1GB. "
        "MyDrive solves this with an asynchronous chunked streaming pipeline: files are sliced into 4MB binary pieces in userspace and "
        "streamed directly to disk. If Wi-Fi disconnects mid-upload, simply re-uploading the file instantly checks existing chunks on the server "
        "and resumes from the exact point of interruption with zero data loss.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Folder Hierarchy Uploads:</b> Clicking '+ New' → 'Upload Folder' (or dragging an entire directory tree on desktop) "
        "preserves complete nested subfolder structures automatically.",
        body_style
    ))
    story.append(Paragraph(
        "<b>Context Menu Operations:</b> Right-clicking any item (or tapping the '⋮' action menu on mobile) provides:<br/>"
        "• <b>Preview / Open:</b> Opens the file in the full-screen interactive lightbox.<br/>"
        "• <b>Download:</b> Downloads the file or streams an on-the-fly zip archive for folders.<br/>"
        "• <b>Star / Unstar:</b> Pins critical files into the Starred favorites view.<br/>"
        "• <b>Rename / Move / Copy:</b> File tree management with atomic metadata updates and collision renaming (e.g., <code>report (1).pdf</code>).<br/>"
        "• <b>Trash & Restore:</b> Safe two-stage deletion. Items move to the Trash folder and can be restored or purged permanently.",
        body_style
    ))

    # Section 5: Media Streaming & Previews
    story.append(Paragraph("5. Universal In-Browser Media & Document Previews", h1_style))
    story.append(Paragraph(
        "• <b>Audio & Video:</b> Streams MP4, WebM, MKV, MP3, WAV, and OGG using <code>HTTP 206 Partial Content</code> range headers. "
        "Users can scrub through multi-hour movies or recordings instantly without buffering the entire file.<br/>"
        "• <b>Images:</b> Fullscreen lightbox supporting PNG, JPG, WebP, SVG, GIF, AVIF, and HEIC with pinch-to-zoom and pan.<br/>"
        "• <b>PDFs:</b> Native high-fidelity PDF viewer with page zoom, search, and navigation.<br/>"
        "• <b>Code & Text:</b> Built-in syntax-colored code viewer for Python, JavaScript, HTML, CSS, JSON, YAML, Markdown, and shell scripts.",
        body_style
    ))

    # Section 6: Secure File Sharing Engine
    story.append(Paragraph("6. Public & Password-Protected Sharing Engine", h1_style))
    story.append(Paragraph(
        "Share files or entire directories with clients or friends without granting account access:<br/>"
        "1. Right-click any file/folder &rarr; Select <b>'Get Share Link'</b>.<br/>"
        "2. <b>Password Protection:</b> (Optional) Require a secure passphrase before access is granted.<br/>"
        "3. <b>Expiration Timers:</b> (Optional) Set the link to expire automatically after 1 Hour, 1 Day, 7 Days, 30 Days, or Never.<br/>"
        "4. <b>Download-Only Mode:</b> Prevent in-browser rendering for confidential documents.<br/>"
        "5. The recipient receives a clean link (e.g., <code>/s/TOKEN_ID</code>). The owner can view download counters and revoke links at any time.",
        body_style
    ))

    # Section 7: Contacts Management & Phone Address Book Sync
    story.append(Paragraph("7. Contacts Management & Phone Address Book Sync", h1_style))
    story.append(Paragraph(
        "MyDrive includes a secure, self-hosted address book engine with multi-format import and export capabilities:<br/>"
        "• <b>Direct Phone Address Book Upload:</b> On modern mobile browsers (e.g. Chrome on Android), tapping <b>'Import from Phone'</b> "
        "invokes the native Contact Picker API (<code>navigator.contacts.select</code>) with system permissions. You can pick any number of contacts "
        "from your device and upload them directly to your private cloud in one tap.<br/>"
        "• <b>Manual Contact Management:</b> Add, view, edit, search, and delete contacts with name, phone, email, company, and notes.<br/>"
        "• <b>Direct Dial & Email Integration:</b> Tap any phone number to place a call instantly (<code>tel:</code> link) or tap an email to compose a message.<br/>"
        "• <b>vCard (.vcf) Import & Export:</b> Import or export contact backup files compatible with Android, iPhone, Google Contacts, Apple Address Book, and Outlook.<br/>"
        "• <b>Spreadsheet CSV Import & Export:</b> Full CSV import with auto-detected columns and clean CSV export for spreadsheets and backups.<br/>"
        "• <b>Favorites & Batch Operations:</b> Star important contacts, multi-select items, and perform bulk deletions.",
        body_style
    ))

    # Section 8: Mobile Responsiveness & Touch Gestures
    story.append(Paragraph("8. Mobile Responsiveness & Touch Optimization Guide", h1_style))
    story.append(Paragraph(
        "MyDrive features an adaptive, app-like touch interface tailored for smartphones and tablets:<br/>"
        "• <b>Safe-Area Inset Handling:</b> Full compatibility with device notches, Dynamic Islands, and curved status bars.<br/>"
        "• <b>Compact Responsive Header:</b> Fits hamburger toggle, search bar, theme switcher, and profile avatar seamlessly down to 320px screens.<br/>"
        "• <b>Mobile Action Bottom Sheet:</b> Replaces desktop context menus with native thumb-friendly bottom sheets on touch devices.<br/>"
        "• <b>Multi-Touch Gestures:</b> Pinch-to-zoom (0.5x–4.0x), double-tap zoom (1x/2x), pull-down to dismiss, and swipe left/right between items.<br/>"
        "• <b>Long-Press Selection:</b> Touch-and-hold any file card or list row for 500ms to activate multi-item selection with haptic feedback.",
        body_style
    ))

    # Section 9: Multi-User Administration & Security
    story.append(Paragraph("9. Multi-User Administration & Security Architecture", h1_style))
    story.append(Paragraph(
        "<b>Role-Based Access Control (RBAC):</b> Administrators have access to the User Management dashboard to create users, "
        "modify account status, reset passwords, and set storage quotas (e.g., 5GB, 20GB, or unlimited). Non-admin users are strictly isolated "
        "in their respective storage namespaces (<code>data/storage/users/&lt;user_id&gt;</code>).",
        body_style
    ))
    story.append(Paragraph(
        "<b>Security Defenses:</b><br/>"
        "• <b>Canonical Path Traversal Protection:</b> The <code>resolve_safe_path()</code> engine computes real canonical paths using <code>os.path.realpath()</code> "
        "and rejects directory escapes (<code>../../</code>) or symlink breakout attacks with HTTP 403.<br/>"
        "• <b>Brute-Force Rate Limiting:</b> Tracks failed login attempts per IP and username, locking out attackers after 5 failures for 15 minutes.<br/>"
        "• <b>Audit Logging:</b> Critical operations (logins, user creations, setting changes, file purges) are permanently recorded in the <code>audit_logs</code> table.",
        body_style
    ))

    # Section 10: Server Management Commands
    story.append(Paragraph("10. Maintenance, Process Management & Backups", h1_style))
    cmd_data = [
        [Paragraph("<b>COMMAND</b>", body_style), Paragraph("<b>PURPOSE & EXECUTION</b>", body_style)],
        [Paragraph("<code>bash scripts/start.sh</code>", code_style), Paragraph("Starts MyDrive in the background detached using <code>setsid</code>.", body_style)],
        [Paragraph("<code>bash scripts/status.sh</code>", code_style), Paragraph("Displays running PID, memory usage, and health endpoint response.", body_style)],
        [Paragraph("<code>bash scripts/stop.sh</code>", code_style), Paragraph("Gracefully terminates the background server.", body_style)],
        [Paragraph("<code>bash scripts/restart.sh</code>", code_style), Paragraph("Restarts the application daemon.", body_style)],
        [Paragraph("<code>bash scripts/backup.sh</code>", code_style), Paragraph("Creates an atomic SQLite WAL backup and storage archive in <code>data/backups/</code>.", body_style)],
        [Paragraph("<code>pytest</code>", code_style), Paragraph("Executes the comprehensive automated test suite (40 integration and unit tests).", body_style)],
    ]
    t_cmd = Table(cmd_data, colWidths=[180, 324])
    t_cmd.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
    ]))
    story.append(t_cmd)
    story.append(Spacer(1, 8))

    # Section 10: Troubleshooting & FAQ
    story.append(Paragraph("10. Troubleshooting & FAQ", h1_style))
    story.append(Paragraph(
        "<b>Q1: Can I mount an external hard drive or SD card as storage?</b><br/>"
        "Yes. Set <code>STORAGE_ROOT=/path/to/mounted/drive</code> in <code>.env</code> and restart the server. Ensure the process has read/write permissions.<br/><br/>"
        "<b>Q2: How do I access MyDrive from outside my local Wi-Fi without port-forwarding?</b><br/>"
        "Use Cloudflare Zero-Trust Tunnels: run <code>cloudflared tunnel --url http://127.0.0.1:8080</code> to receive an encrypted global HTTPS URL.<br/><br/>"
        "<b>Q3: How do I change an administrator password if I am locked out?</b><br/>"
        "Run in terminal: <code>python3 -c \"from app.security import hash_password; from app.database import get_db; conn = get_db_connection(); conn.execute('UPDATE users SET password_hash=? WHERE username=?', (hash_password('NewPassword123!'), 'admin')); conn.close()\"</code>.",
        body_style
    ))

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated PDF manual at: {filename}")

if __name__ == "__main__":
    output_pdf = str(Path(__file__).resolve().parent / "MyDrive_User_Manual.pdf")
    if len(sys.argv) > 1:
        output_pdf = sys.argv[1]
    build_pdf(output_pdf)
