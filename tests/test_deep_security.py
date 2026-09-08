import pytest
import io
import re
from app.config import settings

def test_share_forged_cookie_blocked(auth_client, client):
    """
    Verify that an attacker cannot bypass password-protected shares by forging a static cookie.
    Only cryptographically HMAC-signed cookies produced upon successful password verification are accepted.
    """
    # 1. Upload a confidential file
    content = b"Top secret corporate financial report"
    up_res = auth_client.post(
        "/api/files/upload",
        files={"file": ("classified_report.txt", io.BytesIO(content), "text/plain")}
    )
    assert up_res.status_code == 200

    # 2. Create password-protected share
    share_res = auth_client.post("/api/shares", json={
        "path": "classified_report.txt",
        "password": "SuperSecurePassword987!",
        "download_only": False
    })
    assert share_res.status_code == 200
    token = share_res.json()["token"]

    # 3. Attacker attempts download with forged static cookie
    client.cookies.set(f"share_auth_{token}", "authenticated")
    attack_res = client.get(f"/api/shares/public/download/{token}")
    assert attack_res.status_code == 401, "Forged static cookie must be rejected"

    # 4. Attacker attempts download with invalid HMAC token
    client.cookies.set(f"share_auth_{token}", "deadbeefcafebabe1234567890abcdef")
    attack_res2 = client.get(f"/api/shares/public/download/{token}")
    assert attack_res2.status_code == 401, "Invalid HMAC token must be rejected"

    # 5. Attacker attempts public info check with forged cookie
    info_res = client.get(f"/api/shares/public/info/{token}")
    assert info_res.status_code == 200
    assert info_res.json()["requires_password"] is True, "Forged cookie must not authenticate share info"

    # 6. Legitimate user authenticates with correct password
    client.cookies.clear()
    auth_resp = client.post(
        f"/api/shares/public/verify-password/{token}",
        json={"password": "SuperSecurePassword987!"}
    )
    assert auth_resp.status_code == 200
    assert f"share_auth_{token}" in client.cookies

    # 7. Legitimate download now succeeds with HMAC cookie
    dl_success = client.get(f"/api/shares/public/download/{token}")
    assert dl_success.status_code == 200
    assert dl_success.content == content

from fastapi.testclient import TestClient
from app.main import app

def test_settings_rbac_enforcement(auth_client):
    """
    Verify that non-admin authenticated users cannot access or modify application settings.
    """
    with TestClient(app) as user_client:
        reg_res = user_client.post("/api/auth/register", json={
            "username": "regular_user_settings",
            "password": "UserPass123!@#"
        })
        assert reg_res.status_code == 200
        reg_csrf = reg_res.json()["csrf_token"]

        # Regular user attempts GET /api/settings -> 403 Forbidden
        get_res = user_client.get("/api/settings")
        assert get_res.status_code == 403, f"Regular user should receive 403 on GET /api/settings, got {get_res.status_code}"

        # Regular user attempts POST /api/settings -> 403 Forbidden
        post_res = user_client.post(
            "/api/settings",
            json={"storage_root": "/etc"},
            headers={"X-CSRF-Token": reg_csrf}
        )
        assert post_res.status_code == 403, f"Regular user should receive 403 on POST /api/settings, got {post_res.status_code}"

    # Admin user GET /api/settings -> 200 OK
    admin_get = auth_client.get("/api/settings")
    assert admin_get.status_code == 200
    assert "storage_root" in admin_get.json()

def test_audit_logs_rbac_enforcement(auth_client):
    """
    Verify that audit logs containing sensitive IP and activity histories are accessible only to admins.
    """
    with TestClient(app) as user_client:
        reg_res = user_client.post("/api/auth/register", json={
            "username": "regular_user_audit",
            "password": "UserPass123!@#"
        })
        assert reg_res.status_code == 200

        # Regular user attempts GET /api/audit -> 403 Forbidden
        audit_res = user_client.get("/api/audit")
        assert audit_res.status_code == 403, f"Regular user should receive 403 on GET /api/audit, got {audit_res.status_code}"

    # Admin user GET /api/audit -> 200 OK
    admin_audit = auth_client.get("/api/audit")
    assert admin_audit.status_code == 200
    assert "logs" in admin_audit.json()

def test_registration_quota_tampering_prevented(client):
    """
    Verify that public self-registration cannot be manipulated to grant infinite or inflated storage quota.
    """
    # Attacker requests 99999 GB quota
    reg_res = client.post("/api/auth/register", json={
        "username": "quota_tamperer",
        "password": "UserPass123!@#",
        "quota_gb": 99999
    })
    assert reg_res.status_code == 200

    # Check profile quota in response
    prof_res = client.get("/api/profile")
    assert prof_res.status_code == 200
    quota_assigned = prof_res.json()["user"]["quota_bytes"]
    assert quota_assigned == settings.DEFAULT_USER_QUOTA_BYTES, (
        f"Expected quota {settings.DEFAULT_USER_QUOTA_BYTES}, got {quota_assigned}"
    )

