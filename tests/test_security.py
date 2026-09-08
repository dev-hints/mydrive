import pytest
import os
from pathlib import Path
from app.config import settings

def test_path_traversal_blocked(auth_client):
    attacks = [
        "../../etc/passwd",
        "../..",
        "foo/../../../etc/shadow",
        "nested/../../..",
        "file%00.txt"
    ]
    for attack in attacks:
        res = auth_client.get(f"/api/files/download?path={attack}")
        assert res.status_code in (400, 403, 404), f"Failed to block download attack: {attack}"

        folder_res = auth_client.post("/api/files/folder", json={
            "parent_path": attack,
            "folder_name": "hacked"
        })
        assert folder_res.status_code in (400, 403, 404), f"Failed to block folder creation attack: {attack}"

def test_unauthenticated_access_denied(client):
    # Direct access without login
    res = client.get("/api/files?path=")
    assert res.status_code == 401

    post_res = client.post("/api/files/folder", json={"parent_path": "", "folder_name": "secret"})
    assert post_res.status_code == 401

def test_symlink_escape_blocked(auth_client):
    storage_root = settings.get_resolved_storage_root()
    symlink_path = storage_root / "symlink_to_etc"

    try:
        if not symlink_path.exists() and not symlink_path.is_symlink():
            os.symlink("/etc", symlink_path)

        res = auth_client.get("/api/files/download?path=symlink_to_etc/passwd")
        assert res.status_code in (400, 403, 404)
    finally:
        if symlink_path.is_symlink():
            symlink_path.unlink()
