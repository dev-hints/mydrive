import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    APP_NAME: str = "MyDrive"
    HOST: str = "127.0.0.1"
    PORT: int = 8080
    DEBUG: bool = False
    
    # Storage settings
    # Can be Android shared storage e.g. /storage/emulated/0/MyDrive or local dir
    STORAGE_ROOT: str = str(BASE_DIR / "data" / "storage")
    DATABASE_PATH: str = str(BASE_DIR / "data" / "mydrive.db")
    TEMP_UPLOAD_DIR: str = str(BASE_DIR / "data" / "uploads_temp")
    TRASH_DIR: str = str(BASE_DIR / "data" / "trash")
    
    AVATARS_DIR: str = str(BASE_DIR / "data" / "avatars")
    
    # Security
    SESSION_SECRET: str = "CHANGE_ME_IN_PRODUCTION_USE_AT_LEAST_32_RANDOM_BYTES"
    CSRF_SECRET: str = "CHANGE_ME_IN_PRODUCTION_USE_CSRF_KEY"
    COOKIE_NAME: str = "mydrive_session"
    COOKIE_SECURE: Optional[bool] = None  # None = auto-detect via X-Forwarded-Proto / HTTPS
    SESSION_LIFETIME_DAYS: int = 30
    
    # Rate Limiting & Brute Force Protection
    RATE_LIMIT_LOGIN_ATTEMPTS: int = 5
    RATE_LIMIT_LOCKOUT_MINUTES: int = 15
    
    # Upload limits
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024 * 1024  # 10 GB
    CHUNK_SIZE: int = 4 * 1024 * 1024  # 4 MB
    DEFAULT_USER_QUOTA_BYTES: int = 5 * 1024 * 1024 * 1024  # 5 GB default quota for self-registered users
    
    # Policy
    SHOW_HIDDEN_FILES: bool = False
    ENABLE_DOCS: bool = False
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_resolved_storage_root(self) -> Path:
        expanded = os.path.expanduser(self.STORAGE_ROOT)
        p = Path(expanded)
        if not p.is_absolute():
            p = BASE_DIR / p
        path = p.resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_resolved_trash_dir(self) -> Path:
        expanded = os.path.expanduser(self.TRASH_DIR)
        p = Path(expanded)
        if not p.is_absolute():
            p = BASE_DIR / p
        path = p.resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_resolved_temp_dir(self) -> Path:
        expanded = os.path.expanduser(self.TEMP_UPLOAD_DIR)
        p = Path(expanded)
        if not p.is_absolute():
            p = BASE_DIR / p
        path = p.resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_resolved_db_path(self) -> Path:
        expanded = os.path.expanduser(self.DATABASE_PATH)
        p = Path(expanded)
        if not p.is_absolute():
            p = BASE_DIR / p
        path = p.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def get_resolved_avatars_dir(self) -> Path:
        expanded = os.path.expanduser(self.AVATARS_DIR)
        p = Path(expanded)
        if not p.is_absolute():
            p = BASE_DIR / p
        path = p.resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

settings = Settings()
