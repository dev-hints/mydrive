import os
import shutil
import zipfile
import mimetypes
import datetime
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, AsyncGenerator
from fastapi import HTTPException, status
from app.config import settings
from app.security import resolve_safe_path, sanitize_filename
from app.database import get_db

# Initialize common MIME types
mimetypes.init()
EXTRA_MIMES = {
    ".md": "text/markdown",
    ".py": "text/x-python",
    ".js": "application/javascript",
    ".ts": "application/typescript",
    ".json": "application/json",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".sh": "text/x-shellscript",
    ".apk": "application/vnd.android.package-archive",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".pdf": "application/pdf",
    ".epub": "application/epub+zip",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".avif": "image/avif",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".flv": "video/x-flv",
    ".wmv": "video/x-ms-wmv",
    ".m4v": "video/x-m4v",
    ".3gp": "video/3gpp",
    ".ogv": "video/ogg",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".rtf": "application/rtf",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
}

def guess_mime_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in EXTRA_MIMES:
        return EXTRA_MIMES[ext]
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"

def get_unique_filename(parent_dir: Path, filename: str) -> str:
    """Generate a unique filename like 'document (1).pdf' if 'document.pdf' exists."""
    target = parent_dir / filename
    if not target.exists():
        return filename
    
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1
    while True:
        candidate_name = f"{stem} ({counter}){suffix}"
        if not (parent_dir / candidate_name).exists():
            return candidate_name
        counter += 1

