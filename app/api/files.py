from fastapi import APIRouter, Depends, Request, Response, HTTPException, status, UploadFile, File, Form, Query
from fastapi.responses import StreamingResponse, FileResponse
import os
import uuid
import zipfile
import urllib.parse
from pathlib import Path
from typing import Optional, List
from app.config import settings
from app.database import get_db
from app.storage import storage_manager, guess_mime_type, get_unique_filename
from app.security import get_current_user, log_audit_event, sanitize_filename
from app.schemas import (
    FolderCreateRequest, RenameRequest, MoveCopyRequest,
    StarRequest, DeleteRequest, BatchDownloadRequest, BatchDeleteRequest
)

router = APIRouter(prefix="/api/files", tags=["files"])

def format_content_disposition(disposition_type: str, filename: str) -> str:
    """Format RFC 6266 / RFC 5987 Content-Disposition header supporting Unicode & Emojis."""
    ascii_fallback = filename.encode("ascii", "replace").decode("ascii").replace('"', '\\"')
    encoded_utf8 = urllib.parse.quote(filename, encoding="utf-8")
    return f'{disposition_type}; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded_utf8}'

def parse_range_header(range_header: str, file_size: int):
    """Parses Range header e.g. bytes=0-1048575, bytes=1048576-, bytes=-500."""
    try:
        units, ranges = range_header.split("=", 1)
        if units.strip().lower() != "bytes":
            return None
        parts = ranges.split(",", 1)[0].split("-", 1)
        start_str, end_str = parts[0].strip(), parts[1].strip()

        if start_str and end_str:
            start = int(start_str)
            end = int(end_str)
        elif start_str:
            start = int(start_str)
            end = file_size - 1
        elif end_str:
            suffix_len = int(end_str)
            start = max(0, file_size - suffix_len)
            end = file_size - 1
        else:
            return None

        if start > end or start >= file_size:
            return None

        end = min(end, file_size - 1)
        return start, end
    except Exception:
        return None

@router.get("")
def list_files(
    path: str = Query(default=""),
    show_hidden: Optional[bool] = Query(default=None),
    user: dict = Depends(get_current_user)
):
    return storage_manager.list_directory(path, show_hidden=show_hidden, owner_id=user["id"])

@router.post("/folder")
def create_folder(
    req: FolderCreateRequest,
    request: Request,
    user: dict = Depends(get_current_user)
):
    result = storage_manager.create_directory(req.parent_path, req.folder_name, owner_id=user["id"])
    log_audit_event("CREATE_FOLDER", user["username"], request.client.host if request.client else "", request.headers.get("user-agent", ""), f"Created folder {result['relative_path']}")
    return result

@router.patch("/rename")
def rename_item(
    req: RenameRequest,
    request: Request,
    user: dict = Depends(get_current_user)
):
    result = storage_manager.rename_item(req.path, req.new_name, owner_id=user["id"])
    log_audit_event("RENAME", user["username"], request.client.host if request.client else "", request.headers.get("user-agent", ""), f"Renamed {req.path} to {req.new_name}")
    return result

@router.post("/move")
def move_item(
    req: MoveCopyRequest,
    request: Request,
    user: dict = Depends(get_current_user)
):
    result = storage_manager.move_item(req.source_path, req.destination_dir, overwrite=req.overwrite, owner_id=user["id"])
    log_audit_event("MOVE", user["username"], request.client.host if request.client else "", request.headers.get("user-agent", ""), f"Moved {req.source_path} to {req.destination_dir}")
    return result

@router.post("/copy")
def copy_item(
    req: MoveCopyRequest,
    request: Request,
    user: dict = Depends(get_current_user)
):
    result = storage_manager.copy_item(req.source_path, req.destination_dir, overwrite=req.overwrite, owner_id=user["id"])
    log_audit_event("COPY", user["username"], request.client.host if request.client else "", request.headers.get("user-agent", ""), f"Copied {req.source_path} to {req.destination_dir}")
    return result

@router.delete("")
def delete_item(
    path: str = Query(...),
    request: Request = None,
    user: dict = Depends(get_current_user)
):
    result = storage_manager.move_to_trash(path, owner_id=user["id"])
    log_audit_event("TRASH", user["username"], request.client.host if request and request.client else "", request.headers.get("user-agent", "") if request else "", f"Moved {path} to trash")
    return result

@router.get("/trash")
def list_trash(user: dict = Depends(get_current_user)):
    return {"items": storage_manager.list_trash(owner_id=user["id"])}

@router.post("/trash/restore/{item_id}")
def restore_trash(
    item_id: int,
    request: Request,
    user: dict = Depends(get_current_user)
):
    result = storage_manager.restore_from_trash(item_id, owner_id=user["id"])
    log_audit_event("RESTORE_TRASH", user["username"], request.client.host if request.client else "", request.headers.get("user-agent", ""), f"Restored trash item #{item_id}")
    return result

