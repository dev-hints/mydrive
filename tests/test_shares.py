import pytest
import io
import time

def test_public_share_flow(auth_client, client):
    # Upload a file to share
    content = b"Shared secret document contents"
    up_res = auth_client.post("/api/files/upload", files={"file": ("shared_doc.txt", io.BytesIO(content), "text/plain")})
    assert up_res.status_code == 200

    # Create public share
    share_res = auth_client.post("/api/shares", json={
        "path": "shared_doc.txt",
        "password": None,
        "download_only": False
    })
    assert share_res.status_code == 200
    token = share_res.json()["token"]

    # Access anonymously via public client
    info_res = client.get(f"/api/shares/public/info/{token}")
    assert info_res.status_code == 200
    assert info_res.json()["name"] == "shared_doc.txt"
    assert info_res.json()["requires_password"] is False

    # Download anonymously
    dl_res = client.get(f"/api/shares/public/download/{token}")
    assert dl_res.status_code == 200
    assert dl_res.content == content

    # Revoke share
    revoke_res = auth_client.delete(f"/api/shares/{token}")
    assert revoke_res.status_code == 200

    # Re-access should now be 404
    after_res = client.get(f"/api/shares/public/info/{token}")
    assert after_res.status_code == 404

def test_password_protected_share(auth_client, client):
    content = b"Protected confidential file"
    up_res = auth_client.post("/api/files/upload", files={"file": ("confidential.pdf", io.BytesIO(content), "application/pdf")})
    assert up_res.status_code == 200

    # Create password-protected share
    share_res = auth_client.post("/api/shares", json={
        "path": "confidential.pdf",
        "password": "SecretPassword123!",
        "download_only": True
    })
    assert share_res.status_code == 200
    token = share_res.json()["token"]

    # Public info reports password required
    info_res = client.get(f"/api/shares/public/info/{token}")
    assert info_res.status_code == 200
    assert info_res.json()["requires_password"] is True

    # Attempt download without password -> 401
    dl_fail = client.get(f"/api/shares/public/download/{token}")
    assert dl_fail.status_code == 401

    # Verify wrong password -> 401
    bad_pw = client.post(f"/api/shares/public/verify-password/{token}", json={"password": "WrongPassword"})
    assert bad_pw.status_code == 401

    # Verify correct password -> 200
    good_pw = client.post(f"/api/shares/public/verify-password/{token}", json={"password": "SecretPassword123!"})
    assert good_pw.status_code == 200

    # Download should now succeed because cookie was set
    dl_success = client.get(f"/api/shares/public/download/{token}")
    assert dl_success.status_code == 200
    assert dl_success.content == content
