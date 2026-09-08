from fastapi import APIRouter, Depends
from app.storage import storage_manager
from app.security import get_current_user

router = APIRouter(prefix="/api/storage", tags=["storage"])

@router.get("")
def get_storage(user: dict = Depends(get_current_user)):
    return storage_manager.get_storage_stats(owner_id=user["id"])
