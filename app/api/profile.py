import os
import re
import html
import time
import uuid
import datetime
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse, Response

from app.database import get_db
from app.security import get_current_user, verify_password, log_audit_event
from app.storage import storage_manager
from app.schemas import ProfileUpdateRequest, WipeDriveRequest, AccountDeleteRequest
from app.config import settings
from app.api.files import format_content_disposition

router = APIRouter(prefix="/api/profile", tags=["profile"])

GRADIENT_PALETTES = [
    ("#6366f1", "#a855f7"),  # Indigo to Purple
    ("#0ea5e9", "#2563eb"),  # Ocean Blue
    ("#10b981", "#059669"),  # Emerald to Teal
    ("#f59e0b", "#d97706"),  # Amber to Orange
    ("#ec4899", "#8b5cf6"),  # Rose to Violet
    ("#06b6d4", "#0284c7"),  # Cyan to Blue
    ("#8b5cf6", "#6d28d9"),  # Violet Deep
    ("#14b8a6", "#0d9488"),  # Teal Deep
]

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"

def get_avatar_dir() -> Path:
    return settings.get_resolved_avatars_dir()

@router.get("")
def get_profile(request: Request, user: dict = Depends(get_current_user)):
    with get_db() as conn:
        db_user = conn.execute(
            """
            SELECT id, username, role, is_active, display_name, email, profile_pic,
                   quota_bytes, created_at, updated_at
            FROM users WHERE id = ?
            """,
            (user["id"],)
        ).fetchone()

        if not db_user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        counts = conn.execute(
            """
            SELECT 
                COUNT(CASE WHEN is_trash = 1 THEN 1 END) as trash_count,
                COUNT(CASE WHEN is_starred = 1 AND is_trash = 0 THEN 1 END) as starred_count
            FROM files_metadata
            WHERE owner_id = ?
            """,
            (user["id"],)
        ).fetchone()

        active_sessions = conn.execute(
            "SELECT COUNT(*) as count FROM sessions WHERE user_id = ?",
            (user["id"],)
        ).fetchone()["count"]

    storage_stats = storage_manager.get_storage_stats(owner_id=user["id"])
    user_info = dict(db_user)
    user_info["avatar_url"] = f"/api/profile/avatar/{user['id']}"

    return {
        "status": "ok",
        "user": user_info,
        "storage": storage_stats,
        "counts": {
            "files": storage_stats.get("file_count", 0),
            "folders": storage_stats.get("folder_count", 0),
            "trash": counts["trash_count"] if counts else 0,
            "starred": counts["starred_count"] if counts else 0,
            "active_sessions": active_sessions
        }
    }

@router.patch("")
def update_profile(req: ProfileUpdateRequest, request: Request, user: dict = Depends(get_current_user)):
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")

    display_name = req.display_name.strip() if req.display_name is not None else None
    email = req.email.strip() if req.email is not None else None

    if email:
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email address format")

    with get_db() as conn:
        updates = []
        params = []
        if display_name is not None:
            updates.append("display_name = ?")
            params.append(display_name)
        if email is not None:
            updates.append("email = ?")
            params.append(email)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(user["id"])
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)

        db_user = conn.execute(
            """
            SELECT id, username, role, is_active, display_name, email, profile_pic,
                   quota_bytes, created_at, updated_at
            FROM users WHERE id = ?
            """,
            (user["id"],)
        ).fetchone()

    log_audit_event("PROFILE_UPDATE", user["username"], ip, ua, f"User '{user['username']}' updated profile info")
    user_info = dict(db_user)
    user_info["avatar_url"] = f"/api/profile/avatar/{user['id']}"

    return {
        "status": "ok",
        "message": "Profile updated successfully",
        "user": user_info
    }

@router.post("/avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")

    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    allowed_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image format '{ext}'. Allowed: JPG, PNG, WEBP, GIF"
        )

    content = await file.read()
    max_size = 5 * 1024 * 1024  # 5 MB
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile picture must not exceed 5 MB in size"
        )

    avatar_dir = get_avatar_dir()
    for old_file in avatar_dir.glob(f"avatar_{user['id']}.*"):
        try:
            old_file.unlink()
        except Exception:
            pass

    saved_name = f"avatar_{user['id']}{ext}"
    target_path = avatar_dir / saved_name
    with open(target_path, "wb") as f:
        f.write(content)

    avatar_url = f"/api/profile/avatar/{user['id']}?v={int(time.time())}"
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET profile_pic = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (avatar_url, user["id"])
        )

    log_audit_event("AVATAR_UPLOAD", user["username"], ip, ua, "User updated profile picture")
    return {
        "status": "ok",
        "message": "Avatar uploaded successfully",
        "avatar_url": avatar_url
    }

@router.delete("/avatar")
def delete_avatar(request: Request, user: dict = Depends(get_current_user)):
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")

    avatar_dir = get_avatar_dir()
    for old_file in avatar_dir.glob(f"avatar_{user['id']}.*"):
        try:
            old_file.unlink()
        except Exception:
            pass

    with get_db() as conn:
        conn.execute(
            "UPDATE users SET profile_pic = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user["id"],)
        )

    log_audit_event("AVATAR_DELETE", user["username"], ip, ua, "User deleted profile picture")
    return {
        "status": "ok",
        "message": "Avatar removed",
        "avatar_url": f"/api/profile/avatar/{user['id']}?v={int(time.time())}"
    }

