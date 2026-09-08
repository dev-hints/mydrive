import pytest
import os
import shutil
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient

# Use temporary directories for testing
test_temp_dir = tempfile.mkdtemp(prefix="mydrive_test_")
os.environ["STORAGE_ROOT"] = os.path.join(test_temp_dir, "storage")
os.environ["DATABASE_PATH"] = os.path.join(test_temp_dir, "test.db")
os.environ["TEMP_UPLOAD_DIR"] = os.path.join(test_temp_dir, "uploads_temp")
os.environ["TRASH_DIR"] = os.path.join(test_temp_dir, "trash")
os.environ["AVATARS_DIR"] = os.path.join(test_temp_dir, "avatars")
os.environ["SESSION_SECRET"] = "test_session_secret_32_bytes_long_123456"
os.environ["CSRF_SECRET"] = "test_csrf_secret_32_bytes_long_123456"
os.environ["RATE_LIMIT_LOGIN_ATTEMPTS"] = "5"
os.environ["RATE_LIMIT_LOCKOUT_MINUTES"] = "15"

from app.config import settings
from app.database import init_db, get_db
from app.storage import storage_manager
from app.main import app

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    settings.STORAGE_ROOT = os.path.join(test_temp_dir, "storage")
    settings.DATABASE_PATH = os.path.join(test_temp_dir, "test.db")
    settings.TEMP_UPLOAD_DIR = os.path.join(test_temp_dir, "uploads_temp")
    settings.TRASH_DIR = os.path.join(test_temp_dir, "trash")
    settings.AVATARS_DIR = os.path.join(test_temp_dir, "avatars")

    init_db()
    storage_manager.get_storage_root()
    storage_manager.get_temp_dir()
    storage_manager.get_trash_dir()

    yield

    shutil.rmtree(test_temp_dir, ignore_errors=True)

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

@pytest.fixture
def auth_client(client):
    # Setup initial admin if not existing
    res = client.get("/api/auth/setup-status")
    data = res.json()
    if data.get("needs_setup"):
        setup_res = client.post("/api/auth/setup", json={
            "username": "admin",
            "password": "StrongPassword123!",
            "confirm_password": "StrongPassword123!"
        })
        assert setup_res.status_code == 200
        csrf_token = setup_res.json().get("csrf_token")
    else:
        # Login
        login_res = client.post("/api/auth/login", json={
            "username": "admin",
            "password": "StrongPassword123!"
        })
        assert login_res.status_code == 200
        csrf_token = login_res.json().get("csrf_token")

    # Set CSRF header on client
    client.headers.update({"X-CSRF-Token": csrf_token})
    return client
