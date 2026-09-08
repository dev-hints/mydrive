import json
import os
import re
import uuid
import datetime
import hashlib
from pathlib import Path
from fastapi import APIRouter, Depends, Request, HTTPException, status, UploadFile, File, Form
from app.config import settings
from app.database import get_db
from app.security import get_current_user, log_audit_event, sanitize_filename
from app.storage import storage_manager, get_unique_filename, guess_mime_type
from app.schemas import ChunkInitRequest, ChunkFinishRequest

router = APIRouter(prefix="/api/upload", tags=["upload"])

def get_temp_part_path(upload_id: str, chunk_index: int) -> Path:
    temp_dir = storage_manager.get_temp_dir()
    # Ensure upload_id contains strictly safe alphanumeric/hyphen characters
    safe_id = re.sub(r"[^a-zA-Z0-9_\-]", "", upload_id)
    if not safe_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid upload ID")
    return temp_dir / f"{safe_id}_{chunk_index}.part"

@router.post("/init")
def init_upload(
    req: ChunkInitRequest,
    user: dict = Depends(get_current_user)
):
    if req.total_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum upload limit ({settings.MAX_UPLOAD_SIZE} bytes)"
        )

    with get_db() as conn:
        user_row = conn.execute("SELECT quota_bytes FROM users WHERE id = ?", (user["id"],)).fetchone()
        user_quota = user_row["quota_bytes"] if user_row else 0

    if user_quota > 0:
        current_used = storage_manager.get_user_used_storage(user["id"])
        if (current_used + req.total_size) > user_quota:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Storage quota exceeded. Please delete files or contact your administrator."
            )

    # Verify target directory exists
    target_dir = storage_manager.resolve_path(req.target_dir, owner_id=user["id"], allow_root=True)
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target directory does not exist")

    upload_id = str(uuid.uuid4())
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
    safe_filename = sanitize_filename(req.filename, default="uploaded_file")

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO uploads (id, filename, target_dir, total_size, total_chunks, received_chunks, mime_type, owner_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, '[]', ?, ?, 'uploading', ?, ?)
            """,
            (upload_id, safe_filename, req.target_dir, req.total_size, req.total_chunks, req.mime_type or guess_mime_type(safe_filename), user["id"], now_str, now_str)
        )

    return {
        "status": "ok",
        "upload_id": upload_id,
        "chunk_size": settings.CHUNK_SIZE,
        "total_chunks": req.total_chunks
    }

@router.post("/chunk")
async def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk_file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    with get_db() as conn:
        upload = conn.execute(
            "SELECT id, total_chunks, received_chunks, status, owner_id FROM uploads WHERE id = ?",
            (upload_id,)
        ).fetchone()

        if not upload or upload["owner_id"] != user["id"]:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload session not found")

        if upload["status"] != "uploading":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Upload is in state '{upload['status']}'")

        if chunk_index < 0 or chunk_index >= upload["total_chunks"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid chunk index")

        received = set(json.loads(upload["received_chunks"] or "[]"))

    part_path = get_temp_part_path(upload_id, chunk_index)

    # Stream write chunk to temp file
    with open(part_path, "wb") as f_out:
        while True:
            data = await chunk_file.read(65536)
            if not data:
                break
            f_out.write(data)

    received.add(chunk_index)
    now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

    with get_db() as conn:
        conn.execute(
            "UPDATE uploads SET received_chunks = ?, updated_at = ? WHERE id = ?",
            (json.dumps(sorted(list(received))), now_str, upload_id)
        )

    return {
        "status": "ok",
        "upload_id": upload_id,
        "chunk_index": chunk_index,
        "received_count": len(received),
        "total_chunks": upload["total_chunks"]
    }

@router.get("/status/{upload_id}")
def get_upload_status(
    upload_id: str,
    user: dict = Depends(get_current_user)
):
    with get_db() as conn:
        upload = conn.execute(
            "SELECT id, filename, total_size, total_chunks, received_chunks, status FROM uploads WHERE id = ? AND owner_id = ?",
            (upload_id, user["id"])
        ).fetchone()

        if not upload:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")

        received = json.loads(upload["received_chunks"] or "[]")
        return {
            "upload_id": upload["id"],
            "filename": upload["filename"],
            "total_size": upload["total_size"],
            "total_chunks": upload["total_chunks"],
            "received_chunks": received,
            "is_complete": len(received) == upload["total_chunks"],
            "status": upload["status"]
        }

@router.post("/finish")
def finish_upload(
    req: ChunkFinishRequest,
    request: Request,
    user: dict = Depends(get_current_user)
):
    with get_db() as conn:
        upload = conn.execute(
            "SELECT * FROM uploads WHERE id = ? AND owner_id = ?",
            (req.upload_id, user["id"])
        ).fetchone()

        if not upload:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")

        received = set(json.loads(upload["received_chunks"] or "[]"))
        total_chunks = upload["total_chunks"]

        if len(received) != total_chunks:
            missing = [i for i in range(total_chunks) if i not in received]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Upload incomplete: missing chunks {missing[:10]}"
            )

        conn.execute("UPDATE uploads SET status = 'assembling' WHERE id = ?", (req.upload_id,))

    # Assemble chunks into target file
    dest_dir = storage_manager.resolve_path(upload["target_dir"], owner_id=user["id"], allow_root=True)
    raw_name = sanitize_filename(upload["filename"], default="uploaded_file")
    final_name = get_unique_filename(dest_dir, raw_name)
    target_path = dest_dir / final_name

    assembled_size = 0
    hasher = hashlib.sha256() if req.expected_sha256 else None

    try:
        with open(target_path, "wb") as f_target:
            for idx in range(total_chunks):
                part_path = get_temp_part_path(req.upload_id, idx)
                if not part_path.exists():
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"Temporary chunk #{idx} missing on server"
                    )

                with open(part_path, "rb") as f_part:
                    while True:
                        buf = f_part.read(65536)
                        if not buf:
                            break
                        f_target.write(buf)
                        assembled_size += len(buf)
                        if hasher:
                            hasher.update(buf)

                # Delete part immediately to preserve disk space
                part_path.unlink(missing_ok=True)

        if assembled_size != upload["total_size"]:
            target_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Size mismatch: expected {upload['total_size']} bytes, assembled {assembled_size} bytes"
            )

        if req.expected_sha256 and hasher and hasher.hexdigest().lower() != req.expected_sha256.lower():
            target_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="SHA256 checksum mismatch"
            )

        meta = storage_manager.sync_file_metadata(target_path, owner_id=user["id"])
        storage_manager.invalidate_stats_cache()

        with get_db() as conn:
            conn.execute("UPDATE uploads SET status = 'completed' WHERE id = ?", (req.upload_id,))

        log_audit_event(
            "CHUNKED_UPLOAD",
            user["username"],
            request.client.host if request.client else "",
            request.headers.get("user-agent", ""),
            f"Assembled {meta['relative_path']} ({assembled_size} bytes, {total_chunks} chunks)"
        )

        return {
            "status": "ok",
            "file": meta
        }

    except Exception as e:
        if target_path.exists():
            target_path.unlink(missing_ok=True)
        with get_db() as conn:
            conn.execute("UPDATE uploads SET status = 'failed' WHERE id = ?", (req.upload_id,))
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to assemble file: {str(e)}")

@router.post("/cancel/{upload_id}")
def cancel_upload(
    upload_id: str,
    user: dict = Depends(get_current_user)
):
    with get_db() as conn:
        upload = conn.execute("SELECT * FROM uploads WHERE id = ? AND owner_id = ?", (upload_id, user["id"])).fetchone()
        if not upload:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
        conn.execute("UPDATE uploads SET status = 'cancelled' WHERE id = ?", (upload_id,))

    # Clean up temp parts
    total_chunks = upload["total_chunks"]
    for idx in range(total_chunks):
        part = get_temp_part_path(upload_id, idx)
        part.unlink(missing_ok=True)

    return {"status": "ok", "message": "Upload cancelled"}
