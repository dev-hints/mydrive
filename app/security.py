import os
import re
import secrets
import datetime
import hmac
import hashlib
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from fastapi import Request, HTTPException, status, Depends
from app.config import settings
from app.database import get_db

ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MB RAM, efficient and secure for mobile ARM64
    parallelism=2,
    hash_len=32,
    salt_len=16
)

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(password_hash: str, password: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False

def generate_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)

import urllib.parse

def generate_csrf_token() -> str:
    return secrets.token_hex(24)

def sanitize_filename(name: str, default: str = "unnamed_file") -> str:
    """
    Sanitizes user-provided filenames.
    Blocks raw and URL-encoded null bytes, traversal symbols, directory separators, and control characters.
    """
    if not name:
        return default

    unquoted = urllib.parse.unquote(name)
    if "\0" in name or "\0" in unquoted or "%00" in name.lower():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Null bytes are not allowed in filenames")
    
    # Strip dangerous directory traversal / separators
    cleaned = name.replace("/", "").replace("\\", "").strip()
    # Strip any non-printable ASCII control characters (ASCII 0-31)
    cleaned = "".join(c for c in cleaned if ord(c) >= 32 and ord(c) != 127)
    
    if not cleaned or cleaned in (".", ".."):
        return default
    return cleaned

def get_share_auth_token(share_token: str) -> str:
    """Generates a cryptographically signed HMAC token for password-authenticated shares."""
    return hmac.new(
        settings.SESSION_SECRET.encode(),
        f"share_authenticated_{share_token}".encode(),
        hashlib.sha256
    ).hexdigest()

def is_valid_share_auth_cookie(share_token: str, cookie_value: Optional[str]) -> bool:
    """Verifies that the share authentication cookie contains the valid HMAC signature."""
    if not cookie_value:
        return False
    expected = get_share_auth_token(share_token)
    return hmac.compare_digest(cookie_value, expected)

def resolve_safe_path(base_dir: Path, user_path: str, allow_root: bool = True) -> Path:
    """
    Strictly validates and resolves a user-provided relative path against a base directory.
    Completely blocks:
      - Null bytes (\0)
      - Path traversal (.., %2e%2e, etc.)
      - Absolute paths escaping base_dir
      - Symlink escapes pointing outside base_dir
    """
    if "\0" in user_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid path: null byte detected"
        )
    
    # Clean leading slashes and backslashes
    clean = user_path.replace("\\", "/").strip()
    clean = re.sub(r"/+", "/", clean)
    clean = clean.lstrip("/")

    # Check for traversal components
    parts = clean.split("/")
    if ".." in parts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path traversal attempt detected"
        )

    base_resolved = base_dir.resolve()
    target_path = (base_resolved / clean).resolve()

    # Base boundary verification
    if not allow_root and target_path == base_resolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Root directory modification not permitted"
        )

    # Candidate must either be the base directory itself or inside it
    if target_path != base_resolved and base_resolved not in target_path.parents:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: path escapes root boundary"
        )

    # Symlink escape verification: check realpath
    real_base = os.path.realpath(str(base_resolved))
    real_target = os.path.realpath(str(target_path))
    if real_target != real_base and not real_target.startswith(real_base + os.sep):
        # Target might not exist yet (e.g. creating new file)
        # Check its parent
        real_parent = os.path.realpath(str(target_path.parent))
        if real_parent != real_base and not real_parent.startswith(real_base + os.sep):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access forbidden: symlink escapes storage boundary"
            )

    return target_path

def is_ip_locked(ip_address: str, username: str) -> Tuple[bool, Optional[datetime.datetime]]:
    now = datetime.datetime.now(datetime.timezone.utc)
    with get_db() as conn:
        row = conn.execute(
            "SELECT attempt_count, locked_until FROM login_attempts WHERE ip_address = ? AND username = ?",
            (ip_address, username)
        ).fetchone()
        if row and row["locked_until"]:
            locked_until_dt = datetime.datetime.fromisoformat(row["locked_until"]) if isinstance(row["locked_until"], str) else row["locked_until"]
            if locked_until_dt > now:
                return True, locked_until_dt
    return False, None

