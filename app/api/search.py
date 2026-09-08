from fastapi import APIRouter, Depends, Query, HTTPException, status
from app.storage import storage_manager
from app.security import get_current_user

router = APIRouter(prefix="/api/search", tags=["search"])

@router.get("")
def search(
    q: str = Query(..., min_length=1, max_length=100),
    user: dict = Depends(get_current_user)
):
    results = storage_manager.search_files(q, owner_id=user["id"])
    return {"query": q, "results": results, "count": len(results)}
