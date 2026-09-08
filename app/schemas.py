from pydantic import BaseModel, Field
from typing import Optional, List, Any
import datetime

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)

class SetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)
    storage_root: Optional[str] = None

class PasswordChangeRequest(BaseModel):
    old_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

class FolderCreateRequest(BaseModel):
    parent_path: str = Field(default="")
    folder_name: str = Field(..., min_length=1, max_length=255)

class RenameRequest(BaseModel):
    path: str = Field(...)
    new_name: str = Field(..., min_length=1, max_length=255)

class MoveCopyRequest(BaseModel):
    source_path: str = Field(...)
    destination_dir: str = Field(default="")
    overwrite: bool = Field(default=False)

class StarRequest(BaseModel):
    path: str = Field(...)

class DeleteRequest(BaseModel):
    path: str = Field(...)

class ChunkInitRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=255)
    target_dir: str = Field(default="")
    total_size: int = Field(..., gt=0)
    total_chunks: int = Field(..., gt=0)
    mime_type: Optional[str] = None
    overwrite: bool = Field(default=False)

class ChunkFinishRequest(BaseModel):
    upload_id: str = Field(...)
    expected_sha256: Optional[str] = None

class ShareCreateRequest(BaseModel):
    path: str = Field(...)
    password: Optional[str] = None
    expires_in_hours: Optional[int] = None # None means no expiration
    download_only: bool = Field(default=False)

class SharePasswordRequest(BaseModel):
    password: str = Field(...)

class SettingsUpdateRequest(BaseModel):
    storage_root: Optional[str] = None
    show_hidden_files: Optional[bool] = None
    max_upload_size: Optional[int] = None

class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="user")  # 'user' or 'admin'
    quota_bytes: int = Field(default=0, ge=0)  # 0 means unlimited

class UserUpdateRequest(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    quota_bytes: Optional[int] = Field(default=None, ge=0)
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)
    quota_bytes: Optional[int] = Field(default=0, ge=0)  # 0 means unlimited
    quota_gb: Optional[float] = Field(default=None, ge=0)

class BatchDownloadRequest(BaseModel):
    paths: List[str] = Field(..., min_length=1)

class BatchDeleteRequest(BaseModel):
    paths: List[str] = Field(..., min_length=1)

class StandardResponse(BaseModel):
    status: str
    message: Optional[str] = None
    data: Optional[Any] = None

class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=64)
    email: Optional[str] = Field(default=None, max_length=128)

class WipeDriveRequest(BaseModel):
    password: str = Field(..., min_length=1)

class AccountDeleteRequest(BaseModel):
    password: str = Field(..., min_length=1)

class ContactCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    phone: Optional[str] = Field(default="", max_length=64)
    email: Optional[str] = Field(default="", max_length=255)
    organization: Optional[str] = Field(default="", max_length=255)
    notes: Optional[str] = Field(default="", max_length=2000)
    raw_vcard: Optional[str] = None
    is_starred: Optional[bool] = False

class ContactUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=64)
    email: Optional[str] = Field(default=None, max_length=255)
    organization: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = Field(default=None, max_length=2000)
    is_starred: Optional[bool] = None

class ContactBatchCreateRequest(BaseModel):
    contacts: List[ContactCreateRequest] = Field(..., min_length=1)

class ContactBatchDeleteRequest(BaseModel):
    contact_ids: List[int] = Field(..., min_length=1)
