import io
import zipfile
import pytest
from fastapi.testclient import TestClient
from app.main import app

def get_client_for_user(username, password):
    client = TestClient(app)
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200
    csrf_token = res.json()["csrf_token"]
    client.headers.update({"X-CSRF-Token": csrf_token})
    return client

def test_folder_download_zip(auth_client):
    # Create folder hierarchy
    # ProjectFolder/
    #   file1.txt
    #   Sub/
    #     file2.txt
    auth_client.post("/api/files/folder", json={"parent_path": "", "folder_name": "ProjectFolder"})
    auth_client.post("/api/files/folder", json={"parent_path": "ProjectFolder", "folder_name": "Sub"})

    f1_content = b"Content of file 1 in ProjectFolder"
    f2_content = b"Content of file 2 in ProjectFolder/Sub"

    auth_client.post(
        "/api/files/upload",
        files={"file": ("file1.txt", io.BytesIO(f1_content), "text/plain")},
        data={"target_dir": "ProjectFolder"}
    )
    auth_client.post(
        "/api/files/upload",
        files={"file": ("file2.txt", io.BytesIO(f2_content), "text/plain")},
        data={"target_dir": "ProjectFolder/Sub"}
    )

    # Download folder
    res = auth_client.get("/api/files/download?path=ProjectFolder")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"
    assert 'filename="ProjectFolder.zip"' in res.headers["content-disposition"]

    # Verify ZIP contents
    zip_bytes = io.BytesIO(res.content)
    with zipfile.ZipFile(zip_bytes, "r") as zf:
        namelist = zf.namelist()
        assert "ProjectFolder/file1.txt" in namelist
        assert "ProjectFolder/Sub/file2.txt" in namelist
        assert zf.read("ProjectFolder/file1.txt") == f1_content
        assert zf.read("ProjectFolder/Sub/file2.txt") == f2_content

    # Also test /api/files/download-folder alias
    alias_res = auth_client.get("/api/files/download-folder?path=ProjectFolder")
    assert alias_res.status_code == 200
    assert alias_res.headers["content-type"] == "application/zip"

def test_multiuser_creation_and_admin_permissions(auth_client):
    # 1. Admin lists users
    res = auth_client.get("/api/users")
    assert res.status_code == 200
    users = res.json()["users"]
    assert any(u["username"] == "admin" for u in users)

    # 2. Admin creates a new standard user
    create_res = auth_client.post("/api/users", json={
        "username": "bob_user",
        "password": "BobPassword123!",
        "role": "user",
        "quota_bytes": 10485760 # 10 MB
    })
    assert create_res.status_code == 200
    bob_id = create_res.json()["user"]["id"]
    assert create_res.json()["user"]["username"] == "bob_user"
    assert create_res.json()["user"]["role"] == "user"

    # 3. bob_user logs in
    bob_client = get_client_for_user("bob_user", "BobPassword123!")

    # 4. bob_user (non-admin) CANNOT access /api/users
    forbidden_res = bob_client.get("/api/users")
    assert forbidden_res.status_code == 403

    forbidden_create = bob_client.post("/api/users", json={
        "username": "hacker",
        "password": "Password123!",
        "role": "admin"
    })
    assert forbidden_create.status_code == 403

    # 5. Admin updates bob_user
    patch_res = auth_client.patch(f"/api/users/{bob_id}", json={
        "quota_bytes": 20971520 # 20 MB
    })
    assert patch_res.status_code == 200

    # 6. Admin cannot delete self
    admin_id = next(u["id"] for u in users if u["username"] == "admin")
    del_self = auth_client.delete(f"/api/users/{admin_id}")
    assert del_self.status_code == 400