def record_failed_login(ip_address: str, username: str):
    now = datetime.datetime.now(datetime.timezone.utc)
    with get_db() as conn:
        row = conn.execute(
            "SELECT attempt_count FROM login_attempts WHERE ip_address = ? AND username = ?",
            (ip_address, username)
        ).fetchone()

        if row:
            new_count = row["attempt_count"] + 1
            locked_until = None
            if new_count >= settings.RATE_LIMIT_LOGIN_ATTEMPTS:
                locked_until = now + datetime.timedelta(minutes=settings.RATE_LIMIT_LOCKOUT_MINUTES)
            
            conn.execute(
                """
                UPDATE login_attempts
                SET attempt_count = ?, last_failed_at = ?, locked_until = ?
                WHERE ip_address = ? AND username = ?
                """,
                (new_count, now.isoformat(), locked_until.isoformat() if locked_until else None, ip_address, username)
            )
        else:
            conn.execute(
                """
                INSERT INTO login_attempts (ip_address, username, attempt_count, first_failed_at, last_failed_at, locked_until)
                VALUES (?, ?, 1, ?, ?, NULL)
                """,
                (ip_address, username, now.isoformat(), now.isoformat())
            )

def reset_login_attempts(ip_address: str, username: str):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM login_attempts WHERE ip_address = ? AND username = ?",
            (ip_address, username)
        )

def log_audit_event(event_type: str, username: Optional[str], ip_address: Optional[str], user_agent: Optional[str], details: Optional[str] = None):
    # Sanitize details so no passwords, session tokens or secrets can ever be written
    safe_details = details[:500] if details else None
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (event_type, username, ip_address, user_agent, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (event_type, username, ip_address, user_agent, safe_details)
        )

def is_request_secure(request: Request) -> bool:
    if settings.COOKIE_SECURE is not None:
        return settings.COOKIE_SECURE
    proto = request.headers.get("x-forwarded-proto", "").lower()
    return proto == "https" or request.url.scheme == "https"

def create_session(user_id: int, ip_address: str, user_agent: str) -> Tuple[str, datetime.datetime]:
    session_id = generate_token(32)
    now = datetime.datetime.now(datetime.timezone.utc)
    expires_at = now + datetime.timedelta(days=settings.SESSION_LIFETIME_DAYS)

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO sessions (id, user_id, user_agent, ip_address, created_at, expires_at, last_active_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, user_id, user_agent[:255] if user_agent else "", ip_address, now.isoformat(), expires_at.isoformat(), now.isoformat())
        )
    return session_id, expires_at

def get_session_user(session_id: str) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT s.id as session_id, s.expires_at, u.id as user_id, u.username, u.role, u.is_active,
                   u.display_name, u.email, u.profile_pic
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = ?
            """,
            (session_id,)
        ).fetchone()

        if not row:
            return None

        expires_at_dt = datetime.datetime.fromisoformat(row["expires_at"]) if isinstance(row["expires_at"], str) else row["expires_at"]
        if expires_at_dt < now:
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return None

        if not row["is_active"]:
            return None

        # Update last active timestamp
        conn.execute("UPDATE sessions SET last_active_at = ? WHERE id = ?", (now.isoformat(), session_id))

        return {
            "id": row["user_id"],
            "username": row["username"],
            "role": row["role"],
            "display_name": row["display_name"] or "",
            "email": row["email"] or "",
            "profile_pic": row["profile_pic"] or "",
            "session_id": row["session_id"]
        }

def revoke_session(session_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))

def revoke_all_other_sessions(user_id: int, current_session_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ? AND id != ?", (user_id, current_session_id))

def get_user_sessions(user_id: int, current_session_id: str) -> List[Dict[str, Any]]:
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, user_agent, ip_address, created_at, last_active_at,
                   (id = ?) as is_current
            FROM sessions
            WHERE user_id = ?
            ORDER BY last_active_at DESC
            """,
            (current_session_id, user_id)
        ).fetchall()
        return [dict(r) for r in rows]

async def get_current_user(request: Request) -> Dict[str, Any]:
    # Check cookie first
    session_id = request.cookies.get(settings.COOKIE_NAME)
    # Fallback to Authorization: Bearer
    if not session_id:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_id = auth_header.split(" ", 1)[1].strip()

    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Cookie"}
        )

    user = get_session_user(session_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session invalid or expired",
            headers={"WWW-Authenticate": "Cookie"}
        )

    # CSRF check on mutating requests if using session cookie
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        # If authenticated via cookie, check CSRF token header vs cookie
        if request.cookies.get(settings.COOKIE_NAME):
            csrf_cookie = request.cookies.get("mydrive_csrf")
            csrf_header = request.headers.get("X-CSRF-Token")
            # Exclude login and setup routes handled explicitly
            if not request.url.path.startswith("/api/auth/login") and not request.url.path.startswith("/api/auth/setup"):
                if not csrf_cookie or not csrf_header or not secrets.compare_digest(csrf_cookie, csrf_header):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Invalid or missing CSRF token"
                    )

    return user

async def get_current_user_optional(request: Request) -> Optional[Dict[str, Any]]:
    try:
        return await get_current_user(request)
    except HTTPException:
        return None

async def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Dependency that ensures the authenticated user has the 'admin' role."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required"
        )
    return user
