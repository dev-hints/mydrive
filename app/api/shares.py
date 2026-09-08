import os
import secrets
import datetime
import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, Request, Response, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from app.config import settings
from app.database import get_db
from app.storage import storage_manager, guess_mime_type
from app.security import (
    get_current_user, generate_token, hash_password, verify_password,
    log_audit_event, resolve_safe_path, get_share_auth_token,
    is_valid_share_auth_cookie, is_request_secure
)
from app.schemas import ShareCreateRequest, SharePasswordRequest
from app.api.files import format_content_disposition, parse_range_header

router = APIRouter(prefix="/api/shares", tags=["shares"])

def verify_share_access(token: str, request: Request, provided_password: Optional[str] = None):
    now = datetime.datetime.now(datetime.timezone.utc)
    with get_db() as conn:
        share = conn.execute("SELECT * FROM share_links WHERE token = ?", (token,)).fetchone()
        if not share:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found or revoked")

        if share["expires_at"]:
            expires_at = datetime.datetime.fromisoformat(share["expires_at"]) if isinstance(share["expires_at"], str) else share["expires_at"]
            if expires_at < now:
                raise HTTPException(status_code=status.HTTP_410_GONE, detail="Share link has expired")

        # Check password if configured
        if share["password_hash"]:
            cookie_auth = request.cookies.get(f"share_auth_{token}")
            if is_valid_share_auth_cookie(token, cookie_auth):
                pass
            elif provided_password and verify_password(share["password_hash"], provided_password):
                pass
            else:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Password required")

        # Increment access count
        conn.execute("UPDATE share_links SET access_count = access_count + 1 WHERE token = ?", (token,))

    return share

@router.post("")
def create_share(
    req: ShareCreateRequest,
    request: Request,
    user: dict = Depends(get_current_user)
):
    target = storage_manager.resolve_path(req.path, owner_id=user["id"], allow_root=False)
    if not target.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")

    token = secrets.token_urlsafe(18)
    is_dir = 1 if target.is_dir() else 0
    rel_path = storage_manager.to_relative_path(target, owner_id=user["id"])

    pw_hash = hash_password(req.password) if req.password and req.password.strip() else None

    expires_at_str = None
    if req.expires_in_hours and req.expires_in_hours > 0:
        now = datetime.datetime.now(datetime.timezone.utc)
        expires_at_str = (now + datetime.timedelta(hours=req.expires_in_hours)).isoformat()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO share_links (token, relative_path, is_directory, password_hash, expires_at, download_only, owner_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (token, rel_path, is_dir, pw_hash, expires_at_str, 1 if req.download_only else 0, user["id"])
        )

    log_audit_event("CREATE_SHARE", user["username"], request.client.host if request.client else "", request.headers.get("user-agent", ""), f"Shared {rel_path}")

    return {
        "status": "ok",
        "token": token,
        "share_url": f"/s/{token}",
        "relative_path": rel_path,
        "is_directory": bool(is_dir),
        "has_password": bool(pw_hash),
        "expires_at": expires_at_str,
        "download_only": req.download_only
    }

