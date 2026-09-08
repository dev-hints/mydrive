import os
import logging
import asyncio
import time
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, get_db
from app.storage import storage_manager
from app.security import get_current_user_optional, is_request_secure

# Import API routers
from app.api.auth import router as auth_router
from app.api.files import router as files_router
from app.api.upload import router as upload_router
from app.api.shares import router as shares_router
from app.api.search import router as search_router
from app.api.storage import router as storage_router
from app.api.audit import router as audit_router
from app.api.settings import router as settings_router
from app.api.health import router as health_router
from app.api.users import router as users_router
from app.api.profile import router as profile_router
from app.api.contacts import router as contacts_router

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("mydrive")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
TEMPLATES_DIR = FRONTEND_DIR / "templates"
STATIC_DIR = FRONTEND_DIR / "static"

async def cleanup_abandoned_uploads_task():
    """Background task to periodically clean abandoned chunked uploads and temporary download zips."""
    while True:
        try:
            temp_dir = storage_manager.get_temp_dir()
            now = time.time()
            if temp_dir.exists():
                for item in list(temp_dir.glob("*.part")) + list(temp_dir.glob("download_*.zip")):
                    try:
                        age_limit = 3600 if item.name.endswith(".zip") else 86400
                        if item.stat().st_mtime < (now - age_limit):
                            item.unlink(missing_ok=True)
                    except OSError:
                        pass
        except Exception as e:
            logger.warning(f"Error during abandoned uploads/temp files cleanup: {e}")
        await asyncio.sleep(3600)  # Run hourly

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing MyDrive database and directories...")
    init_db()
    storage_manager.get_storage_root()
    storage_manager.get_trash_dir()
    storage_manager.get_temp_dir()
    logger.info(f"Storage root initialized at: {settings.get_resolved_storage_root()}")

    cleanup_task = asyncio.create_task(cleanup_abandoned_uploads_task())
    yield
    # Shutdown
    cleanup_task.cancel()
    logger.info("MyDrive server stopped gracefully.")

docs_url = "/docs" if settings.ENABLE_DOCS else None
redoc_url = "/redoc" if settings.ENABLE_DOCS else None

app = FastAPI(
    title=settings.APP_NAME,
    description="Lightweight, Production-Ready Private Cloud Drive for Android Termux + Debian PRoot",
    version="1.0.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    lifespan=lifespan
)

# Cache-busting helpers
def get_assets_version() -> str:
    static_targets = [
        STATIC_DIR / "js" / "icons.js",
        STATIC_DIR / "js" / "app.js",
        STATIC_DIR / "js" / "upload.js",
        STATIC_DIR / "js" / "preview.js",
        STATIC_DIR / "css" / "app.css"
    ]
    mtimes = [f.stat().st_mtime for f in static_targets if f.exists()]
    return str(int(max(mtimes))) if mtimes else "2.1.0"

def render_template(template_name: str) -> str:
    template_path = TEMPLATES_DIR / template_name
    content = template_path.read_text(encoding="utf-8")
    v = get_assets_version()
    # Append dynamic version query strings to all static CSS and JS references
    for ext in (".css", ".js"):
        content = content.replace(f'{ext}"', f'{ext}?v={v}"')
        content = content.replace(f"{ext}'", f"{ext}?v={v}'")
    return content

# Security & Cache Control Headers Middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if "Content-Security-Policy" not in response.headers:
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; "
            "media-src 'self' blob:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'self'; "
            "object-src 'none';"
        )

    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    # Aggressive Cache-Busting Control:
    # 1. HTML Pages and API endpoints must never be stored in stale browser cache
    path = request.url.path
    if path in ("/", "/login", "/setup", "/register", "/signup") or path.startswith("/s/") or path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    elif path.startswith("/static/"):
        # 2. Static assets must always be revalidated with the server (ETag / If-Modified-Since)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"

    return response

# Global Exception Handler (Never leak Python tracebacks in production)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception on {request.method} {request.url.path}: {exc}")
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred. Please try again later."}
        )
    return HTMLResponse(
        content="<h1>500 - Internal Server Error</h1><p>An unexpected error occurred. Please check server logs.</p>",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )

# Version Endpoint for Auto-Update Check
@app.get("/api/version")
def get_current_version():
    return {"version": get_assets_version(), "app": settings.APP_NAME}

# Include Routers
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(files_router)
app.include_router(upload_router)
app.include_router(shares_router)
app.include_router(search_router)
app.include_router(storage_router)
app.include_router(audit_router)
app.include_router(settings_router)
app.include_router(users_router)
app.include_router(profile_router)
app.include_router(contacts_router)

# Mount Static Files
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# UI Page Routes
@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    # Check if setup needed
    with get_db() as conn:
        user_count = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
        if user_count == 0:
            return RedirectResponse(url="/setup", status_code=status.HTTP_302_FOUND)

    user = await get_current_user_optional(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    return HTMLResponse(content=render_template("index.html"))

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    with get_db() as conn:
        user_count = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
        if user_count == 0:
            return RedirectResponse(url="/setup", status_code=status.HTTP_302_FOUND)

    user = await get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)

    return HTMLResponse(content=render_template("login.html"))

@app.get("/setup", response_class=HTMLResponse)
async def setup_page():
    with get_db() as conn:
        user_count = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
        if user_count > 0:
            return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    return HTMLResponse(content=render_template("login.html"))

@app.get("/register", response_class=HTMLResponse)
@app.get("/signup", response_class=HTMLResponse)
async def register_page(request: Request):
    user = await get_current_user_optional(request)
    if user:
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    return HTMLResponse(content=render_template("login.html"))

@app.get("/s/{token}", response_class=HTMLResponse)
@app.get("/s/{token}/", response_class=HTMLResponse)
async def share_view_page(token: str):
    return HTMLResponse(content=render_template("share.html"))