@router.get("/avatar/{user_id}")
def get_avatar(user_id: int):
    avatar_dir = get_avatar_dir()
    matches = list(avatar_dir.glob(f"avatar_{user_id}.*"))
    if matches:
        file_path = matches[0]
        ext = file_path.suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif"
        }
        mime = mime_map.get(ext, "application/octet-stream")
        return FileResponse(
            file_path,
            media_type=mime,
            headers={
                "Cache-Control": "public, max-age=86400",
                "Content-Security-Policy": "default-src 'none'; sandbox;",
                "X-Content-Type-Options": "nosniff"
            }
        )

    with get_db() as conn:
        db_user = conn.execute("SELECT username, display_name FROM users WHERE id = ?", (user_id,)).fetchone()

    name = ""
    if db_user:
        name = (db_user["display_name"] or db_user["username"] or "").strip()

    if not name:
        name = "StrangeInfinity"

    parts = name.split()
    if len(parts) >= 2 and len(parts[0]) > 0 and len(parts[1]) > 0:
        initials = (parts[0][0] + parts[1][0]).upper()
    elif len(name) >= 2:
        initials = name[:2].upper()
    elif len(name) == 1:
        initials = name[0].upper()
    else:
        initials = "SI"

    c1, c2 = GRADIENT_PALETTES[user_id % len(GRADIENT_PALETTES)]
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">
  <defs>
    <linearGradient id="g{user_id}" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{c1}" />
      <stop offset="100%" stop-color="{c2}" />
    </linearGradient>
  </defs>
  <rect width="128" height="128" rx="64" fill="url(#g{user_id})" />
  <text x="50%" y="54%" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="52" font-weight="700" fill="#ffffff" dominant-baseline="middle" text-anchor="middle" letter-spacing="1">{html.escape(initials)}</text>
</svg>"""
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Security-Policy": "default-src 'none'; sandbox;",
            "X-Content-Type-Options": "nosniff"
        }
    )

@router.post("/wipe-drive")
def wipe_drive(req: WipeDriveRequest, request: Request, user: dict = Depends(get_current_user)):
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")

    with get_db() as conn:
        db_user = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
        if not db_user or not verify_password(db_user["password_hash"], req.password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password confirmation incorrect")

        storage_manager.wipe_user_storage(user["id"])
        conn.execute("DELETE FROM files_metadata WHERE owner_id = ?", (user["id"],))
        conn.execute("DELETE FROM share_links WHERE owner_id = ?", (user["id"],))
        conn.execute("DELETE FROM uploads WHERE owner_id = ?", (user["id"],))

    log_audit_event("WIPE_DRIVE", user["username"], ip, ua, f"User '{user['username']}' wiped all personal drive files")
    return {
        "status": "ok",
        "message": "All files and folders in your drive have been wiped successfully."
    }

@router.post("/delete-account")
def delete_account(req: AccountDeleteRequest, request: Request, response: Response, user: dict = Depends(get_current_user)):
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")

    with get_db() as conn:
        db_user = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
        if not db_user or not verify_password(db_user["password_hash"], req.password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password confirmation incorrect")

        if user["role"] == "admin":
            admin_count = conn.execute("SELECT COUNT(*) as count FROM users WHERE role = 'admin' AND is_active = 1").fetchone()["count"]
            total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
            if admin_count <= 1 and total_users > 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete the sole administrator account while other users exist. Promote another administrator first."
                )

        storage_manager.delete_user_storage(user["id"])

        avatar_dir = get_avatar_dir()
        for old_file in avatar_dir.glob(f"avatar_{user['id']}.*"):
            try:
                old_file.unlink()
            except Exception:
                pass

        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
        conn.execute("DELETE FROM files_metadata WHERE owner_id = ?", (user["id"],))
        conn.execute("DELETE FROM share_links WHERE owner_id = ?", (user["id"],))
        conn.execute("DELETE FROM uploads WHERE owner_id = ?", (user["id"],))
        conn.execute("DELETE FROM users WHERE id = ?", (user["id"],))

    response.delete_cookie(settings.COOKIE_NAME)
    response.delete_cookie("mydrive_csrf")

    log_audit_event("ACCOUNT_DELETED", user["username"], ip, ua, f"User '{user['username']}' deleted their own account")
    return {
        "status": "ok",
        "message": "Your account and all associated data have been deleted successfully."
    }

@router.get("/export")
def export_my_data(request: Request, user: dict = Depends(get_current_user)):
    user_root = storage_manager.get_user_storage_root(user["id"])
    temp_zip = storage_manager.get_temp_dir() / f"takeout_{user['id']}_{uuid.uuid4().hex}.zip"
    storage_manager.create_folder_zip(user_root, temp_zip)
    zip_size = temp_zip.stat().st_size

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"StrangeInfinity_Drive_Export_{user['username']}_{timestamp}.zip"
    cd_header = format_content_disposition("attachment", archive_name)

    def iter_zip():
        try:
            with open(temp_zip, "rb") as f:
                while chunk := f.read(65536):
                    yield chunk
        finally:
            temp_zip.unlink(missing_ok=True)

    headers = {
        "Accept-Ranges": "none",
        "Content-Length": str(zip_size),
        "Content-Disposition": cd_header,
        "Content-Type": "application/zip"
    }
    return StreamingResponse(
        iter_zip(),
        status_code=status.HTTP_200_OK,
        headers=headers,
        media_type="application/zip"
    )
