import time
import os
from fastapi import APIRouter
from app.config import settings
from app.database import get_db

router = APIRouter(tags=["health"])
START_TIME = time.time()

@router.get("/health")
def health():
    db_status = "ok"
    try:
        with get_db() as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception:
        db_status = "error"

    storage_status = "ok"
    try:
        root = settings.get_resolved_storage_root()
        if not root.exists() or not os.access(root, os.R_OK | os.W_OK):
            storage_status = "unwritable"
    except Exception:
        storage_status = "error"

    uptime_seconds = int(time.time() - START_TIME)

    return {
        "status": "ok" if (db_status == "ok" and storage_status == "ok") else "degraded",
        "database": db_status,
        "storage": storage_status,
        "uptime_seconds": uptime_seconds,
        "app": settings.APP_NAME
    }
