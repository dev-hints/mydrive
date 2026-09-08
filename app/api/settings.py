from fastapi import APIRouter, Depends, HTTPException, status, Request
from pathlib import Path
import os
from app.config import settings
from app.database import get_db
from app.security import get_current_user, require_admin, log_audit_event
from app.schemas import SettingsUpdateRequest

router = APIRouter(prefix="/api/settings", tags=["settings"])

@router.get("")
def get_settings(admin: dict = Depends(require_admin)):
    return {
        "app_name": settings.APP_NAME,
        "storage_root": settings.STORAGE_ROOT,
        "resolved_storage_root": str(settings.get_resolved_storage_root()),
        "max_upload_size": settings.MAX_UPLOAD_SIZE,
        "chunk_size": settings.CHUNK_SIZE,
        "show_hidden_files": settings.SHOW_HIDDEN_FILES,
        "session_lifetime_days": settings.SESSION_LIFETIME_DAYS,
        "rate_limit_attempts": settings.RATE_LIMIT_LOGIN_ATTEMPTS,
        "rate_limit_lockout_minutes": settings.RATE_LIMIT_LOCKOUT_MINUTES
    }

@router.post("")
def update_settings(
    req: SettingsUpdateRequest,
    request: Request,
    admin: dict = Depends(require_admin)
):
    if req.storage_root:
        expanded = os.path.expanduser(req.storage_root)
        candidate = Path(expanded).resolve()
        if not candidate.exists():
            try:
                candidate.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot create storage directory: {str(e)}")
        # Check writable
        test_file = candidate / ".test_write"
        try:
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Storage directory is not writable: {str(e)}")

        settings.STORAGE_ROOT = str(candidate)

    if req.show_hidden_files is not None:
        settings.SHOW_HIDDEN_FILES = req.show_hidden_files

    if req.max_upload_size is not None and req.max_upload_size > 0:
        settings.MAX_UPLOAD_SIZE = req.max_upload_size

    log_audit_event("UPDATE_SETTINGS", admin["username"], request.client.host if request.client else "", request.headers.get("user-agent", ""), "Updated application settings")
    return {"status": "ok", "message": "Settings updated"}