def test_storage_separation_between_users(auth_client):
    # Create user Charlie
    auth_client.post("/api/users", json={
        "username": "charlie",
        "password": "CharliePassword123!",
        "role": "user",
        "quota_bytes": 0
    })
    charlie_client = get_client_for_user("charlie", "CharliePassword123!")

    # Admin uploads admin_private.txt
    admin_content = b"Confidential admin data"
    auth_client.post(
        "/api/files/upload",
        files={"file": ("admin_private.txt", io.BytesIO(admin_content), "text/plain")}
    )

    # Charlie lists files -> admin_private.txt MUST NOT be visible!
    charlie_list = charlie_client.get("/api/files?path=")
    assert charlie_list.status_code == 200
    charlie_items = [i["name"] for i in charlie_list.json()["items"]]
    assert "admin_private.txt" not in charlie_items

    # Charlie uploads charlie_doc.txt
    charlie_content = b"Charlie's personal journal"
    charlie_client.post(
        "/api/files/upload",
        files={"file": ("charlie_doc.txt", io.BytesIO(charlie_content), "text/plain")}
    )

    # Admin lists files -> charlie_doc.txt MUST NOT be in admin's drive!
    admin_list = auth_client.get("/api/files?path=")
    assert admin_list.status_code == 200
    admin_items = [i["name"] for i in admin_list.json()["items"]]
    assert "charlie_doc.txt" not in admin_items

    # Charlie cannot download admin's file
    dl_fail = charlie_client.get("/api/files/download?path=admin_private.txt")
    assert dl_fail.status_code == 404

    # Both users can have a file with the SAME filename without collision
    same_name = "notes.txt"
    admin_notes = b"Admin notes"
    charlie_notes = b"Charlie notes"

    auth_client.post("/api/files/upload", files={"file": (same_name, io.BytesIO(admin_notes), "text/plain")})
    charlie_client.post("/api/files/upload", files={"file": (same_name, io.BytesIO(charlie_notes), "text/plain")})

    # When admin downloads notes.txt -> gets admin_notes
    admin_dl = auth_client.get(f"/api/files/download?path={same_name}")
    assert admin_dl.status_code == 200
    assert admin_dl.content == admin_notes

    # When Charlie downloads notes.txt -> gets charlie_notes
    charlie_dl = charlie_client.get(f"/api/files/download?path={same_name}")
    assert charlie_dl.status_code == 200
    assert charlie_dl.content == charlie_notes

    # Charlie searches -> cannot find admin's files
    search_res = charlie_client.get("/api/search?q=admin")
    assert search_res.status_code == 200
    assert len(search_res.json()["results"]) == 0

def test_quota_enforcement(auth_client):
    # Create user Dave with 500 bytes quota
    create_res = auth_client.post("/api/users", json={
        "username": "dave",
        "password": "DavePassword123!",
        "role": "user",
        "quota_bytes": 500
    })
    assert create_res.status_code == 200
    dave_client = get_client_for_user("dave", "DavePassword123!")

    # Dave uploads 300 bytes -> succeeds
    small_content = b"A" * 300
    res_ok = dave_client.post(
        "/api/files/upload",
        files={"file": ("small.txt", io.BytesIO(small_content), "text/plain")}
    )
    assert res_ok.status_code == 200

    # Dave uploads another 300 bytes -> exceeds 500 bytes quota -> 413 error
    res_fail = dave_client.post(
        "/api/files/upload",
        files={"file": ("overflow.txt", io.BytesIO(small_content), "text/plain")}
    )
    assert res_fail.status_code == 413
    assert "quota exceeded" in res_fail.json()["detail"].lower()

def test_public_shared_folder_zip_download(auth_client, client):
    # Admin creates a folder and files, then shares the folder
    auth_client.post("/api/files/folder", json={"parent_path": "", "folder_name": "SharedPack"})
    doc_content = b"Shared package document"
    auth_client.post(
        "/api/files/upload",
        files={"file": ("pack_doc.txt", io.BytesIO(doc_content), "text/plain")},
        data={"target_dir": "SharedPack"}
    )

    share_res = auth_client.post("/api/shares", json={
        "path": "SharedPack",
        "password": None,
        "download_only": False
    })
    assert share_res.status_code == 200
    token = share_res.json()["token"]

    # Public client downloads the entire shared folder as ZIP
    dl_res = client.get(f"/api/shares/public/download/{token}")
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"] == "application/zip"

    # Verify ZIP contents
    with zipfile.ZipFile(io.BytesIO(dl_res.content), "r") as zf:
        namelist = zf.namelist()
        assert "SharedPack/pack_doc.txt" in namelist
        assert zf.read("SharedPack/pack_doc.txt") == doc_content