@router.delete("/trash/permanent/{item_id}")
def permanent_delete(
    item_id: int,
    request: Request,
    user: dict = Depends(get_current_user)
):
    result = storage_manager.permanently_delete_from_trash(item_id, owner_id=user["id"])
    log_audit_event("PERMANENT_DELETE", user["username"], request.client.host if request.client else "", request.headers.get("user-agent", ""), f"Permanently deleted trash item #{item_id}")
    return result

@router.post("/trash/empty")
def empty_trash(
    request: Request,
    user: dict = Depends(get_current_user)
):
    result = storage_manager.empty_trash(owner_id=user["id"])
    log_audit_event("EMPTY_TRASH", user["username"], request.client.host if request.client else "", request.headers.get("user-agent", ""), "Emptied trash bin")
    return result

@router.post("/star")
def toggle_star(
    req: StarRequest,
    user: dict = Depends(get_current_user)
):
    return storage_manager.toggle_star(req.path, owner_id=user["id"])

@router.get("/starred")
def list_starred(user: dict = Depends(get_current_user)):
    return {"items": storage_manager.list_starred(owner_id=user["id"])}

@router.get("/recent")
def list_recent(user: dict = Depends(get_current_user)):
    return {"items": storage_manager.list_recent(limit=50, owner_id=user["id"])}

@router.get("/photos")
def list_photos(user: dict = Depends(get_current_user)):
    return {"items": storage_manager.list_files_by_category("photos", owner_id=user["id"])}

@router.get("/videos")
def list_videos(user: dict = Depends(get_current_user)):
    return {"items": storage_manager.list_files_by_category("videos", owner_id=user["id"])}

@router.get("/documents")
def list_documents(user: dict = Depends(get_current_user)):
    return {"items": storage_manager.list_files_by_category("documents", owner_id=user["id"])}

@router.get("/category/{category}")
def list_category(category: str, user: dict = Depends(get_current_user)):
    return {"items": storage_manager.list_files_by_category(category, owner_id=user["id"])}

@router.post("/upload")
async def direct_upload(
    request: Request,
    target_dir: str = Form(default=""),
    overwrite: bool = Form(default=False),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    """Direct streaming upload for single files."""
    dest_dir = storage_manager.resolve_path(target_dir, owner_id=user["id"], allow_root=True)
    if not dest_dir.exists() or not dest_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target directory does not exist")

    with get_db() as conn:
        user_row = conn.execute("SELECT quota_bytes FROM users WHERE id = ?", (user["id"],)).fetchone()
        user_quota = user_row["quota_bytes"] if user_row else 0

    current_used = storage_manager.get_user_used_storage(user["id"])
    if user_quota > 0 and current_used >= user_quota:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Storage quota exceeded. Please delete files or contact your administrator."
        )

    original_name = file.filename or "uploaded_file"
    cleaned_name = sanitize_filename(original_name, default="uploaded_file")

    if not overwrite:
        final_name = get_unique_filename(dest_dir, cleaned_name)
    else:
        final_name = cleaned_name

    target_file = dest_dir / final_name
    written_bytes = 0

    # Stream write in 64KB chunks to avoid RAM consumption
    with open(target_file, "wb") as f_out:
        while True:
            chunk = await file.read(65536)
            if not chunk:
                break
            written_bytes += len(chunk)
            if written_bytes > settings.MAX_UPLOAD_SIZE:
                target_file.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File exceeds maximum upload size limit ({settings.MAX_UPLOAD_SIZE} bytes)"
                )
            if user_quota > 0 and (current_used + written_bytes) > user_quota:
                target_file.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Storage quota exceeded while uploading file."
                )
            f_out.write(chunk)

    meta = storage_manager.sync_file_metadata(target_file, owner_id=user["id"])
    storage_manager.invalidate_stats_cache()
    log_audit_event("UPLOAD", user["username"], request.client.host if request.client else "", request.headers.get("user-agent", ""), f"Uploaded {meta['relative_path']} ({written_bytes} bytes)")

    return {
        "status": "ok",
        "file": meta
    }

@router.get("/download")
async def download_file(
    request: Request,
    path: str = Query(...),
    user: dict = Depends(get_current_user)
):
    target = storage_manager.resolve_path(path, owner_id=user["id"], allow_root=False)
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
    range_header = request.headers.get("range")

    cd_header = format_content_disposition("attachment", target.name)

    if range_header:
        parsed_range = parse_range_header(range_header, file_size)
        if parsed_range is None:
            return Response(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                headers={"Content-Range": f"bytes */{file_size}"}
            )
        start, end = parsed_range
        content_length = end - start + 1
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
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

@router.get("/download-folder")
async def download_folder(
    request: Request,
    path: str = Query(...),
    user: dict = Depends(get_current_user)
):
    return await download_file(request, path=path, user=user)

