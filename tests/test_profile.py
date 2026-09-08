import pytest
import io
from fastapi.testclient import TestClient
from app.main import app

def test_profile_endpoints(auth_client):
    client = auth_client

    # 1. Get profile
    res = client.get("/api/profile")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["user"]["username"] == "admin"
    assert "storage" in data
    assert "counts" in data
    assert "files" in data["counts"]
    user_id = data["user"]["id"]

    # 2. Get SVG initials avatar
    res_svg = client.get(f"/api/profile/avatar/{user_id}")
    assert res_svg.status_code == 200
    assert "image/svg+xml" in res_svg.headers.get("content-type", "")
    assert "<svg" in res_svg.text
    assert "linearGradient" in res_svg.text

    # 3. Update profile (display_name & email)
    res_patch = client.patch(
        "/api/profile",
        json={"display_name": "Strange Administrator", "email": "admin@strangeinfinity.com"}
    )
    assert res_patch.status_code == 200
    patch_data = res_patch.json()
    assert patch_data["user"]["display_name"] == "Strange Administrator"
    assert patch_data["user"]["email"] == "admin@strangeinfinity.com"

    # Verify invalid email format rejected
    res_bad_email = client.patch(
        "/api/profile",
        json={"email": "not-an-email"}
    )
    assert res_bad_email.status_code == 400

    # 4. Upload custom avatar (PNG)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    res_upload = client.post(
        "/api/profile/avatar",
        files={"file": ("avatar.png", io.BytesIO(png_bytes), "image/png")}
    )
    assert res_upload.status_code == 200
    assert "avatar_url" in res_upload.json()

    # Now get_avatar returns custom png
    res_avatar = client.get(f"/api/profile/avatar/{user_id}")
    assert res_avatar.status_code == 200
    assert "image/png" in res_avatar.headers.get("content-type", "")

    # 5. Delete custom avatar
    res_del_avatar = client.delete("/api/profile/avatar")
    assert res_del_avatar.status_code == 200

    # After deletion, SVG initials avatar is served again
    res_svg2 = client.get(f"/api/profile/avatar/{user_id}")
    assert res_svg2.status_code == 200
    assert "image/svg+xml" in res_svg2.headers.get("content-type", "")

    # 6. Create a test file and test Takeout Export
    client.post(
        "/api/files/upload",
        files={"file": ("takeout_test.txt", b"Hello StrangeInfinity Data Takeout!", "text/plain")},
        data={"target_dir": ""}
    )
    res_export = client.get("/api/profile/export")
    assert res_export.status_code == 200
    assert "application/zip" in res_export.headers.get("content-type", "")
    assert len(res_export.content) > 0

    # 7. Wipe Drive test
    # Bad password
    res_bad_wipe = client.post(
        "/api/profile/wipe-drive",
        json={"password": "wrongpassword"}
    )
    assert res_bad_wipe.status_code == 400

    # Good password
    res_wipe = client.post(
        "/api/profile/wipe-drive",
        json={"password": "StrongPassword123!"}
    )
    assert res_wipe.status_code == 200
    # Verify files wiped
    res_files = client.get("/api/files?path=")
    assert res_files.status_code == 200
    assert len(res_files.json()["items"]) == 0

    # 8. Account deletion test on non-admin user
    # Register a standard user
    res_reg = client.post(
        "/api/auth/register",
        json={"username": "tempuser", "password": "UserPass123!"}
    )
    assert res_reg.status_code == 200
    user_csrf = res_reg.json()["csrf_token"]

    # Delete non-admin account
    res_del_acc = client.post(
        "/api/profile/delete-account",
        json={"password": "UserPass123!"},
        headers={"X-CSRF-Token": user_csrf}
    )
    assert res_del_acc.status_code == 200

    # Verify user cannot login anymore
    res_login_after = client.post(
        "/api/auth/login",
        json={"username": "tempuser", "password": "UserPass123!"}
    )
    assert res_login_after.status_code == 401
