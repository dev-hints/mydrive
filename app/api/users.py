import re
from fastapi import APIRouter, Depends, Request, HTTPException, status
from app.database import get_db
from app.storage import storage_manager
from app.security import (
    get_current_user, require_admin, hash_password, log_audit_event
)
from app.schemas import UserCreateRequest, UserUpdateRequest

router = APIRouter(prefix="/api/users", tags=["users"])

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"

@router.get("")
def list_users(admin: dict = Depends(require_admin)):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, username, role, quota_bytes, is_active, display_name, email, profile_pic, created_at, updated_at
            FROM users
            ORDER BY id ASC
            """
        ).fetchall()

        users_list = []
        for r in rows:
            u = dict(r)
            user_id = u["id"]
            u["is_active"] = bool(u["is_active"])
            u["storage_used"] = storage_manager.get_user_used_storage(user_id)
            file_row = conn.execute(
                "SELECT COUNT(*) as count FROM files_metadata WHERE owner_id = ? AND is_trash = 0 AND is_directory = 0",
                (user_id,)
            ).fetchone()
            u["file_count"] = file_row["count"] if file_row else 0
            users_list.append(u)

    return {"users": users_list}

@router.post("")
def create_user(
    req: UserCreateRequest,
    request: Request,
    admin: dict = Depends(require_admin)
):
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")
    username = req.username.strip()

    if not re.match(r"^[a-zA-Z0-9_\-\.]{3,32}$", username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be 3-32 characters and contain only letters, numbers, underscores, dashes, and dots."
        )

    if len(req.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long."
        )

    role = req.role.strip().lower()
    if role not in ("user", "admin"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be either 'user' or 'admin'."
        )

    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Username '{username}' already exists."
            )

        pw_hash = hash_password(req.password)
        cursor = conn.execute(
            """
            INSERT INTO users (username, password_hash, role, quota_bytes, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (username, pw_hash, role, max(0, req.quota_bytes))
        )
        new_user_id = cursor.lastrowid

    # Initialize private storage directory for the new user
    storage_manager.get_user_storage_root(new_user_id)
    storage_manager.get_user_trash_dir(new_user_id)

    log_audit_event(
        "USER_CREATED",
        admin["username"],
        ip,
        ua,
        f"Admin created user '{username}' (role={role}, quota={req.quota_bytes} bytes)"
    )

    return {
        "status": "ok",
        "message": f"User '{username}' created successfully.",
        "user": {
            "id": new_user_id,
            "username": username,
            "role": role,
            "quota_bytes": req.quota_bytes,
            "is_active": True
        }
    }

@router.patch("/{user_id}")
def update_user(
    user_id: int,
    req: UserUpdateRequest,
    request: Request,
    admin: dict = Depends(require_admin)
):
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")

    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        # Guard against locking out the system
        if req.role and req.role.lower() != "admin" and user["role"] == "admin":
            admin_count = conn.execute("SELECT COUNT(*) as count FROM users WHERE role = 'admin' AND is_active = 1").fetchone()["count"]
            if admin_count <= 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot demote the only active administrator.")

        if req.is_active is False and user["id"] == admin["id"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot deactivate your own account.")

        updates = []
        params = []

        if req.role is not None:
            r = req.role.strip().lower()
            if r not in ("user", "admin"):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Role must be 'user' or 'admin'.")
            updates.append("role = ?")
            params.append(r)

        if req.is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if req.is_active else 0)
            if not req.is_active:
                # Invalidate all active sessions for deactivated user
                conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

        if req.quota_bytes is not None:
            updates.append("quota_bytes = ?")
            params.append(max(0, req.quota_bytes))

        if req.password:
            if len(req.password) < 8:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters.")
            new_hash = hash_password(req.password)
            updates.append("password_hash = ?")
            params.append(new_hash)
            # Invalidate other sessions
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(user_id)
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", tuple(params))

    log_audit_event("USER_UPDATED", admin["username"], ip, ua, f"Updated user #{user_id} ({user['username']})")
    return {"status": "ok", "message": f"User '{user['username']}' updated successfully."}

@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    admin: dict = Depends(require_admin)
):
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")

    if user_id == admin["id"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account.")

    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        if user["role"] == "admin":
            admin_count = conn.execute("SELECT COUNT(*) as count FROM users WHERE role = 'admin' AND is_active = 1").fetchone()["count"]
            if admin_count <= 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete the only active administrator.")

        # Cleanup dependent records
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM files_metadata WHERE owner_id = ?", (user_id,))
        conn.execute("DELETE FROM share_links WHERE owner_id = ?", (user_id,))
        conn.execute("DELETE FROM uploads WHERE owner_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    # Delete physical storage for the user
    storage_manager.delete_user_storage(user_id)

    log_audit_event("USER_DELETED", admin["username"], ip, ua, f"Deleted user '{user['username']}' and their storage")
    return {"status": "ok", "message": f"User '{user['username']}' deleted successfully."}
