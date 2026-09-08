from fastapi import APIRouter, Depends, Query
from app.database import get_db
from app.security import require_admin

router = APIRouter(prefix="/api/audit", tags=["audit"])

@router.get("")
def get_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: dict = Depends(require_admin)
):
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, event_type, username, ip_address, user_agent, details, created_at
            FROM audit_logs
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset)
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) as count FROM audit_logs").fetchone()["count"]

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "logs": [dict(r) for r in rows]
        }
