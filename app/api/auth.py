from fastapi import APIRouter, Depends, Request, Response, HTTPException, status
import datetime
from app.config import settings
from app.database import get_db
from app.storage import storage_manager
from app.schemas import LoginRequest, SetupRequest, PasswordChangeRequest, StandardResponse, RegisterRequest
from app.security import (
    hash_password, verify_password, create_session, revoke_session,
    revoke_all_other_sessions, get_user_sessions, get_current_user,
    generate_csrf_token, is_ip_locked, record_failed_login,
    reset_login_attempts, log_audit_event, is_request_secure
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"

@router.get("/setup-status")
def setup_status():
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
        user_count = row["count"] if row else 0
    return {"needs_setup": user_count == 0, "app_name": settings.APP_NAME}

@router.post("/setup")
def initial_setup(req: SetupRequest, request: Request, response: Response):
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()
        if row and row["count"] > 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="System is already configured")

        if req.password != req.confirm_password:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")

        if len(req.password) < 8:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters long")

        pw_hash = hash_password(req.password)
        cursor = conn.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active)
            VALUES (?, ?, 'admin', 1)
            """,
            (req.username.strip(), pw_hash)
        )
        user_id = cursor.lastrowid

    # Initialize user storage directories
    storage_manager.get_user_storage_root(user_id)
    storage_manager.get_user_trash_dir(user_id)

    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    session_id, expires_at = create_session(user_id, ip, ua)
    csrf_token = generate_csrf_token()

    secure_cookie = is_request_secure(request)
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
        expires=expires_at
    )
    response.set_cookie(
        key="mydrive_csrf",
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=secure_cookie,
        expires=expires_at
    )

    log_audit_event("INITIAL_SETUP", req.username, ip, ua, "Admin account initialized")
    return {"status": "ok", "message": "Initial setup completed", "username": req.username, "csrf_token": csrf_token}

@router.post("/register")
def register(req: RegisterRequest, request: Request, response: Response):
    username = req.username.strip()
    if len(username) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username must be at least 3 characters long")
    if len(req.password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters long")

    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")

    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username is already taken")

        user_count = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()["count"]
        is_first_user = (user_count == 0)
        role = "admin" if is_first_user else "user"

        # Quota allocation:
        # Initial admin has unlimited storage (0).
        # Self-registered users are assigned system DEFAULT_USER_QUOTA_BYTES
        # to prevent arbitrary quota inflation.
        if is_first_user:
            quota = 0
        else:
            quota = settings.DEFAULT_USER_QUOTA_BYTES

        pw_hash = hash_password(req.password)
        cursor = conn.execute(
            """
            INSERT INTO users (username, password_hash, role, is_active, quota_bytes)
            VALUES (?, ?, ?, 1, ?)
            """,
            (username, pw_hash, role, quota)
        )
        user_id = cursor.lastrowid

    # Initialize user storage directories
    storage_manager.get_user_storage_root(user_id)
    storage_manager.get_user_trash_dir(user_id)

    # Automatically authenticate newly registered user
    session_id, expires_at = create_session(user_id, ip, ua)
    csrf_token = generate_csrf_token()

    secure_cookie = is_request_secure(request)
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
        expires=expires_at
    )
    response.set_cookie(
        key="mydrive_csrf",
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=secure_cookie,
        expires=expires_at
    )

    quota_label = f"{req.quota_gb} GB" if req.quota_gb else ("Unlimited" if quota == 0 else f"{quota} bytes")
    log_audit_event("REGISTER", username, ip, ua, f"User account created (role: {role}, quota: {quota_label})")
    return {
        "status": "ok",
        "message": "Account created successfully",
        "username": username,
        "role": role,
        "quota_bytes": quota,
        "csrf_token": csrf_token
    }

@router.post("/login")
def login(req: LoginRequest, request: Request, response: Response):
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    username = req.username.strip()

    is_locked, locked_until = is_ip_locked(ip, username)
    if is_locked:
        wait_seconds = int((locked_until - datetime.datetime.now(datetime.timezone.utc)).total_seconds())
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Account temporarily locked for {max(1, wait_seconds // 60)} more minutes."
        )

    with get_db() as conn:
        user = conn.execute(
            "SELECT id, username, password_hash, is_active, role, display_name, email, profile_pic FROM users WHERE username = ?",
            (username,)
        ).fetchone()

    if not user or not verify_password(user["password_hash"], req.password):
        record_failed_login(ip, username)
        log_audit_event("LOGIN_FAILED", username, ip, ua, "Invalid credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled"
        )

    reset_login_attempts(ip, username)
    session_id, expires_at = create_session(user["id"], ip, ua)
    csrf_token = generate_csrf_token()

    secure_cookie = is_request_secure(request)
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=secure_cookie,
        expires=expires_at
    )
    response.set_cookie(
        key="mydrive_csrf",
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=secure_cookie,
        expires=expires_at
    )

    log_audit_event("LOGIN_SUCCESS", username, ip, ua, "User logged in")
    return {
        "status": "ok",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "display_name": user["display_name"] or "",
            "email": user["email"] or "",
            "profile_pic": user["profile_pic"] or ""
        },
        "csrf_token": csrf_token
    }

@router.post("/logout")
def logout(request: Request, response: Response, user: dict = Depends(get_current_user)):
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    revoke_session(user["session_id"])

    response.delete_cookie(settings.COOKIE_NAME)
    response.delete_cookie("mydrive_csrf")

    log_audit_event("LOGOUT", user["username"], ip, ua, "User logged out")
    return {"status": "ok", "message": "Logged out successfully"}

@router.get("/me")
def get_me(request: Request, user: dict = Depends(get_current_user)):
    sessions = get_user_sessions(user["id"], user["session_id"])
    csrf_token = request.cookies.get("mydrive_csrf", "")
    return {
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "display_name": user.get("display_name", ""),
            "email": user.get("email", ""),
            "profile_pic": user.get("profile_pic", "")
        },
        "sessions": sessions,
        "csrf_token": csrf_token
    }

@router.post("/change-password")
def change_password(req: PasswordChangeRequest, request: Request, user: dict = Depends(get_current_user)):
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")

    if len(req.new_password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be at least 8 characters")

    with get_db() as conn:
        db_user = conn.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
        if not db_user or not verify_password(db_user["password_hash"], req.old_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password incorrect")

        new_hash = hash_password(req.new_password)
        conn.execute("UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (new_hash, user["id"]))

    log_audit_event("PASSWORD_CHANGE", user["username"], ip, ua, "Password successfully changed")
    return {"status": "ok", "message": "Password updated successfully"}

@router.post("/revoke-other-sessions")
def revoke_others(request: Request, user: dict = Depends(get_current_user)):
    revoke_all_other_sessions(user["id"], user["session_id"])
    return {"status": "ok", "message": "Other sessions terminated"}
