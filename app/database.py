import sqlite3
import os
from contextlib import contextmanager
from typing import Generator, Any, List, Optional, Dict
from app.config import settings

def get_db_connection() -> sqlite3.Connection:
    db_path = settings.get_resolved_db_path()
    conn = sqlite3.connect(
        str(db_path),
        timeout=10.0,
        isolation_level=None,  # Autocommit mode by default, explicit transactions with BEGIN
    )
    conn.row_factory = sqlite3.Row
    # Crucial PRoot & SQLite concurrency pragmas
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn

@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.execute("BEGIN;")
        try:
            # Users table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'admin',
                quota_bytes INTEGER DEFAULT 0, -- 0 means unlimited
                is_active INTEGER NOT NULL DEFAULT 1,
                display_name TEXT,
                email TEXT,
                profile_pic TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Migration for existing DB schema
            user_cols = [c["name"] for c in conn.execute("PRAGMA table_info(users)").fetchall()]
            if "display_name" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN display_name TEXT;")
            if "email" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN email TEXT;")
            if "profile_pic" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN profile_pic TEXT;")

            # Sessions table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                user_agent TEXT,
                ip_address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """)

            # Migrate files_metadata if old UNIQUE constraint exists
            table_info = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='files_metadata'").fetchone()
            if table_info and ("relative_path TEXT UNIQUE" in table_info["sql"] or ("UNIQUE(owner_id, relative_path)" not in table_info["sql"] and "UNIQUE (owner_id, relative_path)" not in table_info["sql"])):
                conn.execute("ALTER TABLE files_metadata RENAME TO _files_metadata_old;")
                conn.execute("""
                CREATE TABLE files_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    is_directory INTEGER NOT NULL DEFAULT 0,
                    size INTEGER NOT NULL DEFAULT 0,
                    mime_type TEXT,
                    is_starred INTEGER NOT NULL DEFAULT 0,
                    is_trash INTEGER NOT NULL DEFAULT 0,
                    original_path TEXT,
                    deleted_at TIMESTAMP,
                    owner_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
                    UNIQUE(owner_id, relative_path)
                );
                """)
                conn.execute("""
                INSERT OR IGNORE INTO files_metadata (id, name, relative_path, is_directory, size, mime_type, is_starred, is_trash, original_path, deleted_at, owner_id, created_at, modified_at)
                SELECT id, name, relative_path, is_directory, size, mime_type, is_starred, is_trash, original_path, deleted_at, owner_id, created_at, modified_at
                FROM _files_metadata_old;
                """)
                conn.execute("DROP TABLE _files_metadata_old;")

            # Files metadata table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS files_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                is_directory INTEGER NOT NULL DEFAULT 0,
                size INTEGER NOT NULL DEFAULT 0,
                mime_type TEXT,
                is_starred INTEGER NOT NULL DEFAULT 0,
                is_trash INTEGER NOT NULL DEFAULT 0,
                original_path TEXT,
                deleted_at TIMESTAMP,
                owner_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                modified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
                UNIQUE(owner_id, relative_path)
            );
            """)

            # Share links table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS share_links (
                token TEXT PRIMARY KEY,
                relative_path TEXT NOT NULL,
                is_directory INTEGER NOT NULL DEFAULT 0,
                password_hash TEXT,
                expires_at TIMESTAMP,
                download_only INTEGER NOT NULL DEFAULT 0,
                access_count INTEGER NOT NULL DEFAULT 0,
                owner_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """)

            # Chunked uploads tracking
            conn.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                target_dir TEXT NOT NULL,
                total_size INTEGER NOT NULL,
                total_chunks INTEGER NOT NULL,
                received_chunks TEXT NOT NULL DEFAULT '', -- JSON or comma separated chunk indices
                mime_type TEXT,
                owner_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'uploading', -- 'uploading', 'assembling', 'completed', 'failed'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """)

            # Settings table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Audit logs table
            conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                username TEXT,
                ip_address TEXT,
                user_agent TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # Rate limiting / failed login attempts
            conn.execute("""
            CREATE TABLE IF NOT EXISTS login_attempts (
                ip_address TEXT NOT NULL,
                username TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 1,
                first_failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                locked_until TIMESTAMP,
                PRIMARY KEY (ip_address, username)
            );
            """)

            # Contacts table for address book management
            conn.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                organization TEXT,
                notes TEXT,
                raw_vcard TEXT,
                is_starred INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
            );
            """)

            # Indexes for fast lookup and responsive UI
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_owner_path ON files_metadata(owner_id, relative_path);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_owner ON files_metadata(owner_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files_metadata(relative_path);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_trash ON files_metadata(is_trash);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_starred ON files_metadata(is_starred);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_shares_path ON share_links(relative_path);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(created_at DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_event ON audit_logs(event_type);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_owner ON contacts(owner_id);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_name ON contacts(owner_id, name);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_starred ON contacts(owner_id, is_starred);")

            conn.execute("COMMIT;")
        except Exception:
            conn.execute("ROLLBACK;")
            raise

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