def test_security_headers_and_csp(client):
    """
    Verify security headers including CSP, nosniff, SAMEORIGIN frame options, and Referrer-Policy.
    """
    res = client.get("/api/version")
    assert res.status_code == 200

    headers = res.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in headers
    csp = headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "object-src 'none'" in csp

def test_svg_preview_csp_sandboxed(auth_client):
    """
    Verify that previewing SVG files injects sandbox Content-Security-Policy to neutralize stored XSS.
    """
    svg_payload = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(document.domain)</script></svg>'
    up_res = auth_client.post(
        "/api/files/upload",
        files={"file": ("vector.svg", io.BytesIO(svg_payload), "image/svg+xml")}
    )
    assert up_res.status_code == 200

    preview_res = auth_client.get("/api/files/preview?path=vector.svg")
    assert preview_res.status_code == 200
    assert "sandbox" in preview_res.headers.get("Content-Security-Policy", "")

def test_avatar_upload_svg_rejected(auth_client):
    """
    Verify that user avatar uploads reject SVG to prevent stored XSS, but accept raster images.
    """
    svg_data = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    bad_res = auth_client.post(
        "/api/profile/avatar",
        files={"file": ("avatar.svg", io.BytesIO(svg_data), "image/svg+xml")}
    )
    assert bad_res.status_code == 400, "SVG avatar upload must be rejected"

    # PNG avatar upload succeeds
    png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    good_res = auth_client.post(
        "/api/profile/avatar",
        files={"file": ("avatar.png", io.BytesIO(png_data), "image/png")}
    )
    assert good_res.status_code == 200

    # Fetch avatar returns sandbox CSP
    prof_res = auth_client.get("/api/profile")
    user_id = prof_res.json()["user"]["id"]
    av_res = auth_client.get(f"/api/profile/avatar/{user_id}")
    assert av_res.status_code == 200
    assert "sandbox" in av_res.headers.get("Content-Security-Policy", "")
    assert av_res.headers.get("X-Content-Type-Options") == "nosniff"

    # Clean up uploaded avatar so subsequent tests start with fresh state
    del_res = auth_client.delete("/api/profile/avatar")
    assert del_res.status_code == 200

def test_csrf_protection_on_mutating_requests(auth_client):
    """
    Verify that state-changing requests authenticated via session cookie require a valid X-CSRF-Token.
    """
    # Remove X-CSRF-Token header
    orig_token = auth_client.headers.pop("X-CSRF-Token", None)

    try:
        # POST without CSRF header should be blocked with 403
        no_csrf_res = auth_client.post("/api/files/folder", json={
            "parent_path": "",
            "folder_name": "csrf_test_dir"
        })
        assert no_csrf_res.status_code == 403, "POST without CSRF header must be rejected with 403"

        # POST with wrong CSRF header should be blocked with 403
        auth_client.headers["X-CSRF-Token"] = "invalid_token_12345"
        bad_csrf_res = auth_client.post("/api/files/folder", json={
            "parent_path": "",
            "folder_name": "csrf_test_dir"
        })
        assert bad_csrf_res.status_code == 403, "POST with invalid CSRF header must be rejected with 403"

        # POST with correct CSRF header succeeds
        auth_client.headers["X-CSRF-Token"] = orig_token
        good_csrf_res = auth_client.post("/api/files/folder", json={
            "parent_path": "",
            "folder_name": "csrf_test_dir"
        })
        assert good_csrf_res.status_code == 200
    finally:
        if orig_token:
            auth_client.headers["X-CSRF-Token"] = orig_token

def test_null_byte_rejection_in_filenames(auth_client):
    """
    Verify that null bytes in filenames are rejected across all file creation and rename operations.
    """
    # 1. Folder creation with null byte
    f_res = auth_client.post("/api/files/folder", json={
        "parent_path": "",
        "folder_name": "test\0dir"
    })
    assert f_res.status_code in (400, 422)

    # 2. Upload with null byte in filename
    up_res = auth_client.post(
        "/api/files/upload",
        files={"file": ("null\0byte.txt", io.BytesIO(b"data"), "text/plain")}
    )
    assert up_res.status_code in (400, 422)

    # 3. Rename with null byte
    ren_res = auth_client.patch("/api/files/rename", json={
        "path": "test.txt",
        "new_name": "renamed\0name.txt"
    })
    assert ren_res.status_code in (400, 404, 422)

    # 4. Chunk init with null byte
    chk_res = auth_client.post("/api/upload/init", json={
        "filename": "chunk\0test.bin",
        "target_dir": "",
        "total_size": 100,
        "total_chunks": 1
    })
    assert chk_res.status_code in (400, 422)