async def handle_batch_download(paths: List[str], user: dict):
    if not paths:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files selected")

    # If only 1 file path is requested and it's a regular file, stream it directly
    if len(paths) == 1:
        single_target = storage_manager.resolve_path(paths[0], owner_id=user["id"], allow_root=False)
        if single_target.exists() and single_target.is_file():
            cd_header = format_content_disposition("attachment", single_target.name)
            mime_type = guess_mime_type(single_target.name)
            file_size = single_target.stat().st_size
            return StreamingResponse(
                storage_manager.get_file_stream(single_target, 0, file_size - 1),
                status_code=status.HTTP_200_OK,
                headers={
                    "Content-Disposition": cd_header,
                    "Content-Length": str(file_size),
                    "Content-Type": mime_type
                }
            )

    temp_zip = storage_manager.get_temp_dir() / f"download_{uuid.uuid4().hex}.zip"
    temp_zip.parent.mkdir(parents=True, exist_ok=True)

    added_items = 0
    with zipfile.ZipFile(str(temp_zip), mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel_path in paths:
            try:
                target = storage_manager.resolve_path(rel_path, owner_id=user["id"], allow_root=False)
                if not target.exists():
                    continue
                if target.is_dir():
                    base_name = target.name
                    has_sub_entries = False
                    for root, dirs, files in os.walk(str(target)):
                        if not settings.SHOW_HIDDEN_FILES:
                            dirs[:] = [d for d in dirs if not d.startswith(".")]
                        for d in dirs:
                            dir_path = Path(root) / d
                            arc_path = base_name + "/" + str(dir_path.relative_to(target)).replace("\\", "/") + "/"
                            zf.writestr(zipfile.ZipInfo(arc_path), "")
                            has_sub_entries = True
                        for f in files:
                            if not settings.SHOW_HIDDEN_FILES and f.startswith("."):
                                continue
                            file_path = Path(root) / f
                            arc_path = base_name + "/" + str(file_path.relative_to(target)).replace("\\", "/")
                            zf.write(str(file_path), arc_path)
                            has_sub_entries = True
                    if not has_sub_entries:
                        zf.writestr(zipfile.ZipInfo(base_name + "/"), "")
                    added_items += 1
                else:
                    zf.write(str(target), target.name)
                    added_items += 1
            except Exception:
                continue

    if added_items == 0 or not temp_zip.exists():
        temp_zip.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No valid files to download")

    zip_size = temp_zip.stat().st_size
    cd_header = format_content_disposition("attachment", "mydrive_selection.zip")

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

@router.get("/download-batch")
async def download_batch_get(
    paths: str = Query(..., description="Comma-separated paths"),
    user: dict = Depends(get_current_user)
):
    path_list = [p.strip() for p in paths.split(",") if p.strip()]
    return await handle_batch_download(path_list, user)

@router.post("/download-batch")
async def download_batch_post(
    req: BatchDownloadRequest,
    user: dict = Depends(get_current_user)
):
    return await handle_batch_download(req.paths, user)

@router.post("/batch-delete")
def batch_delete(
    req: BatchDeleteRequest,
    request: Request,
    user: dict = Depends(get_current_user)
):
    deleted_count = 0
    for p in req.paths:
        try:
            storage_manager.move_to_trash(p, owner_id=user["id"])
            deleted_count += 1
        except Exception:
            continue
    log_audit_event("BATCH_DELETE", user["username"], request.client.host if request.client else "", request.headers.get("user-agent", ""), f"Moved {deleted_count} items to trash")
    return {"status": "ok", "deleted_count": deleted_count}

@router.get("/preview")
async def preview_file(
    request: Request,
    path: str = Query(...),
    user: dict = Depends(get_current_user)
):
    target = storage_manager.resolve_path(path, owner_id=user["id"], allow_root=False)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    file_size = target.stat().st_size
    mime_type = guess_mime_type(target.name)
    range_header = request.headers.get("range")

    cd_header = format_content_disposition("inline", target.name)
    is_sandboxed_preview = mime_type in ("image/svg+xml", "text/html", "text/xml", "application/xhtml+xml", "application/xml")

    if range_header:
        parsed_range = parse_range_header(range_header, file_size)
        if parsed_range is None:
            return Response(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                headers={"Content-Range": f"bytes */{file_size}"}
            )
        start, end = parsed_range
        content_length = end - start + 1
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Disposition": cd_header,
            "Content-Type": mime_type
        }
        if is_sandboxed_preview:
            headers["Content-Security-Policy"] = "default-src 'none'; sandbox;"
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
    if is_sandboxed_preview:
        headers["Content-Security-Policy"] = "default-src 'none'; sandbox;"
    return StreamingResponse(
        storage_manager.get_file_stream(target, 0, file_size - 1),
        status_code=status.HTTP_200_OK,
        headers=headers
    )