def test_user_self_registration(auth_client):
    # 1. New unauthenticated visitor registers via public /api/auth/register
    reg_client = TestClient(app)
    reg_res = reg_client.post("/api/auth/register", json={
        "username": "sarah_reg",
        "password": "SarahPassword123!"
    })
    assert reg_res.status_code == 200
    assert reg_res.json()["status"] == "ok"
    assert reg_res.json()["username"] == "sarah_reg"
    assert reg_res.json()["role"] == "user"
    csrf_token = reg_res.json()["csrf_token"]

    # 2. Authenticated sarah can list files in her fresh private drive
    reg_client.headers.update({"X-CSRF-Token": csrf_token})
    files_res = reg_client.get("/api/files")
    assert files_res.status_code == 200
    assert files_res.json()["items"] == []

    # 3. Duplicate username fails
    dup_res = reg_client.post("/api/auth/register", json={
        "username": "sarah_reg",
        "password": "AnotherPassword123!"
    })
    assert dup_res.status_code == 400
    assert "already taken" in dup_res.json()["detail"].lower()

    # 4. User registers with custom storage quota (e.g. 5 GB)
    quota_client = TestClient(app)
    q_res = quota_client.post("/api/auth/register", json={
        "username": "quota_user",
        "password": "QuotaPassword123!",
        "quota_gb": 5
    })
    assert q_res.status_code == 200
    assert q_res.json()["quota_bytes"] == 5 * 1024 * 1024 * 1024
    quota_csrf = q_res.json()["csrf_token"]
    quota_client.headers.update({"X-CSRF-Token": quota_csrf})
    prof_res = quota_client.get("/api/profile")
    assert prof_res.status_code == 200
    assert prof_res.json()["storage"]["quota_bytes"] == 5 * 1024 * 1024 * 1024

def test_shared_folder_browse_endpoint(auth_client, client):
    # Admin creates shared folder with nested structure
    auth_client.post("/api/files/folder", json={"parent_path": "", "folder_name": "PublicBrowseFolder"})
    auth_client.post("/api/files/folder", json={"parent_path": "PublicBrowseFolder", "folder_name": "Nested"})
    auth_client.post(
        "/api/files/upload",
        files={"file": ("hello.txt", io.BytesIO(b"Hello world"), "text/plain")},
        data={"target_dir": "PublicBrowseFolder"}
    )
    auth_client.post(
        "/api/files/upload",
        files={"file": ("nested_doc.txt", io.BytesIO(b"Nested content"), "text/plain")},
        data={"target_dir": "PublicBrowseFolder/Nested"}
    )

    share_res = auth_client.post("/api/shares", json={
        "path": "PublicBrowseFolder",
        "password": None,
        "download_only": False
    })
    assert share_res.status_code == 200
    token = share_res.json()["token"]

    # Public client browses root of share
    browse_root = client.get(f"/api/shares/public/browse/{token}")
    assert browse_root.status_code == 200
    root_items = browse_root.json()["items"]
    names = [i["name"] for i in root_items]
    assert "hello.txt" in names
    assert "Nested" in names

    # Public client browses subfolder
    browse_sub = client.get(f"/api/shares/public/browse/{token}?subpath=Nested")
    assert browse_sub.status_code == 200
    sub_items = browse_sub.json()["items"]
    sub_names = [i["name"] for i in sub_items]
    assert "nested_doc.txt" in sub_names

def test_batch_download_and_batch_delete(auth_client):
    # Create test items
    auth_client.post("/api/files/folder", json={"parent_path": "", "folder_name": "BatchFolder"})
    auth_client.post(
        "/api/files/upload",
        files={"file": ("file_a.txt", io.BytesIO(b"File A content"), "text/plain")},
        data={"target_dir": ""}
    )
    auth_client.post(
        "/api/files/upload",
        files={"file": ("file_b.txt", io.BytesIO(b"File B content"), "text/plain")},
        data={"target_dir": ""}
    )
    auth_client.post(
        "/api/files/upload",
        files={"file": ("inside.txt", io.BytesIO(b"Inside folder content"), "text/plain")},
        data={"target_dir": "BatchFolder"}
    )

    # 1. Batch download via POST
    post_dl = auth_client.post("/api/files/download-batch", json={
        "paths": ["file_a.txt", "BatchFolder"]
    })
    assert post_dl.status_code == 200
    assert post_dl.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(post_dl.content), "r") as zf:
        namelist = zf.namelist()
        assert "file_a.txt" in namelist
        assert "BatchFolder/inside.txt" in namelist

    # 2. Batch download via GET
    get_dl = auth_client.get("/api/files/download-batch?paths=file_a.txt,BatchFolder")
    assert get_dl.status_code == 200
    assert get_dl.headers["content-type"] == "application/zip"

    # 3. Batch delete
    del_res = auth_client.post("/api/files/batch-delete", json={
        "paths": ["file_a.txt", "file_b.txt"]
    })
    assert del_res.status_code == 200
    assert del_res.json()["deleted_count"] == 2

    # Verify they are now in trash
    trash_res = auth_client.get("/api/files/trash")
    assert trash_res.status_code == 200
    trash_names = [i["name"] for i in trash_res.json()["items"]]
    assert "file_a.txt" in trash_names
    assert "file_b.txt" in trash_names