@router.get("")
def list_shares(user: dict = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT token, relative_path, is_directory, (password_hash IS NOT NULL) as has_password,
                   expires_at, download_only, access_count, created_at
            FROM share_links
            WHERE owner_id = ?
            ORDER BY created_at DESC
            """,
            (user["id"],)
        ).fetchall()
        return {"shares": [dict(r) for r in rows]}

@router.delete("/{token}")
def revoke_share(
    token: str,
    request: Request,
    user: dict = Depends(get_current_user)
):
    with get_db() as conn:
        share = conn.execute("SELECT * FROM share_links WHERE token = ? AND owner_id = ?", (token, user["id"])).fetchone()
        if not share:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share link not found")
        conn.execute("DELETE FROM share_links WHERE token = ?", (token,))

    log_audit_event("REVOKE_SHARE", user["username"], request.client.host if request.client else "", request.headers.get("user-agent", ""), f"Revoked share for {share['relative_path']}")
    return {"status": "ok", "message": "Share link revoked"}

# Public share endpoints
@router.get("/public/info/{token}")
def public_share_info(token: str, request: Request):
    with get_db() as conn:
        share = conn.execute("SELECT * FROM share_links WHERE token = ?", (token,)).fetchone()
        if not share:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Share not found")

        now = datetime.datetime.now(datetime.timezone.utc)
        if share["expires_at"]:
            expires_at = datetime.datetime.fromisoformat(share["expires_at"]) if isinstance(share["expires_at"], str) else share["expires_at"]
            if expires_at < now:
                raise HTTPException(status_code=status.HTTP_410_GONE, detail="Share link expired")

        target = storage_manager.resolve_path(share["relative_path"], owner_id=share["owner_id"], allow_root=True)
        if not target.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared file no longer exists")

        is_dir = target.is_dir()
        size = 0 if is_dir else target.stat().st_size
        mime = "inode/directory" if is_dir else guess_mime_type(target.name)

        has_pw = bool(share["password_hash"])
        is_authenticated = False
        if has_pw:
            cookie_auth = request.cookies.get(f"share_auth_{token}")
            if is_valid_share_auth_cookie(token, cookie_auth):
                is_authenticated = True

        return {
            "token": token,
            "name": target.name,
            "is_directory": is_dir,
            "size": size,
            "mime_type": mime,
            "requires_password": has_pw and not is_authenticated,
            "download_only": bool(share["download_only"]),
            "expires_at": share["expires_at"]
        }

@router.post("/public/verify-password/{token}")
def public_verify_password(token: str, req: SharePasswordRequest, request: Request, response: Response):
    with get_db() as conn:
        share = conn.execute("SELECT * FROM share_links WHERE token = ?", (token,)).fetchone()
        if not share or not share["password_hash"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No password required")

        if not verify_password(share["password_hash"], req.password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")

        response.set_cookie(
            key=f"share_auth_{token}",
            value=get_share_auth_token(token),
            httponly=True,
            samesite="lax",
            secure=is_request_secure(request),
            max_age=86400
        )
        return {"status": "ok", "message": "Authenticated"}

@router.get("/public/browse/{token}")
def public_browse_folder(
    token: str,
    request: Request,
    subpath: str = Query(default="")
):
    share = verify_share_access(token, request)
    if not share["is_directory"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Share is not a directory")

    base_shared_path = storage_manager.resolve_path(share["relative_path"], owner_id=share["owner_id"], allow_root=True)
    if not base_shared_path.exists() or not base_shared_path.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared folder missing")

    # Strictly resolve subpath relative to base_shared_path
    target_sub = resolve_safe_path(base_shared_path, subpath, allow_root=True)
    if not target_sub.exists() or not target_sub.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Folder not found")

    items = []
    with os.scandir(target_sub) as entries:
        for entry in entries:
            if entry.name.startswith("."):
                continue
            is_dir = entry.is_dir(follow_symlinks=False)
            st = entry.stat(follow_symlinks=False)
            # relative to the base shared folder
            rel_to_shared = Path(entry.path).relative_to(base_shared_path)
            items.append({
                "name": entry.name,
                "relative_path": str(rel_to_shared).replace("\\", "/"),
                "is_directory": is_dir,
                "size": 0 if is_dir else st.st_size,
                "mime_type": "inode/directory" if is_dir else guess_mime_type(entry.name),
                "modified_at": datetime.datetime.fromtimestamp(st.st_mtime, tz=datetime.timezone.utc).isoformat()
            })

    items.sort(key=lambda x: (not x["is_directory"], x["name"].lower()))
    rel_sub = "" if target_sub == base_shared_path else str(target_sub.relative_to(base_shared_path)).replace("\\", "/")

    return {
        "share_name": base_shared_path.name,
        "current_subpath": rel_sub,
        "items": items,
        "download_only": bool(share["download_only"])
    }

@router.get("/public/download/{token}")
async def public_download(
    token: str,
    request: Request,
    subpath: str = Query(default="")
):
    share = verify_share_access(token, request)
    base_shared = storage_manager.resolve_path(share["relative_path"], owner_id=share["owner_id"], allow_root=True)

    if share["is_directory"]:
        if not subpath:
            target = base_shared
        else:
            target = resolve_safe_path(base_shared, subpath, allow_root=True)
    else:
        target = base_shared

    if not target.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File or folder not found")

    if target.is_dir():
        temp_zip = storage_manager.get_temp_dir() / f"download_{uuid.uuid4().hex}.zip"
        storage_manager.create_folder_zip(target, temp_zip)
        zip_size = temp_zip.stat().st_size
        cd_header = format_content_disposition("attachment", f"{target.name}.zip")

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

    file_size = target.stat().st_size
    mime_type = guess_mime_type(target.name)
    cd_header = format_content_disposition("attachment", target.name)

    range_header = request.headers.get("range")
    if range_header:
        parsed_range = parse_range_header(range_header, file_size)
        if parsed_range is None:
            return Response(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                headers={"Content-Range": f"bytes */{file_size}"}
            )
        start, end = parsed_range
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            "Content-Disposition": cd_header,
            "Content-Type": mime_type
        }
        return StreamingResponse(
            storage_manager.get_file_stream(target, start, end),
            status_code=status.HTTP_206_PARTIAL_CONTENT,
            headers=headers
        )

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Disposition": cd_header,
        "Content-Type": mime_type
    }
    return StreamingResponse(
        storage_manager.get_file_stream(target, 0, file_size - 1),
        status_code=status.HTTP_200_OK,
        headers=headers
    )