class StorageManager:
    def __init__(self):
        self._stats_cache: Optional[Dict[str, Any]] = None
        self._stats_cache_time: float = 0.0
        self._cache_ttl_seconds: float = 15.0

    def get_storage_root(self) -> Path:
        return settings.get_resolved_storage_root()

    def get_trash_dir(self) -> Path:
        return settings.get_resolved_trash_dir()

    def get_temp_dir(self) -> Path:
        return settings.get_resolved_temp_dir()

    def get_user_storage_root(self, owner_id: int = 1) -> Path:
        users_root = self.get_storage_root() / "users"
        user_dir = users_root / str(owner_id)
        if not user_dir.exists():
            user_dir.mkdir(parents=True, exist_ok=True)
            if owner_id == 1:
                # Migrate any legacy files placed directly in STORAGE_ROOT
                root = self.get_storage_root()
                for item in list(root.iterdir()):
                    if item.name not in ("users", ".trash", ".uploads_temp", ".mydrive") and item != users_root:
                        try:
                            shutil.move(str(item), str(user_dir / item.name))
                        except Exception:
                            pass
        return user_dir

    def get_user_trash_dir(self, owner_id: int = 1) -> Path:
        user_trash = self.get_trash_dir() / "users" / str(owner_id)
        user_trash.mkdir(parents=True, exist_ok=True)
        return user_trash

    def resolve_path(self, rel_path: str, owner_id: int = 1, allow_root: bool = True) -> Path:
        user_root = self.get_user_storage_root(owner_id)
        return resolve_safe_path(user_root, rel_path, allow_root=allow_root)

    def to_relative_path(self, abs_path: Path, owner_id: int = 1) -> str:
        root = self.get_user_storage_root(owner_id)
        try:
            rel = abs_path.relative_to(root)
            return "" if str(rel) == "." else str(rel).replace("\\", "/")
        except ValueError:
            return ""

    def sync_file_metadata(self, abs_path: Path, owner_id: int = 1) -> Dict[str, Any]:
        rel_path = self.to_relative_path(abs_path, owner_id=owner_id)
        is_dir = abs_path.is_dir()
        name = abs_path.name or "Root"
        size = 0 if is_dir else abs_path.stat().st_size
        mime = "inode/directory" if is_dir else guess_mime_type(name)
        mtime = datetime.datetime.fromtimestamp(abs_path.stat().st_mtime, tz=datetime.timezone.utc)

        with get_db() as conn:
            row = conn.execute(
                "SELECT id, is_starred FROM files_metadata WHERE relative_path = ? AND owner_id = ?",
                (rel_path, owner_id)
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE files_metadata
                    SET name = ?, size = ?, mime_type = ?, modified_at = ?, is_trash = 0
                    WHERE id = ? AND owner_id = ?
                    """,
                    (name, size, mime, mtime.isoformat(), row["id"], owner_id)
                )
                file_id = row["id"]
                is_starred = row["is_starred"]
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO files_metadata (name, relative_path, is_directory, size, mime_type, owner_id, created_at, modified_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (name, rel_path, 1 if is_dir else 0, size, mime, owner_id, mtime.isoformat(), mtime.isoformat())
                )
                file_id = cursor.lastrowid
                is_starred = 0

        return {
            "id": file_id,
            "name": name,
            "relative_path": rel_path,
            "is_directory": is_dir,
            "size": size,
            "mime_type": mime,
            "is_starred": bool(is_starred),
            "modified_at": mtime.isoformat()
        }

    def sync_tree_metadata(self, base_path: Path, owner_id: int = 1):
        self.sync_file_metadata(base_path, owner_id=owner_id)
        if base_path.is_dir():
            for root, dirs, files in os.walk(str(base_path)):
                for d in dirs:
                    self.sync_file_metadata(Path(root) / d, owner_id=owner_id)
                for f in files:
                    self.sync_file_metadata(Path(root) / f, owner_id=owner_id)

    def list_directory(self, rel_path: str = "", show_hidden: Optional[bool] = None, owner_id: int = 1) -> Dict[str, Any]:
        target_dir = self.resolve_path(rel_path, owner_id=owner_id, allow_root=True)
        if not target_dir.exists() or not target_dir.is_dir():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Directory not found")

        allow_hidden = settings.SHOW_HIDDEN_FILES if show_hidden is None else show_hidden
        items = []

        try:
            with os.scandir(target_dir) as entries:
                for entry in entries:
                    if not allow_hidden and entry.name.startswith("."):
                        continue
                    # Ignore trash and internal directories if in user root
                    if target_dir == self.get_user_storage_root(owner_id) and entry.name in [".trash", ".uploads_temp", ".mydrive"]:
                        continue

                    entry_path = Path(entry.path)
                    try:
                        st = entry.stat(follow_symlinks=False)
                        is_dir = entry.is_dir(follow_symlinks=False)
                        mime = "inode/directory" if is_dir else guess_mime_type(entry.name)
                        mtime = datetime.datetime.fromtimestamp(st.st_mtime, tz=datetime.timezone.utc).isoformat()
                        rel = self.to_relative_path(entry_path, owner_id=owner_id)

                        # Check DB for star status
                        with get_db() as conn:
                            db_row = conn.execute(
                                "SELECT id, is_starred FROM files_metadata WHERE relative_path = ? AND owner_id = ?",
                                (rel, owner_id)
                            ).fetchone()
                        if db_row:
                            file_id = db_row["id"]
                            is_starred = bool(db_row["is_starred"])
                        else:
                            try:
                                meta = self.sync_file_metadata(entry_path, owner_id=owner_id)
                                file_id = meta["id"]
                                is_starred = False
                            except Exception:
                                file_id = None
                                is_starred = False

                        items.append({
                            "id": file_id,
                            "name": entry.name,
                            "relative_path": rel,
                            "is_directory": is_dir,
                            "size": 0 if is_dir else st.st_size,
                            "mime_type": mime,
                            "is_starred": is_starred,
                            "modified_at": mtime
                        })
                    except (OSError, PermissionError):
                        continue
        except PermissionError:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied reading directory")

        # Sort: directories first, then alphabetically
        items.sort(key=lambda x: (not x["is_directory"], x["name"].lower()))
        return {
            "current_path": self.to_relative_path(target_dir, owner_id=owner_id),
            "items": items,
            "total_count": len(items)
        }

    def create_directory(self, rel_parent_path: str, folder_name: str, owner_id: int = 1) -> Dict[str, Any]:
        cleaned_name = sanitize_filename(folder_name, default="")
        if not cleaned_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid folder name")
        
        parent_dir = self.resolve_path(rel_parent_path, owner_id=owner_id, allow_root=True)
        if not parent_dir.exists() or not parent_dir.is_dir():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent directory not found")

        target = parent_dir / cleaned_name
        if target.exists():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A file or folder with this name already exists")

        target.mkdir(parents=False, exist_ok=False)
        self.invalidate_stats_cache()
        return self.sync_file_metadata(target, owner_id=owner_id)

    def rename_item(self, rel_path: str, new_name: str, owner_id: int = 1) -> Dict[str, Any]:
        cleaned_name = sanitize_filename(new_name, default="")
        if not cleaned_name:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid target name")

        source = self.resolve_path(rel_path, owner_id=owner_id, allow_root=False)
        if not source.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source item not found")

        dest = source.parent / cleaned_name
        if dest.exists() and dest != source:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Target name already exists")

        old_rel = self.to_relative_path(source, owner_id=owner_id)
        new_rel = self.to_relative_path(dest, owner_id=owner_id)

        os.replace(source, dest)

        with get_db() as conn:
            # Update item
            conn.execute(
                "UPDATE files_metadata SET name = ?, relative_path = ?, modified_at = ? WHERE relative_path = ? AND owner_id = ?",
                (cleaned_name, new_rel, datetime.datetime.now(datetime.timezone.utc).isoformat(), old_rel, owner_id)
            )
            # If directory, update all child relative paths
            conn.execute(
                """
                UPDATE files_metadata
                SET relative_path = ? || substr(relative_path, length(?) + 1)
                WHERE relative_path LIKE ? || '/%' AND owner_id = ?
                """,
                (new_rel, old_rel, old_rel, owner_id)
            )
            # Update any active share links
            conn.execute(
                "UPDATE share_links SET relative_path = ? WHERE relative_path = ? AND owner_id = ?",
                (new_rel, old_rel, owner_id)
            )

        self.invalidate_stats_cache()
        return self.sync_file_metadata(dest, owner_id=owner_id)

    def move_item(self, rel_source_path: str, rel_dest_dir: str, overwrite: bool = False, owner_id: int = 1) -> Dict[str, Any]:
        source = self.resolve_path(rel_source_path, owner_id=owner_id, allow_root=False)
        dest_dir = self.resolve_path(rel_dest_dir, owner_id=owner_id, allow_root=True)

        if not source.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source item not found")
        if not dest_dir.is_dir():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destination directory not found")

        dest = dest_dir / source.name
        if dest == source:
            return self.sync_file_metadata(dest, owner_id=owner_id)

        if dest.exists() and not overwrite:
            unique_name = get_unique_filename(dest_dir, source.name)
            dest = dest_dir / unique_name

        old_rel = self.to_relative_path(source, owner_id=owner_id)
        new_rel = self.to_relative_path(dest, owner_id=owner_id)

        shutil.move(str(source), str(dest))

        with get_db() as conn:
            conn.execute(
                "UPDATE files_metadata SET name = ?, relative_path = ?, modified_at = ? WHERE relative_path = ? AND owner_id = ?",
                (dest.name, new_rel, datetime.datetime.now(datetime.timezone.utc).isoformat(), old_rel, owner_id)
            )
            if dest.is_dir():
                conn.execute(
                    """
                    UPDATE files_metadata
                    SET relative_path = ? || substr(relative_path, length(?) + 1)
                    WHERE relative_path LIKE ? || '/%' AND owner_id = ?
                    """,
                    (new_rel, old_rel, old_rel, owner_id)
                )

        self.invalidate_stats_cache()
        return self.sync_file_metadata(dest, owner_id=owner_id)

    def copy_item(self, rel_source_path: str, rel_dest_dir: str, overwrite: bool = False, owner_id: int = 1) -> Dict[str, Any]:
        source = self.resolve_path(rel_source_path, owner_id=owner_id, allow_root=False)
        dest_dir = self.resolve_path(rel_dest_dir, owner_id=owner_id, allow_root=True)

        if not source.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source item not found")
        if not dest_dir.is_dir():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destination directory not found")

        dest = dest_dir / source.name
        if dest.exists() and not overwrite:
            unique_name = get_unique_filename(dest_dir, source.name)
            dest = dest_dir / unique_name

        if source.is_dir():
            shutil.copytree(str(source), str(dest))
            self.sync_tree_metadata(dest, owner_id=owner_id)
        else:
            shutil.copy2(str(source), str(dest))
            self.sync_file_metadata(dest, owner_id=owner_id)

        self.invalidate_stats_cache()
        return self.sync_file_metadata(dest, owner_id=owner_id)

    def move_to_trash(self, rel_path: str, owner_id: int = 1) -> Dict[str, Any]:
        source = self.resolve_path(rel_path, owner_id=owner_id, allow_root=False)
        if not source.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")

        trash_dir = self.get_user_trash_dir(owner_id)
        trash_id = f"{int(time.time())}_{source.name}"
        trash_target = trash_dir / trash_id

        old_rel = self.to_relative_path(source, owner_id=owner_id)
        is_dir = source.is_dir()
        size = 0 if is_dir else source.stat().st_size
        mime = "inode/directory" if is_dir else guess_mime_type(source.name)

        shutil.move(str(source), str(trash_target))

        now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with get_db() as conn:
            row = conn.execute("SELECT id FROM files_metadata WHERE relative_path = ? AND owner_id = ?", (old_rel, owner_id)).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE files_metadata
                    SET relative_path = ?, is_trash = 1, original_path = ?, deleted_at = ?, modified_at = ?
                    WHERE id = ? AND owner_id = ?
                    """,
                    (f".trash/{trash_id}", old_rel, now_str, now_str, row["id"], owner_id)
                )
            else:
                conn.execute(
                    """
                    INSERT INTO files_metadata (name, relative_path, is_directory, size, mime_type, is_trash, original_path, deleted_at, owner_id, modified_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
                    """,
                    (source.name, f".trash/{trash_id}", 1 if is_dir else 0, size, mime, old_rel, now_str, owner_id, now_str)
                )

        self.invalidate_stats_cache()
        return {"status": "moved_to_trash", "original_path": old_rel}

    def list_trash(self, owner_id: int = 1) -> List[Dict[str, Any]]:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT id, name, relative_path, is_directory, size, mime_type, original_path, deleted_at
                FROM files_metadata
                WHERE is_trash = 1 AND owner_id = ?
                ORDER BY deleted_at DESC
                """,
                (owner_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def restore_from_trash(self, trash_db_id: int, owner_id: int = 1) -> Dict[str, Any]:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM files_metadata WHERE id = ? AND is_trash = 1 AND owner_id = ?",
                (trash_db_id, owner_id)
            ).fetchone()

            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trash item not found")

            trash_item_name = Path(row["relative_path"]).name
            trash_source = self.get_user_trash_dir(owner_id) / trash_item_name
            if not trash_source.exists():
                conn.execute("DELETE FROM files_metadata WHERE id = ? AND owner_id = ?", (trash_db_id, owner_id))
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trash physical file missing")

            dest = self.resolve_path(row["original_path"], owner_id=owner_id, allow_root=False)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                unique_name = get_unique_filename(dest.parent, dest.name)
                dest = dest.parent / unique_name

            shutil.move(str(trash_source), str(dest))
            new_rel = self.to_relative_path(dest, owner_id=owner_id)

            conn.execute("DELETE FROM files_metadata WHERE relative_path = ? AND owner_id = ? AND id != ?", (new_rel, owner_id, trash_db_id))

            conn.execute(
                """
                UPDATE files_metadata
                SET is_trash = 0, relative_path = ?, original_path = NULL, deleted_at = NULL, modified_at = ?
                WHERE id = ? AND owner_id = ?
                """,
                (new_rel, datetime.datetime.now(datetime.timezone.utc).isoformat(), trash_db_id, owner_id)
            )

        self.invalidate_stats_cache()
        return {"status": "restored", "relative_path": new_rel}

    def permanently_delete_from_trash(self, trash_db_id: int, owner_id: int = 1) -> Dict[str, Any]:
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM files_metadata WHERE id = ? AND is_trash = 1 AND owner_id = ?",
                (trash_db_id, owner_id)
            ).fetchone()

            if not row:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trash item not found")

            trash_item_name = Path(row["relative_path"]).name
            trash_source = self.get_user_trash_dir(owner_id) / trash_item_name
            if trash_source.exists():
                if trash_source.is_dir():
                    shutil.rmtree(str(trash_source), ignore_errors=True)
                else:
                    try:
                        trash_source.unlink()
                    except OSError:
                        pass

            conn.execute("DELETE FROM files_metadata WHERE id = ? AND owner_id = ?", (trash_db_id, owner_id))

        self.invalidate_stats_cache()
        return {"status": "permanently_deleted"}

    def empty_trash(self, owner_id: int = 1) -> Dict[str, Any]:
        trash_dir = self.get_user_trash_dir(owner_id)
        if trash_dir.exists():
            for item in trash_dir.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(str(item), ignore_errors=True)
                    else:
                        item.unlink()
                except OSError:
                    continue

        with get_db() as conn:
            conn.execute("DELETE FROM files_metadata WHERE is_trash = 1 AND owner_id = ?", (owner_id,))

        self.invalidate_stats_cache()
        return {"status": "trash_emptied"}

    def toggle_star(self, rel_path: str, owner_id: int = 1) -> Dict[str, Any]:
        path = self.resolve_path(rel_path, owner_id=owner_id, allow_root=False)
        if not path.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        
        rel = self.to_relative_path(path, owner_id=owner_id)
        with get_db() as conn:
            row = conn.execute("SELECT id, is_starred FROM files_metadata WHERE relative_path = ? AND owner_id = ?", (rel, owner_id)).fetchone()
            if row:
                new_star = 0 if row["is_starred"] else 1
                conn.execute("UPDATE files_metadata SET is_starred = ? WHERE id = ? AND owner_id = ?", (new_star, row["id"], owner_id))
                return {"relative_path": rel, "is_starred": bool(new_star)}
            else:
                meta = self.sync_file_metadata(path, owner_id=owner_id)
                conn.execute("UPDATE files_metadata SET is_starred = 1 WHERE id = ? AND owner_id = ?", (meta["id"], owner_id))
                return {"relative_path": rel, "is_starred": True}

    def list_starred(self, owner_id: int = 1) -> List[Dict[str, Any]]:
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT id, name, relative_path, is_directory, size, mime_type, modified_at, is_starred
                FROM files_metadata
                WHERE is_starred = 1 AND is_trash = 0 AND owner_id = ?
                ORDER BY name ASC
                """,
                (owner_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def list_recent(self, limit: int = 30, owner_id: int = 1) -> List[Dict[str, Any]]:
        self.scan_and_sync_user_files(owner_id=owner_id)
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT id, name, relative_path, is_directory, size, mime_type, modified_at, is_starred
                FROM files_metadata
                WHERE is_trash = 0 AND is_directory = 0 AND owner_id = ?
                ORDER BY modified_at DESC
                LIMIT ?
                """,
                (owner_id, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def scan_and_sync_user_files(self, owner_id: int = 1):
        """Recursively scans the user storage folder tree to ensure any existing disk files are indexed in files_metadata."""
        user_root = self.get_user_storage_root(owner_id)
        if not user_root.exists():
            return

        # Fetch existing active records for this owner in a single fast query
        with get_db() as conn:
            existing_rows = conn.execute(
                "SELECT id, relative_path, size, modified_at FROM files_metadata WHERE owner_id = ? AND is_trash = 0 AND is_directory = 0",
                (owner_id,)
            ).fetchall()

        db_files = {r["relative_path"]: r for r in existing_rows}
        disk_rel_paths = set()

        for root, dirs, files in os.walk(str(user_root)):
            dirs[:] = [d for d in dirs if d not in (".trash", ".uploads_temp", ".mydrive") and not d.startswith(".")]
            root_path = Path(root)
            for f in files:
                if f.startswith(".") or f in (".trash", ".uploads_temp", ".mydrive"):
                    continue
                file_abs = root_path / f
                try:
                    rel = self.to_relative_path(file_abs, owner_id=owner_id)
                    disk_rel_paths.add(rel)
                    st = file_abs.stat()
                    if rel not in db_files:
                        self.sync_file_metadata(file_abs, owner_id=owner_id)
                    elif st.st_size != db_files[rel]["size"]:
                        self.sync_file_metadata(file_abs, owner_id=owner_id)
                except Exception:
                    continue

        # Clean up stale DB records for files no longer on disk
        stale_ids = [r["id"] for rel, r in db_files.items() if rel not in disk_rel_paths]
        if stale_ids:
            with get_db() as conn:
                placeholders = ",".join("?" * len(stale_ids))
                conn.execute(f"DELETE FROM files_metadata WHERE id IN ({placeholders}) AND owner_id = ?", (*stale_ids, owner_id))

    def list_files_by_category(self, category: str, owner_id: int = 1) -> List[Dict[str, Any]]:
        self.scan_and_sync_user_files(owner_id=owner_id)
        cat = category.lower().strip()

        if cat in ("photos", "photo", "images", "image"):
            sql_filter = """
                (
                    LOWER(mime_type) LIKE 'image/%'
                    OR LOWER(name) LIKE '%.jpg'
                    OR LOWER(name) LIKE '%.jpeg'
                    OR LOWER(name) LIKE '%.png'
                    OR LOWER(name) LIKE '%.gif'
                    OR LOWER(name) LIKE '%.webp'
                    OR LOWER(name) LIKE '%.svg'
                    OR LOWER(name) LIKE '%.bmp'
                    OR LOWER(name) LIKE '%.ico'
                    OR LOWER(name) LIKE '%.heic'
                    OR LOWER(name) LIKE '%.heif'
                    OR LOWER(name) LIKE '%.avif'
                    OR LOWER(name) LIKE '%.tiff'
                    OR LOWER(name) LIKE '%.tif'
                    OR LOWER(name) LIKE '%.raw'
                    OR LOWER(name) LIKE '%.cr2'
                    OR LOWER(name) LIKE '%.nef'
                )
            """
        elif cat in ("videos", "video"):
            sql_filter = """
                (
                    LOWER(mime_type) LIKE 'video/%'
                    OR LOWER(name) LIKE '%.mp4'
                    OR LOWER(name) LIKE '%.webm'
                    OR LOWER(name) LIKE '%.mov'
                    OR LOWER(name) LIKE '%.mkv'
                    OR LOWER(name) LIKE '%.avi'
                    OR LOWER(name) LIKE '%.flv'
                    OR LOWER(name) LIKE '%.wmv'
                    OR LOWER(name) LIKE '%.m4v'
                    OR LOWER(name) LIKE '%.3gp'
                    OR LOWER(name) LIKE '%.ts'
                    OR LOWER(name) LIKE '%.ogv'
                )
            """
        elif cat in ("documents", "document", "docs", "doc"):
            sql_filter = """
                (
                    LOWER(mime_type) = 'application/pdf'
                    OR LOWER(mime_type) LIKE 'text/%'
                    OR LOWER(mime_type) LIKE '%word%'
                    OR LOWER(mime_type) LIKE '%sheet%'
                    OR LOWER(mime_type) LIKE '%excel%'
                    OR LOWER(mime_type) LIKE '%presentation%'
                    OR LOWER(mime_type) LIKE '%powerpoint%'
                    OR LOWER(mime_type) LIKE '%opendocument%'
                    OR LOWER(mime_type) LIKE '%rtf%'
                    OR LOWER(mime_type) LIKE '%epub%'
                    OR LOWER(name) LIKE '%.pdf'
                    OR LOWER(name) LIKE '%.doc'
                    OR LOWER(name) LIKE '%.docx'
                    OR LOWER(name) LIKE '%.txt'
                    OR LOWER(name) LIKE '%.md'
                    OR LOWER(name) LIKE '%.rtf'
                    OR LOWER(name) LIKE '%.odt'
                    OR LOWER(name) LIKE '%.ods'
                    OR LOWER(name) LIKE '%.odp'
                    OR LOWER(name) LIKE '%.xls'
                    OR LOWER(name) LIKE '%.xlsx'
                    OR LOWER(name) LIKE '%.csv'
                    OR LOWER(name) LIKE '%.tsv'
                    OR LOWER(name) LIKE '%.ppt'
                    OR LOWER(name) LIKE '%.pptx'
                    OR LOWER(name) LIKE '%.epub'
                    OR LOWER(name) LIKE '%.pages'
                    OR LOWER(name) LIKE '%.numbers'
                    OR LOWER(name) LIKE '%.key'
                    OR LOWER(name) LIKE '%.log'
                    OR LOWER(name) LIKE '%.tex'
                )
            """
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported category: {category}")

        user_root = self.get_user_storage_root(owner_id)
        with get_db() as conn:
            rows = conn.execute(
                f"""
                SELECT id, name, relative_path, is_directory, size, mime_type, modified_at, is_starred
                FROM files_metadata
                WHERE is_trash = 0 AND is_directory = 0 AND owner_id = ? AND {sql_filter}
                ORDER BY modified_at DESC
                """,
                (owner_id,)
            ).fetchall()

            items = []
            stale_ids = []
            for r in rows:
                item = dict(r)
                item["is_starred"] = bool(item["is_starred"])
                target = user_root / item["relative_path"]
                if not target.exists():
                    stale_ids.append(item["id"])
                    continue
                items.append(item)

            if stale_ids:
                placeholders = ",".join("?" * len(stale_ids))
                conn.execute(f"DELETE FROM files_metadata WHERE id IN ({placeholders}) AND owner_id = ?", (*stale_ids, owner_id))

            return items

    def search_files(self, query: str, owner_id: int = 1) -> List[Dict[str, Any]]:
        query_pattern = f"%{query.strip()}%"
        results = []
        with get_db() as conn:
            rows = conn.execute(
                """
                SELECT id, name, relative_path, is_directory, size, mime_type, modified_at, is_starred
                FROM files_metadata
                WHERE is_trash = 0 AND owner_id = ? AND (name LIKE ? OR relative_path LIKE ?)
                ORDER BY is_directory DESC, name ASC
                LIMIT 100
                """,
                (owner_id, query_pattern, query_pattern)
            ).fetchall()
            for r in rows:
                results.append(dict(r))
        return results

    def get_user_used_storage(self, owner_id: int = 1) -> int:
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(size), 0) as used_bytes
                FROM files_metadata
                WHERE owner_id = ? AND is_trash = 0 AND is_directory = 0
                """,
                (owner_id,)
            ).fetchone()
            return row["used_bytes"] if row else 0

    def get_storage_stats(self, owner_id: Optional[int] = None) -> Dict[str, Any]:
        storage_root = self.get_storage_root()
        total_disk, used_disk, free_disk = shutil.disk_usage(str(storage_root))

        file_count = 0
        folder_count = 0
        total_files_size = 0
        user_quota = 0

        with get_db() as conn:
            if owner_id is not None:
                user_row = conn.execute("SELECT quota_bytes FROM users WHERE id = ?", (owner_id,)).fetchone()
                if user_row:
                    user_quota = user_row["quota_bytes"] or 0

                row = conn.execute(
                    """
                    SELECT 
                        COUNT(CASE WHEN is_directory = 0 AND is_trash = 0 THEN 1 END) as file_count,
                        COUNT(CASE WHEN is_directory = 1 AND is_trash = 0 THEN 1 END) as folder_count,
                        COALESCE(SUM(CASE WHEN is_directory = 0 AND is_trash = 0 THEN size ELSE 0 END), 0) as total_size
                    FROM files_metadata
                    WHERE owner_id = ?
                    """,
                    (owner_id,)
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT 
                        COUNT(CASE WHEN is_directory = 0 AND is_trash = 0 THEN 1 END) as file_count,
                        COUNT(CASE WHEN is_directory = 1 AND is_trash = 0 THEN 1 END) as folder_count,
                        COALESCE(SUM(CASE WHEN is_directory = 0 AND is_trash = 0 THEN size ELSE 0 END), 0) as total_size
                    FROM files_metadata
                    """
                ).fetchone()

            if row:
                file_count = row["file_count"]
                folder_count = row["folder_count"]
                total_files_size = row["total_size"]

        if owner_id is not None and user_quota > 0:
            percent_used = round((total_files_size / user_quota * 100), 1)
        else:
            percent_used = round((used_disk / total_disk * 100), 1) if total_disk > 0 else 0

        user_root = str(self.get_user_storage_root(owner_id)) if owner_id is not None else str(storage_root)

        return {
            "total_disk": total_disk,
            "used_disk": used_disk,
            "free_disk": free_disk,
            "percent_used": percent_used,
            "file_count": file_count,
            "folder_count": folder_count,
            "managed_size": total_files_size,
            "storage_root": user_root,
            "quota_bytes": user_quota,
            "user_storage_used": total_files_size
        }

    def invalidate_stats_cache(self):
        self._stats_cache = None

    def create_folder_zip(self, folder_path: Path, output_zip_path: Path):
        """Creates a zip archive of folder_path preserving directory hierarchy."""
        output_zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(str(output_zip_path), mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            base_folder_name = folder_path.name
            has_entries = False
            for root, dirs, files in os.walk(str(folder_path)):
                if not settings.SHOW_HIDDEN_FILES:
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    files = [f for f in files if not f.startswith(".")]

                root_path = Path(root)
                rel_to_base = root_path.relative_to(folder_path)

                if not dirs and not files and rel_to_base != Path("."):
                    has_entries = True
                    arcname = (Path(base_folder_name) / rel_to_base).as_posix() + "/"
                    zf.writestr(arcname, "")

                for file in files:
                    has_entries = True
                    file_abs = root_path / file
                    arcname = (Path(base_folder_name) / rel_to_base / file).as_posix()
                    zf.write(str(file_abs), arcname=arcname)

            if not has_entries:
                zf.writestr(f"{base_folder_name}/", "")

    def delete_user_storage(self, owner_id: int):
        user_root = self.get_storage_root() / "users" / str(owner_id)
        if user_root.exists():
            shutil.rmtree(str(user_root), ignore_errors=True)
        user_trash = self.get_trash_dir() / "users" / str(owner_id)
        if user_trash.exists():
            shutil.rmtree(str(user_trash), ignore_errors=True)
        self.invalidate_stats_cache()

    def wipe_user_storage(self, owner_id: int):
        self.delete_user_storage(owner_id)
        self.get_user_storage_root(owner_id)
        self.get_user_trash_dir(owner_id)
        self.invalidate_stats_cache()

    async def get_file_stream(self, file_path: Path, start_byte: int, end_byte: int, chunk_size: int = 65536) -> AsyncGenerator[bytes, None]:
        """Streams bytes between start_byte and end_byte without loading entire file into memory."""
        bytes_to_read = end_byte - start_byte + 1
        with open(file_path, "rb") as f:
            f.seek(start_byte)
            while bytes_to_read > 0:
                current_chunk = min(chunk_size, bytes_to_read)
                data = f.read(current_chunk)
                if not data:
                    break
                bytes_to_read -= len(data)
                yield data

storage_manager = StorageManager()
